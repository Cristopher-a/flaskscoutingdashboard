from flask import Flask, jsonify, request
from flask_cors import CORS
import pandas as pd
import requests
from requests.auth import HTTPBasicAuth
from supabase import create_client, Client

# ----------------------------
# Configuración Supabase
# ----------------------------
SUPABASE_URL = "https://rhttqmtzcmwilzshnxwq.supabase.co" 
SUPABASE_KEY = "tu_supabase_key_aqui"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ----------------------------
# Configuración Flask
# ----------------------------
app = Flask(__name__)
CORS(app)

# ----------------------------
# Función de ranking unificada
# ----------------------------
def ranking_alianzas_completo(eventCode: str):
    try:
        pits_data = supabase.table("pits").select("*").execute().data
        matches_data = supabase.table("matches").select("*").execute().data

        if not pits_data or not matches_data:
            return []

        df_pits = pd.DataFrame(pits_data)
        df_matches = pd.DataFrame(matches_data)

        # Combinar pits + matches
        df = pd.merge(
            df_matches,
            df_pits,
            how="left",
            left_on=["team_number", "regional"],
            right_on=["team_number", "region"]
        )
        if "region" in df.columns:
            df = df.drop(columns=["region"])

        # Columnas numéricas para score
        score_cols = [
            'check_inicio', 'count_motiv', 'count_in_cage_auto', 'count_out_cage_auto',
            'count_in_cage_teleop', 'count_out_cage_teleop', 'count_rp', 'check_scoring',
            'count_in_cage_endgame', 'count_out_cage_endgame', 'check_full_park',
            'check_partial_park', 'check_high'
        ]
        for col in score_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        df['score'] = df[score_cols].sum(axis=1)

        # Agrupar por equipo
        team_stats = df.groupby("team_number").agg({
            "score": "mean",
            "count_in_cage_auto": "sum",
            "count_in_cage_teleop": "sum"
        }).reset_index()
        team_stats["score"] = team_stats["score"].round(2)

        # Ranking FTC por equipo
        def obtener_ranking_equipo(team: int):
            url = f"http://ftc-api.firstinspires.org/v2.0/2024/rankings/{eventCode}"
            username = "crisesv4"
            password = "E936A6EC-14B0-4904-8DF4-E4916CA4E9BB"
            try:
                response = requests.get(url, auth=HTTPBasicAuth(username, password))
                response.raise_for_status()
                data = response.json()
                rankings = data.get("rankings")
                if not rankings:
                    return None
                for item in rankings:
                    if item.get("teamNumber") == team:
                        return item.get("rank")
                return None
            except:
                return None

        team_stats["ftc_rank"] = team_stats["team_number"].apply(obtener_ranking_equipo)

        # Calcular alliance_score
        team_stats["efficiency"] = (
            team_stats["count_in_cage_auto"] + team_stats["count_in_cage_teleop"]
        ) / (team_stats["score"] + 1)
        team_stats["ftc_rank_score"] = team_stats["ftc_rank"].apply(lambda x: 1/x if x else 0)
        team_stats["alliance_score"] = (
            team_stats["score"]*0.6 + team_stats["efficiency"]*0.3 + team_stats["ftc_rank_score"]*0.1
        )

        df_final = team_stats.sort_values("alliance_score", ascending=False)
        return df_final[
            ["team_number", "score", "count_in_cage_auto", "count_in_cage_teleop", "ftc_rank", "alliance_score"]
        ].to_dict(orient="records")

    except Exception as e:
        print("Error:", e)
        return []

# ----------------------------
# Endpoint POST con JSON
# ----------------------------
@app.route("/")
def hello():
    return "Hello"
@app.route("/ranking", methods=["POST"])
def get_ranking():
    data = request.get_json()
    eventCode = data.get("eventCode") if data else None
    if not eventCode:
        return jsonify({"error": "No se proporcionó eventCode"}), 400

    ranking = ranking_alianzas_completo(eventCode)
    return jsonify(ranking)

# ----------------------------
# Ejecutar Flask
# ----------------------------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

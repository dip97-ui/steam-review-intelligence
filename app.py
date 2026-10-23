"""SteamLens - Steam Player Feedback & Review Analysis Platform.

Flask backend: serves the dashboard and a small JSON API over the
pre-computed analysis (run scripts/clean_data.py and scripts/analyze.py
first, or just `python run_pipeline.py`).

    GET /                  -> dashboard (static/index.html)
    GET /api/summary       -> KPIs, chart series, insights, cleaning report
    GET /api/games         -> per-game comparison rows
    GET /api/reviews       -> search / filter / sort / paginate reviews
    GET /api/themes        -> theme analysis rows
"""

import json
import os

import pandas as pd
from flask import Flask, jsonify, request, send_from_directory

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROCESSED = os.path.join(BASE_DIR, "data", "processed")
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")


def load_data():
    with open(os.path.join(PROCESSED, "analysis.json")) as f:
        analysis = json.load(f)
    reviews = pd.read_csv(os.path.join(PROCESSED, "reviews_enriched.csv"))
    return analysis, reviews


ANALYSIS, REVIEWS = load_data()


@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/api/summary")
def api_summary():
    """Everything the dashboard charts need in one call."""
    return jsonify({k: v for k, v in ANALYSIS.items() if k != "most_helpful"})


@app.route("/api/games")
def api_games():
    return jsonify({"games": ANALYSIS["games"]})


@app.route("/api/themes")
def api_themes():
    return jsonify({"themes": ANALYSIS["themes"]})


@app.route("/api/reviews")
def api_reviews():
    """Filterable, searchable, sortable, paginated review explorer."""
    q = request.args.get("q", "").strip().lower()
    game = request.args.get("game", "")
    sentiment = request.args.get("sentiment", "")
    voted = request.args.get("voted", "")          # up | down | ""
    sort = request.args.get("sort", "helpful")     # helpful|recent|playtime|long|sentiment
    page = max(int(request.args.get("page", 1)), 1)
    per_page = min(max(int(request.args.get("per_page", 20)), 5), 100)

    df = REVIEWS
    if game:
        df = df[df["game"] == game]
    if sentiment:
        df = df[df["sentiment_label"] == sentiment]
    if voted == "up":
        df = df[df["voted_up"] == True]  # noqa: E712
    elif voted == "down":
        df = df[df["voted_up"] == False]  # noqa: E712
    if q:
        df = df[df["review_text_clean"].str.lower().str.contains(q, regex=False)]

    sort_keys = {
        "helpful": ("votes_up", False),
        "recent": ("date", False),
        "playtime": ("playtime_hours", False),
        "long": ("word_count", False),
        "sentiment": ("sentiment_score", False),
    }
    col, asc = sort_keys.get(sort, sort_keys["helpful"])
    df = df.sort_values(col, ascending=asc)

    total = len(df)
    pages = max((total + per_page - 1) // per_page, 1)
    page = min(page, pages)
    chunk = df.iloc[(page - 1) * per_page: page * per_page]

    cols = ["recommendationid", "game", "date", "review_text_clean",
            "word_count", "voted_up", "votes_up", "votes_funny",
            "sentiment_label", "sentiment_score", "playtime_hours"]
    return jsonify({
        "total": int(total),
        "page": page,
        "pages": int(pages),
        "per_page": per_page,
        "results": chunk[cols].to_dict("records"),
    })


if __name__ == "__main__":
    print("SteamLens dashboard running at http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)

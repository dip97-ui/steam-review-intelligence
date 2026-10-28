"""SteamLens - Steam Player Feedback & Review Analysis Platform.

Flask backend: serves the dashboard and a small JSON API over the
pre-computed analysis (run scripts/clean_data.py and scripts/analyze.py
first, or just `python run_pipeline.py`).

    GET /                  -> dashboard (static/index.html)
    GET /api/summary       -> KPIs, chart series, insights, cleaning report
    GET /api/games         -> per-game comparison rows
    GET /api/reviews       -> search / filter / sort / paginate reviews
    GET /api/themes        -> theme analysis rows
    GET /api/datasets      -> default dataset + any games fetched from the dashboard
    POST /api/fetch        -> fetch + analyze one Steam App ID (background job)
    GET /api/fetch/status  -> progress of the current / last fetch job

Every read endpoint accepts ?dataset=<appid> to look at a game fetched from
the dashboard. Those games live in data/custom/<appid>/ and NEVER touch the
default dataset in data/raw and data/processed.
"""

import json
import os
import re
import sys
import threading
import time
import urllib.request

import pandas as pd
from flask import Flask, jsonify, request, send_from_directory

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROCESSED = os.path.join(BASE_DIR, "data", "processed")
STATIC_DIR = os.path.join(BASE_DIR, "static")

CUSTOM_DIR = os.path.join(BASE_DIR, "data", "custom")
sys.path.insert(0, os.path.join(BASE_DIR, "scripts"))

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")


def load_data(directory=PROCESSED):
    with open(os.path.join(directory, "analysis.json")) as f:
        analysis = json.load(f)
    reviews = pd.read_csv(os.path.join(directory, "reviews_enriched.csv"))
    return analysis, reviews


ANALYSIS, REVIEWS = load_data()

# ---- games fetched from the dashboard --------------------------------------
MAX_REVIEWS = 1000
_cache = {}                      # appid -> (analysis, reviews)
_job_lock = threading.Lock()
_job = {"state": "idle"}         # idle | running | done | error


def custom_path(appid):
    return os.path.join(CUSTOM_DIR, str(int(appid)))


def list_custom():
    out = []
    if os.path.isdir(CUSTOM_DIR):
        for name in sorted(os.listdir(CUSTOM_DIR)):
            meta_path = os.path.join(custom_path(name), "meta.json") \
                if name.isdigit() else None
            if meta_path and os.path.exists(os.path.join(
                    custom_path(name), "processed", "analysis.json")):
                try:
                    with open(meta_path) as f:
                        out.append(json.load(f))
                except (OSError, ValueError):
                    out.append({"appid": int(name), "game": f"appid_{name}"})
    return out


def get_dataset():
    """Return (analysis, reviews) for ?dataset=, defaulting to the bundled one."""
    ds = request.args.get("dataset", "")
    if not ds:
        return ANALYSIS, REVIEWS
    if not ds.isdigit():
        return None
    if ds not in _cache:
        d = os.path.join(custom_path(ds), "processed")
        if not os.path.exists(os.path.join(d, "analysis.json")):
            return None
        _cache[ds] = load_data(d)
    return _cache[ds]


def _not_found():
    return jsonify({"error": "unknown dataset"}), 404


def steam_game_name(appid):
    """Best-effort game name from Steam's store API; falls back to appid_N."""
    url = f"https://store.steampowered.com/api/appdetails?appids={appid}&filters=basic"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        entry = data.get(str(appid), {})
        if entry.get("success") and entry["data"].get("type") in ("game", "dlc"):
            return entry["data"]["name"], True
        if entry.get("success"):
            return entry["data"].get("name", f"appid_{appid}"), True
    except Exception:  # noqa: BLE001 - name lookup is optional
        pass
    return f"appid_{appid}", False


def _set(**kw):
    with _job_lock:
        _job.update(kw)


def run_fetch_job(appid, count):
    import analyze
    import clean_data
    import fetch_steam_reviews as fsr
    try:
        _set(message="Looking up game name ...")
        game, _ = steam_game_name(appid)
        _set(game=game, message=f"Fetching reviews for {game} ...")
        rows = fsr.fetch_game(
            appid, game, count,
            progress=lambda n: _set(message=f"Fetched {n} of {count} reviews ..."))
        if not rows:
            raise ValueError("Steam returned no English reviews for this App ID "
                             "(wrong ID, or the game has no reviews).")
        root = custom_path(appid)
        raw_dir, proc_dir = os.path.join(root, "raw"), os.path.join(root, "processed")
        tmp_root = root + ".tmp"
        # build in a temp folder, swap in only if everything succeeded
        import shutil
        shutil.rmtree(tmp_root, ignore_errors=True)
        os.makedirs(os.path.join(tmp_root, "raw"))
        os.makedirs(os.path.join(tmp_root, "processed"))
        import csv
        raw_csv = os.path.join(tmp_root, "raw", "reviews_raw.csv")
        with open(raw_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fsr.FIELDS)
            w.writeheader()
            w.writerows(rows)
        _set(message="Cleaning reviews ...")
        pdir = os.path.join(tmp_root, "processed")
        report = clean_data.main(raw_csv, os.path.join(pdir, "cleaned_reviews.csv"),
                                 os.path.join(pdir, "cleaning_report.json"))
        if report["rows_out"] < 10:
            raise ValueError(
                f"Only {report['rows_out']} usable English reviews after cleaning "
                "- too few to analyze.")
        _set(message="Analyzing sentiment and themes ...")
        analyze.main(os.path.join(pdir, "cleaned_reviews.csv"),
                     os.path.join(pdir, "reviews_enriched.csv"),
                     os.path.join(pdir, "analysis.json"),
                     os.path.join(pdir, "cleaning_report.json"))
        meta = {"appid": int(appid), "game": game, "requested": count,
                "fetched": len(rows), "analyzed": report["rows_out"],
                "fetched_at": time.strftime("%Y-%m-%d %H:%M")}
        with open(os.path.join(tmp_root, "meta.json"), "w") as f:
            json.dump(meta, f)
        shutil.rmtree(root, ignore_errors=True)   # only this game's old folder
        os.replace(tmp_root, root)
        _cache.pop(str(appid), None)
        _set(state="done", message=f"Done: {report['rows_out']} reviews analyzed.",
             result=meta)
    except Exception as e:  # noqa: BLE001 - surface any failure to the UI
        _set(state="error", message=str(e))


@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/api/summary")
def api_summary():
    """Everything the dashboard charts need in one call."""
    ds = get_dataset()
    if ds is None:
        return _not_found()
    return jsonify({k: v for k, v in ds[0].items() if k != "most_helpful"})


@app.route("/api/games")
def api_games():
    ds = get_dataset()
    if ds is None:
        return _not_found()
    return jsonify({"games": ds[0]["games"]})


@app.route("/api/themes")
def api_themes():
    ds = get_dataset()
    if ds is None:
        return _not_found()
    return jsonify({"themes": ds[0]["themes"]})


@app.route("/api/datasets")
def api_datasets():
    return jsonify({
        "default": {"label": "Default dataset (bundled / your 6-game fetch)",
                    "games": ANALYSIS["kpis"]["games"],
                    "reviews": ANALYSIS["kpis"]["total_reviews"]},
        "custom": list_custom(),
    })


@app.route("/api/fetch", methods=["POST"])
def api_fetch():
    body = request.get_json(silent=True) or {}
    appid = str(body.get("appid", "")).strip()
    if not re.fullmatch(r"\d{1,9}", appid) or int(appid) == 0:
        return jsonify({"error": "App ID must be a number, e.g. 413150."}), 400
    try:
        count = int(body.get("count", 300))
    except (TypeError, ValueError):
        return jsonify({"error": "Review count must be a number."}), 400
    count = min(max(count, 50), MAX_REVIEWS)
    with _job_lock:
        if _job.get("state") == "running":
            return jsonify({"error": "A fetch is already running."}), 409
        _job.clear()
        _job.update({"state": "running", "appid": int(appid), "count": count,
                     "message": "Starting ...", "started": time.time()})
    threading.Thread(target=run_fetch_job, args=(int(appid), count),
                     daemon=True).start()
    return jsonify({"state": "running"}), 202


@app.route("/api/fetch/status")
def api_fetch_status():
    with _job_lock:
        return jsonify(dict(_job))


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

    ds = get_dataset()
    if ds is None:
        return _not_found()
    df = ds[1]
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

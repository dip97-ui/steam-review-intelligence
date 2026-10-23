"""Fetch real, current Steam reviews into data/raw/steam_reviews_raw.csv.

Uses Steam's public appreviews JSON endpoint - no API key needed. Run this
from your own machine/network (some hosting IPs get redirected by Steam):

    python scripts/fetch_steam_reviews.py                # default games below
    python scripts/fetch_steam_reviews.py 413150 200     # appid + per-game count

Default appids are the six games in the bundled dataset. The output schema
matches the bundled raw CSV, so clean_data.py works unchanged afterwards.
"""

import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request

GAMES = {
    1145360: "Hades",
    578080: "PUBG: BATTLEGROUNDS",
    730: "Counter-Strike 2",
    1172470: "Apex Legends",
    1086940: "Baldur's Gate 3",
    252490: "Rust",
}

FIELDS = ["recommendationid", "appid", "game", "author_playtime_at_review",
          "author_playtime_forever", "language", "review", "timestamp_created",
          "timestamp_updated", "voted_up", "votes_up", "votes_funny",
          "weighted_vote_score", "comment_count", "steam_purchase",
          "received_for_free", "written_during_early_access"]

OUT_PATH = os.path.join("data", "raw", "steam_reviews_raw.csv")


def fetch_page(appid, cursor, per_page=100):
    params = {
        "json": 1, "language": "english", "filter": "recent",
        "review_type": "all", "purchase_type": "all",
        "num_per_page": per_page, "cursor": cursor,
    }
    url = f"https://store.steampowered.com/appreviews/{appid}?" \
          + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def fetch_game(appid, game, target):
    rows, cursor, seen = [], "*", set()
    while len(rows) < target:
        data = fetch_page(appid, urllib.parse.quote(cursor))
        if data.get("success") != 1:
            print(f"  {game}: Steam returned success={data.get('success')}, stopping")
            break
        for r in data.get("reviews", []):
            rid = r.get("recommendationid")
            if rid in seen:
                continue
            seen.add(rid)
            author = r.get("author", {})
            rows.append({
                "recommendationid": rid,
                "appid": appid,
                "game": game,
                "author_playtime_at_review": author.get("playtime_at_review", 0),
                "author_playtime_forever": author.get("playtime_forever", 0),
                "language": r.get("language", ""),
                "review": r.get("review", ""),
                "timestamp_created": r.get("timestamp_created", 0),
                "timestamp_updated": r.get("timestamp_updated", 0),
                "voted_up": 1 if r.get("voted_up") else 0,
                "votes_up": r.get("votes_up", 0),
                "votes_funny": r.get("votes_funny", 0),
                "weighted_vote_score": r.get("weighted_vote_score", 0),
                "comment_count": r.get("comment_count", 0),
                "steam_purchase": 1 if r.get("steam_purchase") else 0,
                "received_for_free": 1 if r.get("received_for_free") else 0,
                "written_during_early_access":
                    1 if r.get("written_during_early_access") else 0,
            })
        cursor = data.get("cursor", cursor)
        time.sleep(1.5)  # be polite to Steam's API
    return rows[:target]


def main():
    appids = [int(a) for a in sys.argv[1:2]] or list(GAMES)
    per_game = int(sys.argv[2]) if len(sys.argv) > 2 else 500
    all_rows = []
    for appid in appids:
        game = GAMES.get(appid, f"appid_{appid}")
        print(f"Fetching {game} ({appid}) ...")
        rows = fetch_game(appid, game, per_game)
        print(f"  got {len(rows)} reviews")
        all_rows.extend(rows)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"Saved {len(all_rows)} reviews to {OUT_PATH}")
    print("Next: python scripts/clean_data.py && python scripts/analyze.py")


if __name__ == "__main__":
    main()

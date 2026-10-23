"""Fetch the real-data sample used for the hosted analysis page.

Pulls public Steam reviews from the public Hugging Face dataset
SebastianHops/steam-reviews-english (a mirror of Steam's public review API)
via its rows API, 500 reviews per game, into data/raw/steam_reviews_raw.csv.

The dataset carries no explicit license and review text belongs to its
authors, so the fetched CSV is for your own local analysis - the project
repo ships synthetic demo data instead (see scripts/generate_sample_data.py
and DATA_NOTICE.md).
"""

import csv
import json
import os
import time
import urllib.error
import urllib.request

BASE = ("https://datasets-server.huggingface.co/rows"
        "?dataset=SebastianHops%2Fsteam-reviews-english"
        "&config=default&split=train&offset={off}&length=100")

# offsets probed from the dataset's game ordering (Oct 2026)
TARGETS = [
    (8_000_000, "Hades"),
    (10_000_000, "PUBG: BATTLEGROUNDS"),
    (16_000_000, "Counter-Strike 2"),
    (18_000_000, "Apex Legends"),
    (38_000_000, "Baldur's Gate 3"),
    (40_000_000, "Rust"),
]
PER_GAME = 500

FIELDS = ["recommendationid", "appid", "game", "author_playtime_at_review",
          "author_playtime_forever", "language", "review", "timestamp_created",
          "timestamp_updated", "voted_up", "votes_up", "votes_funny",
          "weighted_vote_score", "comment_count", "steam_purchase",
          "received_for_free", "written_during_early_access"]


def get(url, tries=8):
    wait = 4
    for t in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.load(r)
        except Exception:
            if t < tries - 1:
                time.sleep(wait)
                wait = min(wait * 2, 45)
                continue
            raise


def main():
    out_path = os.path.join("data", "raw", "steam_reviews_raw.csv")
    all_rows = []
    for start, game in TARGETS:
        got, off = [], start
        while len(got) < PER_GAME:
            data = get(BASE.format(off=off))
            rows = [it["row"] for it in data.get("rows", [])]
            if not rows:
                break
            matched = [r for r in rows if r.get("game") == game]
            if not matched and got:
                break
            got.extend(matched)
            off += 100
            time.sleep(2)
        got = got[:PER_GAME]
        print(f"{game}: {len(got)} reviews")
        all_rows.extend({k: r.get(k) for k in FIELDS} for r in got)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(all_rows)
    print(f"Saved {len(all_rows)} reviews to {out_path}")
    print("Next: python scripts/clean_data.py && python scripts/analyze.py")


if __name__ == "__main__":
    main()

"""Fetch real, current Steam reviews into data/raw/steam_reviews_raw.csv.

Uses Valve's IUserReviewsService/GetAppReviews Web API endpoint - no API key
needed for public reviews:

    python scripts/fetch_steam_reviews.py                # default games below
    python scripts/fetch_steam_reviews.py 413150 200     # appid + per-game count

Why not the old store URL? store.steampowered.com/appreviews/<appid>?json=1
was deprecated by Valve and disabled on 2026-10-22; it now redirects every
request to the store homepage (HTML), which crashed the previous version of
this script inside json.load(). The replacement endpoint is documented at
https://partner.steamgames.com/doc/webapi/IUserReviewsService#GetAppReviews

Notes:
  * Anonymous calls need no key but share a lower rate limit; Steam answers
    HTTP 429 when it is exceeded. This script spaces requests out and retries
    429/502/503 a few times with backoff. Anonymous responses may be cached
    by Steam for up to 10 minutes.
  * The existing CSV is replaced ONLY when every requested game was fetched
    successfully. A partial fetch is never written over your existing data.
  * The old CSV is backed up to steam_reviews_raw.backup.csv before a
    successful replacement.
"""

import csv
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API_URL = "https://api.steampowered.com/IUserReviewsService/GetAppReviews/v1/"

# Enums for the GetAppReviews Web API (verified against the live endpoint):
#   filter:        0 = Helpful (default), 1 = Recent, 2 = Updated, 3 = Funny
#   review_type:   0 = All (default),    1 = Positive, 2 = Negative
#   purchase_type: 0 = Steam (default),  1 = All,      2 = Non-Steam
FILTER_RECENT = 1
REVIEW_TYPE_ALL = 0
PURCHASE_TYPE_ALL = 1
LANGUAGES = ["english"]

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
BACKUP_PATH = os.path.join("data", "raw", "steam_reviews_raw.backup.csv")

POLITE_DELAY = 2.0            # seconds between successful page requests
TRANSIENT_RETRIES = 3         # for HTTP 429/502/503 only
TRANSIENT_BACKOFF = [10, 30, 60]


class SteamTransientError(Exception):
    """429/502/503 - worth a bounded retry with backoff."""


class SteamFetchError(Exception):
    """Anything else that stops the fetch - bad status, bad body."""


def fetch_page(appid, cursor, per_page=100):
    args = {
        "appid": appid,
        "filter": FILTER_RECENT,
        "languages": LANGUAGES,
        "review_type": REVIEW_TYPE_ALL,
        "purchase_type": PURCHASE_TYPE_ALL,
        "num_per_page": per_page,
        "cursor": cursor,
    }
    url = API_URL + "?input_json=" + urllib.parse.quote(json.dumps(args))
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/126.0.0.0 Safari/537.36",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
    except urllib.error.HTTPError as e:
        if e.code in (429, 502, 503):
            raise SteamTransientError(f"HTTP {e.code}") from e
        detail = e.read()[:200].decode("utf-8", errors="replace")
        raise SteamFetchError(f"HTTP {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise SteamFetchError(f"connection failed: {e.reason}") from e
    try:
        data = json.loads(body)
    except ValueError:
        raise SteamFetchError("Steam returned a non-JSON response")
    if not isinstance(data, dict) or "response" not in data:
        raise SteamFetchError("Steam returned an unexpected JSON shape")
    return data["response"]


def fetch_page_with_retry(appid, cursor, per_page=100):
    transient_attempt = 0
    while True:
        try:
            return fetch_page(appid, cursor, per_page)
        except SteamTransientError as e:
            transient_attempt += 1
            if transient_attempt > TRANSIENT_RETRIES:
                raise SteamFetchError(
                    f"giving up after {TRANSIENT_RETRIES} retries ({e})") from e
            wait = TRANSIENT_BACKOFF[min(transient_attempt - 1,
                                         len(TRANSIENT_BACKOFF) - 1)]
            print(f"  transient error ({e}); "
                  f"retry {transient_attempt}/{TRANSIENT_RETRIES} in {wait}s ...")
            time.sleep(wait)


def fetch_game(appid, game, target, progress=None):
    rows, cursor, seen = [], "*", set()
    while len(rows) < target:
        resp = fetch_page_with_retry(appid, cursor)
        reviews = resp.get("reviews", [])
        if not reviews:
            break  # reached the end of the review feed
        new_on_page = 0
        for r in reviews:
            rid = r.get("recommendationid")
            if rid in seen:
                continue  # also guards against Steam repeating a cursor page
            seen.add(rid)
            new_on_page += 1
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
        if new_on_page == 0:
            break  # page had no new reviews - stop paging
        next_cursor = resp.get("cursor")
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor
        if progress:
            progress(len(rows))
        time.sleep(POLITE_DELAY)  # be polite to Steam's API
    return rows[:target]


def save_rows(all_rows):
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    if os.path.exists(OUT_PATH):
        shutil.copy2(OUT_PATH, BACKUP_PATH)
        print(f"Backed up previous CSV to {BACKUP_PATH}")
    tmp_path = OUT_PATH + ".tmp"
    with open(tmp_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(all_rows)
    os.replace(tmp_path, OUT_PATH)


def main():
    appids = [int(a) for a in sys.argv[1:2]] or list(GAMES)
    per_game = int(sys.argv[2]) if len(sys.argv) > 2 else 500
    all_rows = []
    completed_all = True
    try:
        for appid in appids:
            game = GAMES.get(appid, f"appid_{appid}")
            print(f"Fetching {game} ({appid}) ...")
            rows = fetch_game(appid, game, per_game)
            print(f"  got {len(rows)} reviews")
            all_rows.extend(rows)
    except SteamFetchError as e:
        completed_all = False
        print()
        print(f"Stopped: could not fetch reviews from Steam ({e}).")
        print("If the error mentions HTTP 429: too many requests -")
        print("anonymous calls share a rate limit, so wait a few")
        print("minutes and run the same command again.")
        print("Your code and Python setup are fine.")
    if not completed_all or not all_rows:
        if all_rows:
            print(f"Discarded {len(all_rows)} partially-fetched reviews -")
            print("your existing CSV was NOT replaced with incomplete data.")
        else:
            print("No new reviews fetched; existing CSV left unchanged.")
        sys.exit(2)
    save_rows(all_rows)
    print(f"Saved {len(all_rows)} reviews to {OUT_PATH}")
    print("Next: python scripts/clean_data.py && python scripts/analyze.py")


if __name__ == "__main__":
    main()

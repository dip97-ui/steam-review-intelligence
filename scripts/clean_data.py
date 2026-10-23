"""Stage 1 of the pipeline: clean the raw Steam reviews CSV.

Input : data/raw/steam_reviews_raw.csv
Output: data/processed/cleaned_reviews.csv
        data/processed/cleaning_report.json

Cleaning steps, in order (each is counted so the dashboard can show the
funnel):
  1. Drop rows whose review text is missing or whitespace only.
  2. Normalize text: strip HTML tags, URLs, markdown image embeds and
     collapse whitespace.
  3. Drop duplicate review IDs, then duplicate (game, normalized text) pairs.
  4. Keep English reviews only (the sentiment stage is English-tuned).
  5. Drop reviews shorter than 3 words (no analytical signal).
  6. Parse timestamps; drop rows without a valid creation time.
  7. Coerce numeric fields; clamp negative playtimes to 0.
"""

import json
import os
import re

import pandas as pd

RAW_PATH = os.path.join("data", "raw", "steam_reviews_raw.csv")
CLEAN_PATH = os.path.join("data", "processed", "cleaned_reviews.csv")
REPORT_PATH = os.path.join("data", "processed", "cleaning_report.json")

HTML_TAG_RE = re.compile(r"<[^>]+>")
URL_RE = re.compile(r"https?://\S+|www\.\S+")
WS_RE = re.compile(r"\s+")


def normalize_text(text):
    if not isinstance(text, str):
        return ""
    text = HTML_TAG_RE.sub(" ", text)
    text = URL_RE.sub(" ", text)
    text = text.replace("\u2605", " ")  # stars sometimes pasted into reviews
    return WS_RE.sub(" ", text).strip()


def main():
    steps = []

    def record(step, before, after):
        steps.append({"step": step, "removed": int(before - after),
                      "remaining": int(after)})

    df = pd.read_csv(RAW_PATH, dtype=str, keep_default_na=False)
    record("Raw rows loaded", 0, len(df))
    start = len(df)

    # 1. missing / empty text
    before = len(df)
    df = df[df["review"].str.strip() != ""]
    record("Drop empty or missing review text", before, len(df))

    # 2. normalize text
    df["review_text_clean"] = df["review"].map(normalize_text)
    df["word_count"] = df["review_text_clean"].str.split().str.len()

    # 3. duplicates
    before = len(df)
    df = df.drop_duplicates(subset=["recommendationid"])
    df["text_key"] = (df["game"] + "|" +
                      df["review_text_clean"].str.lower())
    df = df.drop_duplicates(subset=["text_key"]).drop(columns=["text_key"])
    record("Drop duplicate reviews", before, len(df))

    # 4. language filter
    before = len(df)
    df = df[df["language"].str.lower() == "english"]
    record("Keep English reviews only", before, len(df))

    # 5. too short to analyze
    before = len(df)
    df = df[df["word_count"] >= 3]
    record("Drop reviews shorter than 3 words", before, len(df))

    # 6. timestamps
    before = len(df)
    df["timestamp_created"] = pd.to_numeric(df["timestamp_created"],
                                            errors="coerce")
    df = df.dropna(subset=["timestamp_created"])
    df["date"] = pd.to_datetime(df["timestamp_created"],
                                unit="s").dt.strftime("%Y-%m-%d")
    record("Drop rows without a valid timestamp", before, len(df))

    # 7. numerics
    for col in ["author_playtime_at_review", "author_playtime_forever",
                "votes_up", "votes_funny", "weighted_vote_score",
                "comment_count"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        df.loc[df[col] < 0, col] = 0
    df["voted_up"] = df["voted_up"].astype(str).isin(["1", "1.0", "True"])

    keep = ["recommendationid", "appid", "game", "date",
            "review_text_clean", "word_count", "voted_up", "votes_up",
            "votes_funny", "weighted_vote_score", "comment_count",
            "author_playtime_at_review", "author_playtime_forever",
            "steam_purchase", "received_for_free",
            "written_during_early_access"]
    df = df[keep]
    record("Final cleaned dataset", len(df), len(df))

    os.makedirs(os.path.dirname(CLEAN_PATH), exist_ok=True)
    df.to_csv(CLEAN_PATH, index=False)

    report = {
        "source_raw": RAW_PATH,
        "output_clean": CLEAN_PATH,
        "rows_in": int(start),
        "rows_out": int(len(df)),
        "pct_kept": round(100 * len(df) / max(start, 1), 1),
        "steps": steps,
    }
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)

    print(f"cleaned {start} -> {len(df)} rows")
    for s in steps:
        print(f"  {s['step']:<38} -{s['removed']:<6} = {s['remaining']}")


if __name__ == "__main__":
    main()

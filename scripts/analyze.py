"""Stage 2 of the pipeline: analyze the cleaned reviews.

Input : data/processed/cleaned_reviews.csv
Output: data/processed/reviews_enriched.csv  (clean + sentiment columns)
        data/processed/analysis.json         (everything the dashboard needs)

Adds lexicon sentiment (see sentiment.py), then aggregates:
  - overall KPIs
  - sentiment distribution and monthly trends
  - top positive / negative terms actually driving the scores
  - theme analysis (what players praise vs complain about)
  - positivity by playtime bucket and review length distribution
  - per-game comparison table
  - most helpful reviews
  - auto-generated insights
"""

import json
import os
from collections import Counter, defaultdict

import pandas as pd

from sentiment import score_text, label_for

CLEAN_PATH = os.path.join("data", "processed", "cleaned_reviews.csv")
ENRICHED_PATH = os.path.join("data", "processed", "reviews_enriched.csv")
ANALYSIS_PATH = os.path.join("data", "processed", "analysis.json")
REPORT_PATH = os.path.join("data", "processed", "cleaning_report.json")

# Theme buckets: keyword -> theme. Checked against the review text.
THEMES = {
    "Performance & bugs": ["bug", "bugs", "buggy", "glitch", "glitchy",
                           "crash", "crashes", "crashing", "freeze",
                           "freezes", "lag", "laggy", "stutter",
                           "stuttering", "fps", "optimization", "optimized",
                           "unoptimized", "performance", "broken"],
    "Gameplay & design": ["gameplay", "combat", "mechanics", "levels",
                          "level", "missions", "quest", "quests", "story",
                          "storyline", "characters", "difficulty", "boss",
                          "bosses", "puzzle", "grinding", "grindy", "grind",
                          "repetitive", "fun", "boring", "addictive"],
    "Value & monetization": ["price", "overpriced", "expensive", "cheap",
                             "worth", "refund", "money", "dlc",
                             "microtransactions", "paywall", "p2w",
                             "pay to win", "monetization", "sale",
                             "free", "ripoff", "scam", "value"],
    "Multiplayer & community": ["multiplayer", "servers", "server",
                                "matchmaking", "cheater", "cheaters",
                                "cheating", "hacker", "hackers", "toxic",
                                "community", "team", "teammates", "smurf",
                                "smurfs", "griefer", "griefing", "online",
                                "ranked", "lobby", "queue"],
    "Graphics & audio": ["graphics", "visuals", "art", "artstyle",
                         "soundtrack", "music", "sound", "ost", "voice",
                         "animation", "animations", "beautiful",
                         "gorgeous", "stunning", "atmosphere"],
    "Content & updates": ["update", "updates", "patch", "content", "dlc",
                          "roadmap", "events", "season", "battlepass",
                          "battle pass", "skins", "maps", "weapons",
                          "new content", "abandoned", "dead game"],
}


def theme_hits(text):
    low = " " + text.lower() + " "
    hits = set()
    for theme, keywords in THEMES.items():
        for kw in keywords:
            if kw in low:
                hits.add(theme)
                break
    return hits


def bucket_playtime(hours):
    if hours < 1:
        return "under 1h"
    if hours < 5:
        return "1-5h"
    if hours < 20:
        return "5-20h"
    if hours < 50:
        return "20-50h"
    if hours < 100:
        return "50-100h"
    return "100h+"


PLAYTIME_ORDER = ["under 1h", "1-5h", "5-20h", "20-50h", "50-100h", "100h+"]

LENGTH_ORDER = ["under 20 words", "20-50 words", "50-100 words",
                "100-300 words", "300+ words"]


def bucket_length(words):
    if words < 20:
        return LENGTH_ORDER[0]
    if words < 50:
        return LENGTH_ORDER[1]
    if words < 100:
        return LENGTH_ORDER[2]
    if words < 300:
        return LENGTH_ORDER[3]
    return LENGTH_ORDER[4]


def main():
    df = pd.read_csv(CLEAN_PATH)

    # --- sentiment scoring -------------------------------------------------
    scored = df["review_text_clean"].map(score_text)
    df["sentiment_score"] = [s[0] for s in scored]
    df["sentiment_label"] = df["sentiment_score"].map(label_for)
    pos_terms = Counter()
    neg_terms = Counter()
    for _, hits_pos, hits_neg in scored:
        pos_terms.update(hits_pos)
        neg_terms.update(hits_neg)
    df["playtime_hours"] = (df["author_playtime_at_review"] / 60).round(1)
    df["playtime_bucket"] = df["playtime_hours"].map(bucket_playtime)
    df["length_bucket"] = df["word_count"].map(bucket_length)
    df["month"] = df["date"].str.slice(0, 7)
    df["themes"] = df["review_text_clean"].map(lambda t: sorted(theme_hits(t)))

    df.to_csv(ENRICHED_PATH, index=False)

    # --- aggregates --------------------------------------------------------
    total = len(df)
    pos_share = round(100 * df["voted_up"].mean(), 1)
    avg_sent = round(float(df["sentiment_score"].mean()), 3)
    avg_play = round(float(df["playtime_hours"].mean()), 1)
    non_neutral = df[df["sentiment_label"] != "neutral"]
    agree = round(100 * (
        ((non_neutral["sentiment_label"] == "positive") & non_neutral["voted_up"]) |
        ((non_neutral["sentiment_label"] == "negative") & ~non_neutral["voted_up"])
    ).mean(), 1)
    non_neutral_share = round(100 * len(non_neutral) / total, 1)

    sent_dist = df["sentiment_label"].value_counts().to_dict()

    monthly = (df.groupby("month")
                 .agg(reviews=("recommendationid", "count"),
                      avg_sentiment=("sentiment_score", "mean"),
                      pct_positive=("voted_up", lambda s: 100 * s.mean()))
                 .round(3).reset_index()
                 .sort_values("month").to_dict("records"))

    theme_rows = []
    for theme in THEMES:
        mask = df["themes"].map(lambda hs, t=theme: t in hs)
        sub = df[mask]
        if len(sub) == 0:
            continue
        theme_rows.append({
            "theme": theme,
            "reviews": int(len(sub)),
            "share": round(100 * len(sub) / total, 1),
            "pct_positive": round(100 * sub["voted_up"].mean(), 1),
            "avg_sentiment": round(float(sub["sentiment_score"].mean()), 3),
        })
    theme_rows.sort(key=lambda r: r["reviews"], reverse=True)

    playtime_rows = []
    for b in PLAYTIME_ORDER:
        sub = df[df["playtime_bucket"] == b]
        if len(sub):
            playtime_rows.append({
                "bucket": b, "reviews": int(len(sub)),
                "pct_positive": round(100 * sub["voted_up"].mean(), 1),
                "avg_sentiment": round(float(sub["sentiment_score"].mean()), 3)})

    length_rows = []
    for b in LENGTH_ORDER:
        sub = df[df["length_bucket"] == b]
        if len(sub):
            length_rows.append({"bucket": b, "reviews": int(len(sub))})

    game_rows = []
    for game, sub in df.groupby("game"):
        theme_counter = Counter()
        theme_pos = defaultdict(list)
        for themes, up in zip(sub["themes"], sub["voted_up"]):
            for t in themes:
                theme_counter[t] += 1
                theme_pos[t].append(up)
        praise, complaint = None, None
        if theme_counter:
            ranked = sorted(theme_counter, key=lambda t: (
                pd.Series(theme_pos[t]).mean(), theme_counter[t]), reverse=True)
            praise = ranked[0]
            complaint = sorted(theme_counter,
                               key=lambda t: pd.Series(theme_pos[t]).mean())[0]
        game_rows.append({
            "game": game,
            "appid": int(sub["appid"].iloc[0]),
            "reviews": int(len(sub)),
            "pct_positive": round(100 * sub["voted_up"].mean(), 1),
            "avg_sentiment": round(float(sub["sentiment_score"].mean()), 3),
            "avg_playtime_hours": round(float(sub["playtime_hours"].mean()), 1),
            "avg_words": round(float(sub["word_count"].mean()), 1),
            "most_praised_theme": praise,
            "most_complained_theme": complaint,
        })
    game_rows.sort(key=lambda r: r["pct_positive"], reverse=True)

    helpful = (df.sort_values("votes_up", ascending=False).head(12)[
        ["recommendationid", "game", "date", "votes_up", "votes_funny",
         "sentiment_label", "sentiment_score", "review_text_clean",
         "word_count", "playtime_hours", "voted_up"]]
        .to_dict("records"))

    # --- auto insights -----------------------------------------------------
    best_game = game_rows[0]
    worst_game = game_rows[-1]
    most_praised = max(theme_rows, key=lambda r: r["avg_sentiment"])
    most_complained = min(theme_rows, key=lambda r: r["avg_sentiment"])
    veteran = next((r for r in playtime_rows if r["bucket"] == "100h+"), None)
    casual = next((r for r in playtime_rows if r["bucket"] == "under 1h"), None)
    busiest = max(monthly, key=lambda m: m["reviews"]) if monthly else None

    insights = [
        f"{pos_share}% of the {total:,} reviews recommend the game (thumbs up).",
        f"Where the text scorer takes a position ({non_neutral_share}% of "
        f"reviews), its polarity matches the player's thumbs up/down vote "
        f"{agree}% of the time - the lexicon signal lines up with real votes.",
        f"Most praised game: {best_game['game']} "
        f"({best_game['pct_positive']}% positive). Least positive: "
        f"{worst_game['game']} ({worst_game['pct_positive']}%).",
        f"Players sound happiest when talking about "
        f"'{most_praised['theme'].lower()}' and most negative about "
        f"'{most_complained['theme'].lower()}'.",
    ]
    if veteran and casual:
        diff = round(veteran["pct_positive"] - casual["pct_positive"], 1)
        if diff > 0:
            insights.append(
                f"Veterans (100h+ played) are {diff} points more positive "
                f"than players with under 1 hour, so the games hold up after "
                f"the first impression.")
        else:
            insights.append(
                f"Players with under 1 hour are more positive than 100h+ "
                f"veterans by {abs(diff)} points, suggesting long-term "
                f"issues (updates, balance or community) wear players down.")
    if busiest:
        insights.append(
            f"Busiest month in the sample: {busiest['month']} with "
            f"{int(busiest['reviews']):,} reviews.")

    analysis = {
        "kpis": {
            "total_reviews": int(total),
            "pct_positive": pos_share,
            "avg_sentiment": avg_sent,
            "avg_playtime_hours": avg_play,
            "games": int(df["game"].nunique()),
            "date_min": str(df["date"].min()),
            "date_max": str(df["date"].max()),
            "sentiment_vote_agreement": agree,
            "non_neutral_share": non_neutral_share,
        },
        "sentiment_distribution": {
            k: int(sent_dist.get(k, 0))
            for k in ["positive", "neutral", "negative"]},
        "monthly": monthly,
        "top_positive_terms": pos_terms.most_common(15),
        "top_negative_terms": neg_terms.most_common(15),
        "themes": theme_rows,
        "playtime_buckets": playtime_rows,
        "length_buckets": length_rows,
        "games": game_rows,
        "most_helpful": helpful,
        "insights": insights,
    }

    with open(REPORT_PATH) as f:
        analysis["cleaning_report"] = json.load(f)

    with open(ANALYSIS_PATH, "w") as f:
        json.dump(analysis, f, indent=2, default=str)

    print(f"analyzed {total} reviews -> {ANALYSIS_PATH}")
    for line in insights:
        print(" *", line)


if __name__ == "__main__":
    main()

"""Generate a SYNTHETIC sample dataset so the project runs out of the box.

Output: data/raw/steam_reviews_raw.csv (same schema as the real fetchers).

Every review here is machine-generated filler text written for this project.
It is NOT real Steam user content and must never be presented as such. It
exists so the pipeline and dashboard work immediately; replace it with real
data via scripts/fetch_steam_reviews.py (Steam's public API) or
scripts/fetch_huggingface_sample.py (the public Hugging Face mirror).

The generator intentionally includes a few empty rows, duplicates, very
short reviews and one non-English review so the cleaning funnel in
clean_data.py has something to remove.
"""

import csv
import os
import random

random.seed(42)

GAMES = [
    (1145360, "Hades", 0.96),
    (578080, "PUBG: BATTLEGROUNDS", 0.55),
    (730, "Counter-Strike 2", 0.88),
    (1172470, "Apex Legends", 0.84),
    (1086940, "Baldur's Gate 3", 0.97),
    (252490, "Rust", 0.87),
]

POS_OPENERS = [
    "This game is {pos_adj}.", "Absolutely {pos_adj}.",
    "I {pos_verb} this game.", "What a {pos_adj} experience.",
    "{pos_adj_cap} from start to finish.",
]
POS_BODY = [
    "The {aspect} is {pos_adj} and the {aspect2} keeps me coming back.",
    "Every run feels {pos_adj}, the {aspect} is a masterpiece.",
    "Great {aspect}, beautiful {aspect2}, well worth the price.",
    "The developers really care, updates keep making the {aspect} better.",
    "One of the best {aspect} I have seen in years, highly recommend it.",
]
NEG_OPENERS = [
    "I wanted to {pos_verb} it but the {aspect} is {neg_adj}.",
    "Sadly {neg_adj}.", "This game is {neg_adj} right now.",
    "Cannot recommend in this state.",
]
NEG_BODY = [
    "The {aspect} is {neg_adj} and full of cheaters and hackers.",
    "Constant crashes and lag make the {aspect} unplayable.",
    "It is buggy, repetitive and the {aspect} feels abandoned.",
    "Overpriced for a {neg_adj} {aspect}; asked for a refund.",
    "Toxic community, terrible servers and broken matchmaking.",
]
NEUTRAL = [
    "It is okay, not great but not bad either.",
    "Mixed feelings, the {aspect} is fine but the {aspect2} needs work.",
    "Decent game with friends, average solo.",
]
ASPECTS = ["gameplay", "combat", "story", "graphics", "soundtrack",
           "matchmaking", "servers", "performance", "content", "community",
           "level design", "gunplay", "progression", "art style"]
POS_ADJ = ["amazing", "great", "fantastic", "brilliant", "excellent",
           "addictive", "beautiful", "polished", "incredible", "solid"]
POS_VERBS = ["love", "enjoy", "recommend", "adore"]
NEG_ADJ = ["broken", "buggy", "laggy", "frustrating", "disappointing",
           "unplayable", "terrible", "repetitive", "toxic", "abandoned"]

FIELDS = ["recommendationid", "appid", "game", "author_playtime_at_review",
          "author_playtime_forever", "language", "review", "timestamp_created",
          "timestamp_updated", "voted_up", "votes_up", "votes_funny",
          "weighted_vote_score", "comment_count", "steam_purchase",
          "received_for_free", "written_during_early_access"]


def fill(template):
    return template.format(
        aspect=random.choice(ASPECTS), aspect2=random.choice(ASPECTS),
        pos_adj=random.choice(POS_ADJ), neg_adj=random.choice(NEG_ADJ),
        pos_verb=random.choice(POS_VERBS),
        pos_adj_cap=random.choice(POS_ADJ).capitalize())


def make_review(positive):
    if positive is None:
        return fill(random.choice(NEUTRAL))
    opener = fill(random.choice(POS_OPENERS if positive else NEG_OPENERS))
    body = fill(random.choice(POS_BODY if positive else NEG_BODY))
    tail = random.choice(["", " 10/10.", " Would play again.",
                          " Fix it please.", " gg."])
    return f"{opener} {body}{tail}".strip()


def main():
    rows = []
    rid = 900000001
    base_ts = 1735689600  # 2025-01-01
    for appid, game, pos_rate in GAMES:
        for i in range(500):
            roll = random.random()
            positive = roll < pos_rate if roll < 0.97 else None
            text = make_review(positive)
            ts = base_ts + random.randint(0, 250 * 86400)
            play = max(0, int(random.expovariate(1 / 40) * 60))
            rows.append({
                "recommendationid": rid, "appid": appid, "game": game,
                "author_playtime_at_review": play,
                "author_playtime_forever": play + random.randint(0, 5000),
                "language": "english", "review": text,
                "timestamp_created": ts, "timestamp_updated": ts,
                "voted_up": 1 if positive else 0,
                "votes_up": random.randint(0, 40),
                "votes_funny": random.randint(0, 8),
                "weighted_vote_score": round(random.random(), 2),
                "comment_count": random.randint(0, 4),
                "steam_purchase": 1, "received_for_free": 0,
                "written_during_early_access": 0})
            rid += 1

    # deliberate mess for the cleaning stage
    rows.append({**rows[10], "recommendationid": rid, "review": "   "})
    rid += 1
    rows.append({**rows[20], "recommendationid": rid, "review": "gg"})
    rid += 1
    rows.append({**rows[30], "recommendationid": rid,
                 "language": "russian", "review": "отличная игра"})
    rid += 1
    for _ in range(15):  # exact duplicates of earlier rows (same id)
        rows.append(rows[random.randint(0, 200)])

    out = os.path.join("data", "raw", "steam_reviews_raw.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} SYNTHETIC rows to {out}")
    print("Reminder: this is generated demo data, not real Steam reviews.")


if __name__ == "__main__":
    main()

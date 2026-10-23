"""Lexicon-based sentiment scoring for Steam reviews.

A small, transparent rule-based scorer (no external NLP dependencies) tuned
for gaming language. Every review gets a score in [-1, 1] and a label.

How it works:
  1. Tokenize the lowercased review.
  2. Look up each token in positive / negative lexicons (weight 1 or 2).
  3. Flip the weight when a negation ("not", "never", "n't") appears within
     the previous 3 tokens ("not good" -> negative).
  4. Multiply by 1.5 when a booster ("very", "absolutely") appears within the
     previous 2 tokens ("very good").
  5. Sum, normalize by review length (sqrt of word count) and squash with a
     sigmoid-like function into [-1, 1].

Labels: score >= 0.15 -> positive, <= -0.15 -> negative, else neutral.
"""

import math
import re

POSITIVE = {
    # weight 1
    "good": 1, "great": 1, "fun": 1, "nice": 1, "cool": 1, "solid": 1,
    "enjoyable": 1, "enjoyed": 1, "enjoy": 1, "like": 1, "liked": 1,
    "love": 1, "loved": 1, "loves": 1, "recommend": 1, "recommended": 1,
    "worth": 1, "beautiful": 1, "smooth": 1, "engaging": 1, "immersive": 1,
    "addictive": 1, "relaxing": 1, "charming": 1, "polished": 1,
    "satisfying": 1, "rewarding": 1, "impressive": 1, "interesting": 1,
    "unique": 1, "creative": 1, "funny": 1, "hilarious": 1, "cute": 1,
    "helpful": 1, "friendly": 1, "balanced": 1, "fair": 1, "fast": 1,
    "stable": 1, "optimized": 1, "atmospheric": 1, "gripping": 1,
    "replayable": 1, "replayability": 1, "gem": 1, "win": 1, "winner": 1,
    # weight 2 (strong)
    "amazing": 2, "awesome": 2, "excellent": 2, "fantastic": 2,
    "perfect": 2, "perfectly": 2, "brilliant": 2, "masterpiece": 2,
    "incredible": 2, "outstanding": 2, "superb": 2, "best": 2,
    "exceptional": 2, "phenomenal": 2, "legendary": 2, "gorgeous": 2,
    "stunning": 2, "flawless": 2, "epic": 2, "goat": 2, "peak": 2,
}

NEGATIVE = {
    # weight 1
    "bad": 1, "poor": 1, "boring": 1, "bored": 1, "slow": 1, "bug": 1,
    "bugs": 1, "buggy": 1, "glitch": 1, "glitches": 1, "glitchy": 1,
    "crash": 1, "crashes": 1, "crashed": 1, "crashing": 1, "freeze": 1,
    "freezes": 1, "freezing": 1, "stutter": 1, "stuttering": 1, "lag": 1,
    "lags": 1, "laggy": 1, "disappointing": 1, "disappointed": 1,
    "repetitive": 1, "grindy": 1, "grind": 1, "tedious": 1, "annoying": 1,
    "frustrating": 1, "confusing": 1, "clunky": 1, "dated": 1,
    "overpriced": 1, "expensive": 1, "empty": 1, "shallow": 1,
    "unbalanced": 1, "unfair": 1, "toxic": 1, "cheater": 1, "cheaters": 1,
    "cheating": 1, "hacker": 1, "hackers": 1, "hacking": 1, "smurf": 1,
    "smurfs": 1, "greedy": 1, "paywall": 1, "p2w": 1, "microtransactions": 1,
    "abandoned": 1, "dead": 1, "dying": 1, "empty": 1, "meh": 1,
    "mediocre": 1, "generic": 1, "lazy": 1, "unfinished": 1, "broken": 1,
    "unplayable": 1, "unoptimized": 1, "rubbish": 1, "janky": 1,
    # weight 2 (strong)
    "terrible": 2, "awful": 2, "horrible": 2, "worst": 2, "waste": 2,
    "refund": 2, "refunded": 2, "scam": 2, "ripoff": 2, "trash": 2,
    "garbage": 2, "atrocious": 2, "abysmal": 2, "pathetic": 2,
    "disgusting": 2, "unacceptable": 2, "disaster": 2, "avoid": 2,
    "dogshit": 2, "shit": 2, "crap": 2, "sucks": 2, "suck": 2, "hate": 2,
    "hated": 2, "useless": 2, "pointless": 2,
}

NEGATIONS = {"not", "no", "never", "n't", "cannot", "cant", "can't", "dont",
             "don't", "doesnt", "doesn't", "didnt", "didn't", "isnt",
             "isn't", "wasnt", "wasn't", "wont", "won't", "without",
             "hardly", "barely", "neither", "nor"}

BOOSTERS = {"very", "really", "so", "extremely", "absolutely", "totally",
            "completely", "super", "incredibly", "highly", "insanely",
            "damn", "fucking", "freaking", "seriously", "truly", "pure",
            "most", "quite", "pretty"}

TOKEN_RE = re.compile(r"[a-z][a-z'\-]*")


def tokenize(text):
    return TOKEN_RE.findall(text.lower())


def score_text(text):
    """Return (score in [-1, 1], matched positive terms, matched negative terms)."""
    tokens = tokenize(text or "")
    total = 0.0
    pos_hits, neg_hits = [], []
    for i, tok in enumerate(tokens):
        weight = 0
        if tok in POSITIVE:
            weight = POSITIVE[tok]
        elif tok in NEGATIVE:
            weight = -NEGATIVE[tok]
        if weight == 0:
            continue
        window = tokens[max(0, i - 3):i]
        if any(w in NEGATIONS for w in window):
            weight = -weight  # negation flips polarity
        if any(w in BOOSTERS for w in tokens[max(0, i - 2):i]):
            weight *= 1.5
        total += weight
        (pos_hits if weight > 0 else neg_hits).append(tok)
    if not tokens:
        return 0.0, pos_hits, neg_hits
    normalized = total / math.sqrt(len(tokens))
    squashed = math.tanh(normalized / 2.5)
    return round(squashed, 4), pos_hits, neg_hits


def label_for(score):
    if score >= 0.15:
        return "positive"
    if score <= -0.15:
        return "negative"
    return "neutral"

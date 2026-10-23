# Data provenance & licensing note

## What ships in this repo

- `data/raw/steam_reviews_raw.csv` and `data/processed/*` are SYNTHETIC demo
  data written by `scripts/generate_sample_data.py`. They are not real Steam
  reviews and may be shared freely.

## Real-data fetchers (run them yourself)

- `scripts/fetch_steam_reviews.py` pulls current public reviews from Steam's
  own `appreviews` JSON endpoint (Valve). Reviews belong to their authors;
  keep fetched data for your own local analysis.
- `scripts/fetch_huggingface_sample.py` samples the public dataset
  https://huggingface.co/datasets/SebastianHops/steam-reviews-english
  (a mirror of Steam's public review API; reviews written Mar 2020 - Aug
  2023). That dataset publishes no explicit license, so its review text is
  deliberately NOT bundled here.

## The hosted analysis page

The accompanying analysis page shows aggregate statistics only (counts,
percentages, averages - no review text) computed from a 3,000-review sample
of the Hugging Face dataset taken on 23 Oct 2026. Aggregate facts are not
the authors' expressive content; the underlying text stays out of the repo.

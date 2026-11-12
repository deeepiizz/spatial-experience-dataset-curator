"""Build the combined trial table.

    python -m curator.pipeline            # download (if needed), build, validate, write
    python -m curator.pipeline --offline  # use files already in data/raw
"""

from __future__ import annotations

import argparse
import pathlib

import pandas as pd

from . import adapters, schema
from .sources import RAW_DIR, ROOT, download, load_registry, source_dir

OUT_DIR = ROOT / "data" / "processed"


def build(raw_dir: pathlib.Path = RAW_DIR, fetch: bool = True,
          registry: dict | None = None) -> pd.DataFrame:
    registry = registry or load_registry()
    frames = []
    for sid, meta in registry.items():
        raw = download(meta, raw_dir) if fetch else source_dir(meta, raw_dir)
        frames.append(adapters.load(sid, raw, meta))
    df = pd.concat(frames, ignore_index=True)
    df = df.sort_values(["source_id", "participant_id", "condition", "trial_index"],
                        kind="stable").reset_index(drop=True)
    schema.validate(df)
    return df


def summarise(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("source_id")
    return pd.DataFrame({
        "environment_type": g["environment_type"].first(),
        "presentation": g["presentation"].first(),
        "task": g["task"].first(),
        "participants": g["participant_id"].nunique(),
        "trials": g.size(),
        "conditions": g["condition"].nunique(),
        "median_time_s": g["outcome_time_s"].median().round(1),
        "mean_errors": g["outcome_errors"].mean().round(2),
        "mean_rating": g["outcome_rating"].mean().round(2),
        "age_known_pct": g["age_group"].apply(lambda s: round(100 * (s != "unknown").mean())),
        "gender_known_pct": g["gender"].apply(lambda s: round(100 * (s != "unknown").mean())),
        "licence": g["source_licence"].first(),
        "doi": g["source_doi"].first(),
    }).reset_index()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--offline", action="store_true", help="do not download, use data/raw")
    args = ap.parse_args()

    df = build(fetch=not args.offline)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_DIR / "trials.csv", index=False)
    summary = summarise(df)
    summary.to_csv(OUT_DIR / "source_summary.csv", index=False)
    print(summary.to_string(index=False))
    print(f"\n{len(df)} trials from {df['participant_id'].nunique()} participants "
          f"-> {OUT_DIR / 'trials.csv'}")


if __name__ == "__main__":
    main()

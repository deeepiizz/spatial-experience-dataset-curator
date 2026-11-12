"""The common trial schema that every source is mapped onto.

One row is one trial: a single navigation attempt or a single rating made by one
participant. Columns that a source does not measure are left empty (NaN), never
filled with a guess.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

AGE_GROUPS = ["<18", "18-30", "31-40", "41-50", "51-65", "65+", "unknown"]
GENDERS = ["female", "male", "unknown"]
ENVIRONMENT_TYPES = ["indoor", "urban", "vr"]
PRESENTATIONS = ["physical", "virtual_reality", "static_image"]
TASKS = ["navigation", "rating"]

# Only licences that allow reuse and redistribution of derived data.
ALLOWED_LICENCES = {"CC-BY-4.0", "CC0-1.0"}

# column name -> pandas dtype
COLUMNS: dict[str, str] = {
    "trial_id": "string",
    "source_id": "string",
    "participant_id": "string",
    "age_group": "string",
    "gender": "string",
    "environment_type": "string",
    "presentation": "string",
    "task": "string",
    "task_detail": "string",
    "condition": "string",
    "trial_index": "Int64",
    "outcome_time_s": "Float64",
    "outcome_errors": "Float64",
    "outcome_success": "Int64",
    "outcome_rating": "Float64",
    "rating_scale_min": "Float64",
    "rating_scale_max": "Float64",
    "path_length_m": "Float64",
    "spatial_features": "string",
    "participant_extra": "string",
    "source_doi": "string",
    "source_licence": "string",
    "source_citation": "string",
}

CATEGORIES = {
    "age_group": AGE_GROUPS,
    "gender": GENDERS,
    "environment_type": ENVIRONMENT_TYPES,
    "presentation": PRESENTATIONS,
    "task": TASKS,
}


def age_to_group(age) -> str:
    """Bin an exact age in years into the common age groups."""
    if age is None or pd.isna(age):
        return "unknown"
    age = float(age)
    if age < 18:
        return "<18"
    if age <= 30:
        return "18-30"
    if age <= 40:
        return "31-40"
    if age <= 50:
        return "41-50"
    if age <= 65:
        return "51-65"
    return "65+"


def to_json(d: dict) -> str:
    """Stable JSON for the free-form metadata columns (sorted keys, no NaN)."""
    clean = {}
    for k, v in d.items():
        if v is None or (isinstance(v, float) and np.isnan(v)):
            continue
        if isinstance(v, (np.integer,)):
            v = int(v)
        elif isinstance(v, (np.floating,)):
            v = float(v)
        clean[k] = v
    return json.dumps(clean, sort_keys=True, ensure_ascii=False)


def conform(df: pd.DataFrame) -> pd.DataFrame:
    """Add any missing columns as empty, order them, and cast to schema dtypes."""
    out = df.copy()
    for col in COLUMNS:
        if col not in out.columns:
            out[col] = pd.NA
    out = out[list(COLUMNS)]
    return out.astype(COLUMNS)


class SchemaError(ValueError):
    pass


def validate(df: pd.DataFrame) -> None:
    """Raise SchemaError listing every rule the frame breaks."""
    problems: list[str] = []

    missing = [c for c in COLUMNS if c not in df.columns]
    extra = [c for c in df.columns if c not in COLUMNS]
    if missing:
        problems.append(f"missing columns: {missing}")
    if extra:
        problems.append(f"unexpected columns: {extra}")
    if problems:
        raise SchemaError("; ".join(problems))

    for col, allowed in CATEGORIES.items():
        bad = set(df[col].dropna().unique()) - set(allowed)
        if bad:
            problems.append(f"{col} has values outside {allowed}: {sorted(bad)}")
        if df[col].isna().any():
            problems.append(f"{col} has empty values")

    for col in ("trial_id", "source_id", "participant_id", "condition",
                "source_doi", "source_licence", "source_citation"):
        if df[col].isna().any():
            problems.append(f"{col} has empty values")

    if df["trial_id"].duplicated().any():
        problems.append(f"{int(df['trial_id'].duplicated().sum())} duplicate trial_id values")

    bad_lic = set(df["source_licence"].dropna()) - ALLOWED_LICENCES
    if bad_lic:
        problems.append(f"licences not cleared for reuse: {sorted(bad_lic)}")

    nav = df["task"] == "navigation"
    rate = df["task"] == "rating"
    if df.loc[nav, "outcome_time_s"].isna().any():
        problems.append("navigation trials without outcome_time_s")
    if df.loc[nav, "outcome_rating"].notna().any():
        problems.append("navigation trials with a rating")
    if df.loc[rate, "outcome_rating"].isna().any():
        problems.append("rating trials without outcome_rating")
    r = df.loc[rate]
    if ((r["outcome_rating"] < r["rating_scale_min"]) |
            (r["outcome_rating"] > r["rating_scale_max"])).any():
        problems.append("ratings outside their declared scale")

    if (df["outcome_time_s"].dropna() <= 0).any():
        problems.append("non-positive outcome_time_s")
    err = df["outcome_errors"].dropna()
    if (err < 0).any() or (err != err.round()).any():
        problems.append("outcome_errors must be non-negative whole numbers")
    if not df["outcome_success"].dropna().isin([0, 1]).all():
        problems.append("outcome_success must be 0 or 1")
    if (df["path_length_m"].dropna() < 0).any():
        problems.append("negative path_length_m")

    for col in ("spatial_features", "participant_extra"):
        for v in df[col].dropna():
            try:
                if not isinstance(json.loads(v), dict):
                    raise ValueError
            except ValueError:
                problems.append(f"{col} is not a JSON object: {v[:60]!r}")
                break

    if problems:
        raise SchemaError("; ".join(problems))

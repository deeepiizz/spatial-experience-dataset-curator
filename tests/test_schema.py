"""The validator itself: it must reject each kind of broken row.

These run on a tiny hand-made frame, so they need no downloaded data.
"""

import numpy as np
import pandas as pd
import pytest

from curator import schema


def good_frame() -> pd.DataFrame:
    base = dict(source_id="s", environment_type="vr", presentation="virtual_reality",
                age_group="18-30", gender="female", condition="A",
                source_doi="10.0/x", source_licence="CC-BY-4.0", source_citation="X (2024)")
    nav = dict(base, trial_id="s:p1:A:1", participant_id="s:p1", task="navigation",
               trial_index=1, outcome_time_s=12.5, outcome_errors=1, outcome_success=1,
               path_length_m=20.0, spatial_features='{"layout": "grid"}')
    rate = dict(base, trial_id="s:p1:A:2", participant_id="s:p1", task="rating",
                trial_index=2, outcome_rating=5, rating_scale_min=1, rating_scale_max=7)
    return schema.conform(pd.DataFrame([nav, rate]))


def test_good_frame_passes():
    schema.validate(good_frame())


@pytest.mark.parametrize("col,value,message", [
    ("environment_type", "outdoor", "environment_type"),
    ("task", "memory", "task"),
    ("gender", "M", "gender"),
    ("source_licence", "CC-BY-NC-4.0", "licences not cleared"),
    ("trial_id", "s:p1:A:1", "duplicate trial_id"),
    ("outcome_errors", 1.5, "whole numbers"),
    ("outcome_errors", -1, "whole numbers"),
    ("outcome_time_s", 0.0, "non-positive"),
    ("outcome_success", 2, "0 or 1"),
    ("spatial_features", "not json", "JSON object"),
])
def test_validator_rejects(col, value, message):
    df = good_frame()
    df.loc[1 if col != "outcome_time_s" else 0, col] = value
    with pytest.raises(schema.SchemaError, match=message):
        schema.validate(df)


def test_rating_outside_scale_rejected():
    df = good_frame()
    df.loc[1, "outcome_rating"] = 8
    with pytest.raises(schema.SchemaError, match="outside their declared scale"):
        schema.validate(df)


def test_navigation_needs_time_and_no_rating():
    df = good_frame()
    df.loc[0, "outcome_time_s"] = np.nan
    df.loc[0, "outcome_rating"] = 3
    with pytest.raises(schema.SchemaError) as e:
        schema.validate(df)
    assert "without outcome_time_s" in str(e.value)
    assert "navigation trials with a rating" in str(e.value)


def test_missing_column_rejected():
    with pytest.raises(schema.SchemaError, match="missing columns"):
        schema.validate(good_frame().drop(columns=["source_doi"]))


@pytest.mark.parametrize("age,group", [
    (17, "<18"), (18, "18-30"), (30, "18-30"), (31, "31-40"), (50, "41-50"),
    (65, "51-65"), (66, "65+"), (None, "unknown"), (np.nan, "unknown"),
])
def test_age_bins(age, group):
    assert schema.age_to_group(age) == group

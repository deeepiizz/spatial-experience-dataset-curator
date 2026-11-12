"""Isolation test, in the same spirit as a leakage test.

Corrupt one source's raw file and rebuild. Every row from the OTHER sources must
be byte-for-byte identical, and the corrupted source must actually change. If an
adapter reads another source's files, or shared state leaks between adapters,
this fails.
"""

import shutil

import pandas as pd
import pandas.testing as pdt
import pytest

from curator import pipeline
from curator.sources import RAW_DIR, source_dir


@pytest.fixture
def copied_raw(tmp_path, trials):
    dst = tmp_path / "raw"
    shutil.copytree(RAW_DIR, dst)
    return dst


def test_corrupting_one_source_changes_only_that_source(copied_raw, trials, registry):
    target = registry["tzouras_athens_safety"]
    f = source_dir(target, copied_raw) / "rating_dataset_perceivedSafetyChoices.csv"
    df = pd.read_csv(f)
    df["psafe"] = 8 - df["psafe"]           # reverse every rating
    df.to_csv(f, index=False)

    rebuilt = pipeline.build(raw_dir=copied_raw, fetch=False)

    other = lambda t: t[t.source_id != target["id"]].reset_index(drop=True)
    pdt.assert_frame_equal(other(trials), other(rebuilt))

    a = trials[trials.source_id == target["id"]].outcome_rating.reset_index(drop=True)
    b = rebuilt[rebuilt.source_id == target["id"]].outcome_rating.reset_index(drop=True)
    assert ((a + b) == 8).all()


def test_build_is_deterministic(trials):
    again = pipeline.build(fetch=False)
    pdt.assert_frame_equal(trials, again)


def test_committed_csv_matches_fresh_build(trials):
    path = pipeline.OUT_DIR / "trials.csv"
    if not path.exists():
        pytest.skip("data/processed/trials.csv not built yet")
    committed = pd.read_csv(path, dtype={c: "string" for c in ("trial_id", "participant_id", "condition")})
    assert len(committed) == len(trials)
    assert committed.trial_id.tolist() == trials.trial_id.astype(str).tolist()

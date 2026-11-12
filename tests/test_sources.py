"""Consistency of the combined table, and faithfulness to each raw source.

Every mapping is checked against a number recomputed straight from the raw file,
so a silent change in an adapter (a dropped row, a swapped column, a wrong unit)
fails here.
"""

import io
import json
import re
import zipfile

import numpy as np
import pandas as pd
import pytest

from curator import schema
from curator.adapters.liu_vr_wayfinding import segment_log
from curator.sources import source_dir


def rows(trials, sid):
    return trials[trials.source_id == sid]


# ---------- the combined table ----------------------------------------------

def test_schema_valid(trials):
    schema.validate(trials)


def test_every_source_in_registry_is_present(trials, registry):
    assert set(trials.source_id) == set(registry)


def test_metadata_matches_registry(trials, registry):
    for sid, meta in registry.items():
        r = rows(trials, sid)
        assert (r.source_licence == meta["licence"]).all()
        assert (r.source_doi == meta["doi"]).all()
        assert (r.environment_type == meta["environment_type"]).all()
        assert (r.task == meta["task"]).all()
        assert r.source_citation.str.contains(meta["doi"]).all()


def test_participant_ids_are_namespaced(trials):
    assert (trials.participant_id.str.split(":").str[0] == trials.source_id).all()


def test_demographics_constant_within_participant(trials):
    per = trials.groupby("participant_id")[["age_group", "gender"]].nunique()
    assert (per == 1).all().all(), per[(per > 1).any(axis=1)]


def test_trial_index_has_no_gaps(trials):
    nav = trials[trials.task == "navigation"]
    for (_, _), g in nav.groupby(["participant_id", "condition"]):
        idx = sorted(g.trial_index)
        assert idx == list(range(idx[0], idx[0] + len(idx)))


def test_spatial_features_present_everywhere(trials):
    assert trials.spatial_features.notna().all()
    assert trials.spatial_features.map(lambda s: len(json.loads(s)) > 0).all()


# ---------- Liu VR way-finding -------------------------------------------------

def test_liu_four_trials_per_participant(trials):
    r = rows(trials, "liu_vr_wayfinding")
    assert r.participant_id.nunique() == 50
    assert (r.groupby("participant_id").size() == 4).all()
    assert (r.groupby("condition").participant_id.nunique() == 10).all()


def test_liu_trial_times_add_up_to_last_collection(trials):
    raw = source_dir({"zenodo_record": 10784483})
    r = rows(trials, "liu_vr_wayfinding")
    for path in sorted(raw.glob("P*.csv"))[:50]:
        log = pd.read_csv(path).dropna(subset=["AppleCount"])
        last = log.loc[log.AppleCount.diff() < 0, "TimePassed"].iloc[-1]
        pid = int(re.match(r"P(\d+)", path.name).group(1))
        got = r[r.participant_id == f"liu_vr_wayfinding:{pid}"].outcome_time_s.sum()
        assert got == pytest.approx(last, abs=1e-6), path.name


def test_segment_log_on_synthetic_walk():
    # walk 3 m along x, collect, walk 4 m along z, collect
    log = pd.DataFrame({
        "TimePassed": [0, 1, 2, 3, 4, 5, 6],
        "PosX": [0, 1, 2, 3, 3, 3, 3],
        "PosZ": [0, 0, 0, 0, 2, 4, 4],
        "AppleCount": [2, 2, 2, 1, 1, 0, np.nan],   # trailing empty row like P16CLMG
    })
    t = segment_log(log)
    assert [x["outcome_time_s"] for x in t] == [3, 2]
    assert [x["path_length_m"] for x in t] == pytest.approx([3, 4])


# ---------- Mayor VR labyrinth -------------------------------------------------

def test_labyrinth_phases_reproduce_workbook_totals(trials):
    raw = source_dir({"zenodo_record": 18481749})
    book = pd.ExcelFile(raw / "LabyrinthExperimentALL.xlsx")
    r = rows(trials, "mayor_vr_labyrinth")
    for sheet in book.sheet_names[1:]:
        d = book.parse(sheet).dropna(subset=["USR", "TieTotal"]).set_index("USR")
        got = r[r.condition == sheet].groupby(
            r.participant_id.str.split(":").str[1])[["outcome_time_s", "path_length_m"]].sum()
        assert set(got.index) == set(d.index), sheet
        assert np.allclose(got.loc[d.index, "outcome_time_s"], d.TieTotal, atol=0.02), sheet
        assert np.allclose(got.loc[d.index, "path_length_m"], d.DisTotal, atol=0.02), sheet


def test_labyrinth_dropped_only_documented_empty_rows(trials):
    r = rows(trials, "mayor_vr_labyrinth")
    have = set(zip(r.participant_id.str.split(":").str[1], r.condition))
    every = {(f"U{i:02d}", c) for i in range(1, 37)
             for c in ["Euc", "EucCol", "NoEuc", "NoEucCol", "NoEucDoble"]}
    missing = every - have
    documented = {("U07", "Euc"), ("U08", "EucCol"), ("U33", "NoEucCol"), ("U31", "NoEucDoble")}
    # U34 also has no NoEucDoble row in the workbook at all
    assert missing - documented <= {("U34", "NoEucDoble")}


# ---------- Kumar library ------------------------------------------------------

def test_library_counts_match_description(trials):
    r = rows(trials, "kumar_library_qr")
    assert len(r) == 190 and r.participant_id.nunique() == 95
    groups = r.drop_duplicates("participant_id").participant_extra.map(
        lambda s: json.loads(s)["academic_group"]).value_counts().to_dict()
    assert groups == {"UG": 50, "PhD": 25, "PG": 20}
    assert set(r.condition) == {"Conventional", "QR-assisted"}
    assert (r.groupby("participant_id").condition.nunique() == 2).all()


def test_library_matches_paired_sheet(trials):
    raw = source_dir({"zenodo_record": 23080208})
    with zipfile.ZipFile(raw / "Zenodo_QR_Koha_Navigation_Dataset_Package.zip") as z:
        paired = pd.read_excel(io.BytesIO(z.read("QR_Koha_Navigation_Study_Anonymized_Dataset.xlsx")),
                               sheet_name="Paired_Data").set_index("Participant_ID")
    r = rows(trials, "kumar_library_qr").copy()
    r["pid"] = r.participant_id.str.split(":").str[1]
    wide = r.pivot(index="pid", columns="condition", values="outcome_time_s")
    assert (wide["Conventional"] == paired.loc[wide.index, "Conventional_Duration_sec"]).all()
    assert (wide["QR-assisted"] == paired.loc[wide.index, "QR_Duration_sec"]).all()


# ---------- Tzouras Athens -----------------------------------------------------

def test_athens_every_rating_kept(trials):
    raw = source_dir({"zenodo_record": 14967130})
    src = pd.read_csv(raw / "rating_dataset_perceivedSafetyChoices.csv")
    r = rows(trials, "tzouras_athens_safety")
    assert len(r) == len(src)
    assert r.outcome_rating.mean() == pytest.approx(src.psafe.mean())
    assert r.outcome_rating.value_counts().sort_index().tolist() == \
        src.psafe.value_counts().sort_index().tolist()


def test_athens_age_mapping_agrees_with_young_flag(trials):
    """The README's age codes are off by one; the file's `young` flag is the referee."""
    r = rows(trials, "tzouras_athens_safety")
    young = r.participant_extra.map(lambda s: json.loads(s)["young_flag_raw"])
    assert ((r.age_group == "18-30") == (young == 1)).all()
    assert not (r.age_group == "<18").any()


def test_library_documented_anomalies_unchanged(trials):
    """Pin the known success/accuracy contradiction so a new data version is noticed."""
    r = rows(trials, "kumar_library_qr")
    contradictory = r[(r.outcome_success == 1) & (r.outcome_errors == 3)]
    assert len(contradictory) == 33
    assert set(contradictory.condition) == {"Conventional"}
    whole_minutes = (r.outcome_time_s % 60 == 0).sum()
    assert whole_minutes == 63

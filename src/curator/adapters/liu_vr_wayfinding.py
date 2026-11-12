"""Liu (2024), VR way-finding: one movement log per participant plus a questionnaire.

Each log (P<id><GROUP>.csv) samples position and a target counter (AppleCount),
which falls from 4 to 0 as targets are collected. A trial is the stretch between
two collections; time and horizontal path length are computed from the log.
"""

from __future__ import annotations

import pathlib
import re

import numpy as np
import pandas as pd

from . import finish
from ..schema import age_to_group, to_json

LOG_NAME = re.compile(r"^P(\d+)([A-Z]+)\.csv$")


def segment_log(log: pd.DataFrame) -> list[dict]:
    """Split one movement log into target-to-target trials."""
    log = log.dropna(subset=["AppleCount", "PosX", "PosZ"]).reset_index(drop=True)
    count = log["AppleCount"].to_numpy()
    t = log["TimePassed"].to_numpy(dtype=float)
    step = np.hypot(np.diff(log["PosX"].to_numpy(float)), np.diff(log["PosZ"].to_numpy(float)))
    cum = np.concatenate([[0.0], np.cumsum(step)])

    events = np.flatnonzero(np.diff(count) < 0) + 1   # rows where a target was just collected
    trials, start = [], 0
    for k, end in enumerate(events, start=1):
        trials.append({
            "trial_index": k,
            "outcome_time_s": t[end] - t[start],
            "path_length_m": cum[end] - cum[start],
            "outcome_success": 1,
            "targets_left": int(count[end]),
        })
        start = end
    return trials


def load(raw: pathlib.Path, meta: dict) -> pd.DataFrame:
    survey = pd.read_csv(raw / "UserStudy.csv", encoding="latin-1")
    survey = survey.dropna(subset=["Participant number"])
    survey["pid"] = survey["Participant number"].astype(int)
    survey = survey.set_index("pid")

    rows = []
    for path in sorted(raw.glob("P*.csv")):
        m = LOG_NAME.match(path.name)
        if not m:
            continue
        pid, group = int(m.group(1)), m.group(2)
        s = survey.loc[pid] if pid in survey.index else None
        gender = str(s["Gender"]).strip().lower() if s is not None else "unknown"
        extra = {}
        if s is not None:
            extra = {
                "input_device": str(s["Input"]),
                "vr_experience_1_5": s["VR Experience"],
                "game_frequency_1_5": s["Game Frequency"],
                "nasa_tlx_mental": s["Mental Demand"],
                "nasa_tlx_frustration": s["Frustration Level"],
            }
        for tr in segment_log(pd.read_csv(path)):
            targets_left = tr.pop("targets_left")
            rows.append({
                **tr,
                "participant_id": pid,
                "condition": group,
                "age_group": age_to_group(s["Age"]) if s is not None else "unknown",
                "gender": gender if gender in ("female", "male") else "unknown",
                "task_detail": "find and collect the next of 4 targets in a virtual environment",
                "spatial_features": to_json({"guidance_group": group,
                                             "targets_remaining_after": targets_left}),
                "participant_extra": to_json(extra),
            })
    return finish(pd.DataFrame(rows), meta)

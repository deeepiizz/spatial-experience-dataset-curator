"""Tzouras (2025), perceived safety of imagined Athens road scenarios.

One row in the source is already one rating (respondent x scenario x transport mode).
The road design variables are the spatial features.
"""

from __future__ import annotations

import pathlib

import pandas as pd

from . import finish
from ..schema import to_json

RATINGS = "rating_dataset_perceivedSafetyChoices.csv"

# The README says 1 = <18, 2 = 18-30, ... but the file's own `young` flag (under 30)
# is 1 for exactly the code-1 respondents, so the codes start at 18-30.
# tests/test_sources.py checks this against `young` on every build.
AGE_CODE = {1: "18-30", 2: "31-40", 3: "41-50", 4: "51-65", 5: "65+"}
GENDER = {0: "male", 1: "female"}
MODE = {"car": "car", "ebike": "e-bike", "escoot": "e-scooter", "walk": "walk"}
ROAD_TYPE = {
    1: "one-way urban road, 50 km/h, no cycle lane, sidewalk < 1.5 m",
    2: "one-way urban road, 50 km/h, no cycle lane, sidewalk >= 1.5 m",
    3: "one-way urban road, 50 km/h, with cycle lane",
    4: "shared space, 30 km/h",
}
CROSSING = {0: "none", 1: "zebra, uncontrolled", 2: "zebra, traffic lights"}


def load(raw: pathlib.Path, meta: dict) -> pd.DataFrame:
    r = pd.read_csv(raw / RATINGS)
    r = r.sort_values(["pid", "scenario", "tmode"]).reset_index(drop=True)
    r["trial_index"] = r.groupby("pid").cumcount() + 1

    rows = []
    for _, x in r.iterrows():
        rows.append({
            "participant_id": x["pid"],
            "condition": f"{x['scenario']}|{MODE[x['tmode']]}",
            "trial_index": x["trial_index"],
            "task_detail": f"rate how safe you would feel using a {MODE[x['tmode']]} on this road (image)",
            "outcome_rating": x["psafe"],
            "rating_scale_min": 1,
            "rating_scale_max": 7,
            "age_group": AGE_CODE.get(int(x["age"]), "unknown"),
            "gender": GENDER.get(int(x["gender"]), "unknown"),
            "spatial_features": to_json({
                "scenario": x["scenario"],
                "transport_mode": MODE[x["tmode"]],
                "road_type": ROAD_TYPE[int(x["type"])],
                "pavement_good": int(x["pav"]),
                "obstacles": int(x["obst"]),
                "crossing": CROSSING[int(x["cross"])],
                "vehicles_per_km_lane": float(x["veh"]),
                "two_wheelers_per_km_lane": float(x["bike"]),
                "pedestrians_per_3500_m2": int(x["ped"]),
            }),
            "participant_extra": to_json({
                "age_code_raw": int(x["age"]),
                "young_flag_raw": int(x["young"]),
                "car_owner": int(x["car_own"]),
                "bike_frequency_0_4": x["bike_frequency"],
                "escooter_frequency_0_4": x["escooter_frequency"],
            }),
        })
    return finish(pd.DataFrame(rows), meta)

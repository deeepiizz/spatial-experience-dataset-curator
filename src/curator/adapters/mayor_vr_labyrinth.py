"""Mayor et al. (2026), room-scale VR labyrinths, Euclidean vs partially non-Euclidean.

The workbook has a demographics sheet and one sheet per condition. Each condition
row holds an outbound phase (start to goal) and a return phase (goal to start),
which become two trials.
"""

from __future__ import annotations

import pathlib

import pandas as pd

from . import finish
from ..schema import age_to_group, to_json

WORKBOOK = "LabyrinthExperimentALL.xlsx"

CONDITIONS = {
    "Euc": {"geometry": "euclidean", "coloured_walls": False},
    "EucCol": {"geometry": "euclidean", "coloured_walls": True},
    "NoEuc": {"geometry": "partially_non_euclidean", "coloured_walls": False},
    "NoEucCol": {"geometry": "partially_non_euclidean", "coloured_walls": True},
    # Present in the workbook but not described in the record.
    "NoEucDoble": {"geometry": "partially_non_euclidean_double (undocumented)", "coloured_walls": None},
}

PHASES = {
    1: ("outbound", "Distancia Total Ida", "Veces Perdido Ida", "Tiempo Ida"),
    2: ("return", "Distancia Total Vuelta", "Veces Perdido Vuelta", "Tiempo Vuelta"),
}

GENDER = {"H": "male", "M": "female"}   # Spanish: hombre / mujer


def load(raw: pathlib.Path, meta: dict) -> pd.DataFrame:
    book = pd.ExcelFile(raw / WORKBOOK)
    demo = book.parse("Demo").dropna(subset=["USR"]).set_index("USR")

    rows = []
    for sheet, features in CONDITIONS.items():
        d = book.parse(sheet)
        # drop the unlabeled mean rows at the bottom and participants with no data
        d = d.dropna(subset=["USR"]).dropna(subset=["Tiempo Ida", "Tiempo Vuelta"], how="all")
        for _, r in d.iterrows():
            usr = r["USR"]
            p = demo.loc[usr] if usr in demo.index else None
            for idx, (phase, dist, lost, time) in PHASES.items():
                if pd.isna(r[time]):
                    continue
                rows.append({
                    "participant_id": usr,
                    "condition": sheet,
                    "trial_index": idx,
                    "task_detail": f"labyrinth, {phase} path ({'start to goal' if phase == 'outbound' else 'back to start'})",
                    "outcome_time_s": r[time],
                    "outcome_errors": r[lost],
                    "outcome_success": 1,
                    "path_length_m": r[dist],
                    "age_group": age_to_group(p["Edad"]) if p is not None else "unknown",
                    "gender": GENDER.get(str(p["Sexo"]).strip(), "unknown") if p is not None else "unknown",
                    "spatial_features": to_json({**features, "phase": phase,
                                                 "room_scale": True}),
                    "participant_extra": to_json({} if p is None else {
                        "vr_use_1_7": p["Uso de RV 1-7"],
                        "videogame_use_1_7": p["Uso de vidoejuegos 1-7"],
                        "self_rated_orientation_1_7": p["Cómo crees que te orientas 1-7"],
                    }),
                })
    return finish(pd.DataFrame(rows), meta)

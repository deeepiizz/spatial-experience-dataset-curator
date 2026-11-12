"""Kumar (2026), book finding in a real academic library, conventional vs QR-assisted.

The Zenodo package is a zip with an xlsx workbook; the Task_Data sheet already has
one row per task, so the mapping is mostly a rename.
"""

from __future__ import annotations

import io
import pathlib
import zipfile

import pandas as pd

from . import finish
from ..schema import to_json

PACKAGE = "Zenodo_QR_Koha_Navigation_Dataset_Package.zip"
WORKBOOK = "QR_Koha_Navigation_Study_Anonymized_Dataset.xlsx"


def load(raw: pathlib.Path, meta: dict) -> pd.DataFrame:
    with zipfile.ZipFile(raw / PACKAGE) as z:
        task = pd.read_excel(io.BytesIO(z.read(WORKBOOK)), sheet_name="Task_Data")

    # within each participant, order trials by start time
    task = task.sort_values(["Participant_ID", "Start_Time"])
    task["trial_index"] = task.groupby("Participant_ID").cumcount() + 1

    rows = []
    for _, r in task.iterrows():
        rows.append({
            "participant_id": r["Participant_ID"],
            "condition": r["Condition"],
            "trial_index": r["trial_index"],
            "task_detail": "find a given book on the correct rack, side and shelf",
            "outcome_time_s": r["Duration_sec"],
            "outcome_errors": 3 - r["Accuracy_Score_0_3"],
            "outcome_success": r["Success_0_1"],
            "age_group": "unknown",
            "gender": "unknown",
            "spatial_features": to_json({
                "setting": "academic library stacks",
                "book_label": r["Book_Label"],
                "rack_correct": r["Rack_Correct_0_1"],
                "side_correct": r["Side_Correct_0_1"],
                "shelf_correct": r["Shelf_Correct_0_1"],
                "qr_scans": r["QR_Scans"],
                "staff_assistance": r["Staff_Assistance_0_1"],
            }),
            "participant_extra": to_json({
                "academic_group": r["User_Group"],
                "assignment_sequence": r["Assignment_Sequence"],
            }),
        })
    return finish(pd.DataFrame(rows), meta)

"""One adapter per source. Each takes the source's raw folder and registry entry
and returns rows in the common schema. Adapters never read another source's
files, which the isolation test in tests/test_pipeline.py checks."""

from __future__ import annotations

import pathlib

import pandas as pd

from .. import schema
from ..sources import citation


def finish(df: pd.DataFrame, meta: dict) -> pd.DataFrame:
    """Attach the source-level metadata from the registry and conform to the schema."""
    df = df.copy()
    df["source_id"] = meta["id"]
    df["participant_id"] = meta["id"] + ":" + df["participant_id"].astype(str)
    df["trial_id"] = (df["participant_id"] + ":" + df["condition"].astype(str)
                      + ":" + df["trial_index"].astype(str))
    df["environment_type"] = meta["environment_type"]
    df["presentation"] = meta["presentation"]
    df["task"] = meta["task"]
    df["source_doi"] = meta["doi"]
    df["source_licence"] = meta["licence"]
    df["source_citation"] = citation(meta)
    return schema.conform(df)


def load(source_id: str, raw: pathlib.Path, meta: dict) -> pd.DataFrame:
    from . import kumar_library_qr, liu_vr_wayfinding, mayor_vr_labyrinth, tzouras_athens_safety
    adapters = {
        "liu_vr_wayfinding": liu_vr_wayfinding.load,
        "mayor_vr_labyrinth": mayor_vr_labyrinth.load,
        "kumar_library_qr": kumar_library_qr.load,
        "tzouras_athens_safety": tzouras_athens_safety.load,
    }
    return adapters[source_id](raw, meta)

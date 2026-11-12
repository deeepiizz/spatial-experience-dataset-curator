"""Export the combined trials as a star schema for Power BI.

    python -m curator.powerbi_export

Writes powerbi/data/*.csv: one fact table and four dimensions, plus a table of the
data-quality issues from sources.yaml. See powerbi/README.md for the model and pages.
"""

from __future__ import annotations

import json

import pandas as pd
import yaml

from .pipeline import OUT_DIR
from .schema import AGE_GROUPS
from .sources import REGISTRY, ROOT, load_registry

PBI_DIR = ROOT / "powerbi" / "data"

SHORT_NAMES = {
    "liu_vr_wayfinding": "VR wayfinding (Liu)",
    "mayor_vr_labyrinth": "VR labyrinth (Mayor)",
    "kumar_library_qr": "Library book search (Kumar)",
    "tzouras_athens_safety": "Athens street safety (Tzouras)",
}

CONDITION_LABELS = {
    "Euc": "Euclidean", "EucCol": "Euclidean, coloured walls",
    "NoEuc": "Non-Euclidean", "NoEucCol": "Non-Euclidean, coloured walls",
    "NoEucDoble": "Non-Euclidean double (undocumented)",
}


def build_tables(trials: pd.DataFrame, registry: dict) -> dict[str, pd.DataFrame]:
    t = trials.copy()
    sf = t["spatial_features"].map(json.loads)
    px = t["participant_extra"].map(json.loads)

    # ---- dim_source
    dim_source = pd.DataFrame([{
        "source_id": sid,
        "source_name": SHORT_NAMES[sid],
        "environment_type": m["environment_type"],
        "presentation": m["presentation"],
        "task": m["task"],
        "design": m["design"],
        "trial_definition": " ".join(m["trial_definition"].split()),
        "licence": m["licence"],
        "doi_url": f"https://doi.org/{m['doi']}",
        "year": m["year"],
    } for sid, m in registry.items()])

    # ---- dim_participant
    p = t.assign(academic_group=px.map(lambda d: d.get("academic_group")),
                 vr_experience=px.map(lambda d: d.get("vr_experience_1_5", d.get("vr_use_1_7"))))
    dim_participant = (p.groupby("participant_id", as_index=False)
                       .agg(source_id=("source_id", "first"), age_group=("age_group", "first"),
                            gender=("gender", "first"), academic_group=("academic_group", "first"),
                            vr_experience=("vr_experience", "first")))
    dim_participant["age_group_order"] = dim_participant["age_group"].map(AGE_GROUPS.index)

    # ---- dim_condition (one row per source x condition, with its spatial features)
    t["condition_key"] = t["source_id"] + "|" + t["condition"]
    feats = pd.DataFrame(list(sf), index=t.index)
    c = pd.concat([t[["condition_key", "source_id", "condition"]], feats], axis=1)
    c = c.drop_duplicates("condition_key")
    label = c["condition"].map(CONDITION_LABELS)
    athens = c["source_id"] == "tzouras_athens_safety"
    label = label.fillna(c["condition"])
    label[athens] = c.loc[athens, "scenario"] + " – " + c.loc[athens, "transport_mode"]
    dim_condition = pd.DataFrame({
        "condition_key": c["condition_key"],
        "source_id": c["source_id"],
        "condition": c["condition"],
        "condition_label": label,
        "geometry": c.get("geometry"),
        "coloured_walls": c.get("coloured_walls"),
        "transport_mode": c.get("transport_mode"),
        "road_type": c.get("road_type"),
        "crossing": c.get("crossing"),
        "pavement_good": c.get("pavement_good"),
        "obstacles": c.get("obstacles"),
        "vehicles_per_km_lane": c.get("vehicles_per_km_lane"),
    })

    # ---- fact_trials
    fact = pd.DataFrame({
        "trial_id": t["trial_id"],
        "source_id": t["source_id"],
        "participant_id": t["participant_id"],
        "condition_key": t["condition_key"],
        "trial_index": t["trial_index"],
        "phase": sf.map(lambda d: d.get("phase")),
        "time_s": t["outcome_time_s"],
        "errors": t["outcome_errors"],
        "success": t["outcome_success"],
        "rating": t["outcome_rating"],
        # 0 = lowest point of the scale, 1 = highest; comparable across scales
        "rating_normalised": (t["outcome_rating"] - t["rating_scale_min"])
                             / (t["rating_scale_max"] - t["rating_scale_min"]),
        "path_length_m": t["path_length_m"],
    })

    # ---- data quality issues
    with open(REGISTRY, encoding="utf-8") as f:
        reg = yaml.safe_load(f)
    issues = pd.DataFrame([{"source_id": s["id"], "issue_no": i + 1,
                            "issue": " ".join(txt.split())}
                           for s in reg["sources"] for i, txt in enumerate(s["known_issues"])])

    return {"fact_trials": fact, "dim_source": dim_source, "dim_participant": dim_participant,
            "dim_condition": dim_condition, "quality_issues": issues}


def main() -> None:
    trials = pd.read_csv(OUT_DIR / "trials.csv")
    tables = build_tables(trials, load_registry())
    PBI_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(PBI_DIR / f"{name}.csv", index=False)
        print(f"{name:16s} {len(df):6d} rows")


if __name__ == "__main__":
    main()

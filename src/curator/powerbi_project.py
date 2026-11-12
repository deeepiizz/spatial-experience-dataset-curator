"""Generate a Power BI Project (PBIP) with the data model, relationships and measures.

    python -m curator.powerbi_project

Writes powerbi/SpatialExperience.pbip with a TMDL semantic model that loads the CSVs in
powerbi/data/. Open the .pbip in Power BI Desktop, set the DataFolder parameter to that
folder, refresh, and add the visuals described in powerbi/README.md.
"""

from __future__ import annotations

import json
import uuid

import pandas as pd

from .sources import ROOT

PBI = ROOT / "powerbi"
NAME = "SpatialExperience"
NS = uuid.UUID("6f1c2b9e-3d7a-4c55-9a0e-2b8f6d4e1a77")   # stable lineage tags across rebuilds

TABLES = ["fact_trials", "dim_source", "dim_participant", "dim_condition", "quality_issues"]

INT_COLS = {"trial_index", "age_group_order", "year", "issue_no"}
NUM_COLS = {"success", "time_s", "errors", "rating", "rating_normalised", "path_length_m",
            "vr_experience", "vehicles_per_km_lane", "pavement_good", "obstacles"}
HIDDEN = {"trial_id", "condition_key", "participant_id", "age_group_order"}

RELATIONSHIPS = [
    ("fact_trials", "source_id", "dim_source", "source_id"),
    ("fact_trials", "participant_id", "dim_participant", "participant_id"),
    ("fact_trials", "condition_key", "dim_condition", "condition_key"),
    ("quality_issues", "source_id", "dim_source", "source_id"),
]

# name -> (DAX, format string)
MEASURES = {
    "Trials": ("COUNTROWS ( fact_trials )", "#,0"),
    "Participants": ("DISTINCTCOUNT ( fact_trials[participant_id] )", "#,0"),
    "Sources": ("DISTINCTCOUNT ( fact_trials[source_id] )", "#,0"),
    "Median time (s)": ("MEDIAN ( fact_trials[time_s] )", "#,0.0"),
    "Mean errors": ("AVERAGE ( fact_trials[errors] )", "#,0.00"),
    "Success rate": ("""DIVIDE (
    CALCULATE ( COUNTROWS ( fact_trials ), fact_trials[success] = 1 ),
    CALCULATE ( COUNTROWS ( fact_trials ), NOT ISBLANK ( fact_trials[success] ) )
)""", "0.0%"),
    "Mean rating": ("AVERAGE ( fact_trials[rating] )", "#,0.00"),
    "Mean rating (0-1)": ("AVERAGE ( fact_trials[rating_normalised] )", "#,0.00"),
    "Median path (m)": ("MEDIAN ( fact_trials[path_length_m] )", "#,0.0"),
    "Age known %": ("""DIVIDE (
    CALCULATE ( [Participants], dim_participant[age_group] <> "unknown" ),
    [Participants]
)""", "0%"),
    "Gender known %": ("""DIVIDE (
    CALCULATE ( [Participants], dim_participant[gender] <> "unknown" ),
    [Participants]
)""", "0%"),
    "QR time saving %": ("""VAR conv = CALCULATE ( [Median time (s)], dim_condition[condition] = "Conventional" )
VAR qr = CALCULATE ( [Median time (s)], dim_condition[condition] = "QR-assisted" )
RETURN DIVIDE ( conv - qr, conv )""", "0.0%"),
    "Outbound / return time ratio": ("""DIVIDE (
    CALCULATE ( [Median time (s)], fact_trials[phase] = "outbound" ),
    CALCULATE ( [Median time (s)], fact_trials[phase] = "return" )
)""", "#,0.00"),
    "Safety gap between modes": ("""VAR byMode =
    ADDCOLUMNS ( VALUES ( dim_condition[transport_mode] ), "r", [Mean rating] )
RETURN MAXX ( byMode, [r] ) - MINX ( byMode, [r] )""", "#,0.00"),
    "Known issues": ("COUNTROWS ( quality_issues )", "#,0"),
}

PAGES = ["Overview", "Navigation", "Perceived street safety", "Data quality"]


def tag(*parts: str) -> str:
    return str(uuid.uuid5(NS, "/".join(parts)))


def q(name: str) -> str:
    """Quote a TMDL object name when it is not a plain identifier."""
    return name if name.replace("_", "").isalnum() else "'" + name.replace("'", "''") + "'"


def col_type(col: str) -> tuple[str, str, str]:
    """(TMDL dataType, M type, summarizeBy)"""
    if col in INT_COLS:
        return "int64", "Int64.Type", "none"
    if col in NUM_COLS:
        return "double", "type number", "none"
    return "string", "type text", "none"


def table_tmdl(name: str, columns: list[str]) -> str:
    out = [f"table {name}", f"\tlineageTag: {tag(name)}", ""]
    if name == "fact_trials":
        for m, (dax, fmt) in MEASURES.items():
            if "\n" in dax:
                body = "\n".join("\t\t\t" + line for line in dax.splitlines())
                out.append(f"\tmeasure {q(m)} = ```\n{body}\n\t\t\t```")
            else:
                out.append(f"\tmeasure {q(m)} = {dax}")
            out += [f"\t\tformatString: {fmt}", f"\t\tlineageTag: {tag(name, 'm', m)}", ""]
    for c in columns:
        dt, _, summ = col_type(c)
        out.append(f"\tcolumn {q(c)}")
        out.append(f"\t\tdataType: {dt}")
        if c in HIDDEN:
            out.append("\t\tisHidden")
        if c == "doi_url":
            out.append("\t\tdataCategory: WebUrl")
        out.append(f"\t\tlineageTag: {tag(name, c)}")
        out.append(f"\t\tsummarizeBy: {summ}")
        out.append(f"\t\tsourceColumn: {c}")
        if name == "dim_participant" and c == "age_group":
            out.append("\t\tsortByColumn: age_group_order")
        out.append("")
    types = ", ".join(f'{{"{c}", {col_type(c)[1]}}}' for c in columns)
    m = [
        "let",
        f'    Source = Csv.Document(File.Contents(DataFolder & "{name}.csv"), '
        '[Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
        "    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),",
        # en-US so decimals with "." load correctly on German and other locales
        f'    Typed = Table.TransformColumnTypes(Promoted, {{{types}}}, "en-US")',
        "in",
        "    Typed",
    ]
    out.append(f"\tpartition {name} = m")
    out.append("\t\tmode: import")
    out.append("\t\tsource =")
    out += ["\t\t\t\t" + line for line in m]
    out.append("")
    return "\n".join(out)


def build() -> None:
    sm = PBI / f"{NAME}.SemanticModel"
    rp = PBI / f"{NAME}.Report"
    (sm / "definition" / "tables").mkdir(parents=True, exist_ok=True)
    rp.mkdir(parents=True, exist_ok=True)

    (PBI / f"{NAME}.pbip").write_text(json.dumps({
        "version": "1.0",
        "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
        "settings": {"enableAutoRecovery": True},
    }, indent=2) + "\n")

    (sm / "definition.pbism").write_text(json.dumps({"version": "4.0", "settings": {}}, indent=2) + "\n")
    d = sm / "definition"
    (d / "database.tmdl").write_text("database\n\tcompatibilityLevel: 1567\n")
    (d / "model.tmdl").write_text("\n".join([
        "model Model",
        "\tculture: en-US",
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        "\tsourceQueryCulture: en-US",
        "",
        *[f"ref table {t}" for t in TABLES],
        "",
    ]))
    (d / "expressions.tmdl").write_text(
        'expression DataFolder = "C:\\spatial-experience-dataset-curator\\powerbi\\data\\" '
        'meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]\n'
        f"\tlineageTag: {tag('DataFolder')}\n")
    rel = []
    for ft, fc, tt, tc in RELATIONSHIPS:
        rel += [f"relationship {tag('rel', ft, fc, tt)}",
                f"\tfromColumn: {ft}.{fc}", f"\ttoColumn: {tt}.{tc}", ""]
    (d / "relationships.tmdl").write_text("\n".join(rel))
    for t in TABLES:
        cols = list(pd.read_csv(PBI / "data" / f"{t}.csv", nrows=0).columns)
        (d / "tables" / f"{t}.tmdl").write_text(table_tmdl(t, cols))

    (rp / "definition.pbir").write_text(json.dumps({
        "version": "4.0",
        "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}},
    }, indent=2) + "\n")
    sections = [{
        "config": "{}", "displayName": p, "displayOption": 1, "filters": "[]",
        "height": 720.0, "width": 1280.0, "name": f"ReportSection{i}", "ordinal": i,
        "visualContainers": [],
    } for i, p in enumerate(PAGES)]
    (rp / "report.json").write_text(json.dumps({
        "config": json.dumps({"version": "5.43", "themeCollection": {}}),
        "layoutOptimization": 0, "resourcePackages": [], "sections": sections,
    }, indent=2) + "\n")
    (PBI / ".gitignore").write_text("**/.pbi/localSettings.json\n**/.pbi/cache.abf\n")
    print(f"wrote {PBI / (NAME + '.pbip')}")


if __name__ == "__main__":
    build()

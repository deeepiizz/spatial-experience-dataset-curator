"""The Power BI star schema must have unique dimension keys that every fact row finds."""

from curator.powerbi_export import build_tables


def test_star_schema_keys(trials, registry):
    t = build_tables(trials.astype(object), registry)
    fact = t["fact_trials"]
    assert len(fact) == len(trials)
    for dim, key in [("dim_source", "source_id"), ("dim_participant", "participant_id"),
                     ("dim_condition", "condition_key")]:
        assert t[dim][key].is_unique, dim
        assert fact[key].isin(t[dim][key]).all(), dim


def test_rating_normalised_in_unit_interval(trials, registry):
    r = build_tables(trials.astype(object), registry)["fact_trials"]["rating_normalised"].dropna()
    assert len(r) > 0 and r.between(0, 1).all()


def test_pbip_model_matches_csv_columns():
    """Every column the generated TMDL model reads must exist in its CSV, and vice versa."""
    import re
    import pandas as pd
    from curator import powerbi_project as pp

    pp.build()
    tdir = pp.PBI / f"{pp.NAME}.SemanticModel" / "definition" / "tables"
    for t in pp.TABLES:
        tmdl = (tdir / f"{t}.tmdl").read_text()
        model_cols = re.findall(r"^\t\tsourceColumn: (.+)$", tmdl, flags=re.M)
        csv_cols = list(pd.read_csv(pp.PBI / "data" / f"{t}.csv", nrows=0).columns)
        assert model_cols == csv_cols, t
    rel = (tdir.parent / "relationships.tmdl").read_text()
    assert rel.count("relationship ") == 4

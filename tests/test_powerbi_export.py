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

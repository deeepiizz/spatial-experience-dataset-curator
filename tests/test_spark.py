"""The Spark job must give the same answers as the pandas pipeline.

Runs on the committed data/processed/trials.csv, so it needs no download. Skipped
when pyspark is not installed (``pip install -e ".[spark]"``).
"""

import json

import pandas as pd
import pytest

pytest.importorskip("pyspark")

from curator import pipeline, schema, spark_job as sj  # noqa: E402


@pytest.fixture(scope="module")
def spark():
    s = sj.get_spark("curator-tests", shuffle_partitions=2)
    s.sparkContext.setLogLevel("ERROR")
    yield s
    s.stop()


@pytest.fixture(scope="module")
def sdf(spark):
    return sj.read_trials(spark).cache()


@pytest.fixture(scope="module")
def pdf():
    return pd.read_csv(sj.TRIALS_CSV, dtype=schema.COLUMNS)


def _spark_summary(sdf, **kw) -> pd.DataFrame:
    return pd.DataFrame([r.asDict() for r in sj.summarise(sdf, **kw).collect()])


def test_csv_read_is_lossless(sdf, pdf):
    """Every row, every non-empty cell and every JSON blob survives the Spark CSV reader."""
    back = sdf.toPandas()
    assert len(back) == len(pdf) == 6513
    for c in schema.COLUMNS:
        assert back[c].notna().sum() == pdf[c].notna().sum(), c
    # the JSON columns are the ones with embedded commas and doubled quotes
    for c in ("spatial_features", "participant_extra"):
        assert all(isinstance(json.loads(v), dict) for v in back[c])
    assert back.sort_values("trial_id").trial_id.tolist() == sorted(pdf.trial_id)


def _plain(d: pd.DataFrame) -> pd.DataFrame:
    """Same cells, same missing marker: pandas gives <NA>/NaN where Spark gives None."""
    return d.reset_index(drop=True).astype(object).map(lambda v: None if pd.isna(v) else v)


def test_summary_matches_pandas(sdf, pdf):
    expected = pipeline.summarise(pdf)
    got = _spark_summary(sdf)[expected.columns]
    pd.testing.assert_frame_equal(_plain(got), _plain(expected), check_dtype=False)


def test_summary_matches_committed_file(sdf):
    committed = pd.read_csv(pipeline.OUT_DIR / "source_summary.csv")
    got = _spark_summary(sdf)
    pd.testing.assert_frame_equal(got[committed.columns], committed, check_dtype=False)


def test_readme_numbers(sdf):
    """The within-source results quoted in the README, recomputed in Spark."""
    med = {(r.source_id, r.condition): r.median_time_s
           for r in sj.condition_medians(sdf).collect()}
    assert med["kumar_library_qr", "QR-assisted"] == 161.0
    assert med["kumar_library_qr", "Conventional"] == 360.0

    fl = {(r.source_id, r.which): r.median_time_s for r in sj.first_vs_later(sdf).collect()}
    assert fl["liu_vr_wayfinding", "first"] == 43.9
    assert fl["liu_vr_wayfinding", "first"] > fl["liu_vr_wayfinding", "later"]
    assert fl["mayor_vr_labyrinth", "first"] > fl["mayor_vr_labyrinth", "later"]

    a = {r.road_type: r for r in sj.athens_safety(sdf).collect()}
    lane = a["one-way urban road, 50 km/h, with cycle lane"]
    assert (lane["e-bike"], lane["e-scooter"]) == (5.5, 4.9)
    assert a["one-way urban road, 50 km/h, no cycle lane, sidewalk < 1.5 m"]["walk"] == 4.4


def test_scale_up_keeps_statistics_and_multiplies_counts(sdf):
    base = _spark_summary(sdf).set_index("source_id")
    big = sj.scale_up(sdf, 3)
    assert big.select("trial_id").distinct().count() == 3 * 6513
    scaled = _spark_summary(big).set_index("source_id")
    for c in ("trials", "participants"):
        assert (scaled[c] == 3 * base[c]).all(), c
    for c in ("conditions", "median_time_s", "mean_errors", "mean_rating", "age_known_pct"):
        pd.testing.assert_series_equal(scaled[c], base[c], check_dtype=False)


def test_approximate_summary_is_close(sdf):
    exact = _spark_summary(sdf).set_index("source_id")
    approx = _spark_summary(sdf, exact=False).set_index("source_id")
    for c in ("participants", "conditions", "median_time_s"):
        rel = ((approx[c] - exact[c]).abs() / exact[c]).dropna()
        assert (rel <= 0.02).all(), c


def test_parquet_round_trip(spark, sdf, tmp_path):
    sj.write_parquet(sdf, tmp_path / "t.parquet")
    assert sorted(p.name for p in (tmp_path / "t.parquet").iterdir() if p.is_dir()) == [
        f"source_id={s}" for s in sorted(r.source_id for r in
                                         sdf.select("source_id").distinct().collect())]
    back = spark.read.parquet(str(tmp_path / "t.parquet"))
    assert back.count() == sdf.count()
    assert back.where("source_id = 'liu_vr_wayfinding'").count() == 200

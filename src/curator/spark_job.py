"""The same analyses, written for Spark.

The curated table has 6,513 rows, which pandas handles in milliseconds. This module
exists to show the pipeline's aggregations written the way they would run on a
cluster, checked against the pandas results, and measured on scaled-up copies of
the data (see ``--bench``).

    python -m curator.spark_job                  # summary + analyses, writes Parquet
    python -m curator.spark_job --bench 1 10 100 1000

Runs on a laptop with ``local[*]``. Needs Java 17+ and ``pip install -e ".[spark]"``.
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import time

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F
from pyspark.sql import types as T

from . import schema
from .pipeline import OUT_DIR
from .sources import ROOT

TRIALS_CSV = OUT_DIR / "trials.csv"
SPARK_DIR = ROOT / "data" / "spark"          # not committed

_SPARK_TYPES = {
    "string": T.StringType(),
    "Int64": T.LongType(),
    "Float64": T.DoubleType(),
}
TRIAL_SCHEMA = T.StructType(
    [T.StructField(c, _SPARK_TYPES[t], nullable=True) for c, t in schema.COLUMNS.items()]
)

ATHENS_FEATURES = T.StructType([
    T.StructField("transport_mode", T.StringType()),
    T.StructField("road_type", T.StringType()),
    T.StructField("scenario", T.StringType()),
])


def get_spark(app: str = "curator", shuffle_partitions: int = 8) -> SparkSession:
    return (
        SparkSession.builder.master("local[*]").appName(app)
        # the default of 200 shuffle partitions is tuned for clusters; locally it
        # just adds 200 tiny tasks to every groupBy
        .config("spark.sql.shuffle.partitions", str(shuffle_partitions))
        .config("spark.ui.enabled", "false")
        .config("spark.ui.showConsoleProgress", "false")
        .config("spark.driver.memory", "4g")
        .getOrCreate()
    )


def read_trials(spark: SparkSession, path: pathlib.Path = TRIALS_CSV) -> DataFrame:
    """Read trials.csv with the schema declared up front (no inference pass).

    The JSON columns contain commas and doubled quotes, so quote and escape are both '"'.
    """
    return (
        spark.read.option("header", True).option("quote", '"').option("escape", '"')
        .option("mode", "FAILFAST")
        .schema(TRIAL_SCHEMA).csv(str(path))
    )


# --- the pipeline's per-source summary --------------------------------------

def summarise(df: DataFrame, exact: bool = True) -> DataFrame:
    """Spark version of ``curator.pipeline.summarise``.

    ``F.median`` is exact (interpolates like pandas), and ``bround`` rounds half to
    even like pandas/numpy, so the two summaries can be compared value for value.

    ``exact=False`` swaps the two expensive aggregates for their sketch versions:
    HyperLogLog++ for distinct counts and Greenwald-Khanna for the median. Exact
    distinct counts and medians have to bring every value of a group together;
    the sketches keep a small fixed-size summary per partition and merge those.
    """
    if exact:
        distinct, median = F.countDistinct, F.median
    else:
        distinct = lambda c: F.approx_count_distinct(c, rsd=0.01)
        median = lambda c: F.percentile_approx(c, 0.5, 10_000)
    known = lambda c: F.bround(100 * F.avg((F.col(c) != "unknown").cast("double")), 0)
    return (
        df.groupBy("source_id").agg(
            F.first("environment_type").alias("environment_type"),
            F.first("presentation").alias("presentation"),
            F.first("task").alias("task"),
            distinct("participant_id").alias("participants"),
            F.count(F.lit(1)).alias("trials"),
            distinct("condition").alias("conditions"),
            F.bround(median("outcome_time_s"), 1).alias("median_time_s"),
            F.bround(F.avg("outcome_errors"), 2).alias("mean_errors"),
            F.bround(F.avg("outcome_rating"), 2).alias("mean_rating"),
            known("age_group").cast("long").alias("age_known_pct"),
            known("gender").cast("long").alias("gender_known_pct"),
            F.first("source_licence").alias("licence"),
            F.first("source_doi").alias("doi"),
        )
        .orderBy("source_id")
    )


# --- the README's within-source analyses -------------------------------------

def condition_medians(df: DataFrame) -> DataFrame:
    """Median navigation time per condition, inside each source."""
    return (
        df.where(F.col("task") == "navigation")
        .groupBy("source_id", "condition")
        .agg(F.count(F.lit(1)).alias("trials"),
             F.bround(F.median("outcome_time_s"), 1).alias("median_time_s"))
        .orderBy("source_id", "condition")
    )


def first_vs_later(df: DataFrame) -> DataFrame:
    """Is the first search the slowest? Window over each participant's trials.

    In Liu each participant has four targets in order; in the labyrinth each
    participant x condition has an outbound then a return phase. The window is per
    participant and condition, ordered by trial_index, so both cases are covered.
    """
    w = Window.partitionBy("participant_id", "condition").orderBy("trial_index")
    return (
        df.where(F.col("source_id").isin("liu_vr_wayfinding", "mayor_vr_labyrinth"))
        .withColumn("position", F.row_number().over(w))
        .withColumn("which", F.when(F.col("position") == 1, "first").otherwise("later"))
        .groupBy("source_id", "which")
        .agg(F.count(F.lit(1)).alias("trials"),
             F.bround(F.median("outcome_time_s"), 1).alias("median_time_s"))
        .orderBy("source_id", "which")
    )


def athens_safety(df: DataFrame) -> DataFrame:
    """Mean perceived safety per road type, one column per transport mode.

    The spatial features are a JSON string per row; ``from_json`` parses them into
    columns, then ``pivot`` turns transport modes into columns.
    """
    a = (
        df.where(F.col("source_id") == "tzouras_athens_safety")
        .withColumn("f", F.from_json("spatial_features", ATHENS_FEATURES))
        .select("f.road_type", "f.transport_mode", "outcome_rating")
    )
    return (
        a.groupBy("road_type").pivot("transport_mode", ["car", "e-bike", "e-scooter", "walk"])
        .agg(F.bround(F.avg("outcome_rating"), 1))
        .orderBy("road_type")
    )


# --- scaling -----------------------------------------------------------------

def scale_up(df: DataFrame, copies: int) -> DataFrame:
    """Stack ``copies`` copies of the table, each with its own participants.

    The copies are exact duplicates apart from the IDs, so every median and mean
    stays the same and every count multiplies by ``copies``. That makes the scaled
    output checkable, which random synthetic data would not be.
    """
    if copies == 1:
        return df
    k = df.sparkSession.range(copies).withColumnRenamed("id", "copy")
    suffix = F.concat(F.lit("#"), F.col("copy").cast("string"))
    return (
        df.crossJoin(k)
        .withColumn("participant_id", F.concat("participant_id", suffix))
        .withColumn("trial_id", F.concat("trial_id", suffix))
        .drop("copy")
    )


def write_parquet(df: DataFrame, path: pathlib.Path) -> None:
    """Columnar, compressed, partitioned by source so a source can be read alone."""
    df.write.mode("overwrite").partitionBy("source_id").parquet(str(path))


SUMMARY_COLS = ["source_id", "participant_id", "condition", "environment_type",
                "presentation", "task", "outcome_time_s", "outcome_errors",
                "outcome_rating", "age_group", "gender", "source_licence", "source_doi"]


def _best_of(fn, repeats: int = 2):
    """Run ``fn`` a few times; return (fastest seconds, last result)."""
    best, out = float("inf"), None
    for _ in range(repeats):
        t = time.perf_counter()
        out = fn()
        best = min(best, time.perf_counter() - t)
    return best, out


def bench(spark: SparkSession, scales: list[int], workdir: pathlib.Path) -> list[dict]:
    """Time the per-source summary in pandas and in Spark at several sizes.

    Both read the same Parquet files and only the columns the summary needs, so
    the comparison is the aggregation engine, not CSV parsing. Each timing is the
    best of two runs, after one warm-up query, so JVM start-up is not counted.
    """
    import pandas as pd

    from .pipeline import summarise as pd_summarise

    base = read_trials(spark).cache()
    summarise(base).collect()                        # warm-up
    rows = []
    for n in scales:
        path = workdir / f"trials_x{n}.parquet"
        if not path.exists():
            write_parquet(scale_up(base, n), path)
        size_mb = sum(f.stat().st_size for f in path.rglob("*.parquet")) / 1e6
        scan = lambda: spark.read.parquet(str(path)).select(*SUMMARY_COLS)

        t_exact, exact = _best_of(lambda: summarise(scan()).collect())
        t_approx, approx = _best_of(lambda: summarise(scan(), exact=False).collect())
        # worst relative error of the sketches, over every source and sketched column
        err = max(
            abs(a[c] - e[c]) / e[c]
            for e, a in zip(exact, approx)
            for c in ("participants", "conditions", "median_time_s")
            if e[c] is not None
        )

        def run_pandas():
            pdf = pd.read_parquet(path, columns=SUMMARY_COLS)
            pdf["source_id"] = pdf["source_id"].astype(str)
            pd_summarise(pdf)
            return pdf.memory_usage(deep=True).sum() / 1e6

        t_pandas, pandas_mb = _best_of(run_pandas)

        rows.append({"copies": n, "rows": sum(r["trials"] for r in exact),
                     "parquet_mb": round(size_mb, 1), "pandas_mem_mb": round(pandas_mb),
                     "pandas_s": round(t_pandas, 2), "spark_exact_s": round(t_exact, 2),
                     "spark_approx_s": round(t_approx, 2),
                     "approx_max_rel_err_pct": round(100 * err, 2)})
        print(rows[-1], flush=True)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bench", type=int, nargs="+", metavar="COPIES",
                    help="time pandas vs Spark on this many stacked copies of the table")
    ap.add_argument("--keep", action="store_true", help="keep the scaled Parquet files")
    args = ap.parse_args()

    spark = get_spark()
    spark.sparkContext.setLogLevel("ERROR")
    df = read_trials(spark)

    if args.bench:
        workdir = SPARK_DIR / "bench"
        workdir.mkdir(parents=True, exist_ok=True)
        rows = bench(spark, args.bench, workdir)
        print("\n| Rows | Parquet on disk | pandas in memory | pandas | Spark, exact "
              "| Spark, approx | Approx. error |")
        print("|---:|---:|---:|---:|---:|---:|---:|")
        for r in rows:
            print(f"| {r['rows']:,} | {r['parquet_mb']} MB | {r['pandas_mem_mb']:,} MB "
                  f"| {r['pandas_s']} s | {r['spark_exact_s']} s | {r['spark_approx_s']} s "
                  f"| {r['approx_max_rel_err_pct']}% |")
        if not args.keep:
            shutil.rmtree(workdir)
        return

    for title, out in [("Per-source summary", summarise(df)),
                       ("Median navigation time per condition", condition_medians(df)),
                       ("First vs later search (VR sources)", first_vs_later(df)),
                       ("Athens: mean perceived safety by road type and mode", athens_safety(df))]:
        print(f"\n{title}")
        out.show(200, truncate=False)

    write_parquet(df, SPARK_DIR / "trials.parquet")
    print(f"Parquet written to {SPARK_DIR / 'trials.parquet'}")
    spark.stop()


if __name__ == "__main__":
    main()

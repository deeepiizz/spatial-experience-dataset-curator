# Spatial Experience Dataset Curator

![tests](https://github.com/deeepiizz/spatial-experience-dataset-curator/actions/workflows/tests.yml/badge.svg)

Four open-access studies of how people find their way through spaces and how they rate them,
mapped onto **one trial-level schema** with provenance, licence and demographic metadata on
every row, and a pytest suite that checks every mapping against the raw files.

| | |
|---|---|
| **Trials** | 6,513 |
| **Participants** | 303 |
| **Sources** | 4 Zenodo datasets, all CC-BY-4.0 |
| **Environments** | real library (indoor), two VR environments, urban street images |
| **Tasks** | navigation (time, errors, path length, success) and rating (1–7 perceived safety) |
| **Tests** | 53, including a source-isolation test, checks that rebuild each source's own totals, and pandas-vs-Spark parity |

The combined table is in [`data/processed/trials.csv`](data/processed/trials.csv), with a
per-source overview in [`source_summary.csv`](data/processed/source_summary.csv).

## Why this project

Studies of wayfinding and spatial perception are small, use different measures, and are
published in different formats: one ships raw movement logs, another an Excel workbook with
Spanish column names, another a zip with a data dictionary. Before anyone can ask a question
across them, someone has to decide what a "trial" is in each study, write that down, and prove
the conversion did not lose or invent anything. That is the work this repo does.

## Run it

```bash
pip install -e ".[dev]"
python -m curator.pipeline   # downloads from Zenodo, checks md5 + licence, builds, validates
pytest -v
```

Raw files go to `data/raw/` (not committed). The download step compares each file with the
md5 Zenodo publishes and stops if the licence on Zenodo no longer matches the registry.
CI runs the whole thing on every push and once a week, so a source that changes upstream
shows up as a failing build.

## Common schema

One row = one trial. A column a source did not measure is left empty, never filled in.

| Column | Meaning |
|---|---|
| `trial_id` | `source:participant:condition:index`, unique |
| `source_id`, `participant_id` | participant IDs are prefixed with the source, so they never collide |
| `age_group` | `<18`, `18-30`, `31-40`, `41-50`, `51-65`, `65+`, `unknown` |
| `gender` | `female`, `male`, `unknown` |
| `environment_type` | `indoor`, `urban`, `vr` |
| `presentation` | `physical`, `virtual_reality`, `static_image` (how the space was shown) |
| `task`, `task_detail` | `navigation` or `rating`, plus a plain-language description |
| `condition`, `trial_index` | the study's own condition label, and order within participant |
| `outcome_time_s` | seconds to complete (navigation only) |
| `outcome_errors` | wrong turns / times lost / wrong location levels (see data card) |
| `outcome_success` | 0 / 1 |
| `outcome_rating`, `rating_scale_min/max` | rating and its scale (rating only) |
| `path_length_m` | distance travelled, where tracked |
| `spatial_features` | JSON: layout geometry, wall colour, road type, crossings, traffic density ... |
| `participant_extra` | JSON: VR / game experience, academic group, raw codes kept for audit |
| `source_doi`, `source_licence`, `source_citation` | provenance on every row |

The rules are enforced by `curator.schema.validate`, which the pipeline runs before writing
anything. For example: navigation trials must have a time and no rating, ratings must be inside
their declared scale, errors must be non-negative whole numbers, and every licence must be on
the reuse allowlist.

## How it is tested

The tests follow the same idea as the leakage test in my
[F1 Podium Predictor](https://github.com/deeepiizz/f1-podium-predictor): change something on
purpose and check that only what should change does.

- **Source isolation** (`test_pipeline.py`): reverse every rating in the Athens raw file and
  rebuild. All rows from the other three sources must be byte-for-byte identical, and every
  Athens rating must become `8 − original`.
- **Back to the raw totals** (`test_sources.py`): each source is checked against a number
  recomputed straight from its raw file. The four Liu trial times per participant must add
  up to the time of the last target collection in the movement log. The outbound and return
  phases of each labyrinth run must reproduce the workbook's own `TieTotal` and `DisTotal`. The
  library durations must match the separate `Paired_Data` sheet.
- **Documented quirks are pinned**: for example, the Athens age re-mapping must agree with the
  file's own `young` flag, and the library's 33 contradictory success flags must still number 33.
  If a new version of a source changes these, the test fails and the data card needs updating.
- **The validator is tested too** (`test_schema.py`): ten kinds of broken row, each of which
  must be rejected.

I also checked that the suite catches real bugs. Reapplying the README's own (wrong) Athens age
coding fails the `young`-flag test, and swapping one labyrinth time column fails the totals test.

---

## Data card

### Sources

| Source | Setting | What was measured | Participants | Trials |
|---|---|---|---|---|
| [Liu (2024)](https://doi.org/10.5281/zenodo.10784483) — VR way-finding | Virtual environment, desktop / controller | Time and path length to find each of 4 targets, under 5 guidance conditions (between-subjects); NASA-TLX and experience questionnaire | 50 | 200 |
| [Mayor et al. (2026)](https://doi.org/10.5281/zenodo.18481749) — VR labyrinths | Room-scale VR, walking | Time, distance and times lost going to a goal and back, in Euclidean vs partially non-Euclidean labyrinths with or without coloured walls (within-subjects) | 36 | 352 |
| [Kumar (2026)](https://doi.org/10.5281/zenodo.23080208) — library book finding | Real academic library | Time, success and rack / side / shelf accuracy finding a book, conventional vs QR-assisted (within-subjects, counterbalanced) | 95 | 190 |
| [Tzouras (2025)](https://doi.org/10.5281/zenodo.14967130) — Athens street safety | Images of imagined urban roads | Perceived safety 1–7 for car, e-bike, e-scooter and walking across road designs | 122 | 5,771 |

### How a "trial" was defined per source

- **Liu**: the movement log has a target counter that drops from 4 to 0. One trial runs from
  one collection to the next. Path length is the horizontal (x–z) distance between samples.
- **Mayor**: each participant × condition row has an outbound and a return phase; each phase is
  one trial. Errors are the study's "times lost" (wrong turns found by reversal detection).
- **Kumar**: one book-finding task is one trial. Errors = number of wrong location levels
  (3 − `Accuracy_Score_0_3`).
- **Tzouras**: one rating of one scenario for one transport mode is one trial.

### What I found in the sources

These are all recorded in [`sources.yaml`](sources.yaml) next to the source they belong to.

- **Counts do not match the description.** The Athens record describes 129 respondents and
  5,772 ratings. The file has 122 and 5,771, and 12 respondents have fewer than 48 ratings.
- **A README contradicts its own data.** The Athens README says age code 1 means "under 18",
  but the file's `young` flag marks every code-1 respondent as under 30. I mapped the codes one step down (1 = 18–30) and a test checks this against
  `young`. The README also lists code 3 twice.
- **Success and accuracy disagree.** 33 conventional library tasks are marked "correct book
  retrieved" but scored 0 of 3 for rack, side and shelf. I kept both columns as given.
- **Undocumented conditions.** Liu's five group codes (EDG, CEDG, LMG, CLMG, VG) are not
  explained anywhere in the record. The labyrinth workbook has a fifth condition, `NoEucDoble`,
  that the description does not mention. Both are kept verbatim and flagged.
- **Promised files are missing.** The labyrinth description mentions 10 Hz tracking logs, but
  the record only has the summary workbook. The library dictionary lists `Route_Deviation_m`,
  which is not in the data.
- **Encoding and trailing rows.** Liu's `UserStudy.csv` is not valid UTF-8, and one movement log
  ends with 394 empty sensor rows. The labyrinth sheets end with unlabeled mean rows, which
  would have been read as participants if not dropped.

### What the combined data can support

- Comparing **conditions inside one source**, such as QR vs conventional (median 161 s vs 360 s),
  or Euclidean vs non-Euclidean labyrinths.
- Asking whether **within-study patterns are similar across studies**. One example: in both VR
  sources the first search is the slowest. In Liu, the median is 43.9 s for the first target and
  31–40 s for later ones. In the labyrinth, the outbound path is slower than the return in all five
  conditions. Both fit with people learning the space, though neither study was designed to test that.
- Linking **spatial features to experience** in the Athens data. On 50 km/h roads without a
  cycle lane, e-bikes and e-scooters are rated 2.4–3.0 out of 7, while car and walking stay at
  4.4–5.5. Adding a cycle lane lifts e-bikes to 5.5 and e-scooters to 4.9. A sidewalk under
  1.5 m lowers walking from 5.5 to 4.4.
- Serving as a **template**: a new study needs one adapter, one registry entry and its own
  faithfulness test.

### What it cannot support

- **Pooling outcomes across sources.** A "time" of 35 s to find a virtual target and 230 s to
  find a library book are not the same measure. "Errors" mean three different things.
  Comparisons across sources should be within-source effects, not raw values.
- **Separating environment type from study.** Each environment type comes from only one or two
  studies, so "indoor vs VR" is completely confounded with who ran the study, how and where.
- **Demographic analysis on the library data.** It has no age or gender, only academic group.
  Age is skewed young overall: 72% of trials with a known age come from 18–30 year olds, and nobody is under 18.
- **Learning or order effects in the labyrinth.** The order in which each participant met the
  conditions is not recorded.
- **Real-world urban navigation.** The urban source is ratings of imagined road images, not
  people moving through a city.

### Sources considered and left out

- **MIT Place Pulse 2.0**: I could not confirm the licence on the public mirror, and it holds
  pairwise image votes rather than per-participant trials.
- **Frankfurt street safety / attractiveness (Zenodo 7712811)**: CC-BY-2.0 and aggregated per
  location, so it has no participant-level trials.
- **Hang Hau wayfinding (Zenodo 23645342), building evacuation (Zenodo 24051997)**: the records
  hold only a PDF.

### Licence

Code: MIT. The combined dataset is adapted from CC-BY-4.0 sources and shared under CC-BY-4.0,
with each row citing its source. See [`data/processed/LICENSE.md`](data/processed/LICENSE.md).
The original authors have not endorsed this compilation.

## Big data: the same pipeline in PySpark

The combined table has 6,513 rows, so it does not need Spark. I wrote
[`spark_job.py`](src/curator/spark_job.py) to practise the Spark version of the same
work on data I can check, and to measure where the switch starts to pay off.

```bash
pip install -e ".[dev,spark]"      # needs Java 17+
python -m curator.spark_job        # summary + README analyses in Spark, writes Parquet
python -m curator.spark_job --bench 1 10 100 1000 3000
```

**What it does.** It reads `trials.csv` with a declared schema instead of inferring one. It
rebuilds the per-source summary and the README's numbers. A window function finds each
participant's first search, `from_json` parses the Athens road features, and `pivot` puts
the transport modes into columns. The table is written as Parquet, partitioned by source.

**How it is checked.** `tests/test_spark.py` (7 tests) asserts that the Spark summary
equals `pipeline.summarise` and the committed `source_summary.csv` cell for cell, and that
the README's numbers come out the same. Getting the summary to match exactly needed two
fixes: `bround` instead of `round`, because pandas rounds half to even, and the exact
`median`, which interpolates like pandas does.

**Scaling it up.** The benchmark stacks copies of the table. Each copy gets new participant
IDs and keeps the same values. So every median and mean must stay the same, and every count
must grow by the number of copies. A test checks this, so the large runs can be verified,
which random synthetic data would not allow. The summary was timed on one 4-core,
15 GB machine (Spark `local[*]`). Each time is the best of two runs, after a warm-up.

| Rows | Parquet on disk | pandas in memory | pandas | Spark, exact | Spark, approx. |
|---:|---:|---:|---:|---:|---:|
| 6,513 | 0.1 MB | 1 MB | 0.02 s | 0.56 s | 1.48 s |
| 651,300 | 3.7 MB | 152 MB | 0.24 s | 2.28 s | 1.64 s |
| 6,513,000 | 51 MB | 1.5 GB | 2.6 s | 26.6 s | 6.0 s |
| 19,539,000 | 189 MB | 4.6 GB | 11.3 s | 97.5 s | 15.6 s |

What I took from it:

- **On one machine, pandas wins at every size I tried.** Spark has fixed costs that pandas
  does not: scheduling tasks, shuffling data between them, and running a JVM next to
  Python. Those costs only pay back once the work is spread over several machines.
- **pandas runs out of memory, Spark does not.** pandas needs about 235 bytes per row
  in memory, so on this 15 GB machine it would run out at around 60 million rows.
  That is an estimate from the table above, not a run. Spark reads Parquet in chunks and
  writes to disk when memory fills, so its limit is the disk, and on a cluster, the
  number of machines.
- **Exact distinct counts and medians are the slow part.** `explain()` shows that two
  `countDistinct`s in one `groupBy` make Spark copy every row three times, once per
  distinct column. An exact median has to bring every value of a group together in one
  place. With `approx_count_distinct` and `percentile_approx` (`summarise(exact=False)`),
  the 19.5M-row summary drops from 97 s to 16 s. The cost is that counts and medians are
  off by up to 1.3%. For example, the library has 95 participants and the approximate
  count says 94. Its median is 230 s and the approximate one is 227 s, because
  `percentile_approx` returns a real value from the data instead of the midpoint of the two middle values.
  For a data card I would keep the exact numbers. For monitoring a large table, I would use
  the approximate ones.

## Power BI dashboard

[`powerbi/`](powerbi/) has the combined data as a star schema (one fact table, three dimensions
and a data-quality table), every DAX measure, and a page-by-page build guide for a four-page
report: overview, navigation, perceived street safety and data quality. The guide ends with the
numbers each visual should show, so the finished report can be checked against the pipeline.

## Project layout

```
sources.yaml                 registry: DOI, licence, trial definition, known issues
src/curator/schema.py        common schema + validator
src/curator/sources.py       verified Zenodo download
src/curator/adapters/        one adapter per source
src/curator/pipeline.py      build -> validate -> write data/processed/
src/curator/powerbi_export.py  star schema for Power BI -> powerbi/data/
src/curator/spark_job.py     the same summary and analyses in PySpark, + benchmark
powerbi/                     DAX measures and dashboard build guide
tests/                       schema, per-source faithfulness, isolation, Spark parity
```

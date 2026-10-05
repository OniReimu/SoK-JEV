# SoK-JEV

Code, data and results for the paper

> **SoK: Semantic Decision Engines in Network Control Loops**
> Delong Li, Chen Li, Xu Wang, Haochen Gong, Rui Lang, and Guangsheng Yu. University of Technology Sydney (UTS).

The SoK codes 139 paper families by decision interface, execution path and check ownership, and audits reporting evidence with 50 loop claims and 4 matched claims. Bounded fixed-action tests on transport and edge stacks separate interpretation time from execution and verification.

Related code and datasets: [Edge-Computing-JEV](https://github.com/OniReimu/Edge-Computing-JEV) and [6G-JEV](https://github.com/OniReimu/6G-JEV).
Data: [SoK-JEV on Hugging Face](https://huggingface.co/datasets/OniReimu/SoK-JEV).

| Content | Location |
|---|---|
| Offline reproduction and fixed-action code | `studies/sok/`, `scripts/`, `experiments/EXP-023-decision-path-intervention/` |
| Comparison figures and tables | `paper_assets/` |
| Companion CSV and JSON | `supplement/` |
| Literature extension code, codebooks, aggregates | `literature-review/` |
| Six frozen archives | HF `data/`, downloaded into `studies/sok/data/` |
| Literature retrieval and coding records | HF `runs/literature-review/`, downloaded into `runs/literature-review/` |

## Quick start

Run in the repository root. `prepare` needs about 1.2 GB and a new `--work` directory each time. The download tool preserves repository-relative paths: HF `data/analysis.tar.gz` with `--local-dir studies/sok` lands at `studies/sok/data/analysis.tar.gz`.
Install the Hugging Face CLI separately for the two download commands. All analysis commands after download are offline.

```bash
uv venv --python 3.12
uv pip install -r requirements/analysis.txt
hf download OniReimu/SoK-JEV --repo-type dataset --include "data/*" --local-dir studies/sok
hf download OniReimu/SoK-JEV --repo-type dataset --include "runs/*" --local-dir .
.venv/bin/python -m pytest literature-review/scripts/tests -q
.venv/bin/python studies/sok/reproduce.py verify
.venv/bin/python studies/sok/reproduce.py prepare --work artifacts/reproduction
.venv/bin/python studies/sok/reproduce.py check-records --work artifacts/reproduction
.venv/bin/python studies/sok/reproduce.py figures --work artifacts/reproduction
.venv/bin/python studies/sok/reproduce.py tables --work artifacts/reproduction
bash literature-review/rebuild.sh
```

The steps check the following:

- Tests report `8 passed` for the offline recall functions.
- `verify` checks all six archive hashes and their members. Its output is `{"status": "PASS_DATA_PACKAGE", "files": 15388, "expanded_bytes": 1051754963}`.
- `prepare` extracts and copies inputs into the new work directory. It prints `Prepared isolated reproduction workspace:` followed by the absolute path to `artifacts/reproduction`.
- `check-records` prints `PASS: 111372 normalized fixed records reconstructed exactly` and `PASS: 2,400 physical executions and all 84 queue timelines`. Its queue check reports `PASS_QUEUE_TIMELINE_CHECK` for 166,432 records and 84 cells.
- `figures` prints `PASS: 40 figure hashes matched`. The last step checks the other 7 files, giving 47 figure files byte-identical in total.
- `tables` prints `PASS: 539 numeric table rows; authored prose preserved`. Those rows occur in 26 tables. Two coding table bodies also match. Three authored tables have no checked numeric rows.
- `rebuild.sh` prints `PASS: 13 results, 7 figures, 3 tables byte-identical`. All extension outputs go into `out/literature-review/`.

## Paper element -> how it is checked

| Paper element | How it is checked |
|---|---|
| Data figures | 45 files are byte-identical, including the 7 checked by `literature-review/rebuild.sh` |
| Conceptual figures | `control-boundary.pdf` and `control-boundary.svg` are byte-identical renderings of an authored diagram |
| Numeric tables | 539 numeric rows in 26 tables match the regenerated rows |
| Coding tables | Bodies of `coding-categories.tex` and `coding-agreement-options.tex` match after comment removal |
| Literature-review tables and figures | 3 tables and 7 figure files match byte-for-byte through `literature-review/rebuild.sh` |
| Authored literature map | `literature-map.tex` is authored and has no checked numeric rows. `literature-map-new-families.tex` is an authored input |
| Authored review protocol | `review-protocol.tex` is authored and has no checked numeric rows |
| Authored screening table | `screening.tex` is authored and has no checked numeric rows. The screening figure is rebuilt separately |
| Authored systematization rows | `systematization-new-families.csv` is an authored input. Its rows and the literature map are not claimed as regenerated |

See `literature-review/README.md` for the review stages and offline scope.

## Repository layout

```text
studies/sok/                 Frozen package metadata and reproduction entry point
scripts/sok_*.py             Frozen analysis and rendering code
experiments/EXP-023-decision-path-intervention/
paper_assets/{figures,tables}/
supplement/
literature-review/{scripts,codebooks,results}/
requirements/analysis.txt
```

## What is not included

Paper PDFs and full texts are omitted for copyright reasons. Raw radio traces are in 6G-JEV at the revision described in `studies/sok/data/README.md`.

Code: MIT (`LICENSE`). Released data and results: CC BY 4.0 (`LICENSE-DATA`). Third-party materials in the frozen archives retain their original terms.

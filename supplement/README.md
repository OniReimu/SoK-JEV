# Supplementary data

Companion data for *SoK: Semantic Decision Engines in Network Control Loops*. The manuscript and appendices contain the methods, literature map,
definitions and results. These files support record-level inspection and reuse.

| File | Contents |
| --- | --- |
| `systematization.csv` | 139 paper families: interfaces, workflows and check responsibilities |
| `coding-families.csv` | Adjudicated coding for the 132 families of the initial screen |
| `coding-scopes.csv` | 405 evidence scopes: 374 step definitions and 31 linked scopes |
| `coding-sources.csv` | 138 source/version records linked to bibliographic entries |
| `cells.csv` | 497 task-condition summaries |
| `contrasts.csv` | 239 matched condition contrasts |
| `online.csv` | 151 execution summaries |
| `timing.csv` | 580 task, deployment and collection-batch timing strata |
| `loads.csv` | 83 native load conditions |
| `physical-paths.csv` | 131 measured execution-path summaries |
| `delay-results.csv` | 176 rows: 8 sparse, 24 controlled-load and 144 empirical-replay conditions |
| `radio-modes.csv` | Radio-policy mode comparisons |
| `radio-controls.csv` | Radio-control comparisons |
| `radio-workflows.csv` | Radio interpretation and control-workflow comparisons |
| `radio-eligibility.csv` | Eligibility and direction summaries across radio conditions |
| `radio-comparisons.json` | Radio statistical comparisons and sensitivity analyses |
| `radio-runs.csv` | Radio-simulation run summaries |
| `radio-unavailable.json` | Unavailable radio analyses and their recorded reasons |

CSV files retain task, condition, method, deployment and collection-batch
identifiers. JSON-encoded columns hold intervals, denominators and statistical
metadata. Empty values denote missing or inapplicable measurements. Identifier
and `source_pointer` columns retain stable provenance keys.

In `systematization.csv`, S denotes selection, G generation, C deterministic
computation and U an unspecified interface. A family may have several interfaces.
`NE` marks unresolved check responsibility. `workflow` and the three `*_check`
columns provide short labels; `*_detail` and `evidence_note` provide extended
descriptions and qualifications. The PDF orders families by reference number;
the CSV uses stable family identifiers.

Join `family_id` and `scope_ids` to the `group` and `id` columns in
`coding-scopes.csv`. Join `source_record_ids` to `record_id` in
`coding-sources.csv` for source URLs, evidence locations and hashes. These
joins cover the 132 families of the initial screen. The seven families added by
the second screening (`Q006`, `Q010`, `Q060`, `Q077`, `Q085`, `Q090` and `Q109`)
and their 24 scopes are coded in the literature-review records of the code release. The three-axis synthesis
and the independent 18-field coding remain distinct.

Radio summaries retain their native denominators, time-block intervals and
sensitivity analyses. Delay experiments distinguish physical sparse executions
from real queues followed by measured execution-time replay.

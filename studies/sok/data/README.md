# Data for the current SoK

Six compressed archives preserve selected analysis inputs as original bytes and paths. `../package.json` records archive sizes and SHA-256 hashes. Each archive starts with `DATA-MANIFEST.json`, listing every member, size and hash. `verify` checks every member; `prepare` checks again while writing a fresh isolated workspace.

| Archive | Contents |
| --- | --- |
| `analysis.tar.gz` | Frozen estimates, 111,372 normalized fixed records, source manifests and numeric table baselines |
| `fixed-workloads.tar.gz` | Selected contract, policy, placement and forwarding request records and fixtures |
| `network-workloads.tar.gz` | Network task inputs, responses, timing and execution ledgers selected by source manifests |
| `network-source.tar.gz` | Recorded network-suite Python/C++ code, tests, configuration and licenses |
| `coding.tar.gz` | Final coding, two aligned independent coding records, scope boundaries, agreement input, family view and eligibility |
| `interventions.tar.gz` | Frozen scenes/images/code, 2,400 physical executions and all 166,432 records in 84 FIFO queues |

Fixed synthesis contains 497 cells, 239 matched contrasts and 151 execution summaries. Timing adds 4,800 bundled-request records for 116,172 records and 580 strata. Load replay analyzes 126,588 post-warmup arrivals; warmup remains included. Failed endpoints and all-arrival denominators are preserved.

Literature coding covers 132 included families, 138 source/version records and 405 evidence scopes. Six original coding JSON inputs are supplied; `prepare` builds the ZIP layout expected by the unchanged analyzer. The archive omits intermediate adjudication history and paper PDFs. Recomputed provenance metadata consequently lists the supplied subset; coding values and original input bytes are preserved. Source URLs and evidence locations remain in companion CSVs.

Radio closed-loop comparisons include published run summaries, statistical tables and simulator source. The full trace collection is available from the [dataset at the recorded revision](https://huggingface.co/datasets/OniReimu/6G-JEV/tree/d096f368f054b1473fa792e243e88407be383d47); this is the revision recorded in the included source manifest. The approximately 19 GB full radio raw-output collection is outside this checkout. Redrawing these comparisons is supported; recomputing them from per-UE/time traces requires that raw collection and the recorded ns-3/5G-LENA environment. Older execution appendix tables retain complete cell ledgers; their full original execution logs also remain outside this package.

Verification and plot generation are offline. Credentials, local kubeconfigs, model weights and large transport command logs are excluded. Original model names, batch labels and source locators remain in the data.

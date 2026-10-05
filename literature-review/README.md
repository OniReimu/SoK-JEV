# Literature-review extension

Run from the repository root after the top README Quick start. The initial 132-family coding remains frozen. The blind second screening added 7 families, yielding 139 families, 429 scopes and 393 new-step scopes (`results/corpus-139-metrics.json`). The four headline family counts are 50 loop claims, 4 matched claims, 9 p95+ reports and 4 deadline-attainment reports.

## Review stages

1. Search recall check on OpenAlex. The run found 966 unique works, with 119 matches to the corpus and 847 new hits (`runs/literature-review/recall/dedup_summary.json`).
2. Title/abstract screening of new hits. Two coders screened the 847 hits and retained 594 includes (`results/screening-final.json`).
3. Sampled coverage audit. The audit drew 100 records, 50 per stratum, with seed 42 before access checks. It coded 98 records, with 77 eligible and 2 eligibility-unresolved (`results/coverage-audit-summary.json`). The weighted estimates are 32.4% for loop claims, 6.5% for matched claims, 5.3% for p95+ reports and 2.6% for deadline attainment.
4. Blind second screening of the 111 records the original screen set aside. It sent 24 records to full-text eligibility and added 7 agreed eligible families, with 2 split records (`results/q2-second-screening.json` and `results/q2-fulltext-eligibility.json`). The folder name `q2/` means second screening. Independent coding of the new families agrees on 114 of 126 fields (`results/new-families-summary.json`).
5. Taxonomy double-coding against the published literature map. Two independent coders and a blind mapping of published cells are compared over the 129 non-pilot families (`results/taxonomy-*.json`). Codebooks are in `codebooks/`. Full-text reading copies are omitted.

OpenAlex retrieval, abstract retrieval, full-text retrieval and model coding are not rerun offline. The published-map outputs are released. Generating new mappings requires network access and model calls. The recall script has no offline command. Its pure deduplication functions can rebuild hits from released per-query JSONL. Matching additionally requires the historical bibliography/catalogue, which are not shipped. Systematization rows and the new-family literature-map fragment are author-written inputs.

## Rebuild commands

```bash
bash literature-review/rebuild.sh
```

Outputs go into `out/literature-review/` and are compared with shipped targets without overwriting them.
The script uses `artifacts/reproduction` and accepts an optional Python path as its first argument, defaulting to `.venv/bin/python`. Input directories are copied into a fresh folder under `out/literature-review/` for scripts that write beside their inputs. Successful completion prints `PASS: 13 results, 7 figures, 3 tables byte-identical`. The regenerated audit sample and new-family decisions are also compared with their released records.

`e0_paired_counts.py` recounts coverage-audit independent agreement and second-screening full-text eligibility. Only the two codes `N/A` and `N/A (no claim)` are treated as the same audit answer. All five stored agreement counts match exactly: 89, 59, 70, 83 and 88. Both JSON outputs reproduce the stored formatting byte-for-byte, including the absence of a trailing newline. The coverage agreement uses compact JSON and the full-text summary uses one-space indentation.

The frozen package preserves 132-family rates in the audit's `corpus` comparison field. Corrected rates appear in `corpus-139-metrics.json`. The authored literature-map fragment and systematization rows are listed as authored rather than counted among the 13 regenerated results.

77 abstracts longer than 3,000 characters, which contain full-text sections in the index, are omitted. Every released JSON/JSONL abstract longer than 3,000 characters is replaced by `[omitted: indexed abstract longer than 3,000 characters]`.

The seven families added by the second screening and their 24 scopes are in `runs/literature-review/q2/nf/new_families_final.jsonl`.

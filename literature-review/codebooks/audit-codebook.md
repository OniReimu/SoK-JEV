# Coverage-audit full-text codebook (EXP-2026-004)

Version `AUD-1.0-20261005`. Applies to the 100 sampled OpenAlex includes (`audit_sample.jsonl`). Frozen before
coding. The four evidence fields reuse the E0-1.0 definitions verbatim (`paper/tables/review-protocol.tex`,
Table `tab:e0-codebook`); the eligibility step reuses the screening codebook `SCR-1.0-20261005`.

## Unit

One sampled record, read from its full text (`fulltext_txt/<screen_id>.txt`, extracted from the retrieved PDF).
Read the methods, evaluation and any appendix. A record that reports several decision tasks is coded once at the
record level: a field is positive when any network decision task in the record meets the criterion.

## Step 1: full-text eligibility

`eligible` = the full text reports a primary study (system, method, benchmark, measurement study or explicitly
described conceptual design) in which a semantic decision engine (language model, natural-language processing of
operator input, or explicit intent / high-level-objective processing) produces, selects or checks an identifiable
network configuration, orchestration or diagnostic decision. Latency measurement and positive results are not required.
Otherwise `background` (survey, tutorial, position paper, knowledge benchmark, non-network configuration) or
`exclude` (no such decision). Version of another record: note the other screen_id in `note`. Fields 2-5 are coded
only for `eligible` records and are `N/A` otherwise.

## Step 2: evidence fields (E0-1.0 definitions)

| Field | Positive criterion | Categories |
|---|---|---|
| `explicit_loop_claim` | An explicit control-loop class or time-budget claim for the decision step. | RT/fast; near-RT; non-RT; other budget or multiple loops; not stated; unclear; N/A |
| `supported_loop_claim` | A measurement supports the claimed budget at the corresponding execution boundary. | matched; mismatch; insufficient evidence; N/A (no claim) |
| `tail_latency` | A latency quantile at p95 or higher. | reported; not reported; unclear; N/A |
| `deadline_attainment` | The fraction or count attaining an explicit deadline. | reported; not reported; unclear; N/A |

`not reported` means the methods, evaluation and appendices supply no explicit report. `unclear` means the
description does not resolve the category. `N/A` marks an inapplicable measurement (for example a conceptual design
with no evaluation for the timing fields).

## Output (JSON Lines, one object per coded record)

Only records with a retrieved full text receive a coding row. Access status for all 100 draws lives in
`retrieval_log.jsonl`, the complete manifest; the analysis joins coding rows against it, and every draw without a
coding row enters the bounds analysis as inaccessible.

```json
{"screen_id": "S0003", "eligibility": "eligible|background|exclude", "explicit_loop_claim": "...", "supported_loop_claim": "...", "tail_latency": "...", "deadline_attainment": "...", "evidence": "<= 40 words: section/page locator and quoted phrase for each positive or claim field", "note": ""}
```

## Reconciliation

Disagreements on eligibility or any field are reconciled once by exchanging rationales, as in screening. Remaining
splits are reported as unresolved and enter the bounds analysis on both sides.

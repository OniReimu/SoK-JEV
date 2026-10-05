# Title/abstract screening codebook (EXP-2026-004 Q1)

Version `SCR-1.0-20261005`. Applies to the 847 OpenAlex recall hits not matched to the existing 250 records.
Frozen before coding; not revised after any coder output is read.

## Unit and inputs

One record = one OpenAlex work (merged across DOI/arXiv/title duplicates). The coder sees `screen_id`, title,
year, publication type, venue and abstract (empty for 126 records where OpenAlex has none). The coder sees no other
coder's output and no decision from the original corpus.

## Decision

The criterion combines the review scope ("semantic and intent-based decision making for network configuration,
orchestration, and diagnosis", `paper/sections/review-method.tex`) with the eligibility paragraph of
`paper/tables/review-protocol.tex` (identifiable network decision; conceptual designs and studies without latency
measurement remain eligible; mixed-domain studies contribute their network tasks). The existing corpus applies the
same scope: its eligible records without language-model terms are intent-based systems or configuration synthesis
from network-wide objectives.

Exactly one of:

- **include** — proceed to full-text eligibility. The record reports a primary study (system, method, benchmark,
  measurement study, or an explicitly described conceptual design) in which a *semantic decision engine* produces,
  selects or checks an identifiable network decision of type configuration, orchestration or diagnosis.
  - Semantic decision engine: a language model (LLM, SLM, agent built on one), natural-language processing of
    operator input, or explicit intent / high-level objective processing (intent translation, intent refinement,
    intent-based configuration synthesis from network-wide objectives, intent conflict resolution, intent assurance
    that triggers a decision).
  - Configuration: device or network-wide configuration, routing/ACL/policy synthesis or update, SDN/P4 programs,
    RAN parameter setting. Orchestration: service, slice or network-function deployment, placement, scaling and
    resource allocation. Diagnosis: fault detection with localization, troubleshooting, root-cause analysis,
    misconfiguration finding, repair proposal.
  - Mixed-domain studies are included when one network task is identifiable.
  - Latency measurement and positive results are **not** required.
- **background** — related to semantic decision making for networks or configuration but not a primary network
  decision study: surveys, tutorials, position or vision papers with no specific decision task; telecom LLM knowledge
  or question-answering benchmarks with no operational network decision; language-model configuration of general
  (non-network) software systems; platform papers evaluated only on generic deployment.
- **exclude** — no identifiable network configuration, orchestration or diagnostic decision by a semantic decision
  engine. Examples: traffic, resource or failure *prediction* with no resulting configuration, orchestration or
  diagnostic decision; intent or language processing in domains unrelated to networks or system configuration;
  errata, editorials, front matter, datasets without a study. Language of publication is not a criterion.

## Uncertainty rule

When the title and abstract do not settle the decision between include and the other two, code **include** (the
full-text stage resolves it). With an empty abstract, code exclude only when the title alone places the record outside
networking or outside configuration/orchestration/diagnosis.

Dissertations, books and book chapters are judged on content like any other record and flagged in `note`.

## Output (one JSON object per line, one line per input record, same order)

```json
{"screen_id": "S0001", "decision": "include|background|exclude", "task": "configuration|orchestration|diagnosis|multiple|none", "reason": "<= 25 words citing the title/abstract evidence", "note": ""}
```

`task` is `none` for exclude. `note` is free text for flags (dissertation, possible version of another record,
title-only), otherwise empty.

## Reconciliation

Records on which the two coders differ in `decision` go to reconciliation: each coder receives the other's reason
and the record, and returns a final decision with a one-line rationale. Records still split after one exchange are
coded include (resolved at full text). Agreement is reported before reconciliation (exact agreement, Cohen's kappa,
Gwet's AC1 over the three decisions, and over include vs not-include).

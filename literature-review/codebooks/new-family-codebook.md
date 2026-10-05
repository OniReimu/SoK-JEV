# New-family coding brief (EXP-2026-004, Q2 corpus correction)

Version `NF-1.0-20261005`. Applies to the 7 records that the Q2 second screen found eligible at full text (Q006,
Q010, Q060, Q077, Q085, Q090, Q109). Codebook: E0-1.0 unchanged. Frozen before coding.

## Sources of the definitions (read all three)

1. `paper/tables/review-protocol.tex`: the "Evidence Definitions" subsection and Table `tab:e0-codebook` (positive
   criterion per field), and Appendix `app:e0-c1` "Load and Stability Definitions" (the adjudicated definitions;
   apply them as written).
2. The field options and coding rules below, translated from the E0-1.0 codebook in the frozen data package.
3. The full text at `experiments/EXP-2026-004/runs/q2/fulltext_txt/<id>.txt`.

## Coding rules (E0-1.0, translated)

- A coding unit (scope) is a work, task and decision step together with the evidence range used. Models, prompts and
  repeated runs do not create new units; split only when the output or the measurement boundary differs.
- A paper can contain several decision steps. Do not assign a whole-paper aggregate value to every step. A shared
  call's cost or latency is recorded once and the sharing is stated in the evidence.
- Different versions or implementations of the same step with different answers become an additional scope with
  `relation = same_step_scope` and `parent` = the step's first scope; otherwise `relation = new_step`.
- `not_reported` = the methods, evaluation and relevant appendices were checked and contain no explicit report.
  `unclear` = a description exists but does not settle the category. `na` = the question does not apply to the step;
  say why. Absence from an excerpt is not absence from the full text.
- Timing fields (endpoint, denominator, tail, deadline) concern latency/timeliness evaluation of the current unit. With
  accuracy evaluation only and no latency metric: endpoint `not_reported`, denominator may be `na`; tail and deadline
  are still judged on whether a corresponding report exists.
- endpoint may select several end events; name each metric in the evidence. Do not infer the endpoint from the task
  name. Model return, configuration dispatch, network effect and service result are judged separately.
- baseline compares against a non-learning method; an optimizer, guard or solver used only as an internal module of the
  proposed method is not a comparator. Negative or non-significant comparisons count as a comparison.
- loop_match compares only an explicitly claimed loop budget with the actual measurement boundary. Without a judgeable
  time limit or a corresponding measurement, choose `insufficient`. Average model latency does not prove a complete
  closed loop meets its budget.
- deployment and roundtrip concern where inference/decision computation runs and whether its network round trip is in
  the reported latency. Training hardware is not inference hardware. Non-model steps may be `na`.
- format, semantic and final_state are judged separately: accuracy, syntactic legality and the actual network/service
  outcome are different things. `not_reported` does not mean not implemented.
- code and data record public pointers given in the paper; a link is not a verification of access or licence.
- Each coder codes alone. Initial answers are kept unchanged for field-level agreement; answers after the disagreement
  discussion are stored separately and never overwrite the independent answers. Steps that differ in structure are
  aligned first, and the fields affected by the realignment are rechecked independently before comparison.
- Proportions and agreement are not computed by the coders. Versions of the same work and several scopes of the same
  step are not independent samples; intervals are clustered by paper family.

## Fields and options (single choice unless marked multi)

| Field | Options |
|---|---|
| endpoint (multi) | model, dispatch, network, service, other, not_reported, unclear, na |
| denominator | all, success, other, mixed, unclear, na |
| tail, deadline, load, queue, stability, baseline | yes, not_reported, unclear, na |
| loop_claim | rt, near_rt, non_rt, other, not_stated, unclear, na |
| loop_match | matched, mismatch, insufficient, na |
| deployment (multi) | hosted, gpu, edge, cpu, other, unclear, na |
| roundtrip | included, excluded, unclear, na |
| format, semantic, final_state | reported, explicit_no, not_reported, unclear, na |
| gate_separation | three, partial, no, unclear, na |
| code, data | public_link, on_request, explicit_no, not_reported, unclear, na |

Multi-select fields are JSON lists; all others are strings.

## Task group

`task_group`: the network task types the family's decision steps address, a non-empty subset of
`["configuration", "orchestration", "diagnosis"]`.

## Output

One JSON object per family, written as JSON Lines in the listed order:

```json
{"family": "Q010", "task_group": ["orchestration"],
 "units": [{"uid": "Q010-U1", "task": "...", "step": "...", "scope": "section locator and what is covered",
            "relation": "new_step", "parent": null,
            "answers": {"endpoint": ["model"], "denominator": "...", "tail": "...", "deadline": "...", "load": "...",
                        "queue": "...", "stability": "...", "baseline": "...", "loop_claim": "...", "loop_match": "...",
                        "deployment": ["..."], "roundtrip": "...", "format": "...", "semantic": "...",
                        "final_state": "...", "gate_separation": "...", "code": "...", "data": "..."},
            "evidence": {"<field>": "<= 30 words with locator, for every field except not_reported; every na states why it does not apply"}}]}
```

## Reconciliation and final values

Each coder writes to its own file once; these independent outputs are never edited. Units are aligned by task and step;
fields affected by realignment are rechecked independently. Field disagreements are reconciled once by exchanging
rationales, and the reconciled answers are written to separate files. Every field still split after reconciliation is
listed with both coders' values. A split that changes the family-level indicator (one coder positive, the other not)
takes the final value `unclear` (the corpus category for an undecided description); a category-level split with the same
family-level positivity keeps one coder's categories (coder B) and is reported as unresolved at category level. Every indicator affected by an unresolved split is reported with a lower bound (split counted
non-positive) and an upper bound (split counted positive). Family-level values follow the corpus rule: a family is
positive on a field when at least one of its scopes is positive. Agreement on the new families is reported as its own
stratum and is not pooled with the human-coded agreement of the 132 families.

The three-axis systematization row for each new family is author synthesis, as for the existing 132 (the paper states
that the agreement coefficients apply to the 18-field audit only). It is drafted from the reconciled units and the
full text and checked against both coders' evidence.

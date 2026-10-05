# Taxonomy reliability codebook (EXP-2026-004 Q4)

Version `TX-1.0-20261005`, frozen after the 10-family pilot (clarifications marked *Pilot*). Applies to all 139 corpus families. The axes are
those of `paper/sections/systematization.tex` §"Three Axes"; this codebook only makes them codable.

## Unit and inputs

One paper family, read from `runs/taxonomy/text/<family_id>.txt` (all source versions of the family, separated by
`===== NEXT SOURCE =====`). Code the network decision tasks the family reports (configuration, orchestration,
diagnosis); ignore unrelated background material. A family with several tasks is coded once: a field records every
value that applies to at least one of its network decision tasks.

## Axis 1: decision interface (multi-select)

Who or what produces the network decision, and in what form.

- `S` selection: the engine chooses among an enumerated or permitted set of candidates (templates, tools, actions,
  catalog entries, ranked hypotheses), including choosing to reject or escalate when allowed.
- `G` construction: the engine generates free-form output not restricted to a fixed candidate list (configuration text,
  code, policy, plan, structured intent).
- `C` deterministic computation: a rule, solver, optimizer, verifier or algorithm computes the decision or a decisive
  part of it from formalized inputs.
- `U` unspecified: the paper does not describe how the decision is produced.

Select every letter that applies to a decision-producing component. Do not code `C` for a check that only validates an
output (that belongs to Axis 3), nor for model training. The `engine` is the decision-producing component.

## Axis 2: execution path (two fields)

`path` (single choice), when the decision is taken:

- `offline`: the decision prepares artifacts before operation (synthesis, planning, design, dataset or model
  construction) and is not taken per arriving request.
- `request_driven`: the decision is taken in operation for each arriving request, intent, event or fault.
- `both`: the family reports both kinds of decision.
- `unclear`: the description does not settle it.

`roles` (multi-select), the functional role of the component that consumes the decision output:

- `intent_handler`: translates an operator or business intent for a downstream system.
- `config_synthesis`: compiles, synthesizes, translates or repairs device or network configuration.
- `controller`: an SDN, RAN or device controller, service or infrastructure orchestrator, scheduler or admission
  controller that applies the decision to network or compute resources.
- `assurance`: monitoring, diagnosis, troubleshooting or repair of a running network.
- `planning`: network planning, design or optimization that is not applied per request.
- `policy_agent`: a learned or language-model policy that acts on the environment directly.
- `other`.

*Pilot.* Code only the roles of the components that directly receive the engine's output; do not add roles for
upstream inputs or for later stages. Use `intent_handler` only when the output is an interpreted intent passed to
another system; an engine that turns intent into configuration is `config_synthesis`. Use `assurance` whenever the
task is monitoring, diagnosis or repair of a running network, whoever applies the action. Use `policy_agent` only
when the engine's output is itself the action on the environment, with no named receiving component.

## Axis 3: check responsibility (three check types)

For each check type, code every component that performs it, or `NE` when no component in the reported design or
evaluation performs it.

- `observation`: reconciling the observed state that decisions use (freshness, versioning, contradictory or stale
  observations, snapshot of current state). It counts before the decision and also after an action takes effect, when
  desired and runtime state are compared or drift is reconciled for the next decision.
- `feasibility`: evaluating whether the chosen or generated action satisfies the task's joint constraints (resources,
  conflicts, syntax and semantic validity against the network, policy constraints) before or at execution.
- `coverage`: detecting that no acceptable candidate or solution exists and responding (reject, escalate, report
  infeasible, request new candidates).

Each performing component is one object with four fields:

- `component`: the name the paper gives it (for example "Batfish", "scheduler", "LLM validator"), at most six words.
- `owner`: who it is. `engine` (the decision-producing component itself, whether a language model, learned policy or deterministic solver), `separate_model` (a
  language model or learned validator other than the engine), `controller` (controller, orchestrator, scheduler or state manager logic),
  `tool` (a verifier, solver, parser, simulator or testbed that does not produce the decision), `human` (operator), `other`.
- `mechanism`: how it checks. `model_judgment`, `deterministic` (parser, validator, solver, rule), `execution_test`
  (emulation, dry run, testbed execution, probing), `formal` (formal verification or proof), `human_review`, `other`.
- `evaluated`: `true` when the paper's evaluation exercises the check, `false` when it is only proposed.

*Pilot.*
- Code checks that belong to the system's operating path (designed, proposed or implemented). Checks the authors
  perform only to score their own evaluation (manual output inspection, ground-truth comparison) are not coded.
- `observation` requires a step that checks or reconciles the freshness, version or consistency of state, or compares
  desired with runtime state. Reading current state as a decision input is not an observation check.
- `coverage` requires an explicit outcome when no acceptable result exists (reject, escalate, report infeasible,
  return failure, label unsupported). A validate-and-regenerate loop counts only when it ends in such an outcome; a
  silent fallback or submitting the last attempt is `NE`.
- `engine` is only the component that produces the decision (the language model, learned policy, or a solver that
  computes the decision). Agent or framework code around a model (retry loops, guards, routers) is `controller`. A
  solver that computes the decision and enforces its constraints owns those checks as `engine`.
- A second call to the same model for checking is `engine`; a different model is `separate_model`.
- `formal` covers SMT, model checking, proof and symbolic data-plane verification (for example Batfish or
  Minesweeper); other rule or schema checks are `deterministic`.

## Output (JSON Lines, one object per family, in the listed order)

```json
{"family_id": "RG001", "interfaces": ["G", "C"], "path": "request_driven", "roles": ["controller"],
 "observation": "NE",
 "feasibility": [{"component": "Batfish", "owner": "tool", "mechanism": "deterministic", "evaluated": true}],
 "coverage": [{"component": "scheduler", "owner": "controller", "mechanism": "deterministic", "evaluated": true}],
 "evidence": "<= 60 words with section locators for the interface, the role and each non-NE check"}
```

## Procedure and reporting

Two independent coders (a GPT-family and a Claude-family model), blind to each other and to the published table
(`paper/supplement/systematization.csv`, `paper/tables/literature-map.tex`). Pilot: 10 families drawn with seed 42;
after the pilot the codebook may be clarified once and is then frozen; the pilot families are recoded under the frozen
codebook and excluded from the reliability estimate.

Inter-coder reliability over the remaining 129 families: per-option kappa and AC1 and exact-set agreement for
`interfaces` and `roles`; kappa/AC1 for `path`; for each check type, kappa/AC1 on performed vs `NE`, and, where both
coders code performed, exact-set agreement on the set of `owner` values, the set of `mechanism` values and the set of
(`owner`, `mechanism`) pairs, and kappa/AC1 on `evaluated` reduced to any-evaluated (true if any listed component is
evaluated). `component` names are free text and are not scored; they support the evidence check.

Agreement with the published table: after both coders finish, a third pass maps each published row (its cells only,
blind to both coders) into the same frozen fields, reading `workflow_detail` for `path` and `roles` and the check and
detail cells for `owner`, `mechanism` and `evaluated`; a field the cells do not settle is recorded as `null` and that
family is left out of that field's comparison. Each coder is compared with this mapping on every field with the statistics above.

No reconciliation round: the published table remains the reported systematization, and this exercise measures how
reproducible it is.

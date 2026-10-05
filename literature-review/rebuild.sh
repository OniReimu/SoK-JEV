#!/usr/bin/env bash
# Run from the repository root after the Quick start preparation.
set -euo pipefail
PY=${1:-.venv/bin/python}
S=literature-review/scripts
R=literature-review/results
D=runs/literature-review
W=artifacts/reproduction
O=out/literature-review
export PYTHONDONTWRITEBYTECODE=1 MPLBACKEND=Agg
mkdir -p "$O"
# Scripts that write beside inputs operate only on disposable copies.
I=$(mktemp -d "$O/inputs.XXXXXXXX")
cp -R "$D/screening" "$I/screening"
cp -R "$D/coverage-audit" "$I/coverage-audit"
cp -R "$D/q2" "$I/second-screening"
A="$I/coverage-audit"
Q="$I/second-screening"
results=0
figures=0
tables=0
check_result() {
    cmp "$1" "$R/$2"
    if [[ "$1" != "$O/$2" ]]; then cp "$1" "$O/$2"; fi
    results=$((results + 1))
}
result() {
    local script=$1 name=$2
    shift 2
    "$PY" "$S/$script" "$@" --out "$O/$name"
    check_result "$O/$name" "$name"
}
"$PY" "$S/e0_screen_agreement.py" --screen-dir "$I/screening"
check_result "$I/screening/agreement.json" screening-agreement.json
"$PY" "$S/e0_screen_finalize.py" --screen-dir "$I/screening"
check_result "$I/screening/final_summary.json" screening-final.json
cmp "$I/screening/audit_sample.jsonl" "$D/coverage-audit/audit_sample.jsonl"
cp "$I/screening/final_summary.json" "$A/final_summary.json"
"$PY" "$S/e0_audit_analyze.py" --screen-dir "$A"
check_result "$A/audit/audit_summary.json" coverage-audit-summary.json
result e0_paired_counts.py coverage-audit-agreement.json coverage-audit --input-dir "$A/audit"
"$PY" "$S/e0_screen_agreement.py" --screen-dir "$Q"
check_result "$Q/agreement.json" q2-title-abstract-agreement.json
result e0_q2_compare.py q2-second-screening.json --q2-dir "$Q"
result e0_paired_counts.py q2-fulltext-eligibility.json second-screening --input-dir "$Q/ft"
"$PY" "$S/e0_new_families_finalize.py" --nf-dir "$Q/nf" --out "$O/new_families_final.jsonl" --summary "$O/new-families-summary.json"
cmp "$O/new_families_final.jsonl" "$D/q2/nf/new_families_final.jsonl"
check_result "$O/new-families-summary.json" new-families-summary.json
common=(--coding-tar studies/sok/data/coding.tar.gz --eligibility "$W/docs/sok/e0-current/eligibility.json" --new-families "$O/new_families_final.jsonl")
result e0_corpus_metrics.py corpus-139-metrics.json "${common[@]}"
result e0_taxonomy_patterns.py taxonomy-patterns.json "${common[@]}"
T="$D/taxonomy"
result e0_taxonomy_agreement.py taxonomy-intercoder.json --ids "$T/reliability_ids" --a "$T/coderA/rel129.jsonl" --b "$T/coderB/rel129.jsonl"
result e0_taxonomy_agreement.py taxonomy-coderA-vs-published.json --ids "$T/reliability_ids" --a "$T/coderA/rel129.jsonl" --b "$T/published_map_rel129.jsonl"
result e0_taxonomy_agreement.py taxonomy-coderB-vs-published.json --ids "$T/reliability_ids" --a "$T/coderB/rel129.jsonl" --b "$T/published_map_rel129.jsonl"
"$PY" "$S/e0_render_audit_figures.py" --metrics "$O/corpus-139-metrics.json" --out-dir "$O/reporting"
for name in a b c d legend; do
    cmp "$O/reporting/reporting-$name.pdf" "paper_assets/figures/reporting-$name.pdf"
    figures=$((figures + 1))
done
"$PY" "$S/e0_render_screening.py" --analysis-tar studies/sok/data/analysis.tar.gz --results-dir "$O" --out-dir "$O/screening"
for ext in pdf svg; do
    cmp "$O/screening/figures/screening-flow.$ext" "paper_assets/figures/screening-flow.$ext"
    figures=$((figures + 1))
done
"$PY" "$S/e0_render_taxonomy_table.py" --results-dir "$O" --out "$O/taxonomy-reliability.tex"
"$PY" "$S/e0_render_patterns_table.py" --results-dir "$O" --out "$O/taxonomy-patterns.tex"
"$PY" "$S/e0_render_coverage.py" --metrics "$O/corpus-139-metrics.json" --table paper_assets/tables/reporting-coverage.tex --out "$O/reporting-coverage.tex"
for name in taxonomy-reliability taxonomy-patterns reporting-coverage; do
    cmp "$O/$name.tex" "paper_assets/tables/$name.tex"
    tables=$((tables + 1))
done
printf 'PASS: %s results, %s figures, %s tables byte-identical\n' "$results" "$figures" "$tables"

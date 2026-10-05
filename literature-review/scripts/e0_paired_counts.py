"""Recount paired coverage-audit and second-screening full-text decisions.

Outputs match the stored JSON bytes, including key order and no final newline.
Coverage agreement uses compact JSON. Full-text eligibility uses indent=1.
Only 'N/A' and 'N/A (no claim)' count as the same coverage-audit answer.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def coder(base: Path, side: str) -> dict[str, dict]:
    result = {}
    for path in sorted((base / side).glob('*.jsonl')):
        for row in rows(path):
            key = row['screen_id']
            if key in result:
                raise ValueError(f'Duplicate decision: {key}')
            result[key] = row
    if not result:
        raise ValueError(f'No decisions in {base / side}')
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['coverage-audit', 'second-screening'])
    parser.add_argument('--input-dir', type=Path, required=True,
                        help='Paired coder directory: coverage-audit/audit or q2/ft')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    a, b = coder(args.input_dir, 'coderA'), coder(args.input_dir, 'coderB')
    if set(a) != set(b):
        raise ValueError('Paired coder record ids differ')
    if args.stage == 'coverage-audit':
        def normalize(value: object) -> object:
            return 'N/A' if value in ('N/A', 'N/A (no claim)') else value
        fields = ['eligibility', 'explicit_loop_claim', 'supported_loop_claim',
                  'tail_latency', 'deadline_attainment']
        output = {'records': len(a), **{
            field: sum(normalize(a[i][field]) == normalize(b[i][field]) for i in a)
            for field in fields}}
        text = json.dumps(output)
    else:
        ra = {r['screen_id']: r for r in rows(args.input_dir / 'reconcile/coderA.jsonl')}
        rb = {r['screen_id']: r for r in rows(args.input_dir / 'reconcile/coderB.jsonl')}
        key = 'eligibility'
        final = {i: a[i][key] if a[i][key] == b[i][key] else
                 ra[i][key] if i in ra and i in rb and ra[i][key] == rb[i][key] else
                 'split' for i in sorted(a)}
        output = {
            'units': len(a),
            'independent_agreement': sum(a[i][key] == b[i][key] for i in a),
            'both_eligible_independent': sorted(i for i in a if a[i][key] == b[i][key] == 'eligible'),
            'final': final,
            'eligible': sorted(i for i in final if final[i] == 'eligible'),
            'split': sorted(i for i in final if final[i] == 'split'),
        }
        text = json.dumps(output, indent=1)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding='utf-8')
    print('wrote', args.out)


if __name__ == '__main__':
    main()

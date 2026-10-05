"""Offline SoK collaboration entry point. Never launches models or experiments."""
import argparse
import contextlib
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'studies/sok'
sys.path.insert(0, str(ROOT))
from scripts.sok_package import inspect_archive, sha256

EXP = Path('experiments/EXP-023-decision-path-intervention')


def metadata():
    return json.loads((BASE / 'package.json').read_text())


def verify():
    package = metadata()
    totals = {'files': 0, 'expanded_bytes': 0}
    for spec in package['archives']:
        result = inspect_archive(BASE / spec['path'], spec)
        for key in totals:
            totals[key] += result[key]
    for name in package['code_files']:
        if not (ROOT / name).is_file():
            raise ValueError('Missing code/configuration: ' + name)
    print(json.dumps({'status': 'PASS_DATA_PACKAGE', **totals}))


def prepare(work):
    if work.exists():
        raise ValueError('Choose a new --work directory; existing files are preserved: ' + str(work))
    work.mkdir(parents=True)
    package = metadata()
    for spec in package['archives']:
        inspect_archive(BASE / spec['path'], spec, destination=work)
    for name in package['code_files']:
        target = work / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    coding = work / 'docs/sok/e0-current/analysis/analyze.py'
    coding.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(BASE / 'analysis/coding.py', coding)
    with zipfile.ZipFile(work / 'E0-blind-review.zip', 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted((work / 'E0-review').rglob('*.json')):
            archive.write(path, path.relative_to(work))
    paper = work / 'paper-sok-csur'
    shutil.copytree(ROOT / 'paper_assets', paper)
    shutil.copytree(ROOT / 'supplement', paper / 'supplement')
    mapping = json.loads((BASE / 'manuscript-map.json').read_text())
    for item in mapping['files']:
        target = paper / item['workspace_path']
        if (paper / item['path']).is_file() and target != paper / item['path']:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(paper / item['path'], target)
    frozen = work / EXP / 'sparse-cetus-108281/frozen-inputs'
    shutil.copytree(frozen / 'image-inputs', work / EXP / 'image-inputs')
    shutil.copyfile(frozen / 'experiment.md', work / EXP / 'experiment.md')
    (work / 'prepared.json').write_text(json.dumps({
        'package_sha256': sha256(BASE / 'package.json'),
        'source_root': str(ROOT), 'archives': package['archives'],
    }, indent=2) + '\n')
    print('Prepared isolated reproduction workspace:', work)


def activate(work):
    marker = work / 'prepared.json'
    if not marker.is_file():
        raise ValueError('Run prepare first with the same --work directory')
    if json.loads(marker.read_text())['package_sha256'] != sha256(BASE / 'package.json'):
        raise ValueError('Package changed; prepare a new workspace')
    sys.path.insert(0, str(work / 'scripts'))
    sys.path.insert(0, str(work / EXP))


def run(command, cwd=None):
    subprocess.run(command, cwd=cwd or ROOT, check=True)


def check_records(work):
    activate(work)
    fixed = importlib.import_module('sok_cross_study')
    fixed.load_sok(); fixed.load_edge(); fixed.load_6g()
    expected = [json.loads(line) for line in
                (work / 'artifacts/sok/cross-study/records.jsonl').read_text().splitlines()]
    if fixed.ROWS != expected:
        raise ValueError('Fixed-record reconstruction differs from frozen selection')
    print('PASS:', len(expected), 'normalized fixed records reconstructed exactly')
    analyze = importlib.import_module('analyze_sparse')
    sparse = work / EXP / 'sparse-cetus-108281'
    for name, expected in json.loads((sparse / 'source-hashes.json').read_text()).items():
        if sha256(sparse / 'frozen-inputs' / name) != expected:
            raise ValueError('Frozen measurement input mismatch: ' + name)
    for domain in ['edge', 'transport']:
        scenes = json.loads((sparse / 'frozen-inputs' / (domain + '-scenarios.json')).read_text())
        analyze.check_rows(analyze.read_rows(sparse / domain / 'records.jsonl'), domain,
                           [s['id'] for s in (scenes['scenarios'] if isinstance(scenes, dict) else scenes)], 10)
    run([sys.executable, str(work / EXP / 'analyze_load.py'), '--run',
         str(work / EXP / 'load-cetus-108309'), '--out', str(work / 'checks/queues'), '--check-only'])
    print('PASS: 2,400 physical executions and all 84 queue timelines')


def figures(work):
    activate(work)
    mod = importlib.import_module('sok_family_figures')
    mod.rq_a(); mod.rq_b_c_e(); selected = mod.e1_d(); mod.audit(); ran = mod.e2(); mod.overview()
    mapping = json.loads((BASE / 'manuscript-map.json').read_text())['files']
    public = {m['workspace_path']: m['path'] for m in mapping}
    out = work / 'generated/figures'
    out.mkdir(parents=True, exist_ok=True)
    for item in mod.ARTIFACTS:
        source = work / 'paper-sok-csur' / item['path']
        pdf_key = str(Path(item['path']).with_suffix('.pdf'))
        if pdf_key not in public:
            raise ValueError('Figure has no manuscript mapping: ' + pdf_key)
        name = Path(public[pdf_key]).with_suffix(source.suffix).name
        shutil.copyfile(source, out / name)
    (out / 'sources.json').write_text(json.dumps({
        'inputs': {p: sha256(work / p) for p in mod.SOURCE_FILES},
        'artifacts': mod.ARTIFACTS, 'deadline_strata': selected, 'ran_stages': ran,
    }, indent=2) + '\n')
    expected = json.loads((ROOT / 'paper_assets/expected_sha256.json').read_text())
    extension = {'reporting-' + n + '.pdf' for n in ['a', 'b', 'c', 'd', 'legend']}
    extension |= {'screening-flow.pdf', 'screening-flow.svg'}
    checked = {}
    for name, digest in expected.items():
        if name in extension:
            print(name + ': regenerated by the literature-review extension')
            checked[name] = 'extension-regenerated (separate strict gate)'
            continue
        generated = out / name
        if name.startswith('control-boundary.'):
            generated = work / 'paper-sok-csur/figures/family' / name
        if not generated.is_file() or sha256(generated) != digest:
            raise ValueError('Figure hash differs: ' + name)
        kind = 'conceptual (not data), byte-identical' if name.startswith('control-boundary.') else 'byte-identical'
        print(name + ': ' + kind)
        checked[name] = kind
    (out / 'comparison.json').write_text(json.dumps(checked, indent=2) + '\n')
    print('PASS:', sum(n not in extension for n in expected), 'figure hashes matched')


def tables(work):
    activate(work)
    helper = importlib.import_module('sok_style_check')
    reader = importlib.import_module('sok_e0_tables')
    paper = work / 'paper-sok-csur'
    source = work / 'scripts/sok_manuscript_assets.py'
    out = work / 'generated/tables'
    out.mkdir(parents=True, exist_ok=True)
    # The historical generator also writes prose. Redirect every output into a
    # temporary directory and publish only its numeric table comparison here.
    counts = {}
    inactive = []
    with contextlib.nullcontext(tempfile.mkdtemp(prefix='sok-tables-', dir=work)) as temp:
        target = Path(temp) / 'paper'
        target.mkdir()
        frozen_code = source.read_text()
        old = "data.append([tex(SHORT.get(method,method)),tex(platform),str(c['n']),timing]+vals+[rho])"
        new = "data.append([tex(SHORT.get(method,method)),{'SoK': 'SoK-owned', 'Edge': 'From A', '6G': 'From B'}[study],str(c['n']),timing]+vals+[rho])"
        if frozen_code.count(old) != 1: raise ValueError("Timing ownership rewrite count")
        frozen_code = frozen_code.replace(old, new)
        code = frozen_code.replace("PAPER = ROOT / 'paper-sok-csur'", 'PAPER = Path(' + repr(str(target)) + ')')
        code = code.replace("OUT = ROOT / 'artifacts/sok/restructure'", 'OUT = Path(' + repr(str(Path(temp) / 'receipt')) + ')')
        if "PAPER = ROOT / 'paper-sok-csur'" in code or "OUT = ROOT / 'artifacts/sok/restructure'" in code:
            raise ValueError('Failed to isolate historical table generator')
        exec(compile(code, str(source), 'exec'), {'__file__': str(source), '__name__': 'isolated_tables'})
        replacements = reader.reader_tables(json.loads((work / 'docs/sok/e0-current/analysis/results.json').read_text()))
        for generated in sorted((target / 'tables').glob('*.tex')):
            if generated.name == 'e0-audit-table.tex':
                continue
            if not (paper / 'tables' / generated.name).is_file():
                inactive.append(generated.name)
                continue
            if generated.name in replacements:
                # Export strips comments, so compare their actual LaTeX bodies.
                actual = (paper / 'tables' / generated.name).read_text()
                expected = replacements[generated.name]
                clean = lambda s: '\n'.join(x for x in s.splitlines() if not x.lstrip().startswith('%')).strip()
                if clean(actual) != clean(expected):
                    raise ValueError('Coding table differs: ' + generated.name)
            else:
                actual = paper / 'tables' / generated.name
                if helper.numeric_blocks(actual) != helper.numeric_blocks(generated):
                    raise ValueError('Numeric rows differ: ' + generated.name)
                counts[generated.name] = len(helper.numeric_rows(actual))
        (out / 'comparison.json').write_text(json.dumps({'status': 'PASS_NUMERIC_TABLES',
            'numeric_rows': sum(counts.values()), 'tables': counts,
            'coding_tables': list(replacements), 'inactive_historical_tables': inactive}, indent=2) + '\n')
    print('PASS:', sum(counts.values()), 'numeric table rows; authored prose preserved')


def reanalyze(work, stage):
    activate(work)
    # These CPU analyses can be lengthy. Run this explicit command on an HPC
    # allocation; figures, tables and check-records use the frozen estimates.
    commands = {
        'coding': [sys.executable, str(work / 'docs/sok/e0-current/analysis/analyze.py')],
        'fixed': [sys.executable, str(work / 'scripts/sok_cross_study.py')],
        'timing': [sys.executable, str(work / 'scripts/sok_e1_analysis.py')],
        'sparse': [sys.executable, str(work / EXP / 'analyze_sparse.py'), '--run',
                   str(work / EXP / 'sparse-cetus-108281'), '--out', str(work / 'reanalysis/sparse')],
        'load': [sys.executable, str(work / EXP / 'analyze_load.py'), '--run',
                 str(work / EXP / 'load-cetus-108309'), '--out', str(work / 'reanalysis/load')],
    }
    run(commands[stage], work)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['verify', 'prepare', 'check-records', 'figures', 'tables', 'reanalyze'])
    parser.add_argument('--work', type=Path, default=ROOT / 'artifacts/sok-reproduction')
    parser.add_argument('--stage', choices=['coding', 'fixed', 'timing', 'sparse', 'load'])
    args = parser.parse_args()
    work = args.work.resolve()
    if args.command == 'verify': verify()
    elif args.command == 'prepare': prepare(work)
    elif args.command == 'check-records': check_records(work)
    elif args.command == 'figures': figures(work)
    elif args.command == 'tables': tables(work)
    elif args.command == 'reanalyze':
        if args.stage is None: parser.error('reanalyze requires --stage')
        reanalyze(work, args.stage)


if __name__ == '__main__':
    main()

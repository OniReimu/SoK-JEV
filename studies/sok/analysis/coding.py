#!/usr/bin/env python3
"""Reproduce E0 descriptive analysis from the unchanged author return package."""
import collections
import hashlib
import json
from pathlib import Path
import platform
import zipfile

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
ARCHIVE = ROOT / 'E0-blind-review.zip'
SEED, REPLICATES = 42, 10000

# Fixed analysis definitions. Rates describe reporting, never system performance.
METRICS = [
    ('endpoint', 'Named timing endpoint', ['model', 'dispatch', 'network', 'service', 'other']),
    ('denominator', 'Specified metric denominator', ['all', 'success', 'other', 'mixed']),
    ('tail', 'p95 or higher', ['yes']),
    ('deadline', 'Deadline attainment', ['yes']),
    ('load', 'Input load', ['yes']),
    ('queue', 'Queue / waiting', ['yes']),
    ('stability', 'Stability evidence', ['yes']),
    ('baseline', 'Non-learning comparison', ['yes']),
    ('loop_claim', 'Explicit loop claim', ['rt', 'near_rt', 'non_rt', 'other']),
    ('loop_match', 'Supported loop claim', ['matched']),
    ('deployment', 'Named execution location', ['hosted', 'gpu', 'edge', 'cpu', 'other']),
    ('roundtrip', 'Network round trip included', ['included']),
    ('format', 'Format check reported', ['reported']),
    ('semantic', 'Semantic check reported', ['reported']),
    ('final_state', 'Final-state check reported', ['reported']),
    ('gate_separation', 'Three gates distinguished', ['three']),
    ('code', 'Public code pointer', ['public_link']),
    ('data', 'Public data pointer', ['public_link']),
]
TASKS = {'Configuration': '配置', 'Orchestration': '编排', 'Diagnosis': '诊断'}

def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n')

def vals(x):
    return x if isinstance(x, list) else [x]

def key(x):
    return '|'.join(sorted(x)) if isinstance(x, list) else x

def coefficients(a, b, categories):
    n = len(a)
    assert n == len(b) and n > 0
    assert set(a + b) <= set(categories)
    pa = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = collections.Counter(a), collections.Counter(b)
    pe_k = sum(ca[c] * cb[c] for c in categories) / n ** 2
    p = [(ca[c] + cb[c]) / (2 * n) for c in categories]
    pe_a = sum(x * (1 - x) for x in p) / (len(categories) - 1) if len(categories) > 1 else 0
    # Kappa is undefined if both raters use the same sole category.
    return {'n_pairs': n, 'agree': round(pa * n), 'agreement': pa,
            'kappa': (pa-pe_k)/(1-pe_k) if pe_k < 1 else None,
            'ac1': (pa-pe_a)/(1-pe_a), 'category_count': len(categories),
            'DL_categories': dict(ca), 'CL_categories': dict(cb)}

def pct(x):
    return f'{100*x:.1f}'

def rate_text(r):
    return f"{r['positive']}/{r['n']} ({pct(r['proportion'])}%; {pct(r['ci95'][0])}–{pct(r['ci95'][1])})"

def number(x):
    return '—' if x is None else f'{x:.3f}'

def main():
    with zipfile.ZipFile(ARCHIVE) as z:
        def read(n):
            return json.loads(z.read('E0-review/' + n + '.json'))
        final, paper = read('E0-final'), read('E0-paper-view')
        agreement_source = read('E0-agreement')
        boundaries = read('audit/canonical-boundaries')
        independent = {r: read(f'originals/E0-{r}-aligned') for r in ['DL', 'CL']}
        member_hashes = {i.filename: hashlib.sha256(z.read(i.filename)).hexdigest()
                         for i in z.infolist() if not i.is_dir()}
    eligibility_path = ROOT / 'docs/sok/e0-current/eligibility.json'
    eligibility = json.loads(eligibility_path.read_text())
    prep = {r['id']: r for r in eligibility['records']}
    groups = [g for g in paper['groups'] if g['scope_decision'] == 'include']
    ids = [g['id'] for g in groups]
    units = final['units']
    by_group = {g: [u for u in units if u['group'] == g] for g in ids}
    field_defs = {f['id']: f for q in final['codebook']['questions'] for f in q['fields']}
    options = {f: [o[0] for o in d['options']] for f, d in field_defs.items()}
    aligned = {r: {u['id']: u for g in independent[r]['state']['groups'].values()
                   for u in g.get('units', [])} for r in independent}
    boundary = {u['id']: u for g in boundaries['groups'] for u in g['units']}
    assert len(groups) == 132 and len(units) == 405
    assert len({r for g in groups for r in g['source_reports']}) == 138
    assert sum(u['relation'] == 'new_step' for u in units) == 374
    assert len(field_defs) == 18
    for u in units:
        assert u['group'] in ids
        for f, value in u['answers'].items():
            assert set(vals(value)) <= set(options[f])
            for r in aligned:
                assert key(u['field_provenance'][f][r + '_aligned']) == key(aligned[r][u['id']]['answers'][f])

    # These task strata are the assistant-prepared reading labels, not a newly
    # claimed independently coded taxonomy. A multi-task work enters each stratum.
    task_members = {}
    for g in groups:
        task_members[g['id']] = sorted({t for r in g['source_reports']
                                       for t in (prep[r].get('task_group') or '').split('/') if t})
        assert task_members[g['id']]
    strata = {'All': ids, **{name: [g for g in ids if task in task_members[g]]
                            for name, task in TASKS.items()}}
    # Whole-family resampling: use the same draw weights for all indicators.
    rng = np.random.default_rng(SEED)
    weights = {s: rng.multinomial(len(gs), np.full(len(gs), 1/len(gs)), size=REPLICATES)
               for s, gs in strata.items()}

    def rate(positive, total, stratum='All'):
        a, b = np.array(positive, dtype=float), np.array(total, dtype=float)
        samples = weights[stratum] @ a / (weights[stratum] @ b)
        ci = np.quantile(samples, [.025, .975], method='linear').tolist()
        n, count = int(sum(b)), int(sum(a))
        return {'positive': count, 'n': n, 'proportion': count/n, 'ci95': ci,
                'families': len(a), 'bootstrap_boundary_degenerate': count in (0, n)}

    metrics = []
    for f, label, positive in METRICS:
        matches = lambda u: bool(set(vals(u['answers'][f])) & set(positive))
        hit = {g: [u['id'] for u in by_group[g] if matches(u)] for g in ids}
        m = {'field': f, 'label': label, 'positive_categories': positive,
             'supporting_scopes': {g: u for g, u in hit.items() if u},
             'paper_family': {s: rate([bool(hit[g]) for g in gs], [1]*len(gs), s)
                              for s, gs in strata.items()},
             'scope': rate([len(hit[g]) for g in ids], [len(by_group[g]) for g in ids]),
             'new_step_scope_only': rate([sum(matches(u) and u['relation']=='new_step' for u in by_group[g]) for g in ids],
                                         [sum(u['relation']=='new_step' for u in by_group[g]) for g in ids]),
             'families_with_unclear_any_scope': sum(any('unclear' in vals(u['answers'][f]) for u in by_group[g]) for g in ids),
             'families_all_scopes_na': sum(all(vals(u['answers'][f])==['na'] for u in by_group[g]) for g in ids)}
        metrics.append(m)

    distributions = []
    for f in field_defs:
        for category in options[f]:
            counts = [sum(category in vals(u['answers'][f]) for u in by_group[g]) for g in ids]
            distributions.append({'field': f, 'category': category,
                                  'scope': rate(counts, [len(by_group[g]) for g in ids]),
                                  'paper_family_any': rate([x > 0 for x in counts], [1]*len(ids))})

    selections = {
        'all_scopes': units,
        'unchanged_initial': [u for u in units if not boundary[u['id']]['recheck_fields']],
        'aligned_recheck': [u for u in units if boundary[u['id']]['recheck_fields']],
        'new_steps': [u for u in units if u['relation']=='new_step'],
        'linked_scopes': [u for u in units if u['relation']=='same_step_scope'],
    }
    agreements, multi = [], []
    for stratum, selected in selections.items():
        source = {r['field']: r for r in agreement_source[stratum]}
        for f in field_defs:
            a, b = [[key(aligned[r][u['id']]['answers'][f]) for u in selected] for r in ['DL', 'CL']]
            exact = sum(x==y for x,y in zip(a,b))/len(a)
            assert abs(exact-source[f]['agreement']) < 1e-12
            row = {'stratum': stratum, 'field': f, 'n_pairs': len(a), 'agreement': exact}
            if field_defs[f].get('type') == 'multi':
                row.update(kappa=None, ac1=None, ac1_observed_categories=None,
                           coefficient_note='Exact-set agreement; per-option binary coefficients reported separately.')
                for option in options[f]:
                    aa, bb = [[str(int(option in aligned[r][u['id']]['answers'][f])) for u in selected] for r in ['DL','CL']]
                    multi.append({'stratum':stratum, 'field':f, 'option':option,
                                  **coefficients(aa,bb,['0','1'])})
            else:
                row.update(coefficients(a,b,options[f]))
                row['ac1_observed_categories'] = coefficients(a,b,sorted(set(a+b)))['ac1']
                k = source[f]['kappa']
                assert (k is None and row['kappa'] is None) or abs(k-row['kappa']) < 1e-12
            agreements.append(row)

    # Sanity checks for formula limits and a nontrivial 2-category example.
    assert coefficients(['a','a'],['a','a'],['a','b'])['ac1'] == 1
    assert coefficients(['a','b'],['b','a'],['a','b'])['ac1'] == -1
    test = coefficients(['a','a','a','b'],['a','a','b','b'],['a','b'])
    assert abs(test['ac1'] - 9/17) < 1e-12 and abs(test['kappa']-.5) < 1e-12
    assert len(selections['unchanged_initial']) == 231 and len(selections['aligned_recheck']) == 174
    assert sum('unclear' in vals(v) for u in units for v in u['answers'].values()) == 320

    inventory = [{k:u[k] for k in ['id','group','title','task','step','scope','records','relation','parent','shared_measurement_key','answers']}
                 for u in units]
    result = {
        'metadata': {'analysis_date':'2026-09-29', 'source_archive':str(ARCHIVE.relative_to(ROOT)),
                     'archive_sha256':hashlib.sha256(ARCHIVE.read_bytes()).hexdigest(),
                     'source_member_sha256':member_hashes,
                     'eligibility_sha256':hashlib.sha256(eligibility_path.read_bytes()).hexdigest(),
                     'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                     'python':platform.python_version(), 'numpy':np.__version__, 'matplotlib':matplotlib.__version__,
                     'bootstrap_seed':SEED,'bootstrap_replicates':REPLICATES,
                     'ci_method':'Percentile, whole report-family resampling, conditional descriptive sensitivity; not population inference.',
                     'ac1_category_policy':'Fixed codebook category universe; observed-category sensitivity also reported. Multi-select options are separate binary indicators.',
                     'task_stratum_policy':'Union of pre-author assistant labels of constituent reports; overlapping, exploratory; NOT independently double-coded task taxonomy.',
                     'primary_unit':'Paper/report family; positive if at least one included scope has a positive code.',
                     'scope_unit':'Evidence scope, descriptive, within-paper cluster resampling; linked scopes retained explicitly.',
                     'step_sensitivity':'Only new_step scopes; no propagation from linked or pipeline aggregate scopes to parent steps.',
                     'style_reference_commit':'2731501e6fa25c8f6004b4c06239b9ef2f7afc69'},
        'counts': {'paper_families':len(groups),'reports':138,'scope_records':len(units),'step_definitions':374,'linked_scopes':31,
                   'unclear_cells':320,'pre_adjudication_disagreements':1867},
        'strata':strata,'task_membership':task_members,'metrics':metrics,
        'category_distributions':distributions,'agreement':agreements,'multi_option_agreement':multi,
        'unit_inventory':inventory,
    }
    dump(OUT/'results.json',result)
    render_tables(result)
    render_figure(result)
    print(json.dumps({'counts':result['counts'], 'strata':{k:len(v) for k,v in strata.items()},
                      'metrics':{m['field']:rate_text(m['paper_family']['All']) for m in metrics},
                      'agreement':[r for r in agreements if r['stratum']=='all_scopes']}, ensure_ascii=False, indent=2))

def render_tables(result):
    lines = ['# E0 统计全表', '',
             '数据与口径见 [说明](README.md)。括号中为占比和按论文家族重抽样的95%区间。', '',
             '## 论文层面的证据报告覆盖', '',
             '每篇工作只要任一范围出现目标值即记一次；并不表示所有步骤均满足。主分母固定为132，未报告、不明和不适用均保留在全语料分母。', '',
             '| 字段 | 目标值 | 篇数/132（比例；95%区间） | 含不明的篇数 | 全部范围不适用的篇数 |',
             '|---|---|---|---:|---:|']
    for m in result['metrics']:
        lines.append(f"| {m['label']} | {', '.join(m['positive_categories'])} | {rate_text(m['paper_family']['All'])} | {m['families_with_unclear_any_scope']} | {m['families_all_scopes_na']} |")
    lines += ['', '“含不明”可能与“有报告”重叠，因为同一工作有多个范围。公共链接指论文提供线索，未确认当前能访问或完整复现。', '',
              '## 范围层面与步骤定义敏感性视图', '',
              '405条范围包括31条关联范围；374列仅保留new_step原记录，不继承关联范围中的汇总测量。它们不是独立实验数，也不是同一个估计目标。', '',
              '| 字段 | 全405范围 | 仅374个步骤定义范围 |', '|---|---|---|']
    for m in result['metrics']:
        lines.append(f"| {m['label']} | {rate_text(m['scope'])} | {rate_text(m['new_step_scope_only'])} |")
    lines += ['', '## 完整类别分布', '',
              '保留原始类别。单选范围计数每字段合计405；多选可重叠。论文按“至少一范围该类别”计数，各类别可能重叠。', '',
              '| 字段 | 类别 | 范围/405（比例；95%区间） | 论文/132（比例；95%区间） |','|---|---|---|---|']
    for r in result['category_distributions']:
        lines.append(f"| {r['field']} | {r['category']} | {rate_text(r['scope'])} | {rate_text(r['paper_family_any'])} |")
    lines += ['', '## 裁决前一致性', '',
              'AC1主值使用手册预定义的全部类别；AC1 observed只使用两人实际使用过的类别，作为类别数选择的敏感性结果。无权重。多选字段保留完全相同集合的比例，并在下一表逐选项给出二元κ和AC1。', '']
    labels = {'all_scopes':'全部405条可比独立答案（并非全体首次盲评）', 'unchanged_initial':'231条首次可比范围',
              'aligned_recheck':'174条边界对齐后独立复核', 'new_steps':'374条步骤定义范围', 'linked_scopes':'31条关联范围'}
    for s,label in labels.items():
        lines += ['### '+label,'','| 字段 | n | 一致率 | Cohen κ | AC1 fixed | AC1 observed |','|---|---:|---:|---:|---:|---:|']
        for r in result['agreement']:
            if r['stratum']==s:
                lines.append(f"| {r['field']} | {r['n_pairs']} | {pct(r['agreement'])}% | {number(r['kappa'])} | {number(r['ac1'])} | {number(r['ac1_observed_categories'])} |")
    lines += ['', '## 多选字段逐选项一致性（全部405范围）', '', '| 字段 | 选项 | 一致率 | Cohen κ | AC1（二元） |', '|---|---|---:|---:|---:|']
    for r in result['multi_option_agreement']:
        if r['stratum']=='all_scopes':
            lines.append(f"| {r['field']} | {r['option']} | {pct(r['agreement'])}% | {number(r['kappa'])} | {number(r['ac1'])} |")
    lines += ['', '其他分层的多选一致性、逐篇支持范围和405条完整编码见 results.json；原文证据与裁决链保留在原始ZIP中。',
              '', '当目标事件为0或全体时，非参数bootstrap区间退化为点；这不是“确定不存在”或总体比例已知。']
    (OUT/'full-tables.md').write_text('\n'.join(lines)+'\n')

def render_figure(result):
    plt.rcParams.update({'font.family':'Times New Roman','font.size':8,'axes.titlesize':8,
                         'axes.labelsize':8,'xtick.labelsize':7.2,'ytick.labelsize':7.2,
                         'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none',
                         'axes.spines.top':False,'axes.spines.right':False})
    panels = [
        ('(a) Timing evidence', [('tail','p95+'),('deadline','Deadline')]),
        ('(b) Operating conditions', [('load','Load'),('queue','Queue'),('stability','Stability')]),
        ('(c) System validation', [('baseline','Baseline'),('roundtrip','Round\ntrip'),('gate_separation','Three\ngates')]),
        ('(d) Public pointers', [('code','Code'),('data','Data')]),
    ]
    lookup = {m['field']:m for m in result['metrics']}
    colors, hatches = ['#B9C6E0','#F4CC79','#ED8683'], ['', '///', '...']
    fig, axes = plt.subplots(1,4,figsize=(7.16,2.6),sharey=True)
    fig.subplots_adjust(left=.063,right=.995,bottom=.25,top=.77,wspace=.22)
    for ax,(title,fields) in zip(axes,panels):
        x=np.arange(len(fields)); width=.24
        for j, name in enumerate(TASKS):
            rates=[lookup[f]['paper_family'][name] for f,_ in fields]
            y=np.array([r['proportion']*100 for r in rates])
            low=y-np.array([r['ci95'][0]*100 for r in rates]); high=np.array([r['ci95'][1]*100 for r in rates])-y
            ax.bar(x+(j-1)*width,y,width,color=colors[j],hatch=hatches[j],edgecolor='#333333',linewidth=.45,
                   label=f"{name} (n={len(result['strata'][name])})",zorder=3)
            ax.errorbar(x+(j-1)*width,y,yerr=np.array([low,high]),fmt='none',ecolor='#292929',elinewidth=.55,capsize=1.3,zorder=4)
        ax.set_title(title,pad=7)
        ax.set_xticks(x,[label for _,label in fields]);ax.set_ylim(0,105);ax.set_yticks([0,25,50,75,100])
        ax.grid(axis='y',color='#dddddd',linewidth=.45,zorder=0);ax.tick_params(axis='x',length=0)
    axes[0].set_ylabel('Papers reporting evidence (%)')
    handles, labels=axes[0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='upper center',bbox_to_anchor=(.53,1.0),ncol=3,frameon=False,fontsize=8,columnspacing=1.4)
    fig.text(.5,.035,'Overlapping task strata; whole-paper bootstrap 95% intervals; reporting coverage, not success rates.',ha='center',fontsize=7.2)
    for suffix in ['pdf','svg','png']:
        fig.savefig(OUT/f'e0-audit.{suffix}',dpi=220,metadata={'Creator':'E0 analysis'} if suffix=='pdf' else None)
    plt.close(fig)

if __name__ == '__main__':
    main()

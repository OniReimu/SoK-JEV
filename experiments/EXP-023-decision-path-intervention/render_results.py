"""Advisor-specified 1x4/1x2 E2 figures and grouped table from completed analyses."""
from pathlib import Path
from datetime import datetime
import argparse
import csv
import hashlib
import json
import sys
import numpy as np

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from sok_cross_study_figures import style, export
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

STAGE_COLORS=['#B9C6E0','#F4CC79','#ED8683']
RHO_COLORS=['#597DB0','#DC9C3E','#B74F52']


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def ran_stages():
    ep=ROOT/'artifacts/sok/e1/results.json'
    e1=json.loads(ep.read_text())
    sources=json.loads((ep.parent/'source-manifest.json').read_text())['sources']
    labels={'Jev-1.13.0':'Jev','DeepSeek-V4.1-Flash':'DS','GLM-5.3-Flash':'GLM',
            'Qwen3.8-Flash':'Qw-F','AnyJev-L0':'Any','SemIf-Qwen3.5-4B':'SemIf',
            'Qwen3.5-4B-JSON':'Qw-J'}
    order=list(labels)
    results=[]
    for method in order:
        cell=next(s for s in e1['physical_paths'] if s['study']=='6G' and s['method']==method)
        src=cell['source_ids'][0]
        p=ROOT/src
        assert sha(p)==sources[src]
        rows=[json.loads(x) for x in p.read_text().splitlines()]
        values=[];missing=[];early=[]
        for index,r in enumerate(rows,1):
            fields=['t_intent_issued','t_decision_returned','t_gnb_acknowledged','t_first_kpm_change']
            if any(r.get(k) is None for k in fields):
                missing.append(dict(line=index,missing=[k for k in fields if r.get(k) is None],
                    actuation_error=r.get('actuation_error')))
                continue
            t=[datetime.fromisoformat(r[k].replace('Z','+00:00')).timestamp() for k in
                fields]
            sent=datetime.fromisoformat(r['t_control_sent'].replace('Z','+00:00')).timestamp()
            assert t[0]<=t[1]<=sent<=t[2] and sent<=t[3]
            # Original C3 observes KPM after control send, independently of acknowledgement.
            # Keep signed KPM-minus-ACK gaps; never clamp or discard earlier observations.
            if t[3]<t[2]:early.append(dict(line=index,kpm_minus_ack_s=t[3]-t[2]))
            values.append(np.diff(t))
        assert len(rows)==30
        results.append(dict(method=method,label=labels[method],n=30,
            complete_endpoint_n=len(values),missing_endpoints=missing,kpm_before_ack=early,
            stage_medians_s=np.median(values,axis=0).tolist(),source=src,source_sha256=sha(p),
            conditioning='Both ACK and KPM endpoints observed; missingness reported against all 30 arrivals',
            last_stage='Signed KPM-minus-ACK difference; endpoints need not be strictly ordered'))
    return results


def paths_figure(sparse,ran,out):
    fig,axes=plt.subplots(1,4,figsize=(7.0,2.62))
    fig.subplots_adjust(left=.065,right=.99,top=.78,bottom=.25,wspace=.46)
    def bars(ax,labels,values,title):
        values=np.asarray(values)
        x=np.arange(len(labels));bottom=np.zeros(len(labels))
        for j,(name,hatch) in enumerate([('Decision',''),('Acknowledgement','///'),('Outcome / KPM','...')]):
            ax.bar(x,values[:,j],bottom=bottom,width=.68,color=STAGE_COLORS[j],
                   edgecolor='#333333',linewidth=.35,hatch=hatch,label=name,zorder=3)
            bottom+=values[:,j]
        ax.set_xticks(x,labels)
        ax.set_title(title,fontsize=7.4)
        ax.set_ylabel('Stage median (s)')
        ax.grid(axis='y',color='#dddddd',linewidth=.4,zorder=0)
    bars(axes[0],[r['label'] for r in ran],[r['stage_medians_s'] for r in ran],'(a) RAN: KPM upper bound')
    axes[0].tick_params(axis='x',rotation=60,labelsize=6.8)
    axes[0].set_xlabel('Original implementation')
    for ax,domain,title in zip(axes[1:3],['transport','edge'],['(b) Transport','(c) Edge']):
        cells=next(d for d in sparse['domains'] if d['domain']==domain)['cells']
        values=[[c['stage_medians_s'][k] for k in ['decision','acknowledgement_after_decision','verification_after_acknowledgement']] for c in cells]
        bars(ax,['0','.1','.5','2'],values,title)
        ax.set_xlabel('Injected D (s)')
    ax=axes[3]
    for domain,color,marker,line in [('transport','#597DB0','o','-'),('edge','#B74F52','s','--')]:
        cells=next(d for d in sparse['domains'] if d['domain']==domain)['cells']
        x=[c['injected_delay_s'] for c in cells]
        y=[c['Tb']['p50_s'] for c in cells]
        ax.plot(x,y,marker=marker,color=color,linestyle=line,markersize=3,linewidth=.9,label=domain.title())
        for v,c in zip(x,cells):
            bounds=c['Tb']['ci95_p50_s']
            if bounds:ax.vlines(v,bounds[0],bounds[1],color=color,linewidth=.6)
    ax.set_title('(d) Sparse outcome',fontsize=7.4)
    ax.set_xlabel('Injected D (s)');ax.set_ylabel('Median $T_b$ (s)')
    ax.set_xticks([0,.5,1,2]);ax.grid(axis='y',color='#dddddd',linewidth=.4)
    ax.legend(frameon=False,fontsize=6.8,loc='upper left',handlelength=1.6)
    h,l=axes[0].get_legend_handles_labels()
    fig.legend(h,l,loc='upper center',bbox_to_anchor=(.48,.99),ncol=3,frameon=False,fontsize=7.3)
    export(fig,out,'e2-paths')


def load_figure(load,out):
    fig,axes=plt.subplots(1,2,figsize=(3.375,2.80))
    fig.subplots_adjust(left=.17,right=.985,top=.68,bottom=.20,wspace=.58)
    for i,rho in enumerate([.5,.8,.95]):
        rows=sorted([r for r in load['cells'] if r['type']=='controlled' and r['baseline_rho']==rho],
                    key=lambda r:r['requested_D_s'])
        assert len(rows)==4
        x=[r['requested_D_s'] for r in rows]
        for domain,line,marker in [('transport','-','o'),('edge','--','s')]:
            d=[r['domains'][domain] for r in rows]
            p=[r['budgets'][str(r['reference_budget_s'])]['Tb'] for r in d]
            axes[0].plot(x,[r['Tb']['p95_s'] for r in d],color=RHO_COLORS[i],linestyle=line,
                         marker=marker,markersize=2.5,linewidth=.8)
            axes[1].plot(x,[100*r['value'] for r in p],color=RHO_COLORS[i],linestyle=line,
                         marker=marker,markersize=2.5,linewidth=.8)
            for xx,dd,pp in zip(x,d,p):
                interval=dd['Tb']['ci95_p95_s']
                if interval:axes[0].vlines(xx,*interval,color=RHO_COLORS[i],linewidth=.5)
                if pp['ci95']:axes[1].vlines(xx,*[100*v for v in pp['ci95']],color=RHO_COLORS[i],linewidth=.5)
    axes[0].set_yscale('log');axes[0].set_ylabel('$T_b$ p95 (s)')
    axes[1].set_ylabel('$P(T_b\leq B)$ (%)');axes[1].set_ylim(-3,103);axes[1].set_yticks([0,50,100])
    for ax,title in zip(axes,['(a) Outcome tail','(b) Budget attainment']):
        ax.set_title(title,fontsize=7.2);ax.set_xlabel('Injected D (s)')
        ax.set_xticks([0,.5,2],['0','.5','2']);ax.grid(axis='y',color='#dddddd',linewidth=.4)
    handles=[Line2D([],[],color=RHO_COLORS[i],label=r'$\rho_0='+str(rho)+'$') for i,rho in enumerate([.5,.8,.95])]
    handles += [Line2D([],[],color='#444444',linestyle=line,marker=mark,markersize=3,label=name)
                for name,line,mark in [('Transport','-','o'),('Edge','--','s')]]
    fig.legend(handles=handles,loc='upper center',bbox_to_anchor=(.55,1.),ncol=3,frameon=False,
               fontsize=6.8,handlelength=1.4,columnspacing=.8,labelspacing=.25)
    export(fig,out,'e2-load')


def fmt(v):return 'N/A' if v is None else f'{v:.3f}'


def metric_ledger(sparse, load, out):
    """Every controlled and empirical condition, including unavailable endpoints."""
    rows = []

    def add(identity, values, timing):
        row = dict(identity)
        row.update(reference_budget_s=values['reference_budget_s'],
                   D_over_Ta_median=values['D_over_Ta_median'],
                   D_over_Tb_median=values['D_over_Tb_median'])
        for name, stats in [('D', timing['D']), ('Ta', values['Ta']), ('Tb', values['Tb'])]:
            row[name+'_observed_n'] = stats['observed_n']
            for quantile in ['p50', 'p95']:
                row[name+'_'+quantile+'_s'] = stats[quantile+'_s']
                bounds = stats['ci95_'+quantile+'_s']
                row[name+'_'+quantile+'_ci95_lo_s'] = bounds[0] if bounds else None
                row[name+'_'+quantile+'_ci95_hi_s'] = bounds[1] if bounds else None
        for budget, endpoints in values['budgets'].items():
            for endpoint, stats in endpoints.items():
                prefix = endpoint+'_budget_'+budget+'s_'
                for k in ['numerator', 'denominator', 'value']:
                    row[prefix+k] = stats[k]
                row[prefix+'ci95_lo'] = stats['ci95'][0]
                row[prefix+'ci95_hi'] = stats['ci95'][1]
        rows.append(row)

    for di, domain in enumerate(sparse['domains']):
        for ci, cell in enumerate(domain['cells']):
            add(dict(arm='sparse', domain=domain['domain'], condition='controlled',
                     requested_D_s=cell['injected_delay_s'], baseline_rho=None, rho=None,
                     lambda_per_s=None, arrivals=cell['n'],
                     source_json='sparse-results.json', source_pointer=f'/domains/{di}/cells/{ci}',
                     raw_records=sparse['source_run']+'/'+domain['domain']+'/records.jsonl'), cell, cell)
    for i, cell in enumerate(load['cells']):
        for domain, values in cell['domains'].items():
            identity = cell.get('identity') or {}
            add(dict(arm='load', domain=domain, condition=cell['condition'],
                     requested_D_s=cell['requested_D_s'], baseline_rho=cell['baseline_rho'],
                     rho=cell['rho'], lambda_per_s=cell['lambda_per_s'],
                     arrivals=cell['postwarm_arrivals'], study=identity.get('study'),
                     task=identity.get('task'), method=identity.get('method'),
                     platform=identity.get('platform'), collection_phase=identity.get('collection_phase'),
                     source_json='load-results.json', source_pointer=f'/cells/{i}/domains/{domain}',
                     raw_records=load['source_run']+'/'+cell['cell_id']+'.jsonl',
                     raw_records_sha256=cell['source_records_sha256']), values, cell)
    assert len(rows) == 176 and len({(r['arm'], r['domain'], r['condition'],
                                   r['requested_D_s'], r['baseline_rho']) for r in rows}) == 176
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with (out/'all-results.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return dict(rows=len(rows), sparse_domain_conditions=8, controlled_load_domain_conditions=24,
                empirical_load_domain_conditions=144,
                missing='Blank numeric cells mean unavailable, not zero.',
                fractions='Budget attainment and decision shares are fractions; durations are seconds.',
                source_scope='Summary JSON pointers resolve every row; raw records and analysis manifests retain provenance.')


def results_table(sparse,load,out):
    text=[r'\begin{table*}[t]',r'\centering',
        r'\caption{RQ-F: fixed-action timing and load. Latencies are p50 / p95 in seconds, conditional on observed acknowledgement or verified outcome; $n_v/n$ reports verified outcomes and all arrivals. $D/T_a$ and $D/T_b$ are median percentages. Budget attainment uses all arrivals and gives a 95\% scene- or time-block interval; $B=10$\,s for transport and $2$\,s for edge. $\rho=\lambda E[S]$ is the measured decision-slot load; N/A denotes the sparse arm. Bold marks the lowest latency pair and highest budget attainment within each group, including ties. Load outcomes replay measured execution residuals after real FIFO decision queues.}',
        r'\label{tab:e2-results}',r'\footnotesize',r'\setlength{\tabcolsep}{4pt}',r'\renewcommand{\arraystretch}{1.07}',
        r'\begin{tabular}{@{}rrrrrrrr@{}}',r'\toprule',r'\rowcolor{ebBlue}',
        r'$D$ (s) & $n_v/n$ & $T_a$ p50 / p95 & $T_b$ p50 / p95 & $D/T_a$ & $D/T_b$ & $P(T_b\leq B)$ & $\rho$ \\',r'\midrule']
    row_index=[]
    def group(name,rows):
        text.extend([r'\rowcolor{ebAmber!35}',r'\multicolumn{8}{@{}l}{\textbf{'+name+r'}} \\'])
        best={endpoint:min((values[endpoint]['p50_s'],values[endpoint]['p95_s'])
                  for _,_,values,_,_ in rows) for endpoint in ['Ta','Tb']}
        best_probability=max(values['budgets'][str(values['reference_budget_s'])]['Tb']['value']
                             for _,_,values,_,_ in rows)
        for d,n,values,rho,key in rows:
            p=values['budgets'][str(values['reference_budget_s'])]['Tb']
            probability=f"{100*p['value']:.1f} [{100*p['ci95'][0]:.1f}, {100*p['ci95'][1]:.1f}]"
            share=lambda name: 'N/A' if values[name] is None else f"{100*values[name]:.1f}"
            def latency(endpoint):
                v=values[endpoint]; result=fmt(v['p50_s'])+' / '+fmt(v['p95_s'])
                return r'\textbf{'+result+'}' if (v['p50_s'],v['p95_s'])==best[endpoint] else result
            if p['value']==best_probability:probability=r'\textbf{'+probability+'}'
            text.append(' & '.join([f'{d:g}',f"{values['Tb']['observed_n']}/{n}",
                latency('Ta'),latency('Tb'),
                share('D_over_Ta_median'),share('D_over_Tb_median'),probability,fmt(rho)])+r' \\')
            row_index.append(dict(key=key,source_values=values))
        text.append(r'\midrule')
    for domain in ['transport','edge']:
        ds=next(d for d in sparse['domains'] if d['domain']==domain)
        group(domain.title()+'---sparse physical execution',[(c['injected_delay_s'],c['n'],c,None,
              'sparse/'+domain+'/'+str(c['injected_delay_s'])) for c in ds['cells']])
        for rho in [.5,.8,.95]:
            cells=sorted([c for c in load['cells'] if c['type']=='controlled' and c['baseline_rho']==rho],key=lambda c:c['requested_D_s'])
            group(domain.title()+rf'---queue + execution replay, $\rho_0={rho}$, $\lambda={cells[0]["lambda_per_s"]:.3f}$\,/s',
                [(c['requested_D_s'],c['postwarm_arrivals'],c['domains'][domain],c['rho'],c['cell_id']+'/'+domain) for c in cells])
    text[-1]=r'\bottomrule'
    text.extend([r'\end{tabular}',r'\end{table*}'])
    (out/'tab-e2-results.tex').write_text('\n'.join(text)+'\n')
    (out/'table-source-values.json').write_text(json.dumps(row_index,indent=2,allow_nan=False)+'\n')


def main():
    p=argparse.ArgumentParser();p.add_argument('--sparse',type=Path,required=True)
    p.add_argument('--load',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();sparse=json.loads(a.sparse.read_text());load=json.loads(a.load.read_text())
    assert sparse['status']=='E2_SPARSE_ANALYZED_LOAD_PENDING'
    assert load['status']=='E2_LOAD_REPLAY_ANALYZED' and load['purpose']=='formal_load_replay'
    a.out.mkdir(parents=True,exist_ok=True)
    style();plt.rcParams.update({'mathtext.fontset':'stix','axes.linewidth':.6,'xtick.major.width':.5,'ytick.major.width':.5})
    ran=ran_stages()
    paths_figure(sparse,ran,a.out);load_figure(load,a.out);results_table(sparse,load,a.out)
    ledger=metric_ledger(sparse,load,a.out)
    captions={
        'e2-paths': 'Execution-path decomposition. (a) Original 6G C3 records (30 per implementation); '
        '(b,c) fixed-action transport and edge interventions (30 scenes, ten physical repeats per delay); '
        '(d) verified-outcome median with 95% scene-cluster intervals. Stacks sum stage medians, which need '
        'not equal the median total. RAN conditions on observed ACK and KPM endpoints: '
        'Jev/DS/GLM/Qw-F/Any/SemIf/Qw-J retain 30/30/28/29/27/29/30 of 30 arrivals. '
        'The signed KPM-minus-ACK segment retains six gaps from -2.7 to -0.5 ms. '
        'RAN uses the complete decision wall interval, subsequent gNB acknowledgement '
        '(including control-path waits), and the observed KPM-change upper bound. KPM is not verified service success. '
        'DS: DeepSeek; Qw-F: Qwen Flash; Qw-J: Qwen JSON; Any: AnyJev. Cross-domain comparison is descriptive.',
        'e2-load': 'Finite-window queue amplification. (a) Replayed verified-outcome p95; (b) fraction of all '
        'post-warmup arrivals meeting the task budget (transport 10 s; edge 2 s). Colours identify baseline loads '
        'rho_0; line style and marker identify the domain. Arrival rate is fixed across injected delays within '
        'each baseline load. The 60 s warmup is followed by twenty 10 s arrival blocks and complete draining; '
        'intervals resample whole blocks. Delay occupies the real decision slot; execution residuals are paired '
        'draws from physical D=0 records. Overloaded curves describe a finite nonstationary window.'}
    (a.out/'captions.json').write_text(json.dumps(captions,indent=2)+'\n')
    manifest=dict(experiment='EXP-023-decision-path-intervention',generator=str(Path(__file__).relative_to(ROOT)),
        code_sha256=sha(Path(__file__)),source_sha256={str(a.sparse):sha(a.sparse),str(a.load):sha(a.load)},
        ran_sources=ran,edge_style_commit='86102e9',
        placements={'e2-paths':dict(columns=2,width_in=7.0,height_in=2.62,panels_per_row=4),
                    'e2-load':dict(columns=1,width_in=3.375,height_in=2.80,panels_per_row=2)},
        table_design='32 controlled rows, 8 metrics columns, domain/arm/rho groups; full width to preserve '
                     'both latency endpoints, verification counts, decision shares, budget interval and load. '
                     'Empirical replay strata remain fully available in load-results.json.',
        full_metric_ledger=ledger,
        visual_qa='PENDING final-width agent inspection; not human sign-off')
    (a.out/'figure-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('E2 figures/table generated; final-width visual and source QA required.')


if __name__=='__main__':main()

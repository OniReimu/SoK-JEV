"""Restyle frozen SoK evidence with the advisor's Edge/6G visual grammar.

This renderer performs no inference, bootstrap, model calls or experiment runs.
Native proportions and intervals come from the frozen summaries. Deadline curves
are descriptive ECDFs of the same selected original batches. SVGs retain text.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import colorsys
import re
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'paper-sok-csur/figures/family'
RECEIPT = ROOT / 'artifacts/sok/style-migration/figures.json'
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT/'scripts'))
SOURCE_FILES = [
    'artifacts/sok/cross-study/results.json', 'artifacts/sok/e1/results.json',
    'docs/sok/e0-current/analysis/results.json',
    'experiments/EXP-023-decision-path-intervention/analysis-sparse-108308/sparse-results.json',
    'experiments/EXP-023-decision-path-intervention/analysis-load-108310/load-results.json',
    'artifacts/sok/cross-study/records.jsonl',
]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(s): return json.loads((ROOT/s).read_text())
S, E, A, SPARSE, LOAD = [read(s) for s in SOURCE_FILES[:5]]
CELLS = {(r['study'], r['task'], r['condition'], r['method']): r for r in S['cells']}
PALETTE = dict(Jev='#ED8683', DeepSeek='#ECD7BC', SemIf='#DCE3F0',
    **{'Qwen JSON':'#F7D3D2', 'GLM 5.3':'#F4CC79', 'Qwen 3.8':'#B9C6E0',
       'AnyJev':'#CCFDFE', 'Laya':'#CCFDFE', 'Gemini':'#DCE3F0',
       'GLM 4.7':'#D5C4DD', 'Qwen 3.5':'#B9C6E0', 'Full rule':'#F2F2EE',
       'Lexical rule':'#F2F2EE', 'Task rules':'#F2F2EE', 'MiniLM':'#C7D7C6',
       'DistilBERT F':'#CCCCCC', 'DistilBERT R':'#BAC6B5',
       'Link-only':'#DDDDDD', 'First entry':'#BBBBBB', 'Per-stage rule':'#DDDDDD',
       'Ungated rule':'#CCCCCC'})
EDGE = [('Jev-1.13.0','Jev'), ('DeepSeek-V4.1-Flash','DeepSeek'),
        ('SemIf-Qwen3.5-4B@cuda','SemIf'), ('Qwen3.5-4B-JSON@cuda','Qwen JSON')]
SIX = [('Jev-1.13.0','Jev'), ('DeepSeek-V4.1-Flash','DeepSeek'),
       ('SemIf-Qwen3.5-4B','SemIf'), ('Qwen3.5-4B-JSON','Qwen JSON'),
       ('GLM-5.3-Flash','GLM 5.3'), ('Qwen3.8-Flash','Qwen 3.8'), ('AnyJev-L0','AnyJev')]
SOK = [('jev','Jev'), ('deepseek','DeepSeek'), ('gemini','Gemini'),
       ('glm47','GLM 4.7'), ('qwen','Qwen 3.5'), ('rule','Full rule')]
MARKERS = ['o','s','^','D','v','P','X','h']
MARK_FOR = dict(Jev='o', DeepSeek='D', SemIf='s', **{'Qwen JSON':'X','GLM 5.3':'v','Qwen 3.8':'P','AnyJev':'^','Laya':'^','Gemini':'^','GLM 4.7':'v','Qwen 3.5':'P','Full rule':'X'})
ORDER = ['Jev','SemIf','Laya','AnyJev','DeepSeek','GLM 5.3','Qwen 3.8',
         'Qwen JSON','Gemini','GLM 4.7','Qwen 3.5','DistilBERT F','DistilBERT R',
         'MiniLM','Full rule','Lexical rule','Task rules','Link-only','Per-stage rule',
         'Ungated rule','First entry']
# Figure labels stay compact, as in the 6G reference. The manuscript roster
# binds these aliases to exact versions and deployment/task identities.
LABEL = {'Jev':'Jev','AnyJev':'AnyJev-L0','Qwen JSON':'Qwen-JSON',
         'Gemini':'Gemini 3.1','DistilBERT F':'DistilBERT frozen',
         'DistilBERT R':'DistilBERT retrained'}
def ordered(names): return sorted(dict.fromkeys(names),key=lambda n:ORDER.index(n))
def ordered_methods(methods): return sorted(methods,key=lambda v:ORDER.index(v[1]))
EDGE, SIX, SOK = [ordered_methods(ms) for ms in [EDGE,SIX,SOK]]
def hatch_for(name):
    return '////' if name in ['SemIf','Laya','AnyJev','Qwen JSON','Qwen 3.5','MiniLM'] else {
        'Full rule':'','Lexical rule':'..','Task rules':'..','Link-only':'xx',
        'Per-stage rule':'//','Ungated rule':'\\\\','First entry':'++',
        'DistilBERT F':'..','DistilBERT R':'xx'}.get(name,'')
def marker_for(name): return MARK_FOR.get(name, 'h')
ARTIFACTS = []
plt.rcParams.update({'font.family':'serif', 'font.serif':['Times New Roman','Times','Nimbus Roman','DejaVu Serif'],
    'font.size':7, 'mathtext.fontset':'stix', 'axes.labelsize':8, 'xtick.labelsize':7,
    'ytick.labelsize':7, 'legend.fontsize':7, 'axes.linewidth':.6, 'pdf.fonttype':42,
    'svg.fonttype':'none', 'svg.hashsalt':'jev-sok-family', 'axes.spines.top':False, 'axes.spines.right':False,
    'axes.axisbelow':True, 'hatch.linewidth':.4, 'axes.labelpad':1.5,
    'xtick.major.size':2.5, 'ytick.major.size':2.5,
    'figure.constrained_layout.h_pad':.024, 'figure.constrained_layout.w_pad':.024,
    'figure.constrained_layout.hspace':0, 'figure.constrained_layout.wspace':0})
LAYOUTS = []

def dark(color):
    import matplotlib.colors as mc
    h,l,s = colorsys.rgb_to_hls(*mc.to_rgb(color))
    return colorsys.hls_to_rgb(h, max(.12,l-.35), s)
def model_line(name):
    return '--' if name in ['SemIf','Qwen JSON','Qwen 3.5','Laya','MiniLM'] else '-.' if 'rule' in name.lower() else '-'
def finish(fig, name, kind='panel'):
    fig.canvas.draw()
    LAYOUTS.append(dict(name=name,kind=kind,canvas_in=fig.get_size_inches().tolist(),
        axes_in=[[float(v*s) for v,s in zip(ax.get_position().bounds,
                  [*fig.get_size_inches(),*fig.get_size_inches()])] for ax in fig.axes]))
    for ext in ['pdf','svg']:
        p = OUT/(name+'.'+ext); fig.savefig(p, metadata={'CreationDate':None,'ModDate':None} if ext=='pdf' else {'Date':None})
        ARTIFACTS.append(dict(path=str(p.relative_to(ROOT/'paper-sok-csur')),sha256=sha(p),kind=kind))
    plt.close(fig)
def panel(name, i, ylabel='', xlabel='', width=1.70):
    fig, ax = plt.subplots(figsize=(width,1.30), layout='constrained')
    ax.set_ylabel(ylabel, labelpad=1.5); ax.set_xlabel(xlabel,labelpad=1.5)
    ax.tick_params(length=2.5, width=.6, pad=1.5)
    ax.grid(axis='y', color='#D9D9D9', linewidth=.5, zorder=0)
    return fig, ax

def legend(name, handles, width=7, columns=7):
    fig = plt.figure(figsize=(width,.25))
    # Match the reference's measured-width strip; a fixed column count can clip
    # long identities or silently change the whitespace around the plot row.
    for nc in range(min(columns,len(handles)),0,-1):
        # Matplotlib fills columns. Transpose the supplied order so the visible
        # legend reads in the same left-to-right order as grouped bars and rows.
        visible_order=[handles[j] for col in range(nc) for j in range(col,len(handles),nc)]
        leg=fig.legend(handles=visible_order,loc='center',ncol=nc,frameon=False,
            handlelength=2,handleheight=.9,handletextpad=.4,columnspacing=.9,
            borderaxespad=0,labelspacing=.3)
        fig.canvas.draw()
        if leg.get_window_extent().width<=.99*fig.bbox.width:break
        leg.remove()
    fig.set_size_inches(width,.07+.155*int(np.ceil(len(handles)/nc)))
    finish(fig,name+'-legend','legend')
def model_handles(names, bars=False):
    return [(Patch(facecolor=PALETTE[n],edgecolor='black',linewidth=.9 if n=='Jev' else .6,
                   hatch=hatch_for(n),label=LABEL.get(n,n)) if bars else
        Line2D([],[],color=dark(PALETTE[n]),marker=marker_for(n),markersize=3,
            markerfacecolor=PALETTE[n],markeredgewidth=.6,
            linestyle=model_line(n),linewidth=1.3 if n=='Jev' else .9,label=LABEL.get(n,n))) for n in ordered(names)]
def accuracy(ax, xs, methods, get):
    for i,(m,n) in enumerate(methods):
        rs = [get(m,x) for x in xs]
        y = np.array([r['accuracy'] for r in rs])*100
        ci = np.array([r['accuracy_ci95'] for r in rs])*100
        ax.fill_between(xs,ci[:,0],ci[:,1],color=PALETTE[n],alpha=.45,linewidth=0,zorder=2)
        ax.plot(xs,y,
            color=dark(PALETTE[n]),marker=marker_for(n),linestyle=model_line(n),
            markersize=3.4 if n=='Jev' else 3,linewidth=1.3 if n=='Jev' else .9,
            markerfacecolor=PALETTE[n],markeredgewidth=.6,zorder=5 if n=='Jev' else 3)
    ax.set_ylim(-3,103); ax.set_yticks([0,50,100])

def grouped(name, i, methods, conditions, labels, get, xlabel='Condition'):
    fig,ax = panel(name,i,'Correct (%)',xlabel)
    methods=ordered_methods(methods)
    x=np.arange(len(conditions)); w=.84/len(methods)
    for j,(m,n) in enumerate(methods):
        rs=[get(m,c) for c in conditions]; y=np.array([r['accuracy'] for r in rs])*100
        ci=np.array([r['accuracy_ci95'] for r in rs])*100; xx=x+(j-(len(methods)-1)/2)*w
        ax.bar(xx,y,width=w,facecolor=PALETTE[n],edgecolor='black',linewidth=.9 if n=='Jev' else .6,zorder=3,
            hatch=hatch_for(n))
        ax.errorbar(xx,y,yerr=np.maximum(0,[y-ci[:,0],ci[:,1]-y]),fmt='none',
            ecolor='black',elinewidth=.5,capsize=.9,zorder=4)
    ax.set_xticks(x,labels);ax.set_xlim(-.5,len(conditions)-.5)
    ax.set_ylim(-3,103); ax.set_yticks([0,50,100])
    finish(fig,f'{name}-{i}')

def rq_a():
    name='rq-a-structure'
    specs=[(EDGE,[4,6,8],lambda m,x:CELLS['Edge','RQ3',f'F{x}_low',m],'Output fields'),
           (SIX,[3,7,21,57],lambda m,x:CELLS['6G','C1',f'c{x}_fresh',m]['target_cluster_subsets']['state_dependent'],'Telemetry cells'),
           (SOK,[4,16,64],lambda m,x:CELLS['SoK','policy',{4:'base',16:'effective16',64:'effective64'}[x],m],'Requirements')]
    for i,(methods,xs,get,xlabel) in enumerate(specs):
        fig,ax=panel(name,i,'Correct (%)',xlabel);accuracy(ax,xs,methods,get)
        if i:
            ax.set_xscale('log',base=2 if i==2 else 10)
        ax.set_xticks(xs,[str(x) for x in xs]);ax.minorticks_off()
        if i==0:
            for j,(m,n) in enumerate(methods):
                ax.plot(xs,[100*get(m,x)['mean_field_error_rate'] for x in xs],color=dark(PALETTE[n]),
                    linestyle=':',marker='x',markersize=2,linewidth=.6)
        finish(fig,f'{name}-{i}')
    fig,ax=panel(name,3,'Δ accuracy (pp)','Padded − base');right=ax.twinx()
    spec=[('Edge','RQ1a','Jev-1.13.0','pad_16384'),('Edge','RQ1a','SemIf-Qwen3.5-4B@cuda','pad_16384'),
          ('SoK','policy','jev','padded'),('SoK','policy','deepseek','padded')]
    rs=[next(r for r in S['contrasts'] if (r['study'],r['task'],r['method'],r['left'],r['right'])==(*v,'base')) for v in spec]
    x=np.arange(4);y=np.array([r['delta_pp'] for r in rs]);ci=np.array([r['ci95_pp'] for r in rs])
    ax.bar(x,y,color='#DCE3F0',edgecolor='black',linewidth=.6)
    ax.errorbar(x,y,yerr=np.maximum(0,[y-ci[:,0],ci[:,1]-y]),fmt='none',ecolor='black',elinewidth=.5,capsize=.9)
    y=np.array([r['paired_median_latency_delta_s'] for r in rs]);ci=np.array([r['latency_ci95_s'] for r in rs])
    right.errorbar(x,y,yerr=np.maximum(0,[y-ci[:,0],ci[:,1]-y]),fmt='D',color=dark('#F4CC79'),markersize=3,elinewidth=.5,capsize=.9)
    right.set_ylabel('Δ return (s)',labelpad=1);right.tick_params(pad=1,length=2);right.spines['right'].set_visible(True)
    ax.set_xticks(x,['C:J','C:S','P:J','P:D']);ax.set_ylim(-100,100);ax.set_yticks([-100,0,100]);ax.axhline(0,color='black',linewidth=.5)
    finish(fig,name+'-3')
    names=['Jev','DeepSeek','SemIf','Qwen JSON','GLM 5.3','Qwen 3.8','AnyJev','Gemini','GLM 4.7','Qwen 3.5','Full rule']
    legend(name,model_handles(names)+[Line2D([],[],color='black',linestyle=':',marker='x',label='Field error (a)'),
        Patch(facecolor='#DCE3F0',edgecolor='black',label='Δ accuracy (d)'),
        Line2D([],[],color=dark('#F4CC79'),marker='D',linestyle='none',label='Δ return (d)')],columns=7)

def rq_b_c_e():
    name='rq-b-observation'
    grouped(name,0,SIX,['fresh','stale','noisy','contradictory'],['Fresh','Stale','Noisy','Conflict'],
        lambda m,c:CELLS['6G','C1','c57_'+c,m]['target_cluster_subsets']['state_dependent'])
    for i,conds,labels in [(1,['missing','stale'],['Missing','Stale']),
                            (2,['conflict','resolved'],['Current','Resolved']),
                            (3,['complete','prose'],['Complete','Prose'])]:
        grouped(name,i,SOK,conds,labels,lambda m,c:CELLS['SoK','service',c,m])
    legend(name,model_handles(list(dict.fromkeys(n for _,n in SIX+SOK)),True),columns=6)
    name='rq-c-coverage'
    edge=EDGE+[('GLM-5.3-Flash','GLM 5.3'),('Qwen3.8-Flash','Qwen 3.8'),('Laya@cuda','Laya'),
        ('DistilBERT-Clf-Frozen','DistilBERT F'),('DistilBERT-Clf-Retrained','DistilBERT R'),('MiniLM-Reranker','MiniLM')]
    grouped(name,0,edge,['seen_supported','unseen_supported'],['Seen','Unseen'],
        lambda m,c:CELLS['Edge','RQ4','churn50',m]['service_top1_subsets'][c])
    grouped(name,1,SOK[:-1]+[('rule','Lexical rule'),('reranker','MiniLM')],
        ['base','rekey','refresh_competition'],['Stable','Rekey','New ×2'],lambda m,c:CELLS['SoK','catalogue',c,m])
    grouped(name,2,SOK+[('connectivity','Link-only'),('first','First entry')],['present','absent'],['Present','Absent'],lambda m,c:CELLS['SoK','route',c,m])
    grouped(name,3,SOK[:-1]+[('rule','Task rules')],['catalogue','route'],['Contract','Route'],lambda m,c:CELLS['SoK',c,'absent',m])
    legend(name,model_handles(list(dict.fromkeys(n for _,n in edge+SOK))+['Lexical rule','Task rules','Link-only','First entry'],True),columns=7)
    name='rq-e-gates';methods=SOK+[('per_stage','Per-stage rule'),('ungated','Ungated rule'),('first','First entry')]
    specs=[('public-independent','independent'),('public-complete','complete'),('public-disjoint','disjoint'),('public-complete','public-independent')]
    for i,(left,right) in enumerate(specs):
        fig,ax=panel(name,i,'Δ correct (pp)','Implementation')
        rs=[next(c for c in S['contrasts'] if (c['study'],c['task'],c['method'],c['left'],c['right'])==('SoK','service',m,left,right)) for m,_ in methods]
        x=np.arange(len(methods));y=np.array([r['delta_pp'] for r in rs]);ci=np.array([r['ci95_pp'] for r in rs])
        for xx,yy,(_,n) in zip(x,y,methods):
            ax.bar(xx,yy,color=PALETTE[n],edgecolor='black',linewidth=.9 if n=='Jev' else .6,hatch=hatch_for(n))
        ax.errorbar(x,y,yerr=np.maximum(0,[y-ci[:,0],ci[:,1]-y]),fmt='none',ecolor='black',elinewidth=.5,capsize=.9)
        ax.axhline(0,color='black',linewidth=.5);ax.set_ylim(-75,75);ax.set_yticks([-50,0,50])
        ax.set_xticks(x,['J','D','G','L','Q','F','P','U','1']);finish(fig,f'{name}-{i}')
    legend(name,[Patch(facecolor=PALETTE[n],edgecolor='black',linewidth=.6,hatch=hatch_for(n),label=f'{code}: {LABEL.get(n,n)}') for code,(_,n) in zip(['J','D','G','L','Q','F','P','U','1'],methods)],columns=5)

def e1_d():
    name='e1-deadlines';records={}
    for line in (ROOT/SOURCE_FILES[-1]).open():
        r=json.loads(line);records.setdefault(r['source'],[]).append(r)
    selected=[];grid=np.geomspace(.001,30,300)
    specs=[('SoK','policy','base',SOK[:-1]),('Edge','RQ1a','base',EDGE),
           ('6G','C1','c57_fresh',[(m,n) for m,n in SIX if n in ['Jev','DeepSeek','SemIf','AnyJev']])]
    for i,(study,task,condition,methods) in enumerate(specs):
        fig,ax=panel(name,i,'Valid return (%)','Budget $B$ (s)')
        for j,(m,n) in enumerate(methods):
            stratum=max([r for r in E['fixed'] if (r['study'],r['task'],r['condition'],r['method'])==(study,task,condition,m)],key=lambda r:(r['n'],r['collection_phase']))
            rows=[r for source in stratum['source_ids'] for r in records.get(source,[])];assert len(rows)==stratum['n'],(study,m,len(rows),stratum['n'])
            selected.append({k:stratum[k] for k in ['study','task','condition','method','platform','collection_phase','n']})
            y=[100*sum(bool(r['valid']) and r['latency_s'] is not None and r['latency_s']<=b for r in rows)/len(rows) for b in grid]
            ax.plot(grid,y,color=dark(PALETTE[n]),linestyle=model_line(n),linewidth=1.3 if n=='Jev' else .9)
            for b in [.1,1.]:
                p=stratum['probabilities'][str(b)];ci=p['validated_return_ci']['ci95'];v=100*p['validated_return_probability']
                if ci is not None:ax.errorbar(b,v,yerr=np.maximum(0,[[v-100*ci[0]],[100*ci[1]-v]]),fmt=marker_for(n),color=dark(PALETTE[n]),markerfacecolor=PALETTE[n],markeredgewidth=.6,markersize=3.4 if n=='Jev' else 3,ecolor='black',elinewidth=.5,capsize=.9)
        for b in [.1,1.]:ax.axvline(b,color='#888888',linestyle=':',linewidth=.5)
        ax.set_xscale('log');ax.set_xlim(.001,30);ax.set_xticks([.01,.1,1,10],['.01','.1','1','10']);ax.minorticks_off()
        ax.set_ylim(-3,103);ax.set_yticks([0,50,100]);finish(fig,f'{name}-{i}')
    hosted=[('Jev-1.13.0','Jev'),('DeepSeek-V4.1-Flash','DeepSeek'),('GLM-5.3-Flash','GLM 5.3'),('Qwen3.8-Flash','Qwen 3.8')]
    def native(ax,models,study,xkey,ykey,scale=1,line=None):
        for j,(m,n) in enumerate(models):
            rs=sorted([r for r in E['loads'] if r['study']==study and r['method']==m],key=lambda r:r[xkey])
            if rs:ax.plot([r[xkey] for r in rs],[scale*r[ykey] for r in rs],color=dark(PALETTE[n]),linestyle=line or model_line(n),marker=marker_for(n),markerfacecolor=PALETTE[n],markeredgewidth=.6,markersize=3.4 if n=='Jev' else 3,linewidth=1.3 if n=='Jev' else .9)
    fig,ax=panel(name,3,r'$\rho=\lambda E[S]/c$','Arrivals/s')
    for study,line in [('Edge','-'),('6G','--')]:native(ax,hosted,study,'offered_lambda','rho_offered',line=line)
    ax.set_xscale('log');ax.set_yscale('log');ax.set_xticks([.1,1,10],['.1','1','10']);ax.minorticks_off();ax.axhline(1,color='black',linewidth=.5,linestyle=':');finish(fig,name+'-3')
    names=['Jev','DeepSeek','SemIf','Qwen JSON','AnyJev','Gemini','GLM 4.7','Qwen 3.5','GLM 5.3','Qwen 3.8']
    domains=[Line2D([],[],color='black',linestyle=l,label={'Edge':'Service (d)','6G':'RAN (d)'}[s]) for s,l in [('Edge','-'),('6G','--')]]
    legend(name,model_handles(names)+domains,columns=6)
    name='rq-d-load'
    for i,ylabel,xlabel in [(0,'Correct on time (%)','Requests/s'),(1,r'$\rho=\lambda E[S]/4$','Intents/s'),(2,'Queue p95 (s)','Intents/s'),(3,'Native ≤ B (%)',r'Offered $\rho$')]:
        fig,ax=panel(name,i,ylabel,xlabel)
        if i==0:native(ax,EDGE+hosted[2:]+[('Laya','Laya')],'Edge','offered_lambda','native_attainment',100);ax.set_ylim(-3,103);ax.set_yticks([0,50,100])
        elif i in [1,2]:
            native(ax,SIX,'6G','offered_lambda','rho_offered' if i==1 else 'queue_p95_s');ax.set_xscale('log');ax.set_yscale('log');ax.set_xticks([.1,.5,1,2],['.1','.5','1','2']);ax.minorticks_off()
            if i==1:ax.axhline(1,color='black',linewidth=.5,linestyle=':')
        else:
            for study,line in [('Edge','-'),('6G','--')]:native(ax,hosted,study,'rho_offered','native_attainment',100,line)
            ax.set_xscale('log');ax.set_ylim(-3,103);ax.set_yticks([0,50,100]);ax.axvline(1,color='black',linewidth=.5,linestyle=':')
        finish(fig,f'{name}-{i}')
    legend(name,model_handles([n for _,n in SIX]+['Laya'])+[Line2D([],[],color='black',linestyle=l,label={'Edge':'Service (d)','6G':'RAN (d)'}[s]) for s,l in [('Edge','-'),('6G','--')]],columns=5)
    return selected

def audit():
    name='e0-audit';metrics={r['field']:r for r in A['metrics']};groups=['Configuration','Orchestration','Diagnosis']
    specs=[(['tail','deadline'],['p95+','Deadline']),(['load','queue','stability'],['Load','Queue','Stability']),
           (['baseline','roundtrip','gate_separation'],['Nonlearn.','Roundtrip','3 gates']),(['code','data'],['Code','Data'])]
    colors=['#DCE3F0','#F4CC79','#ED8683']
    for i,(fields,labels) in enumerate(specs):
        fig,ax=panel(name,i,'Families (%)','Reporting indicator');x=np.arange(len(fields))
        for j,g in enumerate(groups):
            rs=[metrics[f]['paper_family'][g] for f in fields];y=np.array([r['proportion'] for r in rs])*100;ci=np.array([r['ci95'] for r in rs])*100;xx=x+(j-1)*.25
            ax.bar(xx,y,width=.25,color=colors[j],edgecolor='black',linewidth=.6,zorder=3)
            ax.errorbar(xx,y,yerr=np.maximum(0,[y-ci[:,0],ci[:,1]-y]),fmt='none',ecolor='black',elinewidth=.5,capsize=.9,zorder=4)
        ax.set_xticks(x,labels);ax.set_ylim(0,100);ax.set_yticks([0,50,100]);finish(fig,f'{name}-{i}')
    legend(name,[Patch(facecolor=c,edgecolor='black',label=g+f' (n={len(A["strata"][g])})') for c,g in zip(colors,groups)],columns=3)

def e2():
    spec=importlib.util.spec_from_file_location('e2_renderer',ROOT/'experiments/EXP-023-decision-path-intervention/render_results.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    # Read the signed raw-stage summary from the evidence renderer. Draw all
    # panels here so E2 uses the same geometry and artist grammar as RQ-A--E.
    ran=module.ran_stages()
    stages=[('Decision','#ED8683',''),('Acknowledgement','#ECD7BC','////'),
            ('Outcome / KPM','#CCFDFE','..')]
    domains=[('transport','#DCE3F0','o','-'),('edge','#ED8683','s','--')]
    name='e2-paths'
    for i in range(3):
        fig,ax=panel(name,i,'Stage median (s)','Implementation' if i==0 else 'Injected $D$ (s)')
        if i==0:
            labels=[r['label'] for r in ran];values=np.array([r['stage_medians_s'] for r in ran])
        else:
            cells=next(d for d in SPARSE['domains'] if d['domain']==domains[i-1][0])['cells']
            labels=['0','.1','.5','2']
            values=np.array([[c['stage_medians_s'][k] for k in ['decision','acknowledgement_after_decision','verification_after_acknowledgement']] for c in cells])
        x=np.arange(len(labels));bottom=np.zeros(len(labels))
        for j,(label,color,hatch) in enumerate(stages):
            ax.bar(x,values[:,j],bottom=bottom,width=.68,facecolor=color,edgecolor='black',linewidth=.6,hatch=hatch,zorder=3)
            bottom+=values[:,j]
        ax.set_xticks(x,labels,rotation=45 if i==0 else 0)
        finish(fig,f'{name}-{i}')
    fig,ax=panel(name,3,'Median $T_b$ (s)','Injected $D$ (s)')
    for domain,fill,mark,line in domains:
        cells=next(d for d in SPARSE['domains'] if d['domain']==domain)['cells']
        x=[c['injected_delay_s'] for c in cells];y=[c['Tb']['p50_s'] for c in cells]
        ax.plot(x,y,color=dark(fill),marker=mark,linestyle=line,markersize=3,
                markerfacecolor=fill,markeredgewidth=.6,linewidth=.9)
        for xx,c in zip(x,cells):
            bounds=c['Tb']['ci95_p50_s']
            if bounds:ax.vlines(xx,*bounds,color='black',linewidth=.5)
    ax.set_xticks([0,.5,1,2]);finish(fig,name+'-3')
    handles=[Patch(facecolor=c,edgecolor='black',linewidth=.6,hatch=h,label=l) for l,c,h in stages]
    handles += [Line2D([],[],color=dark(c),marker=m,linestyle=l,markerfacecolor=c,markeredgewidth=.6,markersize=3,linewidth=.9,label=d.title()) for d,c,m,l in domains]
    legend(name,handles,columns=5)
    name='e2-load';fills=['#DCE3F0','#F4CC79','#ED8683']
    for i in range(2):
        fig,ax=panel(name,i,'$T_b$ p95 (s)' if i==0 else '$P(T_b\\leq B)$ (%)','Injected $D$ (s)',width=1.68)
        for rho,fill in zip([.5,.8,.95],fills):
            rows=sorted([r for r in LOAD['cells'] if r['type']=='controlled' and r['baseline_rho']==rho],key=lambda r:r['requested_D_s'])
            assert len(rows)==4
            x=[r['requested_D_s'] for r in rows]
            for domain,_,mark,line in domains:
                vals=[r['domains'][domain] for r in rows]
                metric=[v['Tb'] if i==0 else v['budgets'][str(v['reference_budget_s'])]['Tb'] for v in vals]
                y=[m['p95_s'] if i==0 else 100*m['value'] for m in metric]
                ax.plot(x,y,color=dark(fill),linestyle=line,marker=mark,markersize=3,
                    markerfacecolor=fill,markeredgewidth=.6,linewidth=.9)
                for xx,m in zip(x,metric):
                    bounds=m['ci95_p95_s'] if i==0 else m['ci95']
                    if bounds:ax.vlines(xx,*[v*(1 if i==0 else 100) for v in bounds],color='black',linewidth=.5)
        if i==0:ax.set_yscale('log')
        else:ax.set_ylim(-3,103);ax.set_yticks([0,50,100])
        ax.set_xticks([0,.5,2],['0','.5','2']);finish(fig,f'{name}-{i}')
    handles=[Line2D([],[],color=dark(c),linewidth=.9,label=r'$\rho_0='+str(rho)+'$') for c,rho in zip(fills,[.5,.8,.95])]
    handles += [Line2D([],[],color='#444444',linestyle=l,marker=m,markerfacecolor='white',markeredgewidth=.6,markersize=3,linewidth=.9,label=d.title()) for d,_,m,l in domains]
    legend(name,handles,width=3.36,columns=3)
    return ran

def overview():
    # Keep a full data-figure regeneration from restoring the former overview.
    from sok_concept_figures import render_control
    row = render_control()
    LAYOUTS.append(dict(name='control-boundary',kind='concept',
        canvas_in=[row['width_in'],row['height_in']],axes_in=[]))
    for ext in ['pdf','svg']:
        p=ROOT/row[ext]
        ARTIFACTS.append(dict(path=str(p.relative_to(ROOT/'paper-sok-csur')),
                             sha256=sha(p),kind='concept'))

def main():
    rq_a();rq_b_c_e();selected=e1_d();audit();ran=e2();overview()
    result=dict(status='FROZEN_EVIDENCE_STYLE_RENDER',generator=str(Path(__file__).relative_to(ROOT)),generator_sha256=sha(Path(__file__)),
        sources={s:sha(ROOT/s) for s in SOURCE_FILES},artifacts=ARTIFACTS,layouts=LAYOUTS,selected_deadline_strata=selected,ran_stages=ran,
        boundaries=['No model calls, experiments or bootstrap reruns.','Native intervals retain original estimands.','RAN signed differences and conditional denominators preserved.'])
    RECEIPT.write_text(json.dumps(result,indent=2)+'\n')
    manifest_path=ROOT/'paper-sok-csur/figure-manifest.yml'
    if manifest_path.exists():
        manifest=json.loads(manifest_path.read_text())
        hashes={r['path']:r['sha256'] for r in ARTIFACTS}
        for item in manifest['artifacts']:
            if item['paper_path'] in hashes:item['sha256']=hashes[item['paper_path']]
        manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
    print(f'{len(ARTIFACTS)} vector assets generated')
if __name__=='__main__':main()

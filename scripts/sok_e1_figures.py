"""E1 and RQ-D tables and four-panel figures; distinct native endpoints retained."""
import numpy as np
import matplotlib.pyplot as plt
from sok_cross_study_figures import style, export, COLORS, STYLES, MARKERS


def pretty(x):return '—' if x is None else f'{x:.4f}'


def interval(point,estimate):
    ci=estimate.get('ci95')
    if ci is None:return f'{100*point:.1f}% [区间不可识别]'
    flag='*' if estimate.get('thin_time_coverage') else ''
    return f'{100*point:.1f}% [{100*ci[0]:.1f}, {100*ci[1]:.1f}]{flag}'


def tables(result,out):
    text=['# E1时标与稳定性再分析','',
      '按原研究、任务、条件、实现/部署与来源批次分层；不汇总成引擎类别分布。P(D≤B)主列是格式合法返回；客户端返回耗时的概率另列。语义正确性与服务完成在跨研究表中单独保留。区间来自30秒非重叠时间块、10,000次重抽样、seed42；星号表示不足8个非空时间块。没有时间戳或不足2块时不给时间区间。p99仅描述。','',
      '## 固定输入：全部批次','',
      '|研究/任务/条件|实现（原平台）|来源批次|n|p50 / p95 / p99秒|合法返回≤100ms|合法返回≤1s|时间块数|',
      '|---|---|---|---:|---|---|---|---:|']
    for row in result['fixed']:
        p=row['probabilities'];b1=p['0.1'];b2=p['1.0']
        text.append(f"|{row['study']}/{row['task']}/{row['condition']}|{row['method']} ({row['platform']})|{row['collection_phase']}|{row['n']}|{pretty(row['p50_s'])} / {pretty(row['p95_s'])} / {pretty(row['p99_descriptive_s'])}|{interval(b1['validated_return_probability'],b1['validated_return_ci'])}|{interval(b2['validated_return_probability'],b2['validated_return_ci'])}|{b2['validated_return_ci']['time_blocks']}|")
    text+=['','## 四种预算：两个返回事件分别报告','',
      '|研究/任务/条件/实现/批次|B秒|客户端返回概率|格式合法返回概率 [时间块95%区间]|60秒区间|120秒区间|',
      '|---|---:|---:|---|---|---|']
    for row in result['fixed']:
        for budget,p in row['probabilities'].items():
            text.append(f"|{row['study']}/{row['task']}/{row['condition']}/{row['method']}/{row['collection_phase']}|{budget}|{100*p['response_elapsed_probability']:.1f}%|{interval(p['validated_return_probability'],p['validated_return_ci'])}|{interval(p['validated_return_probability'],p['sensitivity']['60'])}|{interval(p['validated_return_probability'],p['sensitivity']['120'])}|")
    text+=['','## 负载：所有到达为分母','',
      'Edge的offered ρ为“设定到达率×已派发调用的平均槽占用时间÷4”，未派发/拒绝请求的反事实服务时间未观测，因此是需求代理量。accepted ρ使用已派发数量除以原到达跨度。6G全部300个到达均派发，原主轨迹保留。ρ<1只满足必要的平均容量条件，不证明长期稳定。','',
      '|研究/实现/条件|批次|到达/派发|λ设定/观测|c|E[S]秒|offered ρ [CI]|accepted ρ|排队p50/p95秒|原生预算及终点|预算达成比例 [CI]|',
      '|---|---|---|---|---:|---:|---|---:|---|---|---|']
    for row in result['loads']:
        ci=row['rho_ci95'];cistr='区间不可识别' if ci is None else f'{ci[0]:.4f}, {ci[1]:.4f}'
        text.append(f"|{row['study']}/{row['method']}/{row['condition']}|{row['collection_phase']}|{row['n_arrivals']}/{row['n_dispatched']}|{row['offered_lambda']:.3f}/{row['observed_lambda']:.3f}|{row['slots']}|{row['mean_slot_s']:.4f}|{row['rho_offered']:.4f} [{cistr}]|{row['rho_accepted']:.4f}|{pretty(row['queue_p50_s'])}/{pretty(row['queue_p95_s'])}|{row['native_budget_s']}s; {row['native_endpoint']}|{interval(row['native_attainment'],row['native_attainment_ci'])}|")
    text+=['','## 真实路径：按条件与批次保留','',
      'Edge OCR的所有终止事件包括错误和未支持请求；正确服务时间单列。缺少配置下发确认，因此不补造t_a。6G的KPM变化只能作为观测上界，不能等同于业务完成；ell是适配器耗时，与整个决策墙钟区间分别保留。','',
      '|研究/任务/实现/条件|n|端点或阶段|有效观测数|p50秒|p95秒|',
      '|---|---:|---|---:|---:|---:|']
    for row in result['physical_paths']:
        for name,s in row['stages'].items():
            text.append(f"|{row['study']}/{row['task']}/{row['method']}/{row['condition']}|{row['n']}|{name}|{s['n']}|{pretty(s['p50_s'])}|{pretty(s['p95_s'])}|")
    text+=['','|OCR条件/实现|全部到达/支持请求/正确完成|缓存命中|正确完成：全部到达 [CI]|正确完成：支持请求 [CI]|',
      '|---|---|---:|---|---|']
    for row in result['physical_paths']:
        if row['study']!='Edge':continue
        text.append(f"|{row['condition']}/{row['method']}|{row['n']}/{row['supported_n']}/{row['correct_service_n']}|{row['cache_hits']}|{interval(row['correct_all_probability'],row['correct_all_ci'])}|{interval(row['correct_supported_probability'],row['correct_supported_ci'])}|")
    text+=['','SoK没有独立开放到达率的固定/串行在线子集，ρ不可识别，不用执行完成时间或人为速率补造。','',
      '所有时间块数、60/120秒敏感性、原始文件路径及逐单元机器可读数据见results.json。每个数字以源路径和逐条时间为依据；限定见docs/sok/cross-study-synthesis.md。']
    (out/'tables.md').write_text('\n'.join(text)+'\n')


def render(result,records,out):
    style()
    fixed=result['fixed'];loads=result['loads']
    fig,axes=plt.subplots(1,4,figsize=(7.16,4.15))
    fig.subplots_adjust(left=.075,right=.985,top=.88,bottom=.36,wspace=.48)
    specs=[('SoK','policy','base',[('jev','Jev'),('deepseek','DeepSeek'),('gemini','Gemini'),('glm47','GLM 4.7'),('qwen','Qwen 3.5')]),
           ('Edge','RQ1a','base',[('Jev-1.13.0','Jev'),('DeepSeek-V4.1-Flash','DeepSeek'),('SemIf-Qwen3.5-4B@cuda','SemIf'),('Qwen3.5-4B-JSON@cuda','Qwen JSON')]),
           ('6G','C1','c57_fresh',[('Jev-1.13.0','Jev'),('DeepSeek-V4.1-Flash','DeepSeek'),('SemIf-Qwen3.5-4B','SemIf'),('AnyJev-L0','AnyJev')])]
    grid=np.geomspace(.001,30,300)
    selected_strata=[]
    for ax,(study,task,condition,methods),letter in zip(axes[:3],specs,'abc'):
        for j,(m,label) in enumerate(methods):
            candidates=[r for r in fixed if (r['study'],r['task'],r['condition'],r['method'])==(study,task,condition,m)]
            stratum=max(candidates,key=lambda r:(r['n'],r['collection_phase']))
            selected_strata.append({k:stratum[k] for k in ['study','task','condition','method','platform','collection_phase','n']})
            source=set(stratum['source_ids']);rows=[r for r in records if r['source'] in source]
            assert len(rows)==stratum['n']
            y=[sum(bool(r['valid']) and r['latency_s'] is not None and r['latency_s']<=b for r in rows)/len(rows) for b in grid]
            ax.plot(grid,y,color=COLORS[j],linestyle=STYLES[j],linewidth=.9,label=f'{label} (n={len(rows)})')
            for budget in [.1,1.]:
                p=stratum['probabilities'][str(budget)];ci=p['validated_return_ci']['ci95'];v=p['validated_return_probability']
                if ci is not None:ax.errorbar(budget,v,yerr=np.maximum(0,[[v-ci[0]],[ci[1]-v]]),fmt=MARKERS[j],color=COLORS[j],markersize=2.6,elinewidth=.45,capsize=1)
        for b in [.1,1.]:ax.axvline(b,color='#888888',linestyle=':',linewidth=.5)
        ax.set_xscale('log');ax.set_xlim(.001,30);ax.set_xticks([.01,.1,1,10],['.01','.1','1','10']);ax.set_ylim(-.02,1.02)
        ax.set_yticks([0,.5,1]);ax.grid(axis='y',color='#dddddd',linewidth=.4);ax.set_xlabel('Budget B (s)')
        ax.set_title(f'({letter}) {study}: {task}, {condition}',fontsize=7.1)
        ax.legend(loc='upper center',bbox_to_anchor=(.5,-.25),fontsize=6.2,frameon=False,ncol=1,handlelength=1.5,labelspacing=.12)
    axes[0].set_ylabel('P(validated return ≤ B)')
    ax=axes[3]
    models=[('Jev-1.13.0','Jev'),('DeepSeek-V4.1-Flash','DeepSeek'),('SemIf-Qwen3.5-4B','SemIf'),('Qwen3.5-4B-JSON','Qwen JSON')]
    rho_models=[('Jev-1.13.0','Jev'),('DeepSeek-V4.1-Flash','DS'),('GLM-5.3-Flash','GLM'),('Qwen3.8-Flash','Qwen')]
    for j,(m,name) in enumerate(rho_models):
        for study,line,mark in [('Edge','-',MARKERS[j]),('6G','--',MARKERS[j])]:
            rows=sorted([r for r in loads if r['study']==study and r['method']==m],key=lambda r:r['offered_lambda'])
            ax.plot([r['offered_lambda'] for r in rows],[r['rho_offered'] for r in rows],color=COLORS[j],
                    linestyle=line,marker=mark,markersize=2.5,linewidth=.8,label=('E ' if study=='Edge' else 'R ')+name)
    ax.axhline(1,color='#555555',linestyle=':',linewidth=.8);ax.set_xscale('log');ax.set_yscale('log')
    ax.set_xticks([.1,1,10],['.1','1','10']);ax.set_xlabel('Offered arrivals/s');ax.set_ylabel('ρ = λE[S]/c');ax.set_title('(d) Measured slot demand')
    ax.legend(loc='upper center',bbox_to_anchor=(.5,-.25),fontsize=6.0,frameon=False,ncol=2,handlelength=1.1,columnspacing=.6,labelspacing=.12)
    fig.text(.5,.96,'Single task/condition/batch curves; all strata and 10 ms–10 s budget results in the table.',ha='center',fontsize=7)
    fig.text(.5,.035,'30 s time-block CI; largest batch per curve. (d) E: Edge, R: 6G; all implementations in the table.',ha='center',fontsize=6.7)
    export(fig,out,'e1-deadlines')
    result['figure_selected_strata']=selected_strata

    fig,axes=plt.subplots(1,4,figsize=(7.16,4.1))
    fig.subplots_adjust(left=.075,right=.985,top=.88,bottom=.36,wspace=.49)
    for j,(m,name) in enumerate(models):
        edge=sorted([r for r in loads if r['study']=='Edge' and r['method']==m],key=lambda r:r['offered_lambda'])
        six=sorted([r for r in loads if r['study']=='6G' and r['method']==m],key=lambda r:r['offered_lambda'])
        for ax,rows,field in [(axes[0],edge,'native_attainment'),(axes[1],six,'rho_offered'),(axes[2],six,'queue_p95_s')]:
            y=[100*r[field] if field=='native_attainment' else r[field] for r in rows]
            ax.plot([r['offered_lambda'] for r in rows],y,color=COLORS[j],linestyle=STYLES[j],marker=MARKERS[j],
                    markersize=3,linewidth=.8,label=name)
    for j,(m,name) in enumerate([('GLM-5.3-Flash','GLM 5.3'),('Qwen3.8-Flash','Qwen 3.8'),('AnyJev-L0','AnyJev')],4):
        six=sorted([r for r in loads if r['study']=='6G' and r['method']==m],key=lambda r:r['offered_lambda'])
        edge=sorted([r for r in loads if r['study']=='Edge' and r['method']==m],key=lambda r:r['offered_lambda'])
        if edge:axes[0].plot([r['offered_lambda'] for r in edge],[100*r['native_attainment'] for r in edge],color=COLORS[j],linestyle=STYLES[j],marker=MARKERS[j],markersize=3,linewidth=.8,label=name)
        for ax,field in [(axes[1],'rho_offered'),(axes[2],'queue_p95_s')]:
            ax.plot([r['offered_lambda'] for r in six],[r[field] for r in six],color=COLORS[j],linestyle=STYLES[j],marker=MARKERS[j],markersize=3,linewidth=.8,label=name)
    laya=sorted([r for r in loads if r['study']=='Edge' and r['method']=='Laya'],key=lambda r:r['offered_lambda'])
    axes[0].plot([r['offered_lambda'] for r in laya],[100*r['native_attainment'] for r in laya],color=COLORS[6],linestyle=STYLES[6],marker=MARKERS[6],markersize=3,linewidth=.8,label='Laya')
    for j,(m,name) in enumerate(rho_models):
        for study,line in [('Edge','-'),('6G','--')]:
            rows=sorted([r for r in loads if r['study']==study and r['method']==m],key=lambda r:r['offered_lambda'])
            axes[3].plot([r['rho_offered'] for r in rows],[100*r['native_attainment'] for r in rows],
                color=COLORS[j],linestyle=line,marker=MARKERS[j],markersize=2.6,linewidth=.8,label=('E ' if study=='Edge' else 'R ')+name)
    titles=['(a) Edge: correct + timely','(b) 6G: slot utilization','(c) 6G: queue tail','(d) Native budget attainment']
    for ax,title in zip(axes,titles):
        ax.set_title(title,fontsize=7.1);ax.grid(color='#dddddd',linewidth=.4)
        ax.legend(loc='upper center',bbox_to_anchor=(.5,-.26),fontsize=6.3,frameon=False,ncol=2,
                  columnspacing=.5,handlelength=1.3,labelspacing=.12)
    axes[0].set_xlabel('Requests/s');axes[0].set_ylabel('Correct on time (%)');axes[0].set_ylim(-3,103)
    for ax in axes[1:3]:ax.set_xscale('log');ax.set_xticks([.1,.5,1,2],['.1','.5','1','2']);ax.set_xlabel('Intents/s');ax.set_yscale('log')
    axes[1].set_ylabel('ρ = λE[S]/4');axes[1].axhline(1,color='#555555',linestyle=':',linewidth=.7)
    axes[2].set_ylabel('Queue p95 (s)')
    axes[3].set_xscale('log');axes[3].set_xlabel('ρ (offered demand)');axes[3].set_ylabel('Native endpoint ≤ B (%)')
    axes[3].set_ylim(-3,103);axes[3].axvline(1,color='#555555',linestyle=':',linewidth=.7)
    fig.text(.5,.96,'Distinct native outcomes; observed single-trace trends, no cross-domain pooled effect.',ha='center',fontsize=7)
    fig.text(.5,.035,'Edge: strict modeled service ≤2 s. 6G: scheduled installable policy ≤1 s. (d) E: Edge, R: 6G.',ha='center',fontsize=6.7)
    export(fig,out,'rq-d-load')

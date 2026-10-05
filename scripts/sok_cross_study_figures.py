"""Advisor-specified RQ-A/B plots from source-traced secondary statistics."""
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

COLORS=['#597DB0','#DC9C3E','#B74F52','#609278','#8C6CAA','#777777','#37A3AF','#A47053']
STYLES=['-','--','-.',':','-','--',':','-.']
MARKERS=['o','s','^','D','v','P','X','h']


def style():
    plt.rcParams.update({'font.family':'Times New Roman','font.size':8,'axes.titlesize':7.4,
        'axes.labelsize':7.4,'xtick.labelsize':7,'ytick.labelsize':7,'pdf.fonttype':42,
        'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False})


def export(fig,out,name):
    for ext in ['pdf','svg','png']:fig.savefig(out/f'{name}.{ext}',dpi=220)
    plt.close(fig)


def render_ab(result,out):
    style()
    cells={(r['study'],r['task'],r['condition'],r['method']):r for r in result['cells']}
    contrasts=result['contrasts']
    fig,axes=plt.subplots(1,4,figsize=(7.16,4.45))
    fig.subplots_adjust(left=.075,right=.915,top=.87,bottom=.37,wspace=.52)
    def curves(ax,methods,xs,get,title,xlabel):
        for i,(method,label) in enumerate(methods):
            records=[get(method,x) for x in xs]
            y=np.array([r['accuracy'] for r in records])*100
            err=np.array([[max(0,(r['accuracy']-r['accuracy_ci95'][0])*100) for r in records],
                          [max(0,(r['accuracy_ci95'][1]-r['accuracy'])*100) for r in records]])
            ax.errorbar(xs,y,yerr=err,color=COLORS[i],linestyle=STYLES[i],marker=MARKERS[i],
                        markersize=3,linewidth=.8,elinewidth=.45,capsize=1,label=label)
        ax.set_title(title);ax.set_xlabel(xlabel);ax.set_ylim(-3,103);ax.set_yticks([0,25,50,75,100])
        ax.grid(color='#dddddd',linewidth=.4);ax.set_xticks(xs)
        ax.legend(loc='upper center',bbox_to_anchor=(.5,-.26),ncol=2,fontsize=6.4,
                  frameon=False,columnspacing=.5,handlelength=1.4,labelspacing=.2)
    edge=[('Jev-1.13.0','Jev'),('DeepSeek-V4.1-Flash','DeepSeek'),
          ('SemIf-Qwen3.5-4B@cuda','SemIf'),('Qwen3.5-4B-JSON@cuda','Qwen JSON')]
    curves(axes[0],edge,[4,6,8],lambda m,x:cells['Edge','RQ3',f'F{x}_low',m],
           '(a) Edge: low density','Output fields')
    for i,(m,_) in enumerate(edge):
        axes[0].plot([4,6,8],[100*cells['Edge','RQ3',f'F{x}_low',m]['mean_field_error_rate'] for x in [4,6,8]],
                     color=COLORS[i],linestyle=':',linewidth=.6,marker='x',markersize=2)
    axes[0].set_ylabel('Exact match / field error (%)')
    sixg=[('Jev-1.13.0','Jev'),('DeepSeek-V4.1-Flash','DeepSeek'),('SemIf-Qwen3.5-4B','SemIf'),
          ('Qwen3.5-4B-JSON','Qwen JSON'),('GLM-5.3-Flash','GLM 5.3'),('Qwen3.8-Flash','Qwen 3.8'),('AnyJev-L0','AnyJev')]
    curves(axes[1],sixg,[3,7,21,57],lambda m,x:cells['6G','C1',f'c{x}_fresh',m]['target_cluster_subsets']['state_dependent'],
           '(b) 6G: fresh telemetry','Cells')
    axes[1].set_xscale('log');axes[1].set_xticks([3,7,21,57],['3','7','21','57'])
    sok=[('jev','Jev'),('deepseek','DeepSeek'),('gemini','Gemini'),('qwen','Qwen 3.5'),('glm47','GLM 4.7'),('rule','Full rule')]
    curves(axes[2],sok,[4,16,64],lambda m,x:cells['SoK','policy',{4:'base',16:'effective16',64:'effective64'}[x],m],
           '(c) SoK: access policy','Requirements')
    axes[2].set_xscale('log',base=2);axes[2].set_xticks([4,16,64],['4','16','64'])
    ax=axes[3];right=ax.twinx();right.spines['right'].set_visible(True)
    selected=[('Edge','RQ1a','Jev-1.13.0','pad_16384','Edge\nJev'),
              ('Edge','RQ1a','SemIf-Qwen3.5-4B@cuda','pad_16384','Edge\nSemIf'),
              ('SoK','policy','jev','padded','SoK\nJev'),
              ('SoK','policy','deepseek','padded','SoK\nDeepSeek')]
    rs=[next(r for r in contrasts if (r['study'],r['task'],r['method'],r['left'],r['right'])==(s,t,m,l,'base'))
        for s,t,m,l,_ in selected]
    x=np.arange(len(rs));y=np.array([r['delta_pp'] for r in rs])
    ax.bar(x,y,width=.6,color='#B9C6E0',edgecolor='#444444',linewidth=.4,label='Accuracy Δ')
    ax.errorbar(x,y,yerr=np.maximum(0,np.array([[v-r['ci95_pp'][0] for v,r in zip(y,rs)],
        [r['ci95_pp'][1]-v for v,r in zip(y,rs)]])),fmt='none',color='#333333',capsize=1,elinewidth=.6)
    delta=np.array([r['paired_median_latency_delta_s'] for r in rs]);ci=np.array([r['latency_ci95_s'] for r in rs])
    right.errorbar(x,delta,yerr=np.maximum(0,np.array([delta-ci[:,0],ci[:,1]-delta])),fmt='D',
                   color='#B87F24',markersize=3,elinewidth=.6,capsize=1,label='Latency Δ')
    ax.axhline(0,color='#555555',linewidth=.6);ax.set_ylim(-100,100);ax.set_yticks([-100,-50,0,50,100])
    ax.set_xticks(x,[r[-1] for r in selected],fontsize=6.2);ax.set_title('(d) Padded − base');ax.set_ylabel('Δ accuracy (pp)')
    right.set_ylabel('Paired Δ latency (s)',fontsize=7);ax.grid(axis='y',color='#dddddd',linewidth=.4)
    h,l=ax.get_legend_handles_labels();h2,l2=right.get_legend_handles_labels()
    ax.legend(h+h2,l+l2,loc='upper center',bbox_to_anchor=(.5,-.26),fontsize=6.5,frameon=False)
    fig.text(.5,.96,'Native axes and endpoints; full method/condition tables retain every implementation.',ha='center',fontsize=7.2)
    fig.text(.5,.06,'(a) dotted crosses: field error; (a–c) 95% Wilson CI; (d) 95% paired stratified bootstrap CI.',ha='center',fontsize=6.9)
    fig.text(.5,.025,'(b) n=150 telemetry-dependent cases; (c) n=120. Padding: Edge 16,384 tokens; SoK original condition.',ha='center',fontsize=6.6)
    export(fig,out,'rq-a-structure')

    fig,axes=plt.subplots(1,4,figsize=(7.16,3.85))
    fig.subplots_adjust(left=.10,right=.99,top=.72,bottom=.16,wspace=.77)
    colors=['#B9C6E0','#F4CC79','#ED8683','#ACD2BE'];hatches=['','///','...','xx']
    def bars(ax,title,labels,series,legend):
        y=np.arange(len(labels));w=.74/len(series)
        for j,(records,name) in enumerate(zip(series,legend)):
            v=np.array([r['accuracy'] for r in records])*100
            ci=np.array([r['accuracy_ci95'] for r in records])*100
            yy=y+(j-(len(series)-1)/2)*w
            ax.barh(yy,v,w,color=colors[j],hatch=hatches[j],edgecolor='#333333',linewidth=.3,label=name,zorder=3)
            ax.errorbar(v,yy,xerr=np.maximum(0,np.array([v-ci[:,0],ci[:,1]-v])),fmt='none',
                        ecolor='#333333',elinewidth=.4,capsize=.6,zorder=4)
        ax.set_yticks(y,labels,fontsize=6.6);ax.invert_yaxis();ax.set_xlim(0,105);ax.set_xticks([0,50,100])
        ax.tick_params(axis='y',length=0,pad=2);ax.grid(axis='x',color='#dddddd',linewidth=.4)
        ax.set_title(title,pad=51,fontsize=7.3)
        ax.legend(loc='lower center',bbox_to_anchor=(.5,1.015),frameon=False,fontsize=6.4,handlelength=1.2,
                  labelspacing=.1,borderaxespad=0)
    bars(axes[0],'(a) 6G: 57 cells',[label for _,label in sixg],
         [[cells['6G','C1',f'c57_{q}',m]['target_cluster_subsets']['state_dependent'] for m,_ in sixg]
          for q in ['fresh','stale','noisy','contradictory']],['Fresh','Stale','Noisy','Contradictory'])
    bars(axes[1],'(b) SoK: refresh',[label for _,label in sok],
         [[cells['SoK','service',q,m] for m,_ in sok] for q in ['missing','stale']],['Missing','Stale'])
    bars(axes[2],'(c) SoK: conflict',[label for _,label in sok],
         [[cells['SoK','service',q,m] for m,_ in sok] for q in ['conflict','resolved']],['Current conflict','Old conflict resolved'])
    bars(axes[3],'(d) SoK: representation',[label for _,label in sok],
         [[cells['SoK','service',q,m] for m,_ in sok] for q in ['complete','prose']],['Complete','Equivalent prose'])
    fig.text(.55,.073,'Correct target or task-specific action (%)',ha='center',fontsize=8)
    fig.text(.55,.023,'95% Wilson CI; 6G n=150 state-dependent cases; SoK n=120 per condition.',ha='center',fontsize=7)
    export(fig,out,'rq-b-observation')

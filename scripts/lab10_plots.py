"""Render reproducible report figures from saved measurements (no new load)."""
import json
import os
os.environ.setdefault("MPLCONFIGDIR", "/tmp/sirius-lab10-matplotlib")
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

out = Path('docs/lab10/results')
rows = json.loads((out/'load-summary.json').read_text())
labels = [f"{r['notifier']}\n{r['users']} users" for r in rows]
colors = ['#b98060' if r['notifier']=='sync' else '#245a48' for r in rows]
fig, axes = plt.subplots(2, 2, figsize=(11, 7), layout='constrained')
for ax, key, title in zip(axes.flat, ['rps', 'p95_ms', 'max_api_cpu_percent', 'max_celery_pending'],
                        ['Throughput (requests/s)', 'HTTP latency p95 (ms)', 'API CPU peak (100% = one core)', 'Celery queue peak (tasks)']):
    values = [r[key] for r in rows]
    bars = ax.bar(labels, values, color=colors)
    ax.bar_label(bars, fmt='%.1f', padding=3)
    ax.set_title(title); ax.set_ylim(0, max(values)*1.22 if max(values) else 1)
    ax.spines[['top','right']].set_visible(False)
fig.suptitle('Lab 10: mixed traffic, 25 s per run; one API process')
fig.savefig(out/'load-comparison.png', dpi=150); plt.close(fig)

values=[]
for label in ['before','after']:
    data=json.loads((out/f'mutation-{label}.json').read_text())
    codes=[v for module in data.values() for v in module['exit_code_by_key'].values()]
    values.append((codes.count(1), codes.count(0)))
fig,ax=plt.subplots(figsize=(6,4),layout='constrained')
ax.bar(['Before','After'],[v[0] for v in values],label='Killed',color='#245a48')
ax.bar(['Before','After'],[v[1] for v in values],bottom=[v[0] for v in values],label='Survived',color='#b98060')
for i,(k,s) in enumerate(values):
    ax.text(i,k/2,str(k),ha='center',va='center',color='white')
    ax.text(i,k+s/2,str(s),ha='center',va='center',color='white')
ax.set_title('mutmut: money.py, same 18 mutants'); ax.set_ylabel('Mutants'); ax.legend(loc='upper right',bbox_to_anchor=(1.4,1))
fig.savefig(out/'mutation-comparison.png',dpi=150);plt.close(fig)

#!/usr/bin/env python3
import argparse
from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]

def main():
    a=argparse.ArgumentParser(); a.add_argument('--profile',default='meeting',choices=['meeting','confidence','full']); x=a.parse_args()
    p=ROOT/'results/raw/encoding_runs.csv'
    if not p.exists(): raise SystemExit('No raw results. Run the experiment first.')
    d=pd.read_csv(p); d=d[(d.profile==x.profile)&(d.status=='ok')&(d.warmup.astype(int)==0)].copy()
    if d.empty: raise SystemExit(f'No successful rows for {x.profile}')
    for c in ['preset','crf','bitrate_kbps','wall_time_seconds']: d[c]=pd.to_numeric(d[c],errors='coerce')
    out=ROOT/'results/plots'; out.mkdir(parents=True,exist_ok=True)

    for preset in sorted(d.preset.dropna().unique()):
        g=d[d.preset==preset].groupby(['crf','tune'],as_index=False).bitrate_kbps.mean().sort_values('crf')
        fig,ax=plt.subplots(figsize=(9,5.5))
        for tune,z in g.groupby('tune'): ax.plot(z.crf,z.bitrate_kbps,marker='o',label=tune)
        ax.set_title(f'Mean Bitrate vs CRF — Preset {int(preset)}'); ax.set_xlabel('CRF'); ax.set_ylabel('Mean bitrate (kbps)'); ax.grid(True,alpha=.25); ax.legend(title='Tune'); fig.tight_layout()
        fn=out/f'mean_bitrate_vs_crf_preset_{int(preset)}_{x.profile}.png'; fig.savefig(fn,dpi=180); plt.close(fig); print('Wrote',fn)

    g=d.groupby('preset',as_index=False).wall_time_seconds.mean().sort_values('preset')
    fig,ax=plt.subplots(figsize=(7,5)); ax.bar(g.preset.astype(str),g.wall_time_seconds); ax.set_title('Mean Encoding Time by Preset'); ax.set_xlabel('Preset'); ax.set_ylabel('Mean wall-clock encoding time (s)'); ax.grid(True,axis='y',alpha=.25); fig.tight_layout()
    fn=out/f'mean_encoding_time_by_preset_{x.profile}.png'; fig.savefig(fn,dpi=180); plt.close(fig); print('Wrote',fn)

    g=d.groupby(['resolution_tier','preset'],as_index=False).wall_time_seconds.mean()
    labels=[]; vals=[]
    for tier in ['720p_or_lower','1080p','2160p_or_higher']:
        for preset in sorted(d.preset.dropna().unique()):
            z=g[(g.resolution_tier==tier)&(g.preset==preset)]
            if not z.empty: labels.append(f'{tier}\nP{int(preset)}'); vals.append(float(z.iloc[0].wall_time_seconds))
    fig,ax=plt.subplots(figsize=(9,5.5)); ax.bar(labels,vals); ax.set_title('Mean Encoding Time by Resolution Tier and Preset'); ax.set_xlabel('Resolution tier / preset'); ax.set_ylabel('Mean wall-clock encoding time (s)'); ax.grid(True,axis='y',alpha=.25); fig.tight_layout()
    fn=out/f'mean_encoding_time_by_resolution_{x.profile}.png'; fig.savefig(fn,dpi=180); plt.close(fig); print('Wrote',fn)

if __name__=='__main__': main()

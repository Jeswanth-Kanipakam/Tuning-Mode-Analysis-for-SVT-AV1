#!/usr/bin/env python3
import argparse
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]

def main():
    a=argparse.ArgumentParser(); a.add_argument('--profile',default='meeting'); x=a.parse_args(); p=ROOT/'results/raw/encoding_runs.csv'
    if not p.exists(): raise SystemExit('No encoding results')
    d=pd.read_csv(p); d=d[(d.profile==x.profile)&(d.status=='ok')&(d.warmup.astype(int)==0)].copy()
    if d.empty: raise SystemExit('No matching successful rows')
    src=d[['dataset','video','resolution_tier','width','height','fps','bit_depth']].drop_duplicates().sort_values(['resolution_tier','dataset','video'])
    br=d.groupby(['preset','tune','crf'],as_index=False).bitrate_kbps.mean().sort_values(['preset','tune','crf'])
    tm=d.groupby('preset',as_index=False).wall_time_seconds.mean(); mem=d.groupby(['resolution_tier','preset'],as_index=False).peak_rss_mib.mean()
    text=['# Jonas Meeting — WP1 Results','', '## Experiment configuration','', '- Video tunes: VQ, PSNR, SSIM, MS-SSIM, VMAF','- Presets: 1, 10','- CRFs: 18, 26, 35, 44, 52, 60','- Timing: wall-clock time','- Memory: peak process-tree RSS','', '## Source videos','',src.to_markdown(index=False),'','## Mean bitrate by CRF','',br.to_markdown(index=False),'','## Mean encoding time by preset','',tm.to_markdown(index=False),'','## Mean peak memory by resolution and preset','',mem.to_markdown(index=False),'','## Expected video-quality evaluation','', 'Decode each bitstream and compare it with its original using PSNR, SSIM, MS-SSIM and VMAF. Use bitrate-quality RD curves and BD-Rate/BD-Quality to compare tuning modes across CRF points. Treat evaluation metrics independently from the encoder tuning objective.','', '## Plots','', 'See `results/plots/` for Jonas\'s requested validation plots.']
    out=ROOT/'results/summary/JONAS_MEETING_REPORT.md'; out.write_text('\n'.join(text)); print('Wrote',out)
if __name__=='__main__': main()

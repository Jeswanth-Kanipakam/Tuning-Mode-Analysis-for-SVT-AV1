#!/usr/bin/env python3
from __future__ import annotations

import argparse, csv, hashlib, json, math, os, platform, re, shlex, shutil, subprocess, sys, time
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any

import pandas as pd
import psutil
import yaml
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
RUN_FIELDS = [
    "experiment_id","timestamp_utc","profile","status","dataset","video","input_path",
    "resolution_tier","width","height","fps","bit_depth","chroma","input_size_bytes",
    "input_md5","input_sha256","tune","tune_value","preset","crf","lp","run","warmup",
    "frames","duration_seconds","encoder_time_ms","wall_time_seconds","average_speed_fps",
    "peak_rss_bytes","peak_rss_mib","output_path","output_size_bytes","bitrate_kbps",
    "output_md5","output_sha256","command","return_code","log_path"
]

def path(v: str|Path) -> Path:
    p = Path(v); return p if p.is_absolute() else ROOT/p

def load_cfg(name: str) -> dict[str,Any]:
    with path(name).open() as f: return yaml.safe_load(f)

def ensure_dirs():
    for d in ["data/source","data/manifests","data/encoded","results/raw","results/summary","results/plots","logs"]:
        path(d).mkdir(parents=True, exist_ok=True)

def tool(name: str) -> str:
    p = shutil.which(name)
    if not p: raise RuntimeError(f"Required tool not found in PATH: {name}")
    return p

def digest(p: Path, algo: str) -> str:
    h=hashlib.new(algo)
    with p.open("rb") as f:
        while b:=f.read(8*1024*1024): h.update(b)
    return h.hexdigest()

def y4m_meta(p: Path) -> dict[str,Any]:
    with p.open("rb") as f: h=f.readline().decode("ascii",errors="ignore")
    m=lambda pat: re.search(pat,h)
    w=m(r"(?:^|\s)W(\d+)"); hh=m(r"(?:^|\s)H(\d+)"); fr=m(r"(?:^|\s)F(\d+):(\d+)"); c=m(r"(?:^|\s)C([^\s]+)")
    fps=(int(fr.group(1))/int(fr.group(2))) if fr and int(fr.group(2)) else None
    chroma=c.group(1) if c else None
    bit=12 if chroma and "12" in chroma else 10 if chroma and "10" in chroma else 8
    return {"width":int(w.group(1)) if w else None,"height":int(hh.group(1)) if hh else None,"fps":fps,"bit_depth":bit,"chroma":chroma}

def tier(w,h):
    if not w or not h: return "unknown"
    long_side, short_side=max(int(w),int(h)),min(int(w),int(h))
    if long_side>=3000 or short_side>=1600: return "2160p_or_higher"
    if long_side>=1600 or short_side>=900: return "1080p"
    return "720p_or_lower"

def scan(cfg):
    ffprobe=tool(cfg["tools"]["ffprobe"]); src=path("data/source")
    vids=sorted([p for p in src.rglob("*.y4m") if p.is_file()])
    if not vids: print("No .y4m files found under data/source/"); return 1
    rows=[]
    for i,p in enumerate(vids,1):
        m=y4m_meta(p)
        # Count frames using ffprobe once during scanning; this can take a little time.
        cmd=[ffprobe,"-v","error","-count_frames","-select_streams","v:0","-show_entries","stream=nb_read_frames","-of","default=nw=1:nk=1",str(p)]
        q=subprocess.run(cmd,capture_output=True,text=True)
        frames=int(q.stdout.strip()) if q.returncode==0 and q.stdout.strip().isdigit() else None
        duration=(frames/m["fps"]) if frames and m["fps"] else None
        print(f"[{i}/{len(vids)}] {p.parent.name}/{p.name} {m['width']}x{m['height']} {m['fps']} fps")
        rows.append({"enabled":1,"dataset":p.parent.name,"video":p.name,"relative_path":str(p.relative_to(src)),
                     "resolution_tier":tier(m["width"],m["height"]),**m,"frames":frames,"duration_seconds":duration,
                     "expected_md5":"","actual_md5":digest(p,"md5"),"sha256":digest(p,"sha256"),"size_bytes":p.stat().st_size})
    out=path("data/manifests/source_manifest.csv"); pd.DataFrame(rows).to_csv(out,index=False)
    print(f"\nWrote {out}"); print(pd.DataFrame(rows)["resolution_tier"].value_counts().to_string()); return 0

def manifest():
    p=path("data/manifests/source_manifest.csv")
    if not p.exists(): raise RuntimeError("Run: python scripts/wp1.py scan")
    df=pd.read_csv(p); return df[df["enabled"].fillna(1).astype(int)==1].copy()

def verify():
    df=manifest(); src=path("data/source"); out=[]; fail=0
    for _,r in df.iterrows():
        p=src/str(r.relative_path)
        if not p.exists(): status,actual="missing",""; fail+=1
        else:
            actual=digest(p,"md5"); exp=str(r.get("expected_md5","")).strip()
            if exp and exp.lower()!="nan": status="ok" if actual.lower()==exp.lower() else "mismatch"; fail += status!="ok"
            else: status="recorded_no_reference"
        print(f"[{status.upper()}] {r.dataset}/{r.video}")
        out.append({"dataset":r.dataset,"video":r.video,"expected_md5":r.get("expected_md5",""),"actual_md5":actual,"status":status})
    pd.DataFrame(out).to_csv(path("results/summary/checksum_report.csv"),index=False); return 1 if fail else 0

def capture(cmd):
    p=subprocess.run(cmd,capture_output=True,text=True); return ((p.stdout or "")+(p.stderr or "")).strip()

def snapshot(cfg):
    enc=tool(cfg["tools"]["encoder"]); ffmpeg=tool(cfg["tools"]["ffmpeg"])
    obj={"timestamp_utc":datetime.now(timezone.utc).isoformat(),"platform":platform.platform(),"machine":platform.machine(),
         "cpu_count_logical":os.cpu_count(),"python":sys.version,"encoder_path":enc,"encoder_version":capture([enc,"--version"]),
         "ffmpeg_path":ffmpeg,"ffmpeg_version":capture([ffmpeg,"-version"]).splitlines()[:3],"config":cfg}
    try: obj["git_commit"]=capture(["git","-C",str(ROOT),"rev-parse","HEAD"])
    except Exception: obj["git_commit"]="unavailable"
    path("results/summary/software_snapshot.json").write_text(json.dumps(obj,indent=2)); return obj

def preflight(cfg):
    bad=0
    for k in ["encoder","ffprobe","ffmpeg"]:
        p=shutil.which(cfg["tools"][k]); print(f"{'OK' if p else 'MISSING'} {cfg['tools'][k]}: {p or ''}"); bad+=p is None
    if bad: return 1
    enc=tool(cfg["tools"]["encoder"]); print("\n"+capture([enc,"--version"]))
    helptext=capture([enc,"--help"])
    m=re.search(r"--tune[^\n]*\[(\d+)\s*-\s*(\d+)\]",helptext)
    if m:
        allowed=set(range(int(m.group(1)),int(m.group(2))+1)); requested={int(t["value"]) for t in cfg["encoder"]["tunes"]}
        if requested-allowed: print("Unsupported tune values:",sorted(requested-allowed)); return 1
        print("Tune range check OK:",sorted(requested))
    snapshot(cfg); print("Presets:",cfg["encoder"]["presets"],"CRFs:",cfg["encoder"]["crfs"]); return 0

def select(df, prof):
    s=prof["selection"]; mode=s["mode"]
    if mode=="all": return df.copy()
    if mode=="resolution_balanced":
        parts=[]
        for t in ["720p_or_lower","1080p","2160p_or_higher"]:
            x=df[df.resolution_tier==t].sort_values(["dataset","video"])
            if not x.empty: parts.append(x.head(int(s.get("per_resolution_tier",1))))
        if not parts: raise RuntimeError("No videos selected")
        return pd.concat(parts,ignore_index=True)
    if mode=="prefer_1080p":
        x=df[df.resolution_tier=="1080p"]
        if x.empty: x=df[df.resolution_tier=="720p_or_lower"]
        if x.empty: x=df
        return x.head(int(s.get("max_videos",1))).copy()
    raise RuntimeError(f"Unknown selection mode {mode}")

def plan(cfg,name):
    p=cfg["profiles"][name]; v=select(manifest(),p)
    measured=len(v)*len(p["tunes"])*len(p["presets"])*len(p["crfs"])*int(p["repetitions"])
    warm=len(v)*len(p["tunes"])*len(p["presets"])*len(p["crfs"])*int(p["warmup_runs"])
    print(v[["dataset","video","resolution_tier","width","height"]].to_string(index=False))
    print(f"\nProfile={name} measured={measured} warmups={warm} total={measured+warm}")
    return v,p

def parse_log(text):
    def grab(pats, cast=float):
        for pat in pats:
            m=re.search(pat,text)
            if m:
                try:return cast(m.group(1))
                except:return None
        return None
    return {"frames":grab([r"Total Frames\s+(\d+)"],int),
            "encoder_time_ms":grab([r"Total Encoding Time:\s*(\d+)\s*ms",r"Total Encoding Time\s+(\d+)\s*ms"],int),
            "average_speed_fps":grab([r"Average Speed:\s*([0-9.]+)\s*fps"]),
            "bitrate_kbps":grab([r"Average Bitrate:\s*([0-9.]+)\s*kbps",r"([0-9.]+)\s*kbps"])}

def tree_rss(p):
    total=0; ps=[p]
    try: ps += p.children(recursive=True)
    except: pass
    for x in ps:
        try: total+=x.memory_info().rss
        except: pass
    return total

def monitored(cmd,log,interval):
    log.parent.mkdir(parents=True,exist_ok=True); peak=0
    with log.open("w") as f:
        st=time.perf_counter(); p=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT,text=True); pp=psutil.Process(p.pid)
        while p.poll() is None:
            try: peak=max(peak,tree_rss(pp))
            except: pass
            time.sleep(interval)
        code=p.wait(); wall=time.perf_counter()-st
    return code,wall,peak,log.read_text(errors="replace")

def command(cfg,src,out,tune,preset,crf,frames=None):
    c=[tool(cfg["tools"]["encoder"]),"-i",str(src),"-b",str(out),"--preset",str(preset),"--crf",str(crf),"--tune",str(tune),"--lp",str(cfg["encoder"]["lp"]),"--progress","1"]
    if frames is not None: c += ["-n",str(frames)]
    return c

def functional_check(cfg,src):
    d=path("results/raw/.preflight"); d.mkdir(parents=True,exist_ok=True)
    for t in cfg["encoder"]["tunes"]:
        o=d/f"{t['name']}.ivf"; o.unlink(missing_ok=True); c=command(cfg,src,o,int(t["value"]),10,52,1)
        p=subprocess.run(c,capture_output=True,text=True)
        if p.returncode or not o.exists(): raise RuntimeError(f"Tune check failed {t['name']}={t['value']}\n{shlex.join(c)}\n{p.stdout}\n{p.stderr}")
        o.unlink(missing_ok=True); print(f"[TUNE OK] {t['name']}={t['value']}")

def eid(*xs): return hashlib.sha256("|".join(map(str,xs)).encode()).hexdigest()[:20]

def completed(p):
    if not p.exists(): return set()
    d=pd.read_csv(p,usecols=["experiment_id","status"]); return set(d.loc[d.status=="ok","experiment_id"].astype(str))

def append(p,row):
    ex=p.exists()
    with p.open("a",newline="") as f:
        w=csv.DictWriter(f,fieldnames=RUN_FIELDS)
        if not ex:w.writeheader()
        w.writerow(row)

def run(cfg,name,dry,limit):
    vids,p=plan(cfg,name); srcroot=path("data/source"); raw=path("results/raw/encoding_runs.csv"); done=completed(raw) if cfg["measurement"].get("resume",True) else set()
    tmap={x["name"]:int(x["value"]) for x in cfg["encoder"]["tunes"]}
    first=srcroot/str(vids.iloc[0].relative_path)
    if not dry: functional_check(cfg,first); snapshot(cfg)
    n=0
    for _,m in vids.iterrows():
      src=srcroot/str(m.relative_path)
      for tune_name in p["tunes"]:
       for preset in p["presets"]:
        for crf in p["crfs"]:
         warm=int(p["warmup_runs"]); reps=int(p["repetitions"])
         for idx in range(1,warm+reps+1):
          iswarm=idx<=warm; runno=idx if iswarm else idx-warm; x=eid(name,m.dataset,m.video,tune_name,preset,crf,runno,iswarm)
          if x in done: print("[RESUME]",x); continue
          if limit is not None and n>=limit: print(f"Stopped after {limit}"); return 0
          n+=1; tag=f"warmup{runno}" if iswarm else f"run{runno}"; stem=f"{Path(str(m.video)).stem}__{tune_name}__p{preset}__crf{crf}__{tag}"
          out=path("data/encoded")/name/str(m.dataset)/(stem+".ivf"); log=path("logs")/name/str(m.dataset)/(stem+".log"); out.parent.mkdir(parents=True,exist_ok=True); out.unlink(missing_ok=True)
          c=command(cfg,src,out,tmap[tune_name],preset,crf); print("$",shlex.join(c))
          if dry: continue
          code,wall,peak,text=monitored(c,log,float(cfg["measurement"]["memory_sample_interval_seconds"])); q=parse_log(text); ok=code==0 and out.exists() and out.stat().st_size>0
          frames=q["frames"] or (int(m.frames) if pd.notna(m.frames) else None); fps=float(m.fps) if pd.notna(m.fps) else None; duration=(frames/fps) if frames and fps else (float(m.duration_seconds) if pd.notna(m.duration_seconds) else None)
          size=out.stat().st_size if ok else 0; br=(size*8/duration/1000) if ok and duration else q["bitrate_kbps"]; speed=q["average_speed_fps"] or ((frames/wall) if frames and wall else None)
          row={"experiment_id":x,"timestamp_utc":datetime.now(timezone.utc).isoformat(),"profile":name,"status":"ok" if ok else "failed","dataset":m.dataset,"video":m.video,"input_path":str(src),"resolution_tier":m.resolution_tier,"width":m.width,"height":m.height,"fps":m.fps,"bit_depth":m.bit_depth,"chroma":m.chroma,"input_size_bytes":m.size_bytes,"input_md5":m.actual_md5,"input_sha256":m.sha256,"tune":tune_name,"tune_value":tmap[tune_name],"preset":preset,"crf":crf,"lp":cfg["encoder"]["lp"],"run":runno,"warmup":int(iswarm),"frames":frames,"duration_seconds":duration,"encoder_time_ms":q["encoder_time_ms"],"wall_time_seconds":round(wall,6),"average_speed_fps":speed,"peak_rss_bytes":peak,"peak_rss_mib":round(peak/1024**2,3),"output_path":str(out) if ok else "","output_size_bytes":size if ok else "","bitrate_kbps":br,"output_md5":digest(out,"md5") if ok else "","output_sha256":digest(out,"sha256") if ok else "","command":shlex.join(c),"return_code":code,"log_path":str(log)}
          append(raw,row); print(f"[{row['status'].upper()}] wall={wall:.2f}s memory={row['peak_rss_mib']}MiB bitrate={br}")
          if ok and (iswarm or (runno>1 and not p.get("keep_all_bitstreams",True))): out.unlink(missing_ok=True)
    return 0

def gstats(g,conf):
    t=pd.to_numeric(g.wall_time_seconds,errors="coerce").dropna(); mem=pd.to_numeric(g.peak_rss_mib,errors="coerce").dropna(); br=pd.to_numeric(g.bitrate_kbps,errors="coerce").dropna(); n=len(t); mean=t.mean(); std=t.std(ddof=1) if n>1 else math.nan
    if n>1 and not math.isnan(std): margin=stats.t.ppf((1+conf)/2,n-1)*std/math.sqrt(n); lo,hi=mean-margin,mean+margin
    else: lo=hi=math.nan
    return pd.Series({"n_runs":n,"mean_wall_time_s":mean,"std_wall_time_s":std,"ci95_low_s":lo,"ci95_high_s":hi,"cv_percent":std/mean*100 if n>1 and mean else math.nan,"mean_peak_rss_mib":mem.mean(),"max_peak_rss_mib":mem.max(),"mean_bitrate_kbps":br.mean()})

def summarize(cfg,name):
    raw=path("results/raw/encoding_runs.csv"); d=pd.read_csv(raw); d=d[(d.status=="ok")&(d.warmup.astype(int)==0)]
    if name:d=d[d.profile==name]
    if d.empty: raise RuntimeError("No successful results")
    groups=["profile","dataset","video","resolution_tier","tune","tune_value","preset","crf"]
    s=d.groupby(groups,dropna=False).apply(lambda g:gstats(g,float(cfg["measurement"]["confidence_level"])),include_groups=False).reset_index(); suf=name or "all"
    s.to_csv(path(f"results/summary/encoding_summary_{suf}.csv"),index=False)
    d.groupby(["profile","preset","tune","crf"],as_index=False).bitrate_kbps.mean().rename(columns={"bitrate_kbps":"mean_bitrate_kbps"}).to_csv(path(f"results/summary/mean_bitrate_by_crf_{suf}.csv"),index=False)
    d.groupby(["profile","preset"],as_index=False).wall_time_seconds.mean().rename(columns={"wall_time_seconds":"mean_encoding_time_s"}).to_csv(path(f"results/summary/mean_encoding_time_by_preset_{suf}.csv"),index=False)
    d.groupby(["profile","resolution_tier","preset"],as_index=False).wall_time_seconds.mean().rename(columns={"wall_time_seconds":"mean_encoding_time_s"}).to_csv(path(f"results/summary/mean_encoding_time_by_resolution_{suf}.csv"),index=False)
    print(f"Summary written for {suf}"); return 0

def validate(name):
    d=pd.read_csv(path("results/raw/encoding_runs.csv")); d=d[d.profile==name] if name else d
    fail=len(d[d.status!="ok"]); m=d[d.warmup.astype(int)==0]; print(f"rows={len(d)} measured={len(m)} failed={fail}"); print(pd.crosstab(m.resolution_tier,m.preset).to_string()); print("\nTunes:\n",m.tune.value_counts().to_string()); print("\nCRFs:\n",m.crf.value_counts().sort_index().to_string()); return 1 if fail else 0

def main():
    a=argparse.ArgumentParser(); a.add_argument("--config",default="config/experiment.yaml"); s=a.add_subparsers(dest="cmd",required=True)
    s.add_parser("preflight"); s.add_parser("scan"); s.add_parser("verify")
    p=s.add_parser("plan"); p.add_argument("--profile",choices=["meeting","confidence","full"],required=True)
    r=s.add_parser("run"); r.add_argument("--profile",choices=["meeting","confidence","full"],required=True); r.add_argument("--dry-run",action="store_true"); r.add_argument("--limit",type=int)
    q=s.add_parser("summarize"); q.add_argument("--profile",choices=["meeting","confidence","full"])
    v=s.add_parser("validate"); v.add_argument("--profile",choices=["meeting","confidence","full"])
    x=a.parse_args(); cfg=load_cfg(x.config); ensure_dirs()
    return {"preflight":lambda:preflight(cfg),"scan":lambda:scan(cfg),"verify":verify,"plan":lambda:plan(cfg,x.profile)[0] is None,"run":lambda:run(cfg,x.profile,x.dry_run,x.limit),"summarize":lambda:summarize(cfg,x.profile),"validate":lambda:validate(x.profile)}[x.cmd]()

if __name__=="__main__": raise SystemExit(main())

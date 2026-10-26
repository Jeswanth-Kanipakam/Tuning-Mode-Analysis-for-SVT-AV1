#!/usr/bin/env python3
"""WP2 - Video quality evaluation.

Scores the bitstreams produced by WP1 (results/raw/encoding_runs.csv) against their
source .y4m files, validates the metrics themselves, and checks robustness against
resolution / chroma subsampling / bit depth / missing frames.

Metrics (one ffmpeg+libvmaf pass): PSNR (Y,Cb,Cr,YUV), SSIM, MS-SSIM, VMAF (+ harmonic mean,
min, 1st percentile, temporal std). Bjontegaard-delta rate (BD-rate) between tunes.

Usage:
  python scripts/wp2.py preflight
  python scripts/wp2.py evaluate --ref a.y4m --dist b.ivf          # ad-hoc, any pair
  python scripts/wp2.py selftest                                    # validate the metrics
  python scripts/wp2.py plan --profile meeting
  python scripts/wp2.py run --profile meeting [--dry-run] [--limit N]
  python scripts/wp2.py validate --profile meeting
  python scripts/wp2.py summarize --profile meeting
  python scripts/wp2.py plot --profile meeting [--video NAME] [--preset N] [--crf N]

File lookup: WP1 stores absolute paths from the machine/user it ran on. Those paths are re-anchored onto this
project's data/encoded and data/source folders; if that fails, files are looked up by file name anywhere below
those folders. Rows whose files still cannot be found are skipped, and a per-dataset summary says which ones.
"""
from __future__ import annotations

import argparse, csv, hashlib, json, math, platform, re, shlex, shutil, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ["meeting", "confidence", "full"]
QUALITY_FIELDS = [
    "experiment_id", "encode_experiment_id", "timestamp_utc", "profile", "status", "dataset", "video",
    "resolution_tier", "tune", "preset", "crf", "bitrate_kbps", "ref_path", "dist_path",
    "width", "height", "pix_fmt", "vmaf_model", "scale_flags", "frames_ref", "frames_scored",
    "psnr_y_mean", "psnr_cb_mean", "psnr_cr_mean", "psnr_yuv_mean", "ssim_mean", "ms_ssim_mean",
    "vmaf_mean", "vmaf_harmonic_mean", "vmaf_min", "vmaf_p1", "vmaf_temporal_std",
    "eval_time_seconds", "command", "return_code", "log_path",
]
METRICS = ["psnr_y_mean", "psnr_yuv_mean", "ssim_mean", "ms_ssim_mean", "vmaf_mean"]


# ----------------------------------------------------------------------------- basics
def path(v: str | Path) -> Path:
    p = Path(v)
    return p if p.is_absolute() else ROOT / p


def load_cfg(name: str) -> dict[str, Any]:
    with path(name).open() as f:
        return yaml.safe_load(f)


def ensure_dirs():
    for d in ["results/raw", "results/summary", "results/plots", "logs/quality"]:
        path(d).mkdir(parents=True, exist_ok=True)


def tool(name: str) -> str:
    p = shutil.which(name)
    if not p:
        raise RuntimeError(f"Required tool not found in PATH: {name}")
    return p


def exists(p: Path) -> bool:
    try:
        return p.exists()
    except OSError:  # e.g. PermissionError on another user's home directory
        return False


_INDEX: dict[str, dict[str, list[Path]]] = {}


def name_index(sub: str) -> dict[str, list[Path]]:
    """File name -> paths for everything below <ROOT>/data/<sub> (built once per run)."""
    if sub not in _INDEX:
        idx: dict[str, list[Path]] = {}
        base = ROOT / "data" / sub
        if exists(base):
            for q in base.rglob("*"):
                try:
                    if q.is_file():
                        idx.setdefault(q.name, []).append(q)
                except OSError:
                    continue
        _INDEX[sub] = idx
    return _INDEX[sub]


def resolve(p) -> Path:
    """Find a file that WP1 recorded under a path from another machine/user.
    1. the path as stored; 2. the part starting at data/encoded or data/source re-anchored onto ROOT;
    3. a lookup by file name below ROOT/data/<encoded|source> (parent folder names break ties)."""
    p = Path(str(p))
    if exists(p):
        return p
    parts = p.parts
    sub = None
    for i, part in enumerate(parts[:-1]):
        if part == "data" and parts[i + 1] in ("encoded", "source"):
            sub = parts[i + 1]
            q = ROOT.joinpath(*parts[i:])
            if exists(q):
                return q
            break
    if sub is None:
        sub = "encoded" if p.suffix.lower() in (".ivf", ".obu", ".mkv", ".mp4") else "source"
    cands = name_index(sub).get(p.name, [])
    if len(cands) == 1:
        return cands[0]
    if len(cands) > 1:
        want = set(parts[:-1])
        return max(cands, key=lambda c: len(want & set(c.parts[:-1])))
    return p


def eid(*xs) -> str:
    return hashlib.sha256("|".join(map(str, xs)).encode()).hexdigest()[:20]


def fesc(p) -> str:
    """Escape a path for use inside an ffmpeg filter option."""
    return str(p).replace("\\", "/").replace(":", "\\:")


def capture(cmd) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True)
    return ((p.stdout or "") + (p.stderr or "")).strip()


# ----------------------------------------------------------------------------- core metric engine
def probe(cfg, p: Path) -> dict[str, Any]:
    q = subprocess.run(
        [tool(cfg["tools"]["ffprobe"]), "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,pix_fmt,r_frame_rate", "-of", "json", str(p)],
        capture_output=True, text=True)
    if q.returncode or not q.stdout.strip():
        raise RuntimeError(f"ffprobe failed on {p}: {q.stderr.strip()}")
    s = json.loads(q.stdout)["streams"][0]
    n, d = s["r_frame_rate"].split("/")
    return {"width": int(s["width"]), "height": int(s["height"]), "pix_fmt": s["pix_fmt"],
            "fps": int(n) / int(d) if int(d) else None}


def build_graph(cfg, r: dict, d: dict, log: Path, flags: str, model: str, fmt: str) -> str:
    """Normalisation policy: distorted stream is rescaled to the reference resolution and both are
    converted to the same pixel format (default: the reference's own) before any metric is computed."""
    W, H = r["width"], r["height"]
    dchain = ["setpts=PTS-STARTPTS"]
    if (d["width"], d["height"]) != (W, H):
        dchain.append(f"scale={W}:{H}:flags={flags}")
    dchain.append(f"format={fmt}")
    rchain = f"setpts=PTS-STARTPTS,format={fmt}"
    m = cfg["metrics"]
    feat = "|".join(f"name={f}" for f in m["features"])
    return (f"[0:v]{','.join(dchain)}[d];[1:v]{rchain}[r];"
            f"[d][r]libvmaf=model=version={model}:feature={feat}:n_threads={m['threads']}"
            f":log_fmt=json:shortest=1:repeatlast=0:log_path={fesc(log)}")


def aggregate(frames: list[dict]) -> dict[str, Any]:
    df = pd.DataFrame([{"n": f["frameNum"], **f["metrics"]} for f in frames])

    def col(c):
        return df[c].astype(float) if c in df else pd.Series(dtype=float)

    y, cb, cr, v = col("psnr_y"), col("psnr_cb"), col("psnr_cr"), col("vmaf")
    yuv = (6 * y + cb + cr) / 8 if len(cb) and len(cr) else pd.Series(dtype=float)
    mean = lambda s: float(s.mean()) if len(s) else math.nan
    return {
        "frames_scored": len(df),
        "psnr_y_mean": mean(y), "psnr_cb_mean": mean(cb), "psnr_cr_mean": mean(cr), "psnr_yuv_mean": mean(yuv),
        "ssim_mean": mean(col("float_ssim")), "ms_ssim_mean": mean(col("float_ms_ssim")),
        "vmaf_mean": mean(v),
        "vmaf_harmonic_mean": float(len(v) / (1.0 / (1.0 + v)).sum() - 1.0) if len(v) else math.nan,
        "vmaf_min": float(v.min()) if len(v) else math.nan,
        "vmaf_p1": float(np.percentile(v, 1)) if len(v) else math.nan,
        "vmaf_temporal_std": float(np.diff(v.values).std()) if len(v) > 2 else math.nan,
    }


def evaluate(cfg, ref: Path, dist: Path, log: Path, tier: str | None = None,
             flags: str | None = None, fmt: str | None = None) -> dict[str, Any]:
    """Score `dist` against `ref`. Never raises on ffmpeg failure; check res['ok']."""
    m = cfg["metrics"]
    r, d = probe(cfg, ref), probe(cfg, dist)
    model = m["vmaf_model_4k"] if tier == "2160p_or_higher" and m.get("vmaf_model_4k") else m["vmaf_model"]
    flags = flags or m["scale_flags"]
    fmt = fmt or m["pix_fmt"]
    fmt = r["pix_fmt"] if fmt == "ref" else fmt
    log.parent.mkdir(parents=True, exist_ok=True)
    log.unlink(missing_ok=True)
    cmd = [tool(cfg["tools"]["ffmpeg"]), "-hide_banner", "-nostdin", "-y", "-i", str(dist), "-i", str(ref),
           "-filter_complex", build_graph(cfg, r, d, log, flags, model, fmt), "-f", "null", "-"]
    st = time.perf_counter()
    p = subprocess.run(cmd, capture_output=True, text=True)
    res = {"ok": False, "cmd": cmd, "code": p.returncode, "wall": time.perf_counter() - st,
           "ref": r, "dist": d, "pix_fmt": fmt, "model": model, "flags": flags, "agg": {}, "error": ""}
    if p.returncode == 0 and log.exists():
        try:
            res["agg"] = aggregate(json.loads(log.read_text())["frames"])
            res["ok"] = res["agg"]["frames_scored"] > 0
        except Exception as ex:  # noqa: BLE001
            res["error"] = f"parse error: {ex}"
    else:
        res["error"] = (p.stderr or "")[-1500:]
    return res


# ----------------------------------------------------------------------------- BD-rate
def bd_rate(r1, q1, r2, q2, min_pts: int = 3) -> float:
    """Bjontegaard delta-rate (%) of curve 2 vs anchor curve 1 at equal quality. Negative = saving."""
    r1, q1, r2, q2 = (np.asarray(x, float) for x in (r1, q1, r2, q2))
    if min(len(q1), len(q2)) < min_pts or (r1 <= 0).any() or (r2 <= 0).any():
        return math.nan
    lo, hi = max(q1.min(), q2.min()), min(q1.max(), q2.max())
    if hi <= lo:
        return math.nan
    deg = min(3, len(q1) - 1, len(q2) - 1)
    i1 = np.polyint(np.polyfit(q1, np.log(r1), deg))
    i2 = np.polyint(np.polyfit(q2, np.log(r2), deg))
    avg = ((np.polyval(i2, hi) - np.polyval(i2, lo)) - (np.polyval(i1, hi) - np.polyval(i1, lo))) / (hi - lo)
    return (math.exp(avg) - 1) * 100


# ----------------------------------------------------------------------------- preflight
def preflight(cfg):
    bad = 0
    for k in ["ffmpeg", "ffprobe"]:
        p = shutil.which(cfg["tools"][k])
        print(f"{'OK' if p else 'MISSING'} {cfg['tools'][k]}: {p or ''}")
        bad += p is None
    if bad:
        return 1
    ff = tool(cfg["tools"]["ffmpeg"])
    print("\n" + capture([ff, "-version"]).splitlines()[0])
    if "libvmaf" not in capture([ff, "-hide_banner", "-filters"]):
        print("MISSING ffmpeg filter: libvmaf (build ffmpeg with --enable-libvmaf)")
        return 1
    print("OK libvmaf filter")
    dec = capture([ff, "-hide_banner", "-decoders"])
    if not any(x in dec for x in ["libdav1d", "libaom-av1", " av1 "]):
        print("MISSING AV1 decoder (libdav1d / libaom-av1)")
        return 1
    print("OK AV1 decoder")
    models = {cfg["metrics"]["vmaf_model"], cfg["metrics"].get("vmaf_model_4k")} - {None}
    for mdl in sorted(models):
        src = "testsrc=size=352x288:rate=5:duration=1,format=yuv420p"
        c = [ff, "-hide_banner", "-nostdin", "-f", "lavfi", "-i", src, "-f", "lavfi", "-i", src,
             "-filter_complex", f"[0:v][1:v]libvmaf=model=version={mdl}", "-f", "null", "-"]
        ok = subprocess.run(c, capture_output=True, text=True).returncode == 0
        print(f"{'OK' if ok else 'FAILED'} VMAF model {mdl}")
        bad += not ok
    enc = path(cfg["inputs"]["encoding_runs"])
    print(f"{'OK' if enc.exists() else 'MISSING'} WP1 results: {enc}")
    bad += not enc.exists()
    snap = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "platform": platform.platform(),
            "python": sys.version, "ffmpeg_version": capture([ff, "-version"]).splitlines()[:3], "config": cfg}
    path("results/summary/quality_software_snapshot.json").write_text(json.dumps(snap, indent=2))
    return 1 if bad else 0


# ----------------------------------------------------------------------------- run on WP1 output
def report_missing(d: pd.DataFrame, have: pd.Series, what: str, col: str):
    """Print how many rows are skipped per dataset / resolution tier, with one example path each."""
    miss = d[~have]
    if miss.empty:
        return
    print(f"WARNING: {len(miss)} of {len(d)} rows skipped: {what} not found.")
    keys = [k for k in ["dataset", "resolution_tier"] if k in miss.columns]
    for k, g in miss.groupby(keys, dropna=False):
        k = k if isinstance(k, tuple) else (k,)
        print(f"  - {' / '.join(map(str, k))}: {len(g)} rows missing, e.g. {g[col].iloc[0]}")
    print(f"  Copy the missing files into this project (data/encoded/<profile>/<dataset>/..., "
          f"data/source/<dataset>/...) or re-run WP1 for those datasets.")


def load_encodes(cfg, name: str) -> pd.DataFrame:
    p = path(cfg["inputs"]["encoding_runs"])
    if not p.exists():
        raise RuntimeError("WP1 results not found. Run WP1 first.")
    d = pd.read_csv(p)
    d = d[(d.profile == name) & (d.status == "ok") & (d.warmup.astype(int) == 0)]
    d = d[d.output_path.fillna("").astype(str).str.len() > 0].copy()
    total = len(d)
    d["output_path"] = d.output_path.map(lambda x: str(resolve(x)))
    d["input_path"] = d.input_path.map(lambda x: str(resolve(x)))
    have = d.output_path.map(lambda x: exists(Path(x))).astype(bool)
    report_missing(d, have, "bitstream", "output_path")
    d = d[have]
    src_ok = d.input_path.map(lambda x: exists(Path(x))).astype(bool)
    report_missing(d, src_ok, "source video", "input_path")
    d = d[src_ok]
    if d.empty:
        raise RuntimeError(f"No usable bitstreams for profile '{name}' (0 of {total} rows have both the bitstream and "
                           f"the source video in {ROOT / 'data'}). See the per-dataset warnings above.")
    d = d.sort_values("run")
    # quality is deterministic for identical settings -> score only the first measured run
    d = d.drop_duplicates(["dataset", "video", "tune", "preset", "crf"], keep="first")
    print(f"Usable rows for profile '{name}': {len(d)} of {total}")
    return d.sort_values(["dataset", "video", "tune", "preset", "crf"]).reset_index(drop=True)


def completed(p: Path) -> set:
    if not p.exists():
        return set()
    d = pd.read_csv(p, usecols=["experiment_id", "status"])
    return set(d.loc[d.status == "ok", "experiment_id"].astype(str))


def append(p: Path, row: dict):
    ex = p.exists()
    with p.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=QUALITY_FIELDS)
        if not ex:
            w.writeheader()
        w.writerow(row)


def plan(cfg, name):
    e = load_encodes(cfg, name)
    print(e[["dataset", "video", "tune", "preset", "crf", "resolution_tier"]].to_string(index=False))
    print(f"\nProfile={name} bitstreams to evaluate={len(e)}")
    return e


def run(cfg, name, dry, limit):
    enc = load_encodes(cfg, name)
    raw = path("results/raw/quality_runs.csv")
    sig = hashlib.sha256(json.dumps(cfg["metrics"], sort_keys=True).encode()).hexdigest()[:8]
    done = completed(raw) if cfg["measurement"].get("resume", True) else set()
    n = 0
    for _, e in enc.iterrows():
        x = eid(name, e.experiment_id, sig)
        if x in done:
            print("[RESUME]", x)
            continue
        if limit is not None and n >= limit:
            print(f"Stopped after {limit}")
            return 0
        n += 1
        ref, dist = Path(str(e.input_path)), Path(str(e.output_path))
        log = path("logs/quality") / name / str(e.dataset) / (dist.stem + ".vmaf.json")
        if dry:
            print(f"[DRY] {ref.name} <- {dist.name}")
            continue
        res = evaluate(cfg, ref, dist, log, tier=str(e.resolution_tier))
        a = res["agg"]
        frames_ref = int(e.frames) if pd.notna(e.frames) else None
        status = "ok" if res["ok"] else "failed"
        if res["ok"] and frames_ref and a["frames_scored"] != frames_ref:
            status = "frame_mismatch"
        row = {k: a.get(k, "") for k in QUALITY_FIELDS}
        row.update({
            "experiment_id": x, "encode_experiment_id": e.experiment_id,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(), "profile": name, "status": status,
            "dataset": e.dataset, "video": e.video, "resolution_tier": e.resolution_tier, "tune": e.tune,
            "preset": e.preset, "crf": e.crf, "bitrate_kbps": e.bitrate_kbps, "ref_path": str(ref),
            "dist_path": str(dist), "width": res["ref"]["width"], "height": res["ref"]["height"],
            "pix_fmt": res["pix_fmt"], "vmaf_model": res["model"], "scale_flags": res["flags"],
            "frames_ref": frames_ref, "eval_time_seconds": round(res["wall"], 3),
            "command": shlex.join(res["cmd"]), "return_code": res["code"], "log_path": str(log)})
        append(raw, row)
        print(f"[{status.upper()}] {dist.name} vmaf={a.get('vmaf_mean', float('nan')):.2f} "
              f"psnr={a.get('psnr_yuv_mean', float('nan')):.2f} ssim={a.get('ssim_mean', float('nan')):.4f}")
        if res["error"]:
            print(res["error"])
    return 0


# ----------------------------------------------------------------------------- summarize / validate
def read_quality(name):
    p = path("results/raw/quality_runs.csv")
    if not p.exists():
        raise RuntimeError("No quality results. Run: python scripts/wp2.py run --profile <p>")
    d = pd.read_csv(p)
    return d[d.profile == name] if name else d


def summarize(cfg, name):
    d = read_quality(name)
    d = d[d.status == "ok"]
    if d.empty:
        raise RuntimeError("No successful results")
    suf = name or "all"
    keys = ["profile", "dataset", "video", "resolution_tier", "tune", "preset", "crf"]
    cols = METRICS + ["vmaf_harmonic_mean", "vmaf_min", "vmaf_p1", "vmaf_temporal_std", "bitrate_kbps"]
    rd = d[keys + cols].sort_values(keys)
    rd.to_csv(path(f"results/summary/rd_points_{suf}.csv"), index=False)
    d.groupby(["profile", "tune", "preset", "crf"], as_index=False)[cols].mean() \
        .to_csv(path(f"results/summary/mean_quality_by_setting_{suf}.csv"), index=False)

    bd = cfg["bd_rate"]
    base = bd["baseline_tune"]
    tunes = sorted(d.tune.astype(str).unique())
    if base not in tunes:
        match = [t for t in tunes if t.lower() == str(base).lower()]
        if match:
            print(f"NOTE: baseline_tune '{base}' matched tune '{match[0]}' (case-insensitive)")
            base = match[0]
        else:
            print(f"WARNING: baseline_tune '{base}' not found. Tunes in the results: {tunes}. "
                  f"Set bd_rate.baseline_tune in config/quality.yaml.")
    out = []
    for (prof, ds, vid, tr, pre), g in d.groupby(["profile", "dataset", "video", "resolution_tier", "preset"]):
        a = g[g.tune == base].sort_values("crf")
        if a.empty:
            continue
        for tune, t in g[g.tune != base].groupby("tune"):
            t = t.sort_values("crf")
            for m in bd["metrics"]:
                out.append({"profile": prof, "dataset": ds, "video": vid, "resolution_tier": tr,
                            "preset": pre, "tune": tune, "anchor_tune": base, "metric": m,
                            "bd_rate_percent": bd_rate(a.bitrate_kbps, a[m], t.bitrate_kbps, t[m], int(bd["min_points"])),
                            "n_points": min(len(a), len(t))})
    if out:
        b = pd.DataFrame(out)
        b.to_csv(path(f"results/summary/bd_rate_{suf}.csv"), index=False)
        b.groupby(["profile", "resolution_tier", "preset", "tune", "metric"], as_index=False) \
            .bd_rate_percent.mean().to_csv(path(f"results/summary/bd_rate_mean_{suf}.csv"), index=False)
        print(f"BD-rate vs '{base}' written ({len(b)} rows)")
    else:
        print(f"No BD-rate computed (baseline tune '{base}' missing or too few CRF points)")
    print(f"Summary written for {suf}")
    return 0


def validate(cfg, name):
    q = read_quality(name)
    tol = float(cfg["validate"]["monotonic_tol_vmaf"])
    issues = 0
    print(f"rows={len(q)}  by status:\n{q.status.value_counts().to_string()}")
    ok = q[q.status == "ok"]
    if name:
        exp = load_encodes(cfg, name)
        missing = len(exp) - len(ok)
        print(f"\nexpected={len(exp)} scored_ok={len(ok)} missing={missing}")
        issues += missing > 0
    nan = ok[METRICS].isna().sum()
    if nan.any():
        print("\nNaN metric values:\n", nan[nan > 0].to_string())
        issues += 1
    rng = [("vmaf_mean", 0, 100), ("ssim_mean", 0, 1), ("ms_ssim_mean", 0, 1), ("psnr_y_mean", 0, 100)]
    for c, lo, hi in rng:
        bad = ok[(ok[c] < lo) | (ok[c] > hi)]
        if len(bad):
            print(f"\nOut-of-range {c}: {len(bad)} rows")
            issues += 1
    # sanity: quality and bitrate must fall as CRF rises
    viol = 0
    for _, g in ok.groupby(["dataset", "video", "tune", "preset"]):
        g = g.sort_values("crf")
        viol += int((g.vmaf_mean.diff() > tol).sum()) + int((g.bitrate_kbps.diff() > 0).sum())
    print(f"\nCRF-monotonicity violations (quality or bitrate rising with CRF): {viol}")
    issues += viol > 0
    print("RESULT:", "ISSUES FOUND" if issues else "all checks passed")
    return 1 if issues else 0


# ----------------------------------------------------------------------------- metric self-validation
def mk(cfg, src: Path, out: Path, vf: str | None = None, frames: int | None = None, pix_fmt: str | None = None):
    c = [tool(cfg["tools"]["ffmpeg"]), "-hide_banner", "-nostdin", "-y", "-i", str(src)]
    if frames:
        c += ["-frames:v", str(frames)]
    if vf:
        c += ["-vf", vf]
    if pix_fmt:
        c += ["-pix_fmt", pix_fmt]
    c += ["-strict", "-1", str(out)]  # y4m writer needs -strict -1 for 10/12-bit and some chroma formats
    p = subprocess.run(c, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(f"ffmpeg failed: {shlex.join(c)}\n{p.stderr[-800:]}")
    return out


def native_stats(cfg, ref: Path, dist: Path, which: str, out: Path) -> list[float]:
    """Independent implementation: ffmpeg's built-in psnr / ssim filters (per-frame luma)."""
    fmt = probe(cfg, ref)["pix_fmt"]
    g = (f"[0:v]setpts=PTS-STARTPTS,format={fmt}[d];[1:v]setpts=PTS-STARTPTS,format={fmt}[r];"
         f"[d][r]{which}=stats_file={fesc(out)}")
    out.unlink(missing_ok=True)
    p = subprocess.run([tool(cfg["tools"]["ffmpeg"]), "-hide_banner", "-nostdin", "-i", str(dist), "-i", str(ref),
                        "-filter_complex", g, "-f", "null", "-"], capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr[-800:])
    pat = r"psnr_y:(\S+)" if which == "psnr" else r"\bY:([0-9.]+)"
    return [float(x) for x in re.findall(pat, out.read_text())]


def selftest(cfg, src_arg):
    t = cfg["selftest"]
    d = path("results/raw/.selftest")
    d.mkdir(parents=True, exist_ok=True)
    if src_arg:
        src = Path(src_arg)
    else:
        mp = path("data/manifests/source_manifest.csv")
        if not mp.exists():
            raise RuntimeError("Give --input <video> or run WP1 scan first")
        mf = pd.read_csv(mp)
        mf = mf[mf.resolution_tier == "720p_or_lower"] if (mf.resolution_tier == "720p_or_lower").any() else mf
        src = path("data/source") / str(mf.iloc[0].relative_path)
    n = int(t["frames"])
    ref = mk(cfg, src, d / "ref.y4m", frames=n)
    rp = probe(cfg, ref)
    W, H, pf = rp["width"], rp["height"], rp["pix_fmt"]
    print(f"Self-test on {src.name}: {W}x{H} {pf}, {n} frames\n")
    rows: list[dict] = []

    def add(test, metric, value, expect, passed):
        rows.append({"test": test, "metric": metric, "value": value, "expected": expect,
                     "pass": passed if isinstance(passed, str) else bool(passed)})

    def ev(name, dist, ref_=ref, **kw):
        res = evaluate(cfg, ref_, dist, d / f"{name}.json", **kw)
        if not res["ok"]:
            raise RuntimeError(f"evaluate failed for {name}: {res['error']}")
        return res["agg"]

    # 1. identity -> best possible score
    idt = t["identity"]
    a = ev("identity", ref)
    add("identity", "psnr_y_mean", round(a["psnr_y_mean"], 3), f">={idt['psnr_min']}", a["psnr_y_mean"] >= idt["psnr_min"])
    add("identity", "ssim_mean", round(a["ssim_mean"], 6), f">={idt['ssim_min']}", a["ssim_mean"] >= idt["ssim_min"])
    add("identity", "ms_ssim_mean", round(a["ms_ssim_mean"], 6), f">={idt['ssim_min']}", a["ms_ssim_mean"] >= idt["ssim_min"])
    add("identity", "vmaf_mean", round(a["vmaf_mean"], 3), f">={idt['vmaf_min']}", a["vmaf_mean"] >= idt["vmaf_min"])

    # 2. monotonicity: stronger distortion must never score better
    fam = {
        "noise": (t["noise_levels"], lambda s: f"noise=alls={s}:allf=t+u:all_seed=1"),
        "blur": (t["blur_sigmas"], lambda s: f"gblur=sigma={s}"),
        "resize": (t["resize_factors"], lambda s: f"scale=trunc(iw/{s}/2)*2:trunc(ih/{s}/2)*2,scale={W}:{H}"),
    }
    aggs: dict[tuple, dict] = {}
    files: dict[tuple, Path] = {}
    for f, (levels, vf) in fam.items():
        for s in levels:
            files[(f, s)] = mk(cfg, ref, d / f"{f}_{s}.y4m", vf=vf(s))
            aggs[(f, s)] = ev(f"{f}_{s}", files[(f, s)])
        for m in METRICS:
            vals = [aggs[(f, s)][m] for s in levels]
            add(f"monotonic_{f}", m, [round(v, 4) for v in vals], "strictly decreasing", bool(np.all(np.diff(vals) < 0)))

    # 3. cross-check against independent implementations (ffmpeg native psnr / ssim filters)
    for f in ["noise", "blur"]:
        s = fam[f][0][len(fam[f][0]) // 2]
        dist, a = files[(f, s)], aggs[(f, s)]
        p_nat = float(np.mean(np.minimum(native_stats(cfg, ref, dist, "psnr", d / "nat_psnr.log"), 100)))
        dp = abs(p_nat - a["psnr_y_mean"])
        add(f"crosscheck_{f}_{s}", "psnr_y |libvmaf-native| dB", round(dp, 4), f"<={t['crosscheck']['psnr_db']}", dp <= t["crosscheck"]["psnr_db"])
        # libvmaf's SSIM downsamples frames by ~round(short_side/256), ffmpeg's native ssim does not. To compare the
        # two implementations fairly, run the check at 256 px height, where libvmaf applies no downsampling.
        small = "scale=-2:256:flags=area"
        ref_s = mk(cfg, ref, d / "xs_ref.y4m", vf=small)
        dist_s = mk(cfg, dist, d / f"xs_{f}.y4m", vf=small)
        a_s = ev(f"xs_{f}", dist_s, ref_=ref_s)
        s_nat = float(np.mean(native_stats(cfg, ref_s, dist_s, "ssim", d / "nat_ssim.log")))
        ds = abs(s_nat - a_s["ssim_mean"])
        add(f"crosscheck_{f}_{s}", "ssim_y |libvmaf-native| @256p", round(ds, 4), f"<={t['crosscheck']['ssim_abs']}", ds <= t["crosscheck"]["ssim_abs"])
        s_full = float(np.mean(native_stats(cfg, ref, dist, "ssim", d / "nat_ssim_full.log")))
        add(f"info_ssim_fullres_{f}_{s}", "ssim_y libvmaf vs native @full-res", f"{a['ssim_mean']:.4f} vs {s_full:.4f}",
            "info: libvmaf SSIM is computed on a downsampled frame", "info")

    # 4. robustness: representation changes must not change the score
    s0 = fam["noise"][0][len(fam["noise"][0]) // 2]
    base, dist0 = aggs[("noise", s0)], files[("noise", s0)]
    inv = t["invariance"]
    depth_alt = "yuv420p" if "10" in pf or "12" in pf else "yuv420p10le"
    chroma_alt = ("yuv420p10le" if ("10" in pf or "12" in pf) else "yuv420p") if "444" in pf else \
                 ("yuv444p10le" if ("10" in pf or "12" in pf) else "yuv444p")

    def compare(test, a):
        add(test, "psnr_y diff dB", round(abs(a["psnr_y_mean"] - base["psnr_y_mean"]), 4), f"<={inv['psnr_db']}",
            abs(a["psnr_y_mean"] - base["psnr_y_mean"]) <= inv["psnr_db"])
        add(test, "vmaf diff", round(abs(a["vmaf_mean"] - base["vmaf_mean"]), 4), f"<={inv['vmaf']}",
            abs(a["vmaf_mean"] - base["vmaf_mean"]) <= inv["vmaf"])

    compare("bit_depth_dist", ev("depth_dist", mk(cfg, dist0, d / "depth_dist.y4m", pix_fmt=depth_alt)))
    compare("chroma_dist", ev("chroma_dist", mk(cfg, dist0, d / "chroma_dist.y4m", pix_fmt=chroma_alt)))
    ref_alt = mk(cfg, ref, d / "ref_alt.y4m", pix_fmt=chroma_alt)
    compare("chroma_ref", ev("chroma_ref", dist0, ref_=ref_alt))

    # 5. resolution handling: metric must be insensitive to the choice of rescaling filter (within tolerance)
    half = mk(cfg, ref, d / "half.y4m", vf=f"scale={W // 2 // 2 * 2}:{H // 2 // 2 * 2}:flags=lanczos")
    sp = {fl: ev(f"half_{fl}", half, flags=fl) for fl in t["scale_flags"]}
    for m, key in [("vmaf_mean", "vmaf"), ("psnr_y_mean", "psnr_db")]:
        vals = [sp[f][m] for f in sp]
        spread = max(vals) - min(vals)
        add("scale_filter_spread", m, round(spread, 3), f"<={t['scale_spread'][key]} (warn only)",
            True if spread <= t["scale_spread"][key] else "warn")

    # 6. missing frames must be detectable (frames_scored != frames in reference)
    short = mk(cfg, dist0, d / "short.y4m", frames=n - 5)
    a = ev("short", short)
    add("frame_count_guard", "frames_scored", a["frames_scored"], f"{n - 5} (<{n}, run() flags mismatch)", a["frames_scored"] == n - 5)

    rep = pd.DataFrame(rows)
    pd.set_option("display.width", 200, "display.max_colwidth", 70)
    print(rep.to_string(index=False))
    rep.to_csv(path("results/summary/metric_validation.csv"), index=False)
    failed = int(rep["pass"].map(lambda v: v is False).sum())
    warned = int(rep["pass"].map(lambda v: v == "warn").sum())
    infos = int(rep["pass"].map(lambda v: v == "info").sum())
    checks = len(rep) - infos
    print(f"\n{checks - failed - warned}/{checks} checks passed, {warned} warning(s), {failed} failed, "
          f"{infos} info row(s) -> results/summary/metric_validation.csv")
    if warned:
        print("Warning: scores depend on the rescaling filter. Use ONE metrics.scale_flags for the whole study.")
    return 1 if failed else 0


def cmd_evaluate(cfg, a):
    res = evaluate(cfg, Path(a.ref), Path(a.dist), path("logs/quality/adhoc.vmaf.json"),
                   flags=a.scale_flags, fmt=a.pix_fmt)
    if not res["ok"]:
        print("FAILED:", res["error"])
        return 1
    print(json.dumps({"model": res["model"], "pix_fmt": res["pix_fmt"], "scale_flags": res["flags"], **res["agg"]}, indent=2))
    return 0


# ----------------------------------------------------------------------------- plots
def plot(cfg, name, video=None, preset=None, crf=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    d = read_quality(name)
    d = d[d.status == "ok"]
    if video:
        d = d[d.video == video]
    if d.empty:
        raise RuntimeError("No successful results to plot")
    suf = name or "all"
    out = path("results/plots")
    out.mkdir(parents=True, exist_ok=True)
    dpi = int(cfg["plots"].get("dpi", 150))
    metrics = cfg["plots"]["metrics"]
    made: list[Path] = []

    def save(fig, fname):
        fig.tight_layout()
        f = out / fname
        fig.savefig(f, dpi=dpi)
        plt.close(fig)
        made.append(f)

    def rd_figure(g, m, title, fname):
        presets = sorted(g.preset.unique())
        fig, axs = plt.subplots(1, len(presets), figsize=(4.5 * len(presets), 4), squeeze=False, sharey=True)
        for ax, pre in zip(axs[0], presets):
            for tune, t in g[g.preset == pre].groupby("tune"):
                t = t.sort_values("crf")
                ax.plot(t.bitrate_kbps, t[m], marker="o", label=str(tune))
            ax.set_xscale("log")
            ax.set_title(f"preset {pre}")
            ax.set_xlabel("bitrate (kbps, log)")
            ax.grid(alpha=0.3)
        axs[0][0].set_ylabel(m)
        axs[0][-1].legend(title="tune")
        fig.suptitle(title)
        save(fig, fname)

    # 1. RD curves: per video, and averaged over all videos
    for (ds, vid), g in d.groupby(["dataset", "video"]):
        for m in metrics:
            rd_figure(g, m, f"{ds}/{vid}", f"rd_{ds}_{Path(str(vid)).stem}_{m}_{suf}.png")
    if d[["dataset", "video"]].drop_duplicates().shape[0] > 1:
        mean = d.groupby(["tune", "preset", "crf"], as_index=False)[metrics + ["bitrate_kbps"]].mean()
        for m in metrics:
            rd_figure(mean, m, "mean over all videos", f"rd_mean_{m}_{suf}.png")

    # 2. BD-rate bars (needs `summarize` first)
    bdp = path(f"results/summary/bd_rate_{suf}.csv")
    if bdp.exists():
        bd = pd.read_csv(bdp)
        ms = list(bd.metric.unique())
        fig, axs = plt.subplots(1, len(ms), figsize=(4.5 * len(ms), 4), squeeze=False)
        for ax, m in zip(axs[0], ms):
            pv = bd[bd.metric == m].groupby(["preset", "tune"]).bd_rate_percent.mean().unstack("tune")
            pv.plot.bar(ax=ax, rot=0)
            ax.axhline(0, color="k", lw=0.8)
            ax.set_title(m)
            ax.set_xlabel("preset")
            ax.set_ylabel("BD-rate % (negative = better)")
            ax.grid(axis="y", alpha=0.3)
        fig.suptitle(f"BD-rate vs '{bd.anchor_tune.iloc[0]}'")
        save(fig, f"bd_rate_{suf}.png")
    else:
        print("Skipping BD-rate plot (run `summarize` first)")

    # 3. Per-frame VMAF over time, one line per tune
    for (ds, vid), g in d.groupby(["dataset", "video"]):
        pres = sorted(g.preset.unique())
        pre = preset if preset in pres else pres[len(pres) // 2]
        gp = g[g.preset == pre]
        crfs = sorted(gp.crf.unique())
        c = crf if crf in crfs else crfs[len(crfs) // 2]
        fig, ax = plt.subplots(figsize=(9, 3.8))
        for _, r in gp[gp.crf == c].iterrows():
            lp = Path(str(r.log_path))
            if not lp.exists():
                continue
            fr = json.loads(lp.read_text())["frames"]
            ax.plot([f["frameNum"] for f in fr], [f["metrics"]["vmaf"] for f in fr], lw=1, label=f"{r.tune} ({r.vmaf_mean:.1f})")
        ax.set_xlabel("frame")
        ax.set_ylabel("VMAF")
        ax.set_title(f"{ds}/{vid}  preset {pre}  crf {c}")
        ax.grid(alpha=0.3)
        ax.legend(title="tune (mean VMAF)", fontsize=8)
        save(fig, f"vmaf_per_frame_{ds}_{Path(str(vid)).stem}_{suf}.png")

    for f in made:
        print("wrote", f)
    print(f"{len(made)} plots in {out}")
    return 0


# ----------------------------------------------------------------------------- CLI
def main():
    a = argparse.ArgumentParser()
    a.add_argument("--config", default="config/quality.yaml")
    s = a.add_subparsers(dest="cmd", required=True)
    s.add_parser("preflight")
    p = s.add_parser("plan"); p.add_argument("--profile", choices=PROFILES, required=True)
    r = s.add_parser("run"); r.add_argument("--profile", choices=PROFILES, required=True)
    r.add_argument("--dry-run", action="store_true"); r.add_argument("--limit", type=int)
    q = s.add_parser("summarize"); q.add_argument("--profile", choices=PROFILES)
    v = s.add_parser("validate"); v.add_argument("--profile", choices=PROFILES)
    t = s.add_parser("selftest"); t.add_argument("--input")
    pl = s.add_parser("plot"); pl.add_argument("--profile", choices=PROFILES)
    pl.add_argument("--video"); pl.add_argument("--preset", type=int); pl.add_argument("--crf", type=int)
    e = s.add_parser("evaluate")
    e.add_argument("--ref", required=True); e.add_argument("--dist", required=True)
    e.add_argument("--scale-flags"); e.add_argument("--pix-fmt")
    x = a.parse_args()
    cfg = load_cfg(x.config)
    ensure_dirs()
    return {"preflight": lambda: preflight(cfg), "plan": lambda: plan(cfg, x.profile) is None,
            "run": lambda: run(cfg, x.profile, x.dry_run, x.limit), "summarize": lambda: summarize(cfg, x.profile),
            "validate": lambda: validate(cfg, x.profile), "plot": lambda: plot(cfg, x.profile, x.video, x.preset, x.crf),
            "selftest": lambda: selftest(cfg, x.input),
            "evaluate": lambda: cmd_evaluate(cfg, x)}[x.cmd]()


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""WP2b - Independent quality metrics for the SVT-AV1 tune study.

Why this exists: the encoder tunes optimise PSNR, SSIM, MS-SSIM and VMAF (the metrics of wp2.py), so judging a tune
only with its own target is circular. This program scores the WP1 encodes with metrics that NO tune optimises:

  xpsnr  perceptually weighted PSNR (ffmpeg)                          higher = better
  lpips  deep-feature perceptual distance (PyTorch)                   lower  = better
  dists  deep image structure and texture similarity (PyTorch)        lower  = better
  cvvdp  ColorVideoVDP: video, colour and display aware (JOD scale)   higher = better (10 = no visible difference)

It is a separate program on purpose: it needs PyTorch (and ideally a GPU), which wp2.py does not. It is
self-contained, reads WP1's results, writes its own results, and (if present) puts WP2's scores next to its own.

Usage:
  python scripts/wp2_independent.py preflight
  python scripts/wp2_independent.py evaluate --ref a.y4m --dist b.ivf [--metrics xpsnr,lpips,dists,cvvdp]
  python scripts/wp2_independent.py selftest [--input video.y4m]
  python scripts/wp2_independent.py plan     --profile meeting
  python scripts/wp2_independent.py run      --profile meeting [--metrics ...] [--dry-run] [--limit N] [--rescore]
  python scripts/wp2_independent.py validate  --profile meeting
  python scripts/wp2_independent.py summarize --profile meeting
  python scripts/wp2_independent.py report    --profile meeting
  python scripts/wp2_independent.py plot      --profile meeting [--per-video]
"""
from __future__ import annotations

import argparse, csv, json, math, re, shlex, shutil, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import warnings

import numpy as np
import pandas as pd
import yaml

warnings.filterwarnings("ignore", category=UserWarning, module=r"torchvision\..*")  # harmless 'pretrained' notices

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ["meeting", "confidence", "full"]
INDEP_COL = {"xpsnr": "xpsnr_mean", "lpips": "lpips_mean", "dists": "dists_mean", "cvvdp": "cvvdp_jod"}
REF_COLS = ["vmaf_mean", "psnr_yuv_mean", "ssim_mean", "ms_ssim_mean"]  # WP2 scores, used only for comparison
NICE = {"xpsnr_mean": "XPSNR*", "lpips_mean": "LPIPS*", "dists_mean": "DISTS*", "cvvdp_jod": "ColorVideoVDP*",
        "vmaf_mean": "VMAF", "psnr_yuv_mean": "PSNR", "ssim_mean": "SSIM", "ms_ssim_mean": "MS-SSIM"}
HIGHER_BETTER = {"xpsnr_mean": True, "lpips_mean": False, "dists_mean": False, "cvvdp_jod": True,
                 "vmaf_mean": True, "psnr_yuv_mean": True, "ssim_mean": True, "ms_ssim_mean": True}
FIELDS = ["encode_experiment_id", "profile", "status", "timestamp_utc", "xpsnr_y", "xpsnr_u", "xpsnr_v", "xpsnr_mean",
          "lpips_mean", "lpips_max", "lpips_frames", "dists_mean", "dists_max", "dists_frames", "cvvdp_jod",
          "cvvdp_frames", "settings", "eval_time_seconds", "error"]


# ----------------------------------------------------------------------------- basics
def path(v: str | Path) -> Path:
    p = Path(v)
    return p if p.is_absolute() else ROOT / p


def load_cfg(name: str) -> dict[str, Any]:
    with path(name).open() as f:
        return yaml.safe_load(f)


def ensure_dirs():
    for d in ["results/raw", "results/summary", "results/plots"]:
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


def resolve(p) -> Path:
    """WP1 stores absolute paths from the machine it ran on; re-anchor data/encoded and data/source onto this project."""
    p = Path(str(p))
    if exists(p):
        return p
    parts = p.parts
    for i, part in enumerate(parts[:-1]):
        if part == "data" and parts[i + 1] in ("encoded", "source"):
            q = ROOT.joinpath(*parts[i:])
            if exists(q):
                return q
    return p


def fesc(p) -> str:
    return str(p).replace("\\", "/").replace(":", "\\:")


def probe(cfg, p: Path) -> dict[str, Any]:
    q = subprocess.run([tool(cfg["tools"]["ffprobe"]), "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,pix_fmt,r_frame_rate", "-of", "json", str(p)], capture_output=True, text=True)
    if q.returncode or not q.stdout.strip():
        raise RuntimeError(f"ffprobe failed on {p}: {q.stderr.strip()}")
    s = json.loads(q.stdout)["streams"][0]
    n, d = s["r_frame_rate"].split("/")
    return {"width": int(s["width"]), "height": int(s["height"]), "pix_fmt": s["pix_fmt"],
            "fps": int(n) / int(d) if int(d) else None}


def append(p: Path, row: dict):
    ex = p.exists()
    with p.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if not ex:
            w.writeheader()
        w.writerow(row)


def load_encodes(cfg, name: str) -> pd.DataFrame:
    """The WP1 bitstreams to score: first measured run per setting, files must exist on this machine."""
    p = path(cfg["inputs"]["encoding_runs"])
    if not p.exists():
        raise RuntimeError("WP1 results not found. Run WP1 first, or fix inputs.encoding_runs in the config.")
    d = pd.read_csv(p)
    d = d[(d.profile == name) & (d.status == "ok") & (d.warmup.astype(int) == 0)]
    d = d[d.output_path.fillna("").astype(str).str.len() > 0].copy()
    d["output_path"] = d.output_path.map(lambda x: str(resolve(x)))
    d["input_path"] = d.input_path.map(lambda x: str(resolve(x)))
    have = d.output_path.map(lambda x: exists(Path(x))).astype(bool)
    if (~have).any():
        miss = d.loc[~have].groupby(["dataset", "video"]).size().reset_index(name="missing_bitstreams")
        print(f"WARNING: {int((~have).sum())} encoding rows skipped: bitstream not found. Example: "
              f"{d.loc[~have, 'output_path'].iloc[0]}\nMissing per video:\n" + miss.head(40).to_string(index=False))
    d = d[have]
    src_ok = d.input_path.map(lambda x: exists(Path(x))).astype(bool)
    if (~src_ok).any():
        print(f"WARNING: {int((~src_ok).sum())} rows skipped: source video not found. Example: "
              f"{d.loc[~src_ok, 'input_path'].iloc[0]}")
    d = d[src_ok]
    if d.empty:
        raise RuntimeError(f"No usable bitstreams for profile '{name}'. Check data/encoded and data/source.")
    d = d.sort_values("run").drop_duplicates(["dataset", "video", "tune", "preset", "crf"], keep="first")
    return d.sort_values(["dataset", "video", "tune", "preset", "crf"]).reset_index(drop=True)


# ----------------------------------------------------------------------------- the metrics
def norm_chain(cfg, r: dict, d: dict) -> tuple[str, str]:
    """Same normalisation as wp2.py: distorted stream rescaled to the reference size, both in one pixel format."""
    n = cfg["normalisation"]
    fmt = r["pix_fmt"] if n["pix_fmt"] == "ref" else n["pix_fmt"]
    dchain = "setpts=PTS-STARTPTS"
    if (d["width"], d["height"]) != (r["width"], r["height"]):
        dchain += f",scale={r['width']}:{r['height']}:flags={n['scale_flags']}"
    return f"{dchain},format={fmt}", f"setpts=PTS-STARTPTS,format={fmt}"


def xpsnr_score(cfg, ref: Path, dist: Path) -> dict[str, Any]:
    r, d = probe(cfg, ref), probe(cfg, dist)
    dc, rc = norm_chain(cfg, r, d)
    g = f"[0:v]{dc}[d];[1:v]{rc}[r];[d][r]xpsnr=shortest=1:repeatlast=0"
    p = subprocess.run([tool(cfg["tools"]["ffmpeg"]), "-hide_banner", "-nostdin", "-i", str(dist), "-i", str(ref),
                        "-filter_complex", g, "-f", "null", "-"], capture_output=True, text=True)
    hit = re.findall(r"XPSNR\s+y:\s*(\S+)\s+u:\s*(\S+)\s+v:\s*(\S+)", p.stderr)
    if p.returncode or not hit:
        raise RuntimeError(f"xpsnr failed: {p.stderr[-400:]}")
    y, u, v = (min(float(x), 100.0) for x in hit[-1])  # identical content prints inf; cap like PSNR
    return {"xpsnr_y": y, "xpsnr_u": u, "xpsnr_v": v, "xpsnr_mean": (6 * y + u + v) / 8}


def iter_frame_pairs(cfg, ref: Path, dist: Path, every: int):
    """Yield (ref_rgb, dist_rgb) uint8 arrays for every `every`-th frame; dist is rescaled to the reference size."""
    r, d = probe(cfg, ref), probe(cfg, dist)
    W, H = r["width"], r["height"]
    flags = cfg["normalisation"]["scale_flags"]
    ff = tool(cfg["tools"]["ffmpeg"])

    def cmd(src: Path, size_differs: bool):
        chain = "setpts=PTS-STARTPTS" + (f",scale={W}:{H}:flags={flags}" if size_differs else "")
        chain += f",select=not(mod(n\\,{every}))"
        return [ff, "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(src), "-vf", chain,
                "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]

    n = W * H * 3
    pa = subprocess.Popen(cmd(ref, False), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    pb = subprocess.Popen(cmd(dist, (d["width"], d["height"]) != (W, H)), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        while True:
            a, b = pa.stdout.read(n), pb.stdout.read(n)
            if len(a) < n or len(b) < n:
                break
            yield np.frombuffer(a, np.uint8).reshape(H, W, 3), np.frombuffer(b, np.uint8).reshape(H, W, 3)
    finally:
        for q in (pa, pb):
            q.kill()
            q.wait()


def _torch_device(torch, device: str) -> str:
    return ("cuda" if torch.cuda.is_available() else "cpu") if device == "auto" else device


def load_lpips(net: str = "alex", device: str = "auto"):
    """Return f(ref_rgb, dist_rgb) -> LPIPS distance (0 = identical, higher = more different)."""
    try:
        import torch
        import lpips
    except (ImportError, OSError) as ex:  # OSError: broken PyTorch install
        raise RuntimeError("LPIPS needs: pip install torch torchvision lpips") from ex
    dev = _torch_device(torch, device)
    model = lpips.LPIPS(net=net, verbose=False).to(dev).eval()

    def score(a: np.ndarray, b: np.ndarray) -> float:
        t = lambda x: torch.from_numpy(x.copy()).permute(2, 0, 1)[None].float().div(127.5).sub(1).to(dev)  # [-1, 1]
        with torch.no_grad():
            return float(model(t(a), t(b)).item())
    return score


def load_dists(device: str = "auto"):
    """Return f(ref_rgb, dist_rgb) -> DISTS distance (0 = identical, higher = more different)."""
    try:
        import site
        import torch
        import DISTS_pytorch
        from DISTS_pytorch import DISTS
    except (ImportError, OSError) as ex:
        raise RuntimeError("DISTS needs: pip install torch torchvision DISTS-pytorch") from ex
    dev = _torch_device(torch, device)
    # DISTS-pytorch looks for weights.pt in sys.prefix, which is missing after a user-level pip install. The same file
    # ships inside the package folder, so build the model without it and load the weights from there.
    model = DISTS(load_weights=False)
    cands = [Path(DISTS_pytorch.__file__).parent / "weights.pt", Path(sys.prefix) / "weights.pt",
             Path(site.USER_BASE) / "weights.pt"]
    wp = next((c for c in cands if c.exists()), None)
    if wp is None:
        raise RuntimeError("DISTS weights.pt not found; try: pip install --force-reinstall DISTS-pytorch")
    w = torch.load(str(wp), map_location="cpu")
    model.alpha.data, model.beta.data = w["alpha"], w["beta"]
    model = model.to(dev).eval()

    def score(a: np.ndarray, b: np.ndarray) -> float:
        t = lambda x: torch.from_numpy(x.copy()).permute(2, 0, 1)[None].float().div(255).to(dev)  # [0, 1]
        with torch.no_grad():
            return float(model(t(a), t(b)).mean().item())
    return score


def frame_metric_score(cfg, ref: Path, dist: Path, model_fn, every: int, prefix: str) -> dict[str, Any]:
    vals = [model_fn(a, b) for a, b in iter_frame_pairs(cfg, ref, dist, every)]
    if not vals:
        raise RuntimeError(f"no frames compared for {prefix}")
    return {f"{prefix}_mean": float(np.mean(vals)), f"{prefix}_max": float(np.max(vals)), f"{prefix}_frames": len(vals)}


def cvvdp_available(cfg) -> bool:
    return shutil.which(cfg["independent"].get("cvvdp_command", "cvvdp")) is not None


def cvvdp_score(cfg, ref: Path, dist: Path, max_frames: int | None = None) -> dict[str, Any]:
    """ColorVideoVDP via its command-line tool, on the first `max_frames` frames (0 = whole video)."""
    ic = cfg["independent"]
    if not cvvdp_available(cfg):
        raise RuntimeError("ColorVideoVDP needs: pip install cvvdp (provides the `cvvdp` command)")
    r, d = probe(cfg, ref), probe(cfg, dist)
    resize = ic.get("cvvdp_resize")
    if (r["width"], r["height"]) != (d["width"], d["height"]) and not resize:
        raise RuntimeError("ColorVideoVDP needs equal resolutions; set independent.cvvdp_resize or rescale first")
    n = ic.get("cvvdp_max_frames", 30) if max_frames is None else max_frames
    cmd = [shutil.which(ic.get("cvvdp_command", "cvvdp")), "--test", str(dist), "--ref", str(ref),
           "--display", str(ic.get("cvvdp_display", "standard_fhd")), "--device", str(ic.get("cvvdp_device", "auto")),
           "--quiet"]
    if n and int(n) > 0:
        cmd += ["--nframes", str(int(n))]
    if resize:
        cmd += ["--full-screen-resize", str(resize)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    nums = re.findall(r"-?\d+\.\d+", p.stdout)
    if p.returncode or not nums:
        raise RuntimeError(f"cvvdp failed: {(p.stderr or p.stdout)[-300:]}")
    return {"cvvdp_jod": float(nums[-1]), "cvvdp_frames": int(n) if n else ""}


class Scorer:
    """Loads the requested metrics once and scores file pairs."""

    def __init__(self, cfg, metrics: list[str]):
        ic = cfg["independent"]
        bad = [m for m in metrics if m not in INDEP_COL]
        if bad:
            raise RuntimeError(f"Unknown metric(s) {bad}; choose from {sorted(INDEP_COL)}")
        self.cfg, self.metrics = cfg, metrics
        self.every = int(ic.get("frame_metrics_every_nth_frame", 10))
        self.lp = load_lpips(ic.get("lpips_net", "alex"), ic.get("lpips_device", "auto")) if "lpips" in metrics else None
        self.ds = load_dists(ic.get("dists_device", "auto")) if "dists" in metrics else None
        if "cvvdp" in metrics and not cvvdp_available(cfg):
            raise RuntimeError("ColorVideoVDP needs: pip install cvvdp (provides the `cvvdp` command)")

    def settings(self, m: str) -> dict:
        ic = self.cfg["independent"]
        return {"xpsnr": {}, "lpips": {"net": ic.get("lpips_net", "alex"), "every": self.every},
                "dists": {"every": self.every},
                "cvvdp": {"display": ic.get("cvvdp_display", "standard_fhd"), "frames": ic.get("cvvdp_max_frames", 30),
                          "resize": ic.get("cvvdp_resize")}}[m]

    def score(self, m: str, ref: Path, dist: Path) -> dict[str, Any]:
        if m == "xpsnr":
            return xpsnr_score(self.cfg, ref, dist)
        if m == "lpips":
            return frame_metric_score(self.cfg, ref, dist, self.lp, self.every, "lpips")
        if m == "dists":
            return frame_metric_score(self.cfg, ref, dist, self.ds, self.every, "dists")
        return cvvdp_score(self.cfg, ref, dist)


# ----------------------------------------------------------------------------- commands: preflight / evaluate / plan / run
def preflight(cfg):
    bad = 0
    for k in ["ffmpeg", "ffprobe"]:
        p = shutil.which(cfg["tools"][k])
        print(f"{'OK     ' if p else 'MISSING'} {cfg['tools'][k]}: {p or ''}")
        bad += p is None
    if bad:
        return 1
    ff = tool(cfg["tools"]["ffmpeg"])
    has_x = "xpsnr" in subprocess.run([ff, "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    print(f"{'OK     ' if has_x else 'MISSING'} xpsnr filter in ffmpeg" + ("" if has_x else " (needs ffmpeg 7.0 or newer)"))
    print("\nOptional metrics (a missing one is only a problem if you want it):")
    try:
        import torch
        print(f"OK      PyTorch {torch.__version__}, CUDA available: {torch.cuda.is_available()}")
    except (ImportError, OSError):
        print("MISSING PyTorch (needed for lpips and dists): pip install torch torchvision")
    for name, loader in (("lpips", lambda: load_lpips()), ("dists", lambda: load_dists())):
        try:
            loader()
            print(f"OK      {name}")
        except RuntimeError as ex:
            print(f"MISSING {name}: {ex}")
        except Exception as ex:  # noqa: BLE001 - e.g. weights could not be downloaded
            print(f"FAILED  {name}: {str(ex)[:150]}")
    print(f"{'OK     ' if cvvdp_available(cfg) else 'MISSING'} cvvdp command"
          + ("" if cvvdp_available(cfg) else " (pip install cvvdp)"))
    enc = path(cfg["inputs"]["encoding_runs"])
    print(f"\n{'OK     ' if enc.exists() else 'MISSING'} WP1 results: {enc}")
    q = path(cfg["inputs"].get("quality_runs", "results/raw/quality_runs.csv"))
    print(f"{'OK     ' if q.exists() else 'absent '} WP2 results (optional, for side-by-side tables): {q}")
    return 1 if (bad or not has_x or not enc.exists()) else 0


def cmd_evaluate(cfg, a):
    want = [m for m in (a.metrics or ",".join(cfg["independent"]["metrics"])).split(",") if m]
    sc = Scorer(cfg, want)
    out: dict[str, Any] = {}
    for m in want:
        out.update(sc.score(m, Path(a.ref), Path(a.dist)))
    print(json.dumps(out, indent=2))
    return 0


def done_sets(cfg, name) -> dict[str, set]:
    have = {m: set() for m in INDEP_COL}
    p = path("results/raw/independent_runs.csv")
    if p.exists():
        e = pd.read_csv(p)
        e = e[e.profile == name]
        for m, c in INDEP_COL.items():
            if c in e:
                have[m] = set(e.loc[e[c].notna(), "encode_experiment_id"].astype(str))
    return have


def plan(cfg, name, only=None):
    enc = load_encodes(cfg, name)
    want = [m for m in (only or ",".join(cfg["independent"]["metrics"])).split(",") if m]
    have = done_sets(cfg, name)
    g = enc.groupby(["dataset", "video", "resolution_tier"]).size().reset_index(name="bitstreams")
    print(g.to_string(index=False))
    print(f"\nProfile={name} videos={len(g)} bitstreams={len(enc)}")
    for m in want:
        todo = int((~enc.experiment_id.astype(str).isin(have[m])).sum())
        print(f"  {m:6s}: {todo} to score, {len(enc) - todo} done")
    return enc


def run(cfg, name, dry, limit, only=None, rescore=False):
    want = [m for m in (only or ",".join(cfg["independent"]["metrics"])).split(",") if m]
    enc = load_encodes(cfg, name)
    out = path("results/raw/independent_runs.csv")
    have = {m: set() for m in INDEP_COL} if rescore or not cfg["measurement"].get("resume", True) else done_sets(cfg, name)
    todo = [(r, [m for m in want if str(r.experiment_id) not in have[m]]) for _, r in enc.iterrows()]
    todo = [(r, ms) for r, ms in todo if ms]
    total = min(len(todo), limit) if limit is not None else len(todo)
    print(f"metrics={want}: {len(todo)} bitstreams to score ({len(enc) - len(todo)} already done)")
    if dry:
        for r, ms in todo[:5]:
            print(f"[DRY] {ms} {Path(str(r.input_path)).name} <- {Path(str(r.output_path)).name}")
        return 0
    sc = Scorer(cfg, want)  # loads models / checks tools before the long loop
    t0 = time.perf_counter()
    for n, (r, ms) in enumerate(todo[:total], 1):
        ref, dist = Path(str(r.input_path)), Path(str(r.output_path))
        row = {k: "" for k in FIELDS}
        row.update({"encode_experiment_id": r.experiment_id, "profile": name, "status": "ok",
                    "timestamp_utc": datetime.now(timezone.utc).isoformat()})
        st, used = time.perf_counter(), {}
        for m in ms:  # one failing metric must not lose the others
            try:
                row.update(sc.score(m, ref, dist))
                used[m] = sc.settings(m)
            except Exception as ex:  # noqa: BLE001
                row["status"] = "failed"
                row["error"] = (row["error"] + f" [{m}] " + str(ex)[:250].replace("\n", " ")).strip()
        row["settings"] = json.dumps(used, sort_keys=True)
        row["eval_time_seconds"] = round(time.perf_counter() - st, 3)
        append(out, row)
        eta = (time.perf_counter() - t0) / n * (total - n) / 60
        vals = " ".join(f"{m}={round(row[INDEP_COL[m]], 4)}" if row[INDEP_COL[m]] != "" else f"{m}=-" for m in ms)
        print(f"[{n}/{total}] ETA {eta:.0f} min | [{row['status'].upper()}] {dist.name} {vals}")
    return 0


# ----------------------------------------------------------------------------- results assembly
def results_frame(cfg, name) -> pd.DataFrame:
    """WP1 settings + independent scores (+ WP2 scores if available), one row per bitstream."""
    p = path("results/raw/independent_runs.csv")
    if not p.exists():
        raise RuntimeError("No results yet. Run: python scripts/wp2_independent.py run --profile <p>")
    enc = load_encodes(cfg, name)
    e = pd.read_csv(p)
    e = e[e.profile == name]
    cols = [c for c in e.columns if c in INDEP_COL.values() or c.endswith(("_max", "_frames", "_y", "_u", "_v"))]
    e = e.sort_values("timestamp_utc").groupby("encode_experiment_id", as_index=False)[cols].last()
    d = enc.merge(e, left_on="experiment_id", right_on="encode_experiment_id", how="inner")
    qp = path(cfg["inputs"].get("quality_runs", "results/raw/quality_runs.csv"))
    if qp.exists():
        q = pd.read_csv(qp)
        q = q[q.profile == name].sort_values("timestamp_utc").drop_duplicates("encode_experiment_id", keep="last")
        d = d.merge(q[["encode_experiment_id"] + [c for c in REF_COLS if c in q.columns]], on="encode_experiment_id", how="left")
    return d


def bd_rate(r1, q1, r2, q2, min_pts: int = 3) -> float:
    """Bjontegaard delta-rate (%) of curve 2 vs anchor curve 1 at equal quality. Negative = bitrate saved.
    The sign does not depend on whether a higher or a lower score means better quality."""
    r1, q1, r2, q2 = (np.asarray(x, float) for x in (r1, q1, r2, q2))
    k1, k2 = np.isfinite(r1) & np.isfinite(q1), np.isfinite(r2) & np.isfinite(q2)
    r1, q1, r2, q2 = r1[k1], q1[k1], r2[k2], q2[k2]
    if min(len(q1), len(q2)) < min_pts or (r1 <= 0).any() or (r2 <= 0).any():
        return math.nan
    lo, hi = max(q1.min(), q2.min()), min(q1.max(), q2.max())
    if hi <= lo:
        return math.nan
    deg = min(3, len(q1) - 1, len(q2) - 1)
    try:
        i1 = np.polyint(np.polyfit(q1, np.log(r1), deg))
        i2 = np.polyint(np.polyfit(q2, np.log(r2), deg))
    except np.linalg.LinAlgError:
        return math.nan
    avg = ((np.polyval(i2, hi) - np.polyval(i2, lo)) - (np.polyval(i1, hi) - np.polyval(i1, lo))) / (hi - lo)
    return (math.exp(avg) - 1) * 100


def crf_window(df: pd.DataFrame, cfg) -> pd.DataFrame:
    lo, hi = cfg["bd_rate"].get("crf_min"), cfg["bd_rate"].get("crf_max")
    if lo is not None:
        df = df[df.crf >= lo]
    if hi is not None:
        df = df[df.crf <= hi]
    return df


def present(d: pd.DataFrame, cols: list[str]) -> list[str]:
    return [c for c in cols if c in d.columns and d[c].notna().any()]


def baseline_name(cfg, d) -> str:
    base = str(cfg["bd_rate"]["baseline_tune"])
    tunes = sorted(d.tune.astype(str).unique())
    if base not in tunes:
        match = [t for t in tunes if t.lower() == base.lower()]
        if match:
            print(f"NOTE: baseline_tune '{base}' matched tune '{match[0]}' (case-insensitive)")
            return match[0]
        print(f"WARNING: baseline_tune '{base}' not found. Tunes in the results: {tunes}.")
    return base


# ----------------------------------------------------------------------------- validate / summarize
def validate(cfg, name):
    d = results_frame(cfg, name)
    exp = load_encodes(cfg, name)
    issues = 0
    raw = pd.read_csv(path("results/raw/independent_runs.csv"))
    failed = raw[(raw.profile == name) & (raw.status != "ok")]
    print(f"bitstreams expected={len(exp)}  with results={len(d)}  failed rows in file={len(failed)}")
    if len(failed):
        print(failed[["encode_experiment_id", "error"]].tail(3).to_string(index=False))
        issues += 1
    for m in cfg["independent"]["metrics"]:
        c = INDEP_COL[m]
        have = int(d[c].notna().sum()) if c in d else 0
        print(f"  {m:6s}: {have}/{len(exp)} scored")
        issues += have < len(exp)
    rng = {"xpsnr_mean": (0, 100.01), "lpips_mean": (0, 1.5), "dists_mean": (0, 1.5), "cvvdp_jod": (-5, 10.01)}
    for c, (lo, hi) in rng.items():
        if c in d and d[c].notna().any():
            bad = int(((d[c] < lo) | (d[c] > hi)).sum())
            if bad:
                print(f"Out-of-range {c}: {bad} rows")
                issues += 1
    tol = {"xpsnr_mean": 0.1, "lpips_mean": 0.002, "dists_mean": 0.002, "cvvdp_jod": 0.05}
    # quality must get WORSE with CRF: higher-is-better metrics must not rise, lower-is-better must not fall
    viol = 0
    for _, g in d.groupby(["dataset", "video", "tune", "preset"]):
        g = g.sort_values("crf")
        for c, t in tol.items():
            if c in g and g[c].notna().sum() > 1:
                diff = g[c].diff().dropna()
                viol += int((diff > t).sum()) if HIGHER_BETTER[c] else int((diff < -t).sum())
    print(f"\nCRF-monotonicity violations (quality improving as CRF rises): {viol}")
    issues += viol > 0
    print("RESULT:", "ISSUES FOUND" if issues else "all checks passed")
    return 1 if issues else 0


def summarize(cfg, name):
    d = results_frame(cfg, name)
    suf = name
    base = baseline_name(cfg, d)
    metrics = present(d, cfg["bd_rate"]["metrics"])
    skipped = [m for m in cfg["bd_rate"]["metrics"] if m not in metrics]
    if skipped:
        print(f"NOTE: no data for {skipped}")
    keys = ["profile", "dataset", "video", "resolution_tier", "tune", "preset", "crf"]
    d.sort_values(keys)[keys + metrics + ["bitrate_kbps"]].to_csv(path(f"results/summary/independent_rd_points_{suf}.csv"), index=False)
    db = crf_window(d, cfg)
    if len(db) != len(d):
        print(f"BD-rate uses CRF window {cfg['bd_rate'].get('crf_min')}..{cfg['bd_rate'].get('crf_max')}")
    out = []
    for (ds, vid, tr, pre), g in db.groupby(["dataset", "video", "resolution_tier", "preset"]):
        a = g[g.tune.astype(str) == base].sort_values("crf")
        if a.empty:
            continue
        for tune, t in g[g.tune.astype(str) != base].groupby("tune"):
            t = t.sort_values("crf")
            for m in metrics:
                out.append({"dataset": ds, "video": vid, "resolution_tier": tr, "preset": pre, "tune": tune,
                            "anchor_tune": base, "metric": m,
                            "bd_rate_percent": bd_rate(a.bitrate_kbps, a[m], t.bitrate_kbps, t[m], int(cfg["bd_rate"]["min_points"])),
                            "n_points": min(len(a), len(t))})
    if not out:
        print(f"No BD-rate computed (baseline tune '{base}' missing or too few CRF points)")
        return 1
    b = pd.DataFrame(out)
    b.to_csv(path(f"results/summary/independent_bd_rate_{suf}.csv"), index=False)
    b.groupby(["resolution_tier", "preset", "tune", "metric"], as_index=False).bd_rate_percent.mean() \
        .to_csv(path(f"results/summary/independent_bd_rate_mean_{suf}.csv"), index=False)
    print(f"BD-rate vs '{base}' written ({len(b)} rows)\nSummary written for {suf}")
    return 0


def md_table(df: pd.DataFrame) -> str:
    out = ["| " + " | ".join(map(str, df.columns)) + " |", "|" + "|".join("---" for _ in df.columns) + "|"]
    out += ["| " + " | ".join(str(v) for v in r.values) + " |" for _, r in df.iterrows()]
    return "\n".join(out)


def report(cfg, name):
    d = results_frame(cfg, name)
    bdp = path(f"results/summary/independent_bd_rate_{name}.csv")
    if not bdp.exists():
        raise RuntimeError("Run `summarize` first")
    bd = pd.read_csv(bdp)
    base = bd.anchor_tune.iloc[0]
    indep = [m for m in INDEP_COL.values() if m in bd.metric.unique()]
    refm = [m for m in REF_COLS if m in bd.metric.unique()]
    L = [f"# Independent-metric results (profile: {name})", "", "## 1. What was measured", ""]
    vids = d[["dataset", "video", "resolution_tier"]].drop_duplicates()
    L += [f"- {len(d)} encoded files, {len(vids)} videos. Videos per tier: " +
          ", ".join(f"{t}: {int((vids.resolution_tier.astype(str) == t).sum())}" for t in sorted(vids.resolution_tier.astype(str).unique())) + ".",
          f"- Independent metrics (marked *): {', '.join(NICE[m] for m in indep)}. No encoder tune optimises these.",
          (f"- For comparison, the metrics the tunes do target: {', '.join(NICE[m] for m in refm)} (from WP2)." if refm
           else "- WP2 results were not found, so no side-by-side comparison with PSNR / SSIM / MS-SSIM / VMAF is shown."),
          f"- Each tune is compared with the baseline tune **{base}** using BD-rate (negative = bitrate saved at equal quality).", ""]
    L += ["## 2. Tune comparison", "",
          "Each cell: mean BD-rate over the videos of the tier, and in how many videos the tune beats the baseline.", ""]
    agree_lines = []
    for (tr, pre), g in bd.groupby(["resolution_tier", "preset"]):
        n = g[["dataset", "video"]].drop_duplicates().shape[0]
        L += [f"### {tr}, preset {pre} ({n} video{'s' if n != 1 else ''})", ""]
        rows = []
        for tune, gt in g.groupby("tune"):
            r = {"tune": tune}
            for m in indep + refm:
                x = gt[gt.metric == m].bd_rate_percent.dropna()
                r[NICE[m]] = f"{x.mean():+.1f}% ({int((x < 0).sum())}/{len(x)})" if len(x) else "n/a"
            rows.append(r)
        L += [md_table(pd.DataFrame(rows)), ""]
        winners = {}
        for m in indep + refm:
            mm = g[g.metric == m].groupby("tune").bd_rate_percent.mean().dropna()
            if len(mm):
                mm[str(base)] = 0.0
                winners[m] = mm.idxmin()
        L += ["Best tune per metric: " + "; ".join(f"{NICE[m]}: **{w}**" for m, w in winners.items()) + ".", ""]
        ind_w = {winners[m] for m in indep if m in winners}
        ref_w = {winners[m] for m in refm if m in winners}
        if ind_w and ref_w:
            if len(ind_w) == 1 and ind_w == ref_w:
                msg = f"All independent metrics pick **{next(iter(ind_w))}**, the same as the tune-targeted metrics."
            elif len(ind_w) == 1:
                msg = (f"The independent metrics agree on **{next(iter(ind_w))}**, but the tune-targeted metrics pick "
                       f"{', '.join(sorted(ref_w))}.")
            else:
                msg = "The independent metrics do not agree with each other here: " + ", ".join(sorted(ind_w)) + "."
            L += [msg, ""]
            agree_lines.append(f"- {tr}, preset {pre}: {msg}")
    L += ["## 3. Do the independent metrics support the tune-targeted results?", ""] + (agree_lines or ["(needs WP2 results)"]) + [""]
    L += ["## 4. How to read this and what to be careful about", "",
          "- The tunes optimise PSNR, SSIM, MS-SSIM or VMAF, so a tune winning on its own metric is partly circular. "
          "A gain that also shows on the independent metrics is more credible; a gain that appears only on the tune's own "
          "metric may be specific to that metric.",
          "- XPSNR is a PSNR variant, so it is independent of the tunes but not of the PSNR family. LPIPS and DISTS (neural "
          "features) and ColorVideoVDP (human-vision model with display, colour and motion) are more different.",
          "- Lower is better for LPIPS and DISTS, higher is better for the others. BD-rate signs are the same for all.",
          "- LPIPS and DISTS score every Nth frame; ColorVideoVDP scores the first frames of each video. Details are in the "
          "`settings` column of `results/raw/independent_runs.csv`.",
          "- Few videos per tier, and a wide CRF range, make small differences weak evidence.",
          "- No objective metric replaces viewers: for the final claim about a tune, compare a few clips by eye.", ""]
    text = "\n".join(L)
    out = path(f"results/summary/independent_report_{name}.md")
    out.write_text(text)
    print(text)
    print(f"\nWritten to {out}")
    return 0


# ----------------------------------------------------------------------------- plots
def plot(cfg, name, per_video=False):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    d = results_frame(cfg, name)
    metrics = present(d, list(INDEP_COL.values()))
    dpi = int(cfg["plots"].get("dpi", 150))
    out = path("results/plots")
    made = []

    def save(fig, fname, rect=None):
        fig.tight_layout(rect=rect) if rect else fig.tight_layout()
        fig.savefig(out / fname, dpi=dpi)
        plt.close(fig)
        made.append(out / fname)

    def rd(g, m, title, fname):
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
        axs[0][0].set_ylabel(NICE[m] + ("  (higher = better)" if HIGHER_BETTER[m] else "  (lower = better)"))
        axs[0][-1].legend(title="tune")
        fig.suptitle(title)
        save(fig, fname)

    for tr in sorted(d.resolution_tier.astype(str).unique()):
        gt = d[d.resolution_tier.astype(str) == tr]
        mean = gt.groupby(["tune", "preset", "crf"], as_index=False)[metrics + ["bitrate_kbps"]].mean()
        for m in metrics:
            rd(mean, m, f"mean over {tr} videos", f"independent_rd_mean_{tr}_{m}_{name}.png")
    if per_video:
        for (ds, vid), g in d.groupby(["dataset", "video"]):
            for m in metrics:
                rd(g, m, f"{ds}/{vid}", f"independent_rd_{ds}_{Path(str(vid)).stem}_{m}_{name}.png")
    bdp = path(f"results/summary/independent_bd_rate_{name}.csv")
    if bdp.exists():
        bd = pd.read_csv(bdp)
        for tr, g in bd.groupby("resolution_tier"):
            ms = [m for m in list(INDEP_COL.values()) + REF_COLS if m in g.metric.unique()]
            ncol = min(4, len(ms))
            nrow = math.ceil(len(ms) / ncol)
            fig, axs = plt.subplots(nrow, ncol, figsize=(4.4 * ncol, 3.9 * nrow), squeeze=False)
            for ax in axs.flat[len(ms):]:
                ax.axis("off")
            for ax, m in zip(axs.flat, ms):
                pv = g[g.metric == m].groupby(["preset", "tune"]).bd_rate_percent.mean().unstack("tune")
                pv.plot.bar(ax=ax, rot=0, legend=False, width=0.8)
                for c in ax.containers:
                    ax.bar_label(c, fmt="%.1f", fontsize=7, padding=1)
                ax.axhline(0, color="k", lw=0.8)
                ax.set_title(NICE[m])
                ax.set_xlabel("preset")
                ax.set_ylabel("BD-rate % (negative = better)")
                ax.grid(axis="y", alpha=0.3)
                ax.margins(y=0.12)
            h, lab = axs[0][0].get_legend_handles_labels()
            fig.legend(h, lab, title="tune", loc="lower center", ncol=len(lab))
            fig.suptitle(f"BD-rate vs '{bd.anchor_tune.iloc[0]}', {tr} videos   (* = independent metric)")
            save(fig, f"independent_bd_rate_{tr}_{name}.png", rect=[0, 0.08 if nrow == 1 else 0.05, 1, 0.95])
    else:
        print("Skipping BD-rate plots (run `summarize` first)")
    for f in made:
        print("wrote", f)
    print(f"{len(made)} plots in {out}")
    return 0


# ----------------------------------------------------------------------------- selftest
def mk(cfg, src: Path, out: Path, vf: str | None = None, frames: int | None = None, pix_fmt: str | None = None):
    c = [tool(cfg["tools"]["ffmpeg"]), "-hide_banner", "-nostdin", "-y", "-i", str(src)]
    if frames:
        c += ["-frames:v", str(frames)]
    if vf:
        c += ["-vf", vf]
    if pix_fmt:
        c += ["-pix_fmt", pix_fmt]
    c += ["-strict", "-1", str(out)]
    p = subprocess.run(c, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(f"ffmpeg failed: {shlex.join(c)}\n{p.stderr[-800:]}")
    return out


def selftest(cfg, src_arg, only=None):
    t = cfg["selftest"]
    d = path("results/raw/.selftest_independent")
    d.mkdir(parents=True, exist_ok=True)
    if src_arg:
        src = Path(src_arg)
    else:
        mp = path("data/manifests/source_manifest.csv")
        if not mp.exists():
            raise RuntimeError("Give --input <video.y4m>")
        mf = pd.read_csv(mp)
        mf = mf[mf.resolution_tier == "720p_or_lower"] if (mf.resolution_tier == "720p_or_lower").any() else mf
        src = path("data/source") / str(mf.iloc[0].relative_path)
    n = int(t["frames"])
    ref = mk(cfg, src, d / "ref.y4m", frames=n)
    rp = probe(cfg, ref)
    W, H = rp["width"], rp["height"]
    print(f"Self-test on {src.name}: {W}x{H} {rp['pix_fmt']}, {n} frames\n")
    rows: list[dict] = []

    def add(test, metric, value, expect, passed):
        rows.append({"test": test, "metric": metric, "value": value, "expected": expect,
                     "pass": passed if isinstance(passed, str) else bool(passed)})

    avail = ["xpsnr"]
    sc_args = {}
    for m, loader, hint in (("lpips", lambda: load_lpips(cfg["independent"].get("lpips_net", "alex"), cfg["independent"].get("lpips_device", "auto")),
                             "pip install torch torchvision lpips"),
                            ("dists", lambda: load_dists(cfg["independent"].get("dists_device", "auto")),
                             "pip install torch torchvision DISTS-pytorch")):
        if only and m not in only.split(","):
            continue
        try:
            loader()
            avail.append(m)
        except RuntimeError:
            add(m, "available", "no", f"needs: {hint} (skipped)", "info")
        except Exception as ex:  # noqa: BLE001 - e.g. weights could not be downloaded
            add(m, "available", "no", f"failed to load: {str(ex)[:70]} (skipped)", "info")
    if only and "cvvdp" not in only.split(","):
        pass
    elif cvvdp_available(cfg):
        avail.append("cvvdp")
    else:
        add("cvvdp", "available", "no", "needs: pip install cvvdp (skipped)", "info")
    sc = Scorer(cfg, avail)
    every = max(1, n // 6)
    sc.every = every
    nf = min(n, 10)

    def score(m, dist):
        if m == "cvvdp":
            return cvvdp_score(cfg, ref, dist, nf)[INDEP_COL[m]]
        return sc.score(m, ref, dist)[INDEP_COL[m]]

    fam = {"noise": (t["noise_levels"], lambda s: f"noise=alls={s}:allf=t+u:all_seed=1"),
           "blur": (t["blur_sigmas"], lambda s: f"gblur=sigma={s}"),
           "resize": (t["resize_factors"], lambda s: f"scale=trunc(iw/{s}/2)*2:trunc(ih/{s}/2)*2,scale={W}:{H}")}
    files = {(f, s): mk(cfg, ref, d / f"{f}_{s}.y4m", vf=vf(s)) for f, (lv, vf) in fam.items() for s in lv}
    for m in avail:
        c = INDEP_COL[m]
        idv = score(m, ref)
        if HIGHER_BETTER[c]:
            thr = 50 if m == "xpsnr" else 9.9
            add("identity", c, round(idv, 4), f">={thr}", idv >= thr)
        else:
            add("identity", c, round(idv, 5), "<=0.001", idv <= 0.001)
        for f, (levels, _) in fam.items():
            vals = [score(m, files[(f, s)]) for s in levels]
            diff = np.diff(vals)
            ok = np.all(diff < 0) if HIGHER_BETTER[c] else np.all(diff > 0)
            add(f"monotonic_{f}", c, [round(v, 4) for v in vals],
                "strictly decreasing" if HIGHER_BETTER[c] else "strictly increasing", ok)
    # Luma XPSNR must not change when only the representation (bit depth, chroma format) changes. Luma is used because
    # a 4:2:0 -> 4:4:4 -> 4:2:0 round trip slightly alters the chroma planes themselves.
    base_d = files[("noise", t["noise_levels"][len(t["noise_levels"]) // 2])]
    base_v = sc.score("xpsnr", ref, base_d)["xpsnr_y"]
    pf = rp["pix_fmt"]
    deep = "yuv420p" if ("10" in pf or "12" in pf) else "yuv420p10le"
    chroma = "yuv444p10le" if ("10" in pf or "12" in pf) else "yuv444p"
    for tag, fmt in (("bit_depth", deep), ("chroma", chroma)):
        v = sc.score("xpsnr", ref, mk(cfg, base_d, d / f"alt_{tag}.y4m", pix_fmt=fmt))["xpsnr_y"]
        add(f"{tag}_invariance", "xpsnr_y diff dB", round(abs(v - base_v), 4), "<=0.5", abs(v - base_v) <= 0.5)
    short = mk(cfg, base_d, d / "short.y4m", frames=n - 5)
    k = len(list(iter_frame_pairs(cfg, ref, short, 1)))
    add("frame_count_guard", "frames compared", k, f"{n - 5} (shorter video limits the comparison)", k == n - 5)
    rep = pd.DataFrame(rows)
    pd.set_option("display.width", 200, "display.max_colwidth", 70)
    print(rep.to_string(index=False))
    rep.to_csv(path("results/summary/independent_metric_validation.csv"), index=False)
    failed = int(rep["pass"].map(lambda v: v is False).sum())
    infos = int(rep["pass"].map(lambda v: v == "info").sum())
    print(f"\n{len(rep) - failed - infos}/{len(rep) - infos} checks passed, {failed} failed, {infos} info row(s) "
          f"-> results/summary/independent_metric_validation.csv")
    return 1 if failed else 0


# ----------------------------------------------------------------------------- CLI
def main():
    a = argparse.ArgumentParser()
    a.add_argument("--config", default="config/independent.yaml")
    s = a.add_subparsers(dest="cmd", required=True)
    s.add_parser("preflight")
    e = s.add_parser("evaluate"); e.add_argument("--ref", required=True); e.add_argument("--dist", required=True)
    e.add_argument("--metrics", help="comma list: xpsnr,lpips,dists,cvvdp")
    t = s.add_parser("selftest"); t.add_argument("--input")
    t.add_argument("--metrics", help="test only these (comma list), e.g. xpsnr,lpips,dists; cvvdp can be slow on a CPU")
    p = s.add_parser("plan"); p.add_argument("--profile", choices=PROFILES, required=True); p.add_argument("--metrics")
    r = s.add_parser("run"); r.add_argument("--profile", choices=PROFILES, required=True)
    r.add_argument("--metrics"); r.add_argument("--dry-run", action="store_true"); r.add_argument("--limit", type=int)
    r.add_argument("--rescore", action="store_true", help="score again even if a value exists (e.g. after changing settings)")
    for c in ("validate", "summarize", "report"):
        q = s.add_parser(c); q.add_argument("--profile", choices=PROFILES, required=True)
    pl = s.add_parser("plot"); pl.add_argument("--profile", choices=PROFILES, required=True)
    pl.add_argument("--per-video", action="store_true")
    x = a.parse_args()
    cfg = load_cfg(x.config)
    ensure_dirs()
    return {"preflight": lambda: preflight(cfg), "evaluate": lambda: cmd_evaluate(cfg, x),
            "selftest": lambda: selftest(cfg, x.input, x.metrics), "plan": lambda: plan(cfg, x.profile, x.metrics) is None,
            "run": lambda: run(cfg, x.profile, x.dry_run, x.limit, x.metrics, x.rescore),
            "validate": lambda: validate(cfg, x.profile), "summarize": lambda: summarize(cfg, x.profile),
            "report": lambda: report(cfg, x.profile), "plot": lambda: plot(cfg, x.profile, x.per_video)}[x.cmd]()


if __name__ == "__main__":
    raise SystemExit(main())
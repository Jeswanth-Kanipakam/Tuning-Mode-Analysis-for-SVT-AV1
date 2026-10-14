# OM

# Tuning Mode Analysis for SVT-AV1

## Fixes compared with the old repository

- All video tuning modes supported by SVT-AV1 v4.2.0: **VQ, PSNR, SSIM, MS-SSIM, VMAF**
- IQ/tune 3 is intentionally excluded because v4.2.0 documents it as still-image-only
- Presets **1 and 10**
- CRFs **18, 26, 35, 44, 52, 60** so the middle of the range is sampled
- automatic selection across **<=720p, 1080p, and >1080p/4K** for the meeting profile
- wall-clock and encoder-reported encoding time
- peak process-tree RSS memory
- bitrate from actual output file size and source duration
- exact command logging
- input/output MD5 and SHA-256
- resumable experiments
- five-run confidence profile with 95% Student-t confidence intervals
- plots specifically requested by Jonas
- generated meeting report

## Folder structure

```text
SVT_AV1_Jonas_Ready_Workspace/
├── config/
│   └── experiment.yaml
├── data/
│   ├── source/                 # put new AOM-CTC .y4m videos here
│   ├── manifests/
│   └── encoded/
├── docs/
│   ├── METHODOLOGY.md
│   ├── QUALITY_EVALUATION_PLAN.md
│   └── OLD_SCRIPTS.md
├── logs/
├── results/
│   ├── raw/
│   ├── summary/
│   └── plots/
├── scripts/
│   ├── wp1.py
│   ├── plot_results.py
│   └── make_meeting_report.py
├── requirements.txt
└── run_meeting.sh
```

## 1. Put new videos in `data/source/`

Use subfolders so the dataset identity is preserved, for example:

```text
data/source/
├── a3_720p/
│   └── ControlledBurn_....y4m
├── a2_1080p/
│   └── CrowdRun_....y4m
└── a1_4k/
    └── BoxingPractice_....y4m
```

## 2. Install Python dependencies

```bash
cd SVT_AV1_Workspace
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

External tools must already be available in PATH:

```bash
which SvtAv1EncApp
SvtAv1EncApp --version
ffmpeg -version
ffprobe -version
```

On your existing Homebrew setup, the script finds `/opt/homebrew/bin/SvtAv1EncApp` automatically there is no machine-specific hard-coded encoder path.

## 3. Safe test sequence

```bash
python scripts/wp1.py preflight
python scripts/wp1.py scan
python scripts/wp1.py verify
python scripts/wp1.py plan --profile meeting
python scripts/wp1.py run --profile meeting --dry-run
```

Run exactly one real encode first:

```bash
python scripts/wp1.py run --profile meeting --limit 1
```

If it succeeds, run the complete meeting profile:

```bash
python scripts/wp1.py run --profile meeting
```

The runner is resumable. Re-running the command skips successful experiment IDs.

## 4. Create everything and run

```bash
python scripts/wp1.py summarize --profile meeting
python scripts/wp1.py validate --profile meeting
python scripts/plot_results.py --profile meeting
python scripts/make_meeting_report.py --profile meeting
```

Or after the one-encode test succeeds:

```bash
./run_meeting.sh
```

## 5. Outputs

```text
results/raw/encoding_runs.csv
results/summary/encoding_summary_meeting.csv
results/summary/mean_bitrate_by_crf_meeting.csv
results/summary/mean_encoding_time_by_preset_meeting.csv
results/summary/mean_encoding_time_by_resolution_meeting.csv
results/summary/checksum_report.csv
results/summary/software_snapshot.json
results/summary/MEETING_REPORT.md
results/plots/mean_bitrate_vs_crf_preset_1_meeting.png
results/plots/mean_bitrate_vs_crf_preset_10_meeting.png
results/plots/mean_encoding_time_by_preset_meeting.png
results/plots/mean_encoding_time_by_resolution_meeting.png
```

Generated AV1 bitstreams and full encoder logs are under `data/encoded/meeting/` and `logs/meeting/`.

## 6. Confidence test

After the meeting-profile code is working:

```bash
python scripts/wp1.py plan --profile confidence
python scripts/wp1.py run --profile confidence
python scripts/wp1.py summarize --profile confidence
python scripts/wp1.py validate --profile confidence
```

The default confidence profile deliberately uses one representative 1080p source, PSNR, Presets 1/10 and CRFs 26/35/44 with five measured repetitions plus one warm-up. This establishes timing repeatability without multiplying the entire corpus by six executions.

## 7. Full corpus

Final corrected design:

```bash
python scripts/wp1.py plan --profile full
python scripts/wp1.py run --profile full
python scripts/wp1.py summarize --profile full
python scripts/plot_results.py --profile full
python scripts/wp1.py validate --profile full
```

## Expected behavior to discuss

- Increasing CRF should generally reduce bitrate and reconstructed quality.
- Preset 1 should take substantially longer than Preset 10.
- Higher-resolution content should require more computation and usually more memory.
- Tuning modes may trade metrics differently, so no mode should be declared best only using the metric it optimizes.

## Proposed quality evaluation

The next evaluation stage should decode each bitstream and compare it with the original 
# WP2 – Video Quality Evaluation

Framework for scoring the bitstreams produced by WP1 (SVT-AV1 encodes) against their source videos,
validating the quality metrics themselves, and checking that they are robust against resolution,
chroma subsampling and bit depth.

## What it does

| Goal | How it is addressed |
|---|---|
| Easy-to-use framework implementing various quality metrics | One CLI (`scripts/wp2.py`), one YAML config, one ffmpeg + libvmaf pass per video pair. Ad-hoc `evaluate` command for any ref/dist pair. |
| Validate that the metrics work | `selftest`: identity, monotonicity, cross-check against independent implementations. |
| Robust against resolution, subsampling, … | Normalisation policy (common pixel format + rescaling to reference resolution) and robustness checks in `selftest`. |

### Metrics

| Output column | Metric |
|---|---|
| `psnr_y_mean`, `psnr_cb_mean`, `psnr_cr_mean` | PSNR per plane, averaged over frames |
| `psnr_yuv_mean` | Combined PSNR per frame, `(6·Y + Cb + Cr) / 8`, averaged over frames |
| `ssim_mean` | SSIM (luma) |
| `ms_ssim_mean` | MS-SSIM (luma) |
| `vmaf_mean` | VMAF (`vmaf_v0.6.1`; `vmaf_4k_v0.6.1` for the 2160p tier) |
| `vmaf_harmonic_mean`, `vmaf_min`, `vmaf_p1`, `vmaf_temporal_std` | VMAF pooling variants: harmonic mean, worst frame, 1st percentile, frame-to-frame variation |

Also computed in `summarize`: **BD-rate** (Bjøntegaard delta-rate) of each tune against a baseline tune.

## Requirements

- Python 3.10+ with `numpy`, `pandas`, `pyyaml`, `matplotlib` (only for `plot`)
- `ffmpeg` and `ffprobe` in `PATH`, with:
  - the `libvmaf` filter (`--enable-libvmaf`)
  - an AV1 decoder (`libdav1d` or `libaom-av1`)
- WP1 results in `results/raw/encoding_runs.csv` (not needed for `evaluate` and `selftest --input`)

```bash
pip install numpy pandas pyyaml matplotlib
python scripts/wp2.py preflight      # checks everything above
```

## Repository layout

```
config/quality.yaml            # WP2 settings
scripts/wp2.py                 # CLI
results/raw/quality_runs.csv   # one row per scored bitstream (append-only, resumable)
results/summary/               # RD points, BD-rate, validation report
logs/quality/                  # per-frame libvmaf JSON for every run
```

## Quick start

```bash
# 1. check the environment
python scripts/wp2.py preflight

# 2. validate the metrics (do this once, before trusting any numbers)
python scripts/wp2.py selftest --input data/source/<dataset>/<video>.y4m

# 3. score the WP1 encodes
python scripts/wp2.py plan     --profile meeting
python scripts/wp2.py run      --profile meeting --dry-run
python scripts/wp2.py run      --profile meeting

# 4. check and summarise
python scripts/wp2.py validate  --profile meeting
python scripts/wp2.py summarize --profile meeting
python scripts/wp2.py plot      --profile meeting     # PNGs in results/plots/
```

## Commands

| Command | Description |
|---|---|
| `preflight` | Verifies ffmpeg, libvmaf, VMAF models, AV1 decoder and WP1 results. Writes `results/summary/quality_software_snapshot.json`. |
| `evaluate --ref A --dist B [--scale-flags F] [--pix-fmt P]` | Scores a single pair and prints the metrics as JSON. Works with any format ffmpeg can read. |
| `plan --profile P` | Lists the bitstreams that would be evaluated. |
| `run --profile P [--dry-run] [--limit N]` | Scores all bitstreams of a WP1 profile. Resumable: finished rows are skipped. |
| `validate [--profile P]` | Completeness, NaN/range checks and CRF-monotonicity checks on the results. Exit code 1 if issues are found. |
| `summarize [--profile P]` | Writes RD points, mean quality per setting and BD-rate tables. |
| `plot [--profile P] [--video V] [--preset N] [--crf N]` | Draws RD curves, BD-rate bars and per-frame VMAF curves into `results/plots/`. Run `summarize` first to get the BD-rate figure. |
| `selftest [--input VIDEO]` | Validates the metrics and their robustness. Writes `results/summary/metric_validation.csv`. |

Profiles are the same as in WP1: `meeting`, `confidence`, `full`. The global option `--config` selects a
different YAML file (default `config/quality.yaml`).

## How scoring works

1. `run` reads WP1's `encoding_runs.csv` and keeps rows with `status == ok` and `warmup == 0` whose
   bitstream still exists. Quality is deterministic for identical settings, so only the first measured run
   per `(dataset, video, tune, preset, crf)` is scored.
2. For each pair, one ffmpeg command runs the `libvmaf` filter with the distorted stream as first input and
   the reference as second input.
3. **Normalisation policy** (applied before any metric is computed):
   - if the distorted resolution differs from the reference, it is rescaled to the reference resolution
     with `metrics.scale_flags` (default `bicubic`);
   - both streams are converted to the same pixel format (`metrics.pix_fmt: ref` = the reference's own
     format), so bit depth or chroma format differences between the two files do not leak into the scores;
   - timestamps are reset (`setpts=PTS-STARTPTS`), so the streams are compared frame by frame.
4. Per-frame values are stored in `logs/quality/<profile>/<dataset>/<name>.vmaf.json`; per-video aggregates
   go to `quality_runs.csv`.
5. If the number of scored frames differs from the frame count recorded by WP1, the row gets
   `status = frame_mismatch` and is **not** counted as done (it is retried on the next run and ignored by
   `summarize`).

## Visualisation (`plot`)

`plot` reads `quality_runs.csv` (and `bd_rate_<profile>.csv` if `summarize` was run) and writes PNGs to `results/plots/`:

| File | Content |
|---|---|
| `rd_<dataset>_<video>_<metric>_<profile>.png` | Rate-distortion curves per video: bitrate (log) vs. metric, one panel per preset, one line per tune, one marker per CRF. Curves further up and to the left are better. |
| `rd_mean_<metric>_<profile>.png` | Same, averaged over all videos (only if more than one video was scored). |
| `bd_rate_<profile>.png` | Bars of BD-rate vs. the baseline tune, per preset and metric. Below zero = bitrate saving. |
| `vmaf_per_frame_<dataset>_<video>_<profile>.png` | VMAF per frame, one line per tune, for one preset/CRF (defaults to the middle values; override with `--preset` / `--crf`). Shows *where* in the video quality drops, which the mean hides. |

Metrics shown in the RD plots are set in `plots.metrics` (default `vmaf_mean`, `psnr_yuv_mean`); resolution in `plots.dpi`.

## Metric validation (`selftest`)

Runs on a short clip (`selftest.frames`, default 30) of a source video and writes a pass/fail table.

| Test | What it checks |
|---|---|
| Identity | Reference vs. itself gives the maximum score (PSNR ≥ 50 dB, SSIM/MS-SSIM ≥ 0.9999, VMAF ≥ 99.5). |
| Monotonicity | Increasing noise, blur or downscale factor strictly decreases PSNR, SSIM, MS-SSIM and VMAF. |
| Cross-check | PSNR-Y and SSIM-Y from libvmaf agree with ffmpeg's native `psnr` / `ssim` filters within tolerance. |
| Bit depth invariance | Converting the distorted file to another bit depth does not change scores. |
| Chroma invariance | Converting the distorted *or* the reference file to 4:4:4 / 4:2:0 does not change luma-based scores. |
| Scaling-filter spread | A half-resolution distorted video is scored with bilinear / bicubic / lanczos upscaling. The spread across filters must stay within tolerance. |
| Frame-count guard | A video with 5 missing frames is detected through `frames_scored`. |

Tolerances live in the `selftest` section of `config/quality.yaml`. The defaults are starting values; adjust them
once you have seen real numbers on your data.

Not covered by `selftest`: correlation with subjective scores (SROCC / PLCC against a MOS dataset such as
KoNViD-1k or LIVE-VQA), no-reference metrics, and automatic frame-offset detection.

## Configuration (`config/quality.yaml`)

| Key | Meaning |
|---|---|
| `tools.ffmpeg`, `tools.ffprobe` | Executable names or paths. |
| `inputs.encoding_runs` | Path to WP1's results CSV. |
| `measurement.resume` | Skip already finished rows. |
| `metrics.features` | libvmaf features to compute alongside VMAF (`psnr`, `float_ssim`, `float_ms_ssim`). |
| `metrics.vmaf_model`, `metrics.vmaf_model_4k` | VMAF models; the 4K model is used for the `2160p_or_higher` tier. |
| `metrics.pix_fmt` | `ref` (default) or a fixed ffmpeg pixel format, e.g. `yuv420p10le`. |
| `metrics.scale_flags` | ffmpeg scaler used when resolutions differ. |
| `metrics.threads` | libvmaf threads. |
| `bd_rate.baseline_tune` | Tune name used as BD-rate anchor. **Set this to a tune name from your WP1 config.** |
| `bd_rate.metrics`, `bd_rate.min_points` | Quality axes for BD-rate and minimum number of CRF points. |
| `validate.monotonic_tol_vmaf` | Allowed VMAF increase when CRF rises (noise margin). |
| `plots.metrics`, `plots.dpi` | Metrics drawn in the RD plots and image resolution. |
| `selftest.*` | Clip length, distortion levels and tolerances for `selftest`. |

## Output files

| File | Content |
|---|---|
| `results/raw/quality_runs.csv` | One row per scored bitstream: settings, bitrate (from WP1), all metrics, ffmpeg command, status. |
| `results/summary/rd_points_<profile>.csv` | Rate-distortion points per video / tune / preset / CRF. |
| `results/summary/mean_quality_by_setting_<profile>.csv` | Metrics averaged over videos per tune / preset / CRF. |
| `results/summary/bd_rate_<profile>.csv` | BD-rate per video, preset, tune and metric against the baseline tune. |
| `results/summary/bd_rate_mean_<profile>.csv` | BD-rate averaged per resolution tier, preset, tune and metric. |
| `results/plots/*.png` | Figures written by `plot`. |
| `results/summary/metric_validation.csv` | Result table of `selftest`. |
| `results/summary/quality_software_snapshot.json` | ffmpeg version, platform and config used. |

### Reading BD-rate

A BD-rate of **−5 %** means the tune needs 5 % less bitrate than the baseline tune for the same quality on that
metric; **+5 %** means 5 % more. It is a cubic fit of log-bitrate over quality across the CRF points, integrated
over the overlapping quality range. It needs at least `bd_rate.min_points` CRF values per curve (four are
recommended) and returns NaN if the quality ranges do not overlap.

## Known limitations

- VMAF, SSIM and MS-SSIM here are luma-only; chroma errors are only visible in the PSNR-Cb/Cr columns.
- VMAF models are trained on specific viewing conditions (1080p at 3× screen height for `vmaf_v0.6.1`, 4K TV
  for the 4K model). Scores for other conditions are not directly comparable.
- Resolution mismatches are handled by upscaling the distorted video. The scaling filter changes absolute
  scores, so use one setting for a whole study (`selftest` reports the sensitivity).
- Frame rate differences and frame drops are only detected through frame-count mismatch, not repaired.
- All metrics assume identical content in both files; there is no spatial or temporal alignment step.

## Troubleshooting

| Problem | Fix |
|---|---|
| `MISSING ffmpeg filter: libvmaf` | Install an ffmpeg build with libvmaf enabled. |
| `MISSING AV1 decoder` | Use a build with `libdav1d` or `libaom-av1`. |
| `VMAF model ... FAILED` in preflight | Your libvmaf lacks that built-in model; change `metrics.vmaf_model` / `vmaf_model_4k` or upgrade. |
| Rows skipped: "bitstream deleted by WP1" | WP1 deleted bitstreams (`keep_all_bitstreams: false`); rerun WP1 for those settings or keep run 1 bitstreams. |
| `frame_mismatch` rows | Encoded video has a different frame count than the source (WP1 `-n` limit, dropped frames). Check the encode. |
| Windows paths in filter errors | Prefer paths without drive letters or run from the repository root; colons in filter options need escaping. |


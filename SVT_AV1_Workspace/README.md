# Tuning Mode Analysis for SVT-AV1 — Jonas-Ready WP1 Workspace

This is the cleaned-up Person 1 workspace built around Jonas's latest feedback.

## Fixes compared with the old repository

- all video tuning modes supported by SVT-AV1 v4.2.0: **VQ, PSNR, SSIM, MS-SSIM, VMAF**
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

For the next Jonas meeting, make sure at least one <=720p, one 1080p, and one 4K/>1080p source is present. The meeting profile automatically chooses one from each available tier.

## 2. Install Python dependencies

```bash
cd SVT_AV1_Jonas_Ready_Workspace
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

On your existing Homebrew setup, the script finds `/opt/homebrew/bin/SvtAv1EncApp` automatically; there is no machine-specific hard-coded encoder path.

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

## 4. Create everything Jonas asked to see

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

## 5. Outputs to take to Jonas

```text
results/raw/encoding_runs.csv
results/summary/encoding_summary_meeting.csv
results/summary/mean_bitrate_by_crf_meeting.csv
results/summary/mean_encoding_time_by_preset_meeting.csv
results/summary/mean_encoding_time_by_resolution_meeting.csv
results/summary/checksum_report.csv
results/summary/software_snapshot.json
results/summary/JONAS_MEETING_REPORT.md
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

Only after Jonas agrees with the corrected design:

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

The next evaluation stage should decode each bitstream and compare it with the original using **PSNR, SSIM, MS-SSIM, and VMAF**, build bitrate-quality rate-distortion curves, and use **BD-Rate/BD-Quality** to compare tuning modes.

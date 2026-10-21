# WP2 results summary (profile: meeting)

## 1. What was measured

- 780 encoded files were compared with their originals (13 videos).
- Videos per resolution tier: 2160p_or_higher: 6, 720p_or_lower: 7.
- Tunes: MS_SSIM, PSNR, SSIM, VMAF, VQ. Presets: [1, 10]. CRFs: [18, 26, 35, 44, 52, 60].
- Scores: PSNR, SSIM, MS-SSIM and VMAF. Each tune is compared with the baseline tune **PSNR** using BD-rate.

## 2. How quality and size change with CRF

Baseline tune (PSNR), slowest preset (1), averaged over the videos of each tier.

| tier | CRF | bitrate kbps | VMAF | PSNR dB | SSIM |
|---|---|---|---|---|---|
| 2160p_or_higher | 18 | 115600.03 | 96.90 | 43.19 | 1.00 |
| 2160p_or_higher | 26 | 54310.09 | 95.26 | 42.41 | 1.00 |
| 2160p_or_higher | 35 | 28379.90 | 92.56 | 41.50 | 1.00 |
| 2160p_or_higher | 44 | 15376.91 | 88.13 | 40.44 | 0.99 |
| 2160p_or_higher | 52 | 8981.84 | 82.83 | 39.39 | 0.99 |
| 2160p_or_higher | 60 | 3955.97 | 73.71 | 37.70 | 0.97 |
| 720p_or_lower | 18 | 2242.54 | 98.75 | 44.05 | 0.98 |
| 720p_or_lower | 26 | 1507.94 | 98.50 | 42.66 | 0.98 |
| 720p_or_lower | 35 | 877.58 | 97.40 | 40.94 | 0.97 |
| 720p_or_lower | 44 | 463.38 | 94.08 | 39.20 | 0.95 |
| 720p_or_lower | 52 | 249.69 | 89.67 | 37.63 | 0.93 |
| 720p_or_lower | 60 | 112.20 | 79.76 | 35.23 | 0.90 |

Reading: lower CRF gives higher quality and a bigger file. The table shows how much bitrate each quality step costs.

## 3. Effect of the preset (preset 10 vs. preset 1)

Extra bitrate preset 10 needs to reach the same quality as preset 1, averaged over tunes and videos.

| tier | metric | BD-rate % (preset 10 vs 1) |
|---|---|---|
| 2160p_or_higher | PSNR | 120.2 |
| 2160p_or_higher | VMAF | 65.7 |
| 720p_or_lower | PSNR | 117.1 |
| 720p_or_lower | VMAF | 136.6 |

Positive = the faster preset needs more bitrate (it compresses less efficiently). This is the price paid for encoding speed; compare it with the speed gain measured in WP1.

## 4. Tune comparison (BD-rate vs. PSNR)

Each cell: mean BD-rate over the videos of the tier, and in how many videos the tune beats the baseline (BD-rate below 0). Negative = bitrate saved at equal quality.

### 2160p_or_higher, preset 1 (6 videos)

| tune | VMAF | PSNR | SSIM | MS-SSIM |
|---|---|---|---|---|
| MS_SSIM | +40.5% (0/6) | +20.6% (0/6) | +25.0% (0/6) | +21.2% (0/6) |
| SSIM | +4.5% (0/6) | +3.5% (0/6) | -3.8% (6/6) | -2.6% (6/6) |
| VMAF | -9.9% (6/6) | +5.0% (0/6) | +2.9% (0/6) | +0.2% (4/6) |
| VQ | -0.7% (3/6) | +12.2% (0/6) | +4.0% (1/6) | +7.4% (0/6) |

Best tune per metric: VMAF: **VMAF** (-9.9%); PSNR: **PSNR** (baseline, no tune beats it); SSIM: **SSIM** (-3.8%); MS-SSIM: **SSIM** (-2.6%).

The metrics do **not** agree on one winner here, so the answer depends on which quality measure you trust.

### 2160p_or_higher, preset 10 (6 videos)

| tune | VMAF | PSNR | SSIM | MS-SSIM |
|---|---|---|---|---|
| MS_SSIM | +52.3% (0/6) | +42.8% (0/6) | +60.2% (0/6) | +38.3% (0/6) |
| SSIM | +5.1% (0/6) | +2.3% (1/6) | -3.9% (6/6) | -2.2% (6/6) |
| VMAF | -7.7% (6/6) | +4.7% (1/6) | +3.3% (0/6) | +2.0% (1/6) |
| VQ | +1.8% (3/6) | +14.3% (0/6) | +6.3% (0/6) | +11.1% (0/6) |

Best tune per metric: VMAF: **VMAF** (-7.7%); PSNR: **PSNR** (baseline, no tune beats it); SSIM: **SSIM** (-3.9%); MS-SSIM: **SSIM** (-2.2%).

The metrics do **not** agree on one winner here, so the answer depends on which quality measure you trust.

### 720p_or_lower, preset 1 (7 videos)

| tune | VMAF | PSNR | SSIM | MS-SSIM |
|---|---|---|---|---|
| MS_SSIM | +23.1% (0/7) | +16.3% (0/7) | +0.4% (3/7) | -9.6% (7/7) |
| SSIM | +9.2% (0/7) | +10.6% (0/7) | -4.2% (7/7) | -7.9% (7/7) |
| VMAF | -12.8% (7/7) | +5.5% (0/7) | -3.4% (7/7) | +1.0% (2/7) |
| VQ | +6.8% (2/7) | +4.8% (0/7) | +4.4% (1/7) | +2.6% (1/7) |

Best tune per metric: VMAF: **VMAF** (-12.8%); PSNR: **PSNR** (baseline, no tune beats it); SSIM: **SSIM** (-4.2%); MS-SSIM: **MS_SSIM** (-9.6%).

The metrics do **not** agree on one winner here, so the answer depends on which quality measure you trust.

### 720p_or_lower, preset 10 (7 videos)

| tune | VMAF | PSNR | SSIM | MS-SSIM |
|---|---|---|---|---|
| MS_SSIM | +16.9% (1/7) | +9.0% (0/7) | -5.7% (7/7) | -15.2% (7/7) |
| SSIM | +6.9% (0/7) | +9.3% (0/7) | -4.0% (6/7) | -7.9% (7/7) |
| VMAF | -11.5% (6/7) | +1.9% (0/7) | -3.1% (5/7) | +0.4% (4/7) |
| VQ | +1.0% (4/7) | +7.3% (0/7) | +13.8% (1/7) | +7.3% (0/7) |

Best tune per metric: VMAF: **VMAF** (-11.5%); PSNR: **PSNR** (baseline, no tune beats it); SSIM: **MS_SSIM** (-5.7%); MS-SSIM: **MS_SSIM** (-15.2%).

The metrics do **not** agree on one winner here, so the answer depends on which quality measure you trust.

## 5. How to read this and what to be careful about

- BD-rate compares bitrate at equal quality over the overlapping quality range. Comparing tunes at the same CRF is misleading, because tunes change the bitrate as well.
- **PSNR** is the reference, so it is not listed. A tune that optimises something else will usually look worse on PSNR's own metric.
- VMAF is the most perceptual score here; PSNR measures pixel error only. When they disagree, say so instead of picking one.
- SSIM and MS-SSIM from libvmaf are computed on downsampled frames, so compare them only inside one resolution tier.
- Each quality value comes from one encode per setting (quality is deterministic). Small differences (a few percent) between tunes, or tiers with only a few videos, are not strong evidence.
- The CRF range is wide, so very low and very high quality regions both enter the BD-rate fit.

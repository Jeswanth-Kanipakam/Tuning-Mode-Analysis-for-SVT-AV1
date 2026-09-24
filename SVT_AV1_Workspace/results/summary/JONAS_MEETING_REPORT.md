# Jonas Meeting — WP1 Results

## Experiment configuration

- Video tunes: VQ, PSNR, SSIM, MS-SSIM, VMAF
- Presets: 1, 10
- CRFs: 18, 26, 35, 44, 52, 60
- Timing: wall-clock time
- Memory: peak process-tree RSS

## Source videos

| dataset   | video                                   | resolution_tier   |   width |   height |      fps |   bit_depth |
|:----------|:----------------------------------------|:------------------|--------:|---------:|---------:|------------:|
| a1_4k     | Jockey_3840x2160_120fps_8bit.y4m        | 2160p_or_higher   |    3840 |     2160 | 120      |           8 |
| a1_4k     | MeridianRoad_3840x2160_5994_hdr10.y4m   | 2160p_or_higher   |    3840 |     2160 |  59.9401 |          10 |
| a1_4k     | ReadySteadyGo_3840x2160_120fps_8bit.y4m | 2160p_or_higher   |    3840 |     2160 | 120      |           8 |
| a1_4k     | ShakeNDry_3840x2160_120fps_8bit.y4m     | 2160p_or_higher   |    3840 |     2160 | 120      |           8 |
| a1_4k     | SparksWelding_4096x2160_5994_hdr10.y4m  | 2160p_or_higher   |    4096 |     2160 |  59.9401 |          10 |
| a1_4k     | YachtRide_3840x2160_120fps_8bit.y4m     | 2160p_or_higher   |    3840 |     2160 | 120      |           8 |
| a4_360p   | BlueSky_360p25.y4m                      | 720p_or_lower     |     640 |      360 |  25      |           8 |
| a4_360p   | BlueSky_360p25_v2.y4m                   | 720p_or_lower     |     640 |      360 |  25      |           8 |
| a4_360p   | RedKayak_360_2997.y4m                   | 720p_or_lower     |     640 |      360 |  29.97   |           8 |
| a4_360p   | SnowMountain_640x360_2997.y4m           | 720p_or_lower     |     640 |      360 |  29.97   |           8 |
| a4_360p   | SpeedBag_640x360_2997.y4m               | 720p_or_lower     |     640 |      360 |  29.97   |           8 |
| a4_360p   | Stockholm_640x360_5994.y4m              | 720p_or_lower     |     640 |      360 |  59.9401 |           8 |
| a4_360p   | TouchdownPass_640x360_2997.y4m          | 720p_or_lower     |     640 |      360 |  29.97   |           8 |

## Mean bitrate by CRF

|   preset | tune    |   crf |   bitrate_kbps |
|---------:|:--------|------:|---------------:|
|        1 | MS_SSIM |    18 |      123093    |
|        1 | MS_SSIM |    26 |       59966.6  |
|        1 | MS_SSIM |    35 |       29317.1  |
|        1 | MS_SSIM |    44 |       14377.2  |
|        1 | MS_SSIM |    52 |        8331.54 |
|        1 | MS_SSIM |    60 |        4018.98 |
|        1 | PSNR    |    18 |       54561.4  |
|        1 | PSNR    |    26 |       25878.2  |
|        1 | PSNR    |    35 |       13571    |
|        1 | PSNR    |    44 |        7346.55 |
|        1 | PSNR    |    52 |        4279.92 |
|        1 | PSNR    |    60 |        1886.25 |
|        1 | SSIM    |    18 |       57458.5  |
|        1 | SSIM    |    26 |       25896.9  |
|        1 | SSIM    |    35 |       13381.6  |
|        1 | SSIM    |    44 |        7106.42 |
|        1 | SSIM    |    52 |        4113.81 |
|        1 | SSIM    |    60 |        1815.98 |
|        1 | VMAF    |    18 |       70078.2  |
|        1 | VMAF    |    26 |       27947.1  |
|        1 | VMAF    |    35 |       14108.2  |
|        1 | VMAF    |    44 |        7574.22 |
|        1 | VMAF    |    52 |        4392.7  |
|        1 | VMAF    |    60 |        1917.72 |
|        1 | VQ      |    18 |       63811.5  |
|        1 | VQ      |    26 |       27811.1  |
|        1 | VQ      |    35 |       13701    |
|        1 | VQ      |    44 |        7399.34 |
|        1 | VQ      |    52 |        4313.53 |
|        1 | VQ      |    60 |        1904.13 |
|       10 | MS_SSIM |    18 |      198446    |
|       10 | MS_SSIM |    26 |       97120.8  |
|       10 | MS_SSIM |    35 |       44490.6  |
|       10 | MS_SSIM |    44 |       20421.6  |
|       10 | MS_SSIM |    52 |       10538.3  |
|       10 | MS_SSIM |    60 |        4190.6  |
|       10 | PSNR    |    18 |      116238    |
|       10 | PSNR    |    26 |       45317.4  |
|       10 | PSNR    |    35 |       19801.5  |
|       10 | PSNR    |    44 |        9658.47 |
|       10 | PSNR    |    52 |        5063.08 |
|       10 | PSNR    |    60 |        2033.09 |
|       10 | SSIM    |    18 |      114304    |
|       10 | SSIM    |    26 |       44988.6  |
|       10 | SSIM    |    35 |       19308.6  |
|       10 | SSIM    |    44 |        9329.75 |
|       10 | SSIM    |    52 |        4846.1  |
|       10 | SSIM    |    60 |        2002.16 |
|       10 | VMAF    |    18 |      150179    |
|       10 | VMAF    |    26 |       52763.4  |
|       10 | VMAF    |    35 |       20710.9  |
|       10 | VMAF    |    44 |       10111.9  |
|       10 | VMAF    |    52 |        5264.36 |
|       10 | VMAF    |    60 |        2095.82 |
|       10 | VQ      |    18 |      135356    |
|       10 | VQ      |    26 |       53673.3  |
|       10 | VQ      |    35 |       21245.6  |
|       10 | VQ      |    44 |       10219    |
|       10 | VQ      |    52 |        5357.57 |
|       10 | VQ      |    60 |        2158    |

## Mean encoding time by preset

|   preset |   wall_time_seconds |
|---------:|--------------------:|
|        1 |           278.325   |
|       10 |             6.74462 |

## Mean peak memory by resolution and preset

| resolution_tier   |   preset |   peak_rss_mib |
|:------------------|---------:|---------------:|
| 2160p_or_higher   |        1 |       7275.33  |
| 2160p_or_higher   |       10 |       3045.38  |
| 720p_or_lower     |        1 |        345.485 |
| 720p_or_lower     |       10 |        132.903 |

## Expected video-quality evaluation

Decode each bitstream and compare it with its original using PSNR, SSIM, MS-SSIM and VMAF. Use bitrate-quality RD curves and BD-Rate/BD-Quality to compare tuning modes across CRF points. Treat evaluation metrics independently from the encoder tuning objective.

## Plots

See `results/plots/` for Jonas's requested validation plots.
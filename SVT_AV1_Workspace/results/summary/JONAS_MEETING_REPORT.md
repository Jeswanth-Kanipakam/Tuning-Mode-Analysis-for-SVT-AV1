# Jonas Meeting — WP1 Results

## Experiment configuration

- Video tunes: VQ, PSNR, SSIM, MS-SSIM, VMAF
- Presets: 1, 10
- CRFs: 18, 26, 35, 44, 52, 60
- Timing: wall-clock time
- Memory: peak process-tree RSS

## Source videos

| dataset   | video                                  | resolution_tier   |   width |   height |     fps |   bit_depth |
|:----------|:---------------------------------------|:------------------|--------:|---------:|--------:|------------:|
| a1_4k     | MeridianRoad_3840x2160_5994_hdr10.y4m  | 2160p_or_higher   |    3840 |     2160 | 59.9401 |          10 |
| a1_4k     | SparksWelding_4096x2160_5994_hdr10.y4m | 2160p_or_higher   |    4096 |     2160 | 59.9401 |          10 |
| a4_360p   | BlueSky_360p25.y4m                     | 720p_or_lower     |     640 |      360 | 25      |           8 |
| a4_360p   | BlueSky_360p25_v2.y4m                  | 720p_or_lower     |     640 |      360 | 25      |           8 |
| a4_360p   | RedKayak_360_2997.y4m                  | 720p_or_lower     |     640 |      360 | 29.97   |           8 |
| a4_360p   | SnowMountain_640x360_2997.y4m          | 720p_or_lower     |     640 |      360 | 29.97   |           8 |
| a4_360p   | SpeedBag_640x360_2997.y4m              | 720p_or_lower     |     640 |      360 | 29.97   |           8 |
| a4_360p   | Stockholm_640x360_5994.y4m             | 720p_or_lower     |     640 |      360 | 59.9401 |           8 |
| a4_360p   | TouchdownPass_640x360_2997.y4m         | 720p_or_lower     |     640 |      360 | 29.97   |           8 |

## Mean bitrate by CRF

|   preset | tune    |   crf |   bitrate_kbps |
|---------:|:--------|------:|---------------:|
|        1 | MS_SSIM |    18 |      43245.4   |
|        1 | MS_SSIM |    26 |      22898.3   |
|        1 | MS_SSIM |    35 |      12554.6   |
|        1 | MS_SSIM |    44 |       6615.18  |
|        1 | MS_SSIM |    52 |       3701.12  |
|        1 | MS_SSIM |    60 |       1737.37  |
|        1 | PSNR    |    18 |      21972.8   |
|        1 | PSNR    |    26 |      12397.3   |
|        1 | PSNR    |    35 |       6311.94  |
|        1 | PSNR    |    44 |       3345.98  |
|        1 | PSNR    |    52 |       1886.41  |
|        1 | PSNR    |    60 |        777.441 |
|        1 | SSIM    |    18 |      21779.2   |
|        1 | SSIM    |    26 |      12121.5   |
|        1 | SSIM    |    35 |       6063.99  |
|        1 | SSIM    |    44 |       3139.55  |
|        1 | SSIM    |    52 |       1751.04  |
|        1 | SSIM    |    60 |        721.863 |
|        1 | VMAF    |    18 |      26620.8   |
|        1 | VMAF    |    26 |      13927.3   |
|        1 | VMAF    |    35 |       6727     |
|        1 | VMAF    |    44 |       3550.03  |
|        1 | VMAF    |    52 |       1986.92  |
|        1 | VMAF    |    60 |        809.307 |
|        1 | VQ      |    18 |      23271.5   |
|        1 | VQ      |    26 |      12766.2   |
|        1 | VQ      |    35 |       6383.58  |
|        1 | VQ      |    44 |       3371.42  |
|        1 | VQ      |    52 |       1904.54  |
|        1 | VQ      |    60 |        788.64  |
|       10 | MS_SSIM |    18 |      59090     |
|       10 | MS_SSIM |    26 |      33329.4   |
|       10 | MS_SSIM |    35 |      17906.8   |
|       10 | MS_SSIM |    44 |       9377.32  |
|       10 | MS_SSIM |    52 |       4922.55  |
|       10 | MS_SSIM |    60 |       1876.92  |
|       10 | PSNR    |    18 |      34779.2   |
|       10 | PSNR    |    26 |      18587.4   |
|       10 | PSNR    |    35 |       9216.42  |
|       10 | PSNR    |    44 |       4559.79  |
|       10 | PSNR    |    52 |       2356.49  |
|       10 | PSNR    |    60 |        870.453 |
|       10 | SSIM    |    18 |      34259     |
|       10 | SSIM    |    26 |      18330.9   |
|       10 | SSIM    |    35 |       8972.33  |
|       10 | SSIM    |    44 |       4321.62  |
|       10 | SSIM    |    52 |       2173.75  |
|       10 | SSIM    |    60 |        819.113 |
|       10 | VMAF    |    18 |      45141.5   |
|       10 | VMAF    |    26 |      21167.3   |
|       10 | VMAF    |    35 |       9841.93  |
|       10 | VMAF    |    44 |       4883.83  |
|       10 | VMAF    |    52 |       2504.96  |
|       10 | VMAF    |    60 |        910.763 |
|       10 | VQ      |    18 |      38606.6   |
|       10 | VQ      |    26 |      19832.2   |
|       10 | VQ      |    35 |       9535.73  |
|       10 | VQ      |    44 |       4727.78  |
|       10 | VQ      |    52 |       2449.16  |
|       10 | VQ      |    60 |        916.988 |

## Mean encoding time by preset

|   preset |   wall_time_seconds |
|---------:|--------------------:|
|        1 |            61.4833  |
|       10 |             1.61785 |

## Mean peak memory by resolution and preset

| resolution_tier   |   preset |   peak_rss_mib |
|:------------------|---------:|---------------:|
| 2160p_or_higher   |        1 |       8829.55  |
| 2160p_or_higher   |       10 |       3725.96  |
| 720p_or_lower     |        1 |        345.485 |
| 720p_or_lower     |       10 |        132.903 |

## Expected video-quality evaluation

Decode each bitstream and compare it with its original using PSNR, SSIM, MS-SSIM and VMAF. Use bitrate-quality RD curves and BD-Rate/BD-Quality to compare tuning modes across CRF points. Treat evaluation metrics independently from the encoder tuning objective.

## Plots

See `results/plots/` for Jonas's requested validation plots.
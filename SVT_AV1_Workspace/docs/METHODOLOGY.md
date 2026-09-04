# WP1 Measurement Methodology

## Meeting/full encoding grid

- Tunes: VQ, PSNR, SSIM, MS-SSIM, VMAF
- Presets: 1 and 10
- CRFs: 18, 26, 35, 44, 52, 60

IQ/tune 3 is excluded because SVT-AV1 v4.2.0 documents it as still-image-only.

## Timing

The runner records external wall-clock time with `time.perf_counter()` and also records the encoder-reported time when it can be parsed. External wall time is used for comparison and confidence statistics.

## Memory

Peak resident memory is sampled for the encoder process and its descendants every 0.10 s. This is a sampling-based peak RSS measurement, so the same method and interval should be kept for all compared runs.

## Confidence

The confidence profile uses one warm-up followed by five measured runs. For repeated configurations, the summary calculates mean, sample standard deviation, coefficient of variation, and a two-sided Student-t 95% confidence interval.

## Reproducibility

Each run records the complete command, input/output MD5 and SHA-256, return code, log path, tune/preset/CRF, software snapshot, and machine/OS information.

# Video Quality Evaluation — Preparation for Jonas

## Proposed metrics

**PSNR**: baseline pixel-domain fidelity measure.

**SSIM**: structural similarity measure that captures local structure more directly than squared error.

**MS-SSIM**: multi-scale structural similarity.

**VMAF**: perceptual video-quality metric.

## Rate-distortion workflow

For every source, preset and tuning mode, encode CRFs 18, 26, 35, 44, 52 and 60; record bitrate; decode the bitstream; compare the reconstruction with the original using PSNR/SSIM/MS-SSIM/VMAF; build bitrate-versus-quality curves; then calculate BD-Rate or BD-Quality between tuning modes.

The evaluation metric must be treated independently from the encoder tuning objective. A PSNR-tuned encode should not be called generally best just because it scores best on PSNR.

## Questions to confirm with Jonas

- Should metrics always be calculated at native resolution?
- Should 10-bit material remain 10-bit throughout metric computation?
- Which tuning mode should be the BD-Rate reference curve?
- Should BD values be computed per sequence first and then aggregated by AOM-CTC class?
- Are HDR classes in scope now or later?

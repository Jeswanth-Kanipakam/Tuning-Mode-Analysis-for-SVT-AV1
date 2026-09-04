Place new AOM-CTC Y4M videos in subfolders here, then run:

python scripts/wp1.py scan

Example:
data/source/a3_720p/ControlledBurn_....y4m
data/source/a2_1080p/CrowdRun_....y4m
data/source/a1_4k/BoxingPractice_....y4m

The scanner creates data/manifests/source_manifest.csv. If you have official expected AOM-CTC MD5 values, paste them into the expected_md5 column and rerun `python scripts/wp1.py verify`.

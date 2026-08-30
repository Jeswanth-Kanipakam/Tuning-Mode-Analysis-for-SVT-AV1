import subprocess
import re
import csv
import statistics
from pathlib import Path
from collections import defaultdict

# ==================================================
# PROJECT PATHS
# ==================================================

PROJECT_DIR = Path(
    '~/research/projects/svt-av1-tuning-analysis'
).expanduser()

ENCODER = Path(
    '~/research/tools/SVT-AV1/Bin/Release/SvtAv1EncApp'
).expanduser()

SOURCE_DIR = PROJECT_DIR / 'data/source'
OUTPUT_DIR = PROJECT_DIR / 'data/encodes'
RESULTS_DIR = PROJECT_DIR / 'results'
LOG_DIR = PROJECT_DIR / 'logs'

# ==================================================
# EXPERIMENT CONFIGURATION
# ==================================================
TUNING_MODES = {
    'PSNR': 1
}
#TUNING_MODES = {
#   'VQ': 0,
#    'PSNR': 1,
#   'SSIM': 2,
#   'IQ': 3,
#    'MS_SSIM': 4,
#   'VMAF': 5
#}

# Professor recommendation
PRESETS = [1, 10]

# Professor recommendation
CRFS = [18, 26, 44, 52, 60]

NUMBER_OF_RUNS = 5
WARMUP_RUNS = 1
THREADS = 8

# ==================================================
# CREATE DIRECTORIES
# ==================================================

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ==================================================
# PARSE ENCODER OUTPUT
# ==================================================

def parse_encoder_output(output: str):
    """Extract timing, speed, bitrate, and frame count from SVT-AV1 log."""

    encoding_time_match = re.search(
        r'Total Encoding Time:\s+(\d+)\s+ms',
        output
    )

    speed_match = re.search(
        r'Average Speed:\s+([0-9.]+)\s+fps',
        output
    )

    bitrate_match = re.search(
        r'Average Bitrate:\s+([0-9.]+)\s+kbps',
        output
    )

    if bitrate_match is None:
        bitrate_match = re.search(
            r'([0-9.]+)\s+kbps',
            output
        )

    frames_match = re.search(
        r'Total Frames\s+(\d+)',
        output
    )

    return {
        'encoding_time_ms': (
            int(encoding_time_match.group(1))
            if encoding_time_match else None
        ),
        'average_speed_fps': (
            float(speed_match.group(1))
            if speed_match else None
        ),
        'bitrate_kbps': (
            float(bitrate_match.group(1))
            if bitrate_match else None
        ),
        'frames': (
            int(frames_match.group(1))
            if frames_match else None
        )
    }

# ==================================================
# FIND ALL VIDEOS
# ==================================================

videos = []

for dataset_folder in sorted(SOURCE_DIR.iterdir()):
    if not dataset_folder.is_dir():
        continue

    for video in sorted(dataset_folder.glob('*.y4m')):
        videos.append({
            'dataset': dataset_folder.name,
            'video': video
        })

print(f'\nFound {len(videos)} videos.')
print(f'Tuning modes: {len(TUNING_MODES)}')
print(f'Presets: {PRESETS}')
print(f'CRFs: {CRFS}')
print(f'Runs per configuration: {NUMBER_OF_RUNS}')
print(f'Total encodes: {len(videos) * len(TUNING_MODES) * len(PRESETS) * len(CRFS) * NUMBER_OF_RUNS}')

# ==================================================
# CSV FILES
# ==================================================

RAW_RESULTS_FILE = RESULTS_DIR / 'raw_results.csv'
SUMMARY_RESULTS_FILE = RESULTS_DIR / 'summary_results.csv'

raw_fieldnames = [
    'dataset',
    'video',
    'tune',
    'tune_value',
    'preset',
    'crf',
    'run',
    'frames',
    'bitrate_kbps',
    'encoding_time_ms',
    'average_speed_fps'
]

summary_fieldnames = [
    'dataset',
    'video',
    'tune',
    'preset',
    'crf',
    'mean_time_ms',
    'std_time_ms',
    'cv_percent',
    'mean_speed_fps',
    'mean_bitrate_kbps'
]

# ==================================================
# MAIN EXPERIMENT LOOP
# ==================================================

all_results = []

for preset in PRESETS:

    print('\n' + '=' * 80)
    print(f'PRESET {preset}')
    print('=' * 80)

    for crf in CRFS:

        print('\n' + '-' * 80)
        print(f'CRF {crf}')
        print('-' * 80)

        for tune_name, tune_value in TUNING_MODES.items():

            print(f'\nTUNE: {tune_name}')

            for video_index, item in enumerate(videos, start=1):

                dataset = item['dataset']
                input_video = item['video']

                print(f'[{video_index}/{len(videos)}] {dataset} | {input_video.name}')

                video_output_dir = (
                    OUTPUT_DIR /
                    f'preset_{preset}' /
                    f'crf_{crf}' /
                    tune_name /
                    dataset /
                    input_video.stem
                )

                video_log_dir = (
                    LOG_DIR /
                    f'preset_{preset}' /
                    f'crf_{crf}' /
                    tune_name /
                    dataset /
                    input_video.stem
                )

                video_output_dir.mkdir(parents=True, exist_ok=True)
                video_log_dir.mkdir(parents=True, exist_ok=True)

                # --------------------------------------------------
                # Warm-up run
                # --------------------------------------------------

                for warmup in range(WARMUP_RUNS):

                    warmup_file = video_output_dir / f'warmup_{warmup + 1}.ivf'

                    warmup_command = [
                        str(ENCODER),
                        '-i', str(input_video),
                        '-b', str(warmup_file),
                        '--preset', str(preset),
                        '--crf', str(crf),
                        '--tune', str(tune_value),
                        '--lp', str(THREADS)
                    ]

                    subprocess.run(
                        warmup_command,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )

                # --------------------------------------------------
                # Measured runs
                # --------------------------------------------------

                for run_number in range(1, NUMBER_OF_RUNS + 1):

                    print(f'  Run {run_number}/{NUMBER_OF_RUNS}')

                    output_file = (
                        video_output_dir /
                        f'run_{run_number}.ivf'
                    )

                    log_file = (
                        video_log_dir /
                        f'run_{run_number}.log'
                    )

                    command = [
                        str(ENCODER),
                        '-i', str(input_video),
                        '-b', str(output_file),
                        '--preset', str(preset),
                        '--crf', str(crf),
                        '--tune', str(tune_value),
                        '--lp', str(THREADS)
                    ]

                    result = subprocess.run(
                        command,
                        capture_output=True,
                        text=True
                    )

                    output = result.stdout + result.stderr

                    with open(log_file, 'w') as file:
                        file.write(output)

                    if result.returncode != 0:
                        print('  ERROR')
                        continue

                    measurements = parse_encoder_output(output)

                    row = {
                        'dataset': dataset,
                        'video': input_video.name,
                        'tune': tune_name,
                        'tune_value': tune_value,
                        'preset': preset,
                        'crf': crf,
                        'run': run_number,
                        'frames': measurements['frames'],
                        'bitrate_kbps': measurements['bitrate_kbps'],
                        'encoding_time_ms': measurements['encoding_time_ms'],
                        'average_speed_fps': measurements['average_speed_fps']
                    }

                    all_results.append(row)

# ==================================================
# SAVE RAW RESULTS
# ==================================================

with open(RAW_RESULTS_FILE, 'w', newline='') as file:

    writer = csv.DictWriter(file, fieldnames=raw_fieldnames)
    writer.writeheader()
    writer.writerows(all_results)

print(f'\nRaw results saved to: {RAW_RESULTS_FILE}')

# ==================================================
# AGGREGATE SUMMARY
# ==================================================

grouped = defaultdict(list)

for row in all_results:

    key = (
        row['dataset'],
        row['video'],
        row['tune'],
        row['preset'],
        row['crf']
    )

    grouped[key].append(row)

summary_rows = []

for key, rows in grouped.items():

    dataset, video, tune, preset, crf = key

    times = [
        r['encoding_time_ms']
        for r in rows
        if r['encoding_time_ms'] is not None
    ]

    speeds = [
        r['average_speed_fps']
        for r in rows
        if r['average_speed_fps'] is not None
    ]

    bitrates = [
        r['bitrate_kbps']
        for r in rows
        if r['bitrate_kbps'] is not None
    ]

    if len(times) == 0:
        continue

    mean_time = statistics.mean(times)
    std_time = statistics.stdev(times) if len(times) > 1 else 0.0
    cv = (std_time / mean_time * 100) if mean_time > 0 else 0.0

    mean_speed = statistics.mean(speeds) if speeds else None
    mean_bitrate = statistics.mean(bitrates) if bitrates else None

    summary_rows.append({
        'dataset': dataset,
        'video': video,
        'tune': tune,
        'preset': preset,
        'crf': crf,
        'mean_time_ms': round(mean_time, 2),
        'std_time_ms': round(std_time, 2),
        'cv_percent': round(cv, 2),
        'mean_speed_fps': round(mean_speed, 3) if mean_speed else None,
        'mean_bitrate_kbps': round(mean_bitrate, 3) if mean_bitrate else None
    })

with open(SUMMARY_RESULTS_FILE, 'w', newline='') as file:

    writer = csv.DictWriter(file, fieldnames=summary_fieldnames)
    writer.writeheader()
    writer.writerows(summary_rows)

print(f'Summary results saved to: {SUMMARY_RESULTS_FILE}')

# ==================================================
# PRINT SUMMARY TABLE
# ==================================================

print('\n' + '=' * 120)
print('SUMMARY')
print('=' * 120)

header = (
    f'{"Dataset":<12}'
    f'{"Video":<32}'
    f'{"Tune":<10}'
    f'{"P":<5}'
    f'{"CRF":<6}'
    f'{"Mean(ms)":<12}'
    f'{"Std(ms)":<12}'
    f'{"CV(%)":<10}'
)

print(header)
print('-' * 120)

for row in summary_rows:

    print(
        f'{row["dataset"]:<12}'
        f'{row["video"][:31]:<32}'
        f'{row["tune"]:<10}'
        f'{row["preset"]:<5}'
        f'{row["crf"]:<6}'
        f'{row["mean_time_ms"]:<12}'
        f'{row["std_time_ms"]:<12}'
        f'{row["cv_percent"]:<10}'
    )

print('=' * 120)
print('\nExperiment completed successfully.')

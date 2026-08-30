import subprocess
import re
import csv
from pathlib import Path


# --------------------------------------------------
# Paths
# --------------------------------------------------

ENCODER = Path(
    "~/research/tools/SVT-AV1/Bin/Release/SvtAv1EncApp"
).expanduser()

PROJECT_DIR = Path(
    "~/research/projects/svt-av1-tuning-analysis"
).expanduser()

INPUT_VIDEO = (
    PROJECT_DIR /
    "data/source/park_joy_90p_8_420.y4m"
)

OUTPUT_BITSTREAM = (
    PROJECT_DIR /
    "data/encoded/park_joy_test.ivf"
)

RESULTS_FILE = (
    PROJECT_DIR /
    "results/encoding/encoding_results.csv"
)

LOG_FILE = (
    PROJECT_DIR /
    "logs/park_joy_test.log"
)


# --------------------------------------------------
# Create required directories
# --------------------------------------------------

OUTPUT_BITSTREAM.parent.mkdir(
    parents=True,
    exist_ok=True
)

RESULTS_FILE.parent.mkdir(
    parents=True,
    exist_ok=True
)

LOG_FILE.parent.mkdir(
    parents=True,
    exist_ok=True
)


# --------------------------------------------------
# SVT-AV1 command
# --------------------------------------------------

command = [
    str(ENCODER),

    "-i",
    str(INPUT_VIDEO),

    "-b",
    str(OUTPUT_BITSTREAM),

    "--preset",
    "8",

    "--qp",
    "30"
]


# --------------------------------------------------
# Run encoder
# --------------------------------------------------

print("Starting SVT-AV1 encoding...")

result = subprocess.run(
    command,
    capture_output=True,
    text=True
)


# Combine stdout and stderr
output = result.stdout + result.stderr


# Save complete encoder log
with open(
    LOG_FILE,
    "w"
) as log_file:

    log_file.write(output)


# Check for errors
if result.returncode != 0:

    print("Encoding failed!")

    print(output)

    raise SystemExit(1)


print("Encoding completed successfully.")


# --------------------------------------------------
# Extract measurements
# --------------------------------------------------

frames_match = re.search(
    r"Total Frames\s+(\d+)",
    output
)

bitrate_match = re.search(
    r"(\d+\.\d+)\s+kbps",
    output
)

encoding_time_match = re.search(
    r"Total Encoding Time\s+(\d+)\s+ms",
    output
)

speed_match = re.search(
    r"Average Speed:\s+(\d+\.\d+)\s+fps",
    output
)


# Extract values
frames = (
    frames_match.group(1)
    if frames_match
    else None
)

bitrate = (
    bitrate_match.group(1)
    if bitrate_match
    else None
)

encoding_time = (
    encoding_time_match.group(1)
    if encoding_time_match
    else None
)

average_speed = (
    speed_match.group(1)
    if speed_match
    else None
)


# --------------------------------------------------
# Save results
# --------------------------------------------------

result_row = {

    "video":
    INPUT_VIDEO.name,

    "tune":
    "PSNR",

    "preset":
    8,

    "qp":
    30,

    "frames":
    frames,

    "bitrate_kbps":
    bitrate,

    "encoding_time_ms":
    encoding_time,

    "average_speed_fps":
    average_speed
}


fieldnames = list(
    result_row.keys()
)


file_exists = RESULTS_FILE.exists()


with open(
    RESULTS_FILE,
    "a",
    newline=""
) as csv_file:

    writer = csv.DictWriter(
        csv_file,
        fieldnames=fieldnames
    )

    if not file_exists:

        writer.writeheader()

    writer.writerow(
        result_row
    )


print(
    f"Results saved to: {RESULTS_FILE}"
)

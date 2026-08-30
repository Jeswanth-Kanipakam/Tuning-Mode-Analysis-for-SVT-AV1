import subprocess
import re
import csv
from pathlib import Path


# ==================================================
# PROJECT PATHS
# ==================================================

PROJECT_DIR = Path(
    "~/research/projects/svt-av1-tuning-analysis"
).expanduser()

ENCODER = Path(
    "~/research/tools/SVT-AV1/Bin/Release/SvtAv1EncApp"
).expanduser()

INPUT_DIR = (
    PROJECT_DIR /
    "data/source/a3_720p"
)

OUTPUT_DIR = (
    PROJECT_DIR /
    "data/encoded/a3_720p"
)

RESULTS_FILE = (
    PROJECT_DIR /
    "results/encoding/a3_720p_results.csv"
)

LOG_DIR = (
    PROJECT_DIR /
    "logs/a3_720p"
)


# ==================================================
# ENCODING CONFIGURATION
# ==================================================

PRESET = 8
QP = 30
TUNE = 0


# ==================================================
# CREATE DIRECTORIES
# ==================================================

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)

RESULTS_FILE.parent.mkdir(
    parents=True,
    exist_ok=True
)

LOG_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ==================================================
# PARSE Y4M HEADER
# ==================================================

def parse_y4m_header(video_path):

    with open(
        video_path,
        "rb"
    ) as file:

        header = file.readline().decode(
            "ascii",
            errors="ignore"
        ).strip()


    width_match = re.search(
        r"W(\d+)",
        header
    )

    height_match = re.search(
        r"H(\d+)",
        header
    )

    fps_match = re.search(
        r"F(\d+):(\d+)",
        header
    )

    chroma_match = re.search(
        r"C([^\s]+)",
        header
    )


    width = (
        int(width_match.group(1))
        if width_match
        else None
    )

    height = (
        int(height_match.group(1))
        if height_match
        else None
    )


    if fps_match:

        fps_num = int(
            fps_match.group(1)
        )

        fps_den = int(
            fps_match.group(2)
        )

        fps = fps_num / fps_den

    else:

        fps = None


    chroma = (
        chroma_match.group(1)
        if chroma_match
        else None
    )


    # Determine bit depth
    if chroma and (
        "p10" in chroma
        or "10" in chroma
    ):

        bit_depth = 10

    elif chroma and (
        "p12" in chroma
        or "12" in chroma
    ):

        bit_depth = 12

    else:

        bit_depth = 8


    return {

        "width": width,

        "height": height,

        "fps": round(
            fps,
            3
        )
        if fps
        else None,

        "bit_depth": bit_depth,

        "chroma_format": chroma

    }


# ==================================================
# PARSE SVT-AV1 OUTPUT
# ==================================================

def parse_encoder_output(output):


    frames_match = re.search(
        r"Total Frames\s+(\d+)",
        output
    )


    bitrate_match = re.search(
        r"(\d+\.\d+)\s+kbps",
        output
    )


    encoding_time_match = re.search(
        r"Total Encoding Time:\s+(\d+)\s+ms",
        output
    )


    speed_match = re.search(
        r"Average Speed:\s+(\d+\.\d+)\s+fps",
        output
    )


    return {

        "frames": (

            int(
                frames_match.group(1)
            )

            if frames_match

            else None

        ),

        "bitrate_kbps": (

            float(
                bitrate_match.group(1)
            )

            if bitrate_match

            else None

        ),

        "encoding_time_ms": (

            int(
                encoding_time_match.group(1)
            )

            if encoding_time_match

            else None

        ),

        "average_speed_fps": (

            float(
                speed_match.group(1)
            )

            if speed_match

            else None

        )

    }


# ==================================================
# FIND INPUT VIDEOS
# ==================================================

input_videos = sorted(
    INPUT_DIR.glob("*.y4m")
)


if not input_videos:

    print(
        f"No Y4M videos found in {INPUT_DIR}"
    )

    raise SystemExit(1)


print(
    f"\nFound {len(input_videos)} input videos.\n"
)


# ==================================================
# RESULTS
# ==================================================

results = []


# ==================================================
# PROCESS EACH VIDEO
# ==================================================

for index, input_video in enumerate(
    input_videos,
    start=1
):


    print(
        f"[{index}/{len(input_videos)}] "
        f"Encoding {input_video.name}"
    )


    # ----------------------------------------------
    # Extract metadata
    # ----------------------------------------------

    metadata = parse_y4m_header(
        input_video
    )


    # ----------------------------------------------
    # Output paths
    # ----------------------------------------------

    output_bitstream = (

        OUTPUT_DIR /

        f"{input_video.stem}.ivf"

    )


    log_file = (

        LOG_DIR /

        f"{input_video.stem}.log"

    )


    # ----------------------------------------------
    # SVT-AV1 command
    # ----------------------------------------------

    command = [

        str(ENCODER),

        "-i",

        str(input_video),

        "-b",

        str(output_bitstream),

        "--preset",

        str(PRESET),

        "--qp",

        str(QP),

        "--tune",

        str(TUNE)

    ]


    # ----------------------------------------------
    # Run encoder
    # ----------------------------------------------

    result = subprocess.run(

        command,

        capture_output=True,

        text=True

    )


    output = (

        result.stdout +

        result.stderr

    )


    # ----------------------------------------------
    # Save log
    # ----------------------------------------------

    with open(

        log_file,

        "w"

    ) as log_file_handle:


        log_file_handle.write(
            output
        )


    # ----------------------------------------------
    # Check encoder status
    # ----------------------------------------------

    if result.returncode != 0:

        print(
            f"ERROR encoding {input_video.name}"
        )

        print(output)

        continue


    # ----------------------------------------------
    # Extract encoding measurements
    # ----------------------------------------------

    encoding_data = parse_encoder_output(
        output
    )


    # ----------------------------------------------
    # Create result row
    # ----------------------------------------------

    row = {

        "video":
        input_video.name,

        "width":
        metadata["width"],

        "height":
        metadata["height"],

        "fps":
        metadata["fps"],

        "bit_depth":
        metadata["bit_depth"],

        "chroma_format":
        metadata["chroma_format"],

        "tune":
        "PSNR",

        "preset":
        PRESET,

        "qp":
        QP,

        "frames":
        encoding_data["frames"],

        "bitrate_kbps":
        encoding_data["bitrate_kbps"],

        "encoding_time_ms":
        encoding_data["encoding_time_ms"],

        "average_speed_fps":
        encoding_data["average_speed_fps"]

    }


    results.append(
        row
    )


    print(
        "Completed."
    )


# ==================================================
# SAVE CSV
# ==================================================

fieldnames = [

    "video",

    "width",

    "height",

    "fps",

    "bit_depth",

    "chroma_format",

    "tune",

    "preset",

    "qp",

    "frames",

    "bitrate_kbps",

    "encoding_time_ms",

    "average_speed_fps"

]


with open(

    RESULTS_FILE,

    "w",

    newline=""

) as csv_file:


    writer = csv.DictWriter(

        csv_file,

        fieldnames=fieldnames

    )


    writer.writeheader()


    writer.writerows(
        results
    )


# ==================================================
# DISPLAY RESULTS AS TABLE
# ==================================================

print("\n")
print("=" * 150)

print(
    "A3 720p SVT-AV1 ENCODING RESULTS"
)

print("=" * 150)


headers = [

    "Video",

    "Resolution",

    "FPS",

    "Bit Depth",

    "Chroma",

    "Tune",

    "QP",

    "Frames",

    "Bitrate",

    "Time",

    "Speed"

]


print(

    f"{headers[0]:<40}"

    f"{headers[1]:<12}"

    f"{headers[2]:<8}"

    f"{headers[3]:<10}"

    f"{headers[4]:<12}"

    f"{headers[5]:<8}"

    f"{headers[6]:<6}"

    f"{headers[7]:<8}"

    f"{headers[8]:<12}"

    f"{headers[9]:<10}"

    f"{headers[10]:<12}"

)


print("-" * 150)


for row in results:

    resolution = (
        f"{row['width']}x"
        f"{row['height']}"
    )

    print(

        f"{str(row['video']):<40}"

        f"{str(resolution):<12}"

        f"{str(row['fps']):<8}"

        f"{str(row['bit_depth']):<10}"

        f"{str(row['chroma_format']):<12}"

        f"{str(row['tune']):<8}"

        f"{str(row['qp']):<6}"

        f"{str(row['frames']):<8}"

        f"{str(row['bitrate_kbps']):<12}"

        f"{str(row['encoding_time_ms']):<10}"

        f"{str(row['average_speed_fps']):<12}"

    )


print("=" * 150)


print(

    f"\nResults saved to:\n"

    f"{RESULTS_FILE}\n"

)

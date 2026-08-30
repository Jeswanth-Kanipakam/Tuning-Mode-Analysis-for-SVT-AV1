import subprocess
import re
import csv
from pathlib import Path


# ==================================================
# PATHS
# ==================================================

PROJECT_DIR = Path(
    "~/research/projects/svt-av1-tuning-analysis"
).expanduser()

ENCODER = Path(
    "~/research/tools/SVT-AV1/Bin/Release/SvtAv1EncApp"
).expanduser()

SOURCE_DIR = PROJECT_DIR / "data/source"

ENCODED_DIR = PROJECT_DIR / "data/encoded"

LOG_DIR = PROJECT_DIR / "logs"

RESULTS_FILE = (
    PROJECT_DIR /
    "results/encoding/all_encoding_results.csv"
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

ENCODED_DIR.mkdir(
    parents=True,
    exist_ok=True
)

LOG_DIR.mkdir(
    parents=True,
    exist_ok=True
)

RESULTS_FILE.parent.mkdir(
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


    if chroma and "p10" in chroma:

        bit_depth = 10

    elif chroma and "p12" in chroma:

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
# FIND ALL DATASET FOLDERS
# ==================================================

dataset_folders = sorted(

    [

        folder

        for folder in SOURCE_DIR.iterdir()

        if folder.is_dir()

    ]

)


if not dataset_folders:

    print(
        "No dataset folders found."
    )

    raise SystemExit(1)


print(
    f"\nFound {len(dataset_folders)} dataset folders.\n"
)


# ==================================================
# CSV COLUMNS
# ==================================================

fieldnames = [

    "dataset",

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


results = []


# ==================================================
# PROCESS ALL DATASETS
# ==================================================

for dataset_folder in dataset_folders:


    dataset_name = (

        dataset_folder.name

    )


    print(
        f"\n===== {dataset_name} ====="
    )


    input_videos = sorted(

        dataset_folder.glob(
            "*.y4m"
        )

    )


    if not input_videos:

        print(
            "No Y4M videos found."
        )

        continue


    dataset_encoded_dir = (

        ENCODED_DIR /

        dataset_name

    )


    dataset_log_dir = (

        LOG_DIR /

        dataset_name

    )


    dataset_encoded_dir.mkdir(

        parents=True,

        exist_ok=True

    )


    dataset_log_dir.mkdir(

        parents=True,

        exist_ok=True

    )


    for index, input_video in enumerate(

        input_videos,

        start=1

    ):


        print(

            f"[{index}/{len(input_videos)}] "

            f"{input_video.name}"

        )


        metadata = parse_y4m_header(

            input_video

        )


        output_bitstream = (

            dataset_encoded_dir /

            f"{input_video.stem}.ivf"

        )


        log_path = (

            dataset_log_dir /

            f"{input_video.stem}.log"

        )


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


        result = subprocess.run(

            command,

            capture_output=True,

            text=True

        )


        output = (

            result.stdout +

            result.stderr

        )


        with open(

            log_path,

            "w"

        ) as log_file:


            log_file.write(

                output

            )


        if result.returncode != 0:


            print(

                f"ERROR: {input_video.name}"

            )

            continue


        encoding_data = (

            parse_encoder_output(

                output

            )

        )


        row = {


            "dataset":

            dataset_name,


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

            "Completed"

        )


# ==================================================
# SAVE CSV
# ==================================================

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
# DISPLAY RESULTS
# ==================================================

print("\n")

print("=" * 180)

print(

    "ALL SVT-AV1 ENCODING RESULTS"

)

print("=" * 180)


print(

    f"{'Dataset':<12}"

    f"{'Video':<40}"

    f"{'Resolution':<12}"

    f"{'FPS':<8}"

    f"{'Bit':<6}"

    f"{'Tune':<8}"

    f"{'QP':<6}"

    f"{'Frames':<8}"

    f"{'Bitrate':<12}"

    f"{'Time(ms)':<12}"

    f"{'Speed':<12}"

)


print("-" * 180)


for row in results:


    resolution = (

        f"{row['width']}x"

        f"{row['height']}"

    )


    print(

        f"{str(row['dataset']):<12}"

        f"{str(row['video'])[:39]:<40}"

        f"{str(resolution):<12}"

        f"{str(row['fps']):<8}"

        f"{str(row['bit_depth']):<6}"

        f"{str(row['tune']):<8}"

        f"{str(row['qp']):<6}"

        f"{str(row['frames']):<8}"

        f"{str(row['bitrate_kbps']):<12}"

        f"{str(row['encoding_time_ms']):<12}"

        f"{str(row['average_speed_fps']):<12}"

    )


print("=" * 180)


print(

    "\nResults saved to:"

)

print(

    RESULTS_FILE

)

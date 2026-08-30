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


SOURCE_DIR = (
    PROJECT_DIR /
    "data/source"
)


ENCODED_DIR = (
    PROJECT_DIR /
    "data/encoded"
)


LOG_DIR = (
    PROJECT_DIR /
    "logs"
)


RESULTS_FILE = (

    PROJECT_DIR /

    "results/encoding/"

    "experiment_matrix.csv"

)


# ==================================================
# EXPERIMENT CONFIGURATION
# ==================================================

TUNING_MODES = {

    "VQ": 0,

    "PSNR": 1,

    "SSIM": 2,

    "IQ": 3,

    "MS_SSIM": 4,

    "VMAF": 5

}


QP_VALUES = [

    20,

    30,

    40

]


PRESET = 8


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


        header = (

            file.readline()

            .decode(

                "ascii",

                errors="ignore"

            )

            .strip()

        )


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

        int(

            width_match.group(1)

        )

        if width_match

        else None

    )


    height = (

        int(

            height_match.group(1)

        )

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


        "fps": (

            round(

                fps,

                3

            )

            if fps

            else None

        ),


        "bit_depth": bit_depth,


        "chroma_format": chroma

    }


# ==================================================
# PARSE ENCODER OUTPUT
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
# FIND DATASETS
# ==================================================

dataset_folders = sorted(

    [

        folder

        for folder in SOURCE_DIR.iterdir()

        if folder.is_dir()

    ]

)


# ==================================================
# FIND ALL EXPERIMENTS
# ==================================================

experiments = []


for dataset_folder in dataset_folders:


    dataset_name = (

        dataset_folder.name

    )


    input_videos = sorted(

        dataset_folder.glob(

            "*.y4m"

        )

    )


    for input_video in input_videos:


        for tune_name, tune_value in (

            TUNING_MODES.items()

        ):


            for qp in QP_VALUES:


                experiments.append(

                    {


                        "dataset":

                        dataset_name,


                        "video":

                        input_video,


                        "tune_name":

                        tune_name,


                        "tune_value":

                        tune_value,


                        "qp":

                        qp

                    }

                )


print(

    f"\nTotal experiments: "

    f"{len(experiments)}\n"

)


# ==================================================
# RESULT COLUMNS
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

    "tune_value",

    "preset",

    "qp",

    "frames",

    "bitrate_kbps",

    "encoding_time_ms",

    "average_speed_fps"

]


results = []


# ==================================================
# RUN EXPERIMENTS
# ==================================================

for index, experiment in enumerate(

    experiments,

    start=1

):


    dataset = (

        experiment["dataset"]

    )


    input_video = (

        experiment["video"]

    )


    tune_name = (

        experiment["tune_name"]

    )


    tune_value = (

        experiment["tune_value"]

    )


    qp = (

        experiment["qp"]

    )


    print(

        f"\n[{index}/{len(experiments)}] "

        f"{dataset} | "

        f"{input_video.name} | "

        f"{tune_name} | "

        f"QP {qp}"

    )


    metadata = parse_y4m_header(

        input_video

    )


    output_dir = (

        ENCODED_DIR /

        dataset /

        tune_name /

        f"QP{qp}"

    )


    log_dir = (

        LOG_DIR /

        dataset /

        tune_name /

        f"QP{qp}"

    )


    output_dir.mkdir(

        parents=True,

        exist_ok=True

    )


    log_dir.mkdir(

        parents=True,

        exist_ok=True

    )


    output_bitstream = (

        output_dir /

        f"{input_video.stem}.ivf"

    )


    log_file = (

        log_dir /

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

        str(qp),


        "--tune",

        str(tune_value)

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

        log_file,

        "w"

    ) as file:


        file.write(

            output

        )


    if result.returncode != 0:


        print(

            "ERROR"

        )


        continue


    encoding_data = (

        parse_encoder_output(

            output

        )

    )


    row = {


        "dataset":

        dataset,


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

        tune_name,


        "tune_value":

        tune_value,


        "preset":

        PRESET,


        "qp":

        qp,


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

) as file:


    writer = csv.DictWriter(

        file,

        fieldnames=fieldnames

    )


    writer.writeheader()


    writer.writerows(

        results

    )


print(

    "\nExperiment completed."

)


print(

    "Results saved to:"

)


print(

    RESULTS_FILE

)

import subprocess
import re
import csv
import statistics
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


OUTPUT_DIR = (
    PROJECT_DIR /
    "data/confidence_test"
)


RESULTS_DIR = (
    PROJECT_DIR /
    "results/confidence"
)


LOG_DIR = (
    PROJECT_DIR /
    "logs/confidence_test"
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


PRESET = 8

QP = 30

NUMBER_OF_RUNS = 5


# ==================================================
# CREATE DIRECTORIES
# ==================================================

OUTPUT_DIR.mkdir(

    parents=True,

    exist_ok=True

)


RESULTS_DIR.mkdir(

    parents=True,

    exist_ok=True

)


LOG_DIR.mkdir(

    parents=True,

    exist_ok=True

)


# ==================================================
# PARSE ENCODER OUTPUT
# ==================================================

def parse_encoder_output(output):


    encoding_time_match = re.search(

        r"Total Encoding Time:\s+(\d+)\s+ms",

        output

    )


    speed_match = re.search(

        r"Average Speed:\s+(\d+\.\d+)\s+fps",

        output

    )


    bitrate_match = re.search(

        r"(\d+\.\d+)\s+kbps",

        output

    )


    frames_match = re.search(

        r"Total Frames\s+(\d+)",

        output

    )


    return {


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

        ),


        "bitrate_kbps": (

            float(

                bitrate_match.group(1)

            )

            if bitrate_match

            else None

        ),


        "frames": (

            int(

                frames_match.group(1)

            )

            if frames_match

            else None

        )

    }


# ==================================================
# FIND ALL DATASETS AND VIDEOS
# ==================================================

videos = []


for dataset_folder in sorted(

    SOURCE_DIR.iterdir()

):


    if not dataset_folder.is_dir():

        continue


    for video in sorted(

        dataset_folder.glob(

            "*.y4m"

        )

    ):


        videos.append(

            {

                "dataset":

                dataset_folder.name,


                "video":

                video

            }

        )


print(

    f"\nFound {len(videos)} videos."

)


print(

    f"Tuning modes: "

    f"{len(TUNING_MODES)}"

)


print(

    f"Runs per video: "

    f"{NUMBER_OF_RUNS}"

)


print(

    f"Total encodings: "

    f"{len(videos) * len(TUNING_MODES) * NUMBER_OF_RUNS}"

)


# ==================================================
# RUN EACH TUNING MODE
# ==================================================

for tune_name, tune_value in (

    TUNING_MODES.items()

):


    print("\n")

    print("=" * 80)

    print(

        f"CONFIDENCE TEST: {tune_name}"

    )

    print("=" * 80)


    results = []


    # ----------------------------------------------
    # PROCESS ALL VIDEOS
    # ----------------------------------------------

    for video_index, item in enumerate(

        videos,

        start=1

    ):


        dataset = (

            item["dataset"]

        )


        input_video = (

            item["video"]

        )


        print(

            f"\n[{video_index}/{len(videos)}] "

            f"{dataset} | "

            f"{input_video.name}"

        )


        video_output_dir = (

            OUTPUT_DIR /

            tune_name /

            dataset /

            input_video.stem

        )


        video_log_dir = (

            LOG_DIR /

            tune_name /

            dataset /

            input_video.stem

        )


        video_output_dir.mkdir(

            parents=True,

            exist_ok=True

        )


        video_log_dir.mkdir(

            parents=True,

            exist_ok=True

        )


        # ------------------------------------------
        # REPEAT ENCODING
        # ------------------------------------------

        for run_number in range(

            1,

            NUMBER_OF_RUNS + 1

        ):


            print(

                f"  Run "

                f"{run_number}/"

                f"{NUMBER_OF_RUNS}"

            )


            output_file = (

                video_output_dir /

                f"run_{run_number}.ivf"

            )


            log_file = (

                video_log_dir /

                f"run_{run_number}.log"

            )


            command = [

                str(ENCODER),


                "-i",


                str(input_video),


                "-b",


                str(output_file),


                "--preset",


                str(PRESET),


                "--qp",


                str(QP),


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

                    "  ERROR"

                )


                continue


            measurements = (

                parse_encoder_output(

                    output

                )

            )


            results.append(

                {


                    "dataset":

                    dataset,


                    "video":

                    input_video.name,


                    "tune":

                    tune_name,


                    "tune_value":

                    tune_value,


                    "preset":

                    PRESET,


                    "qp":

                    QP,


                    "run":

                    run_number,


                    "frames":

                    measurements[

                        "frames"

                    ],


                    "bitrate_kbps":

                    measurements[

                        "bitrate_kbps"

                    ],


                    "encoding_time_ms":

                    measurements[

                        "encoding_time_ms"

                    ],


                    "average_speed_fps":

                    measurements[

                        "average_speed_fps"

                    ]

                }

            )


    # ==================================================
    # SAVE RAW RESULTS
    # ==================================================

    result_file = (

        RESULTS_DIR /

        f"{tune_name}_confidence.csv"

    )


    fieldnames = [

        "dataset",

        "video",

        "tune",

        "tune_value",

        "preset",

        "qp",

        "run",

        "frames",

        "bitrate_kbps",

        "encoding_time_ms",

        "average_speed_fps"

    ]


    with open(

        result_file,

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


    # ==================================================
    # DISPLAY SUMMARY
    # ==================================================

    print("\n")

    print(

        f"{tune_name} SUMMARY"

    )


    print("-" * 100)


    print(

        f"{'Dataset':<12}"

        f"{'Video':<40}"

        f"{'Mean(ms)':<12}"

        f"{'Std(ms)':<12}"

        f"{'CV(%)':<10}"

    )


    print("-" * 100)


    # Group results by video

    grouped = {}


    for row in results:


        key = (

            row["dataset"],

            row["video"]

        )


        if key not in grouped:

            grouped[key] = []


        if (

            row["encoding_time_ms"]

            is not None

        ):


            grouped[key].append(

                row["encoding_time_ms"]

            )


    for key, times in grouped.items():


        dataset, video = key


        if len(times) >= 2:


            mean_time = (

                statistics.mean(

                    times

                )

            )


            std_time = (

                statistics.stdev(

                    times

                )

            )


            cv = (

                std_time /

                mean_time

            ) * 100


            print(

                f"{dataset:<12}"

                f"{video[:39]:<40}"

                f"{mean_time:<12.2f}"

                f"{std_time:<12.2f}"

                f"{cv:<10.2f}"

            )


    print("-" * 100)


    print(

        f"\nResults saved to:\n"

        f"{result_file}"

    )

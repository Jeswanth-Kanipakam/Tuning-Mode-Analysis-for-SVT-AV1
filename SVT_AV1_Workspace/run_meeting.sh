#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ -d .venv ]]; then source .venv/bin/activate; fi
python scripts/wp1.py preflight
python scripts/wp1.py scan
python scripts/wp1.py verify
python scripts/wp1.py plan --profile meeting
python scripts/wp1.py run --profile meeting
python scripts/wp1.py summarize --profile meeting
python scripts/wp1.py validate --profile meeting
python scripts/plot_results.py --profile meeting
python scripts/make_meeting_report.py --profile meeting
echo "Ready: results/summary/JONAS_MEETING_REPORT.md and results/plots/"

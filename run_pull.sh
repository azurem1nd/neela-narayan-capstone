#!/bin/bash
# Absolute paths throughout: cron's PATH/cwd can't be relied on.
# If this repo is ever moved, update the paths below.
set -euo pipefail
cd "/Users/nn/TANGIBLE_WORK/NeelaNarayan-capstone"
"/Users/nn/TANGIBLE_WORK/NeelaNarayan-capstone/.venv/bin/python" pull_history.py >> pull.log 2>&1

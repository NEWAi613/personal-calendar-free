#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 generate_calendar.py
git add calendar.ics
git commit -m "update calendar feed" || true
git push

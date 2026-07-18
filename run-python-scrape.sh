#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"
touch "scraper-last-run"
python3 ./courtbot.py run

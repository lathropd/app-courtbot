#!/bin/bash
set -euo pipefail

echo $COURTBOT_USER
echo $COURTBOT_PASSWORD
echo $GMAIL_USER
echo $GMAIL_PWD


cd "$(dirname "$0")"
touch "scraper-last-run"
python3 ./courtbot.py run

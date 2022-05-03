#!/bin/bash

source ~/.profile
cd `dirname $0`
touch "scraper-last-run"
carton exec -- ./courtbot.pl
carton exec -- ./send-email.pl


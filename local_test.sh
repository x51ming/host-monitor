#!/bin/bash
make -C src install
trap "kill 0" SIGINT

export GOHM_ADDR=0.0.0.0:7203
export GOHM_ALLOW=127.0.0.1/32
bin/hmonitor &

PYTHONPATH=. bin/main.py --addr 0.0.0.0 --port 5001 &

while true ; do
    sleep 1s
done

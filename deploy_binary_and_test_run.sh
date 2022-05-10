#!/bin/bash

# please modify this environment variable
# example: FRONT_END=10.1.2.3 TARGET_FILENAME=/tmp/host-monitor
FRONT_END=${FRONT_END}
TARGET_FILENAME=${TARGET_FILENAME}

if [ "$FRONT_END" == "" ]; then
    echo 'Please set $FRONT_END'
    exit 1
fi

if [ "$TARGET_FILENAME" == "" ]; then
    echo 'Please set $TARGET_FILENAME'
    exit 1
fi

if [ "$1" == "" ]; then
    echo '编译'
    make -C src clean
    make -C src install
    echo '编译完成'

    echo 上传
    parallel-ssh -t 3 -h pssh-hosts "pkill $(basename $TARGET_FILENAME) ; mkdir -pv $(dirname $TARGET_FILENAME)"
    parallel-scp -t 3 -h pssh-hosts bin/hmonitor $TARGET_FILENAME
    parallel-scp -t 3 -h pssh-hosts $0 /tmp/hmonitor.sh
    echo ===============
    parallel-ssh -it 3 -h pssh-hosts "chmod +x /tmp/hmonitor.sh && FRONT_END=$FRONT_END TARGET_FILENAME=$TARGET_FILENAME /tmp/hmonitor.sh start"
    echo '这里会显示超时，不要紧，hmonitor已经在后台运行'

    echo '请手动部署前端'
else
    set -o errexit
    export GOHM_ADDR=0.0.0.0:9203
    export GOHM_ALLOW=$FRONT_END/32
    chmod +x $TARGET_FILENAME
    nohup $TARGET_FILENAME 2>&1 >/tmp/hm.log &
fi

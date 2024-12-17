#!/bin/bash

set -e

echo "-- HOME is $HOME"

VENV_PATH=/.local/.venv

export PIP_CACHE_DIR=/.local/.pipcache

PIP="$VENV_PATH/bin/pip"
PIP_INSTALL="$VENV_PATH/bin/pip install -U --upgrade-strategy=eager"

if [ ! -e $VENV_PATH ]; then
    echo "-- Creating virtual env"
    python3 -m venv --system-site-package $VENV_PATH
fi


echo "-- Installing packages"
$PIP_INSTALL -q pip setuptools wheel
$PIP_INSTALL -q --prefer-binary -r /src/docker/requirements.txt

$PIP install --no-deps \
    -e /src/python_modules/qjazz-contrib   \
    -e /src/python_modules/qjazz-cache     \
    -e .

LOGLEVEL=${LOGLEVEL:-info}

exec $VENV_PATH/bin/python -m qjazz_printserver -C tests/worker-config.toml -l $LOGLEVEL

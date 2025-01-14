#!/bin/bash

set -e

echo "-- HOME is $HOME"

VENV_PATH=/.local/.venv

export PIP_CACHE_DIR=/.local/.pipcache

PIP="$VENV_PATH/bin/pip"
PIP_INSTALL="$VENV_PATH/bin/pip install -U --upgrade-strategy=eager"

exec $VENV_PATH/bin/python -m qjazz_processes serve

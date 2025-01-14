#!/bin/bash

SOURCE=`dirname ${BASH_SOURCE[0]}`

export $(cat $SOURCE/tests.env)
exec ipython -i $SOURCE/prelude.py

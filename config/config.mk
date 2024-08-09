
topsrcdir:=$(shell realpath $(DEPTH))

# Global project version
VERSION=1.0.0.dev0
VERSION_SHORT=1.0dev0

REQUIREMENTS=requirements.txt

PYTHON=python3

MYPY=mypy --config-file=$(topsrcdir)/config/mypy.ini

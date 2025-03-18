
topsrcdir:=$(shell realpath $(DEPTH))

QJAZZ_VERSION=0.1.0

ifndef CI_COMMIT_TAG
QJAZZ_VERSION_RC_TAG=dev0
VERSION=$(QJAZZ_VERSION).$(QJAZZ_VERSION_RC_TAG)
# Global project version
else 
VERSION=$(QJAZZ_VERSION)
endif

REQUIREMENTS=requirements.txt

PYTHON=python3

MYPY=mypy --config-file=$(topsrcdir)/config/mypy.ini

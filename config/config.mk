
topsrcdir:=$(shell realpath $(DEPTH))

VERSION=0.1.0

ifdef CI_COMMIT_TAG
ifeq ($(shell echo $(CI_COMMIT_TAG) | head -c 8), release-)
	BUILD_RELEASE=$(shell date -u +%Y-%m-%dT%H-%M-%SZ)
endif
endif

ifndef BUILD_RELEASE
QJAZZ_VERSION_RC_TAG=dev0
VERSION_TAG=$(VERSION).$(QJAZZ_VERSION_RC_TAG)
else
VERSION_TAG=$(VERSION)
endif

REQUIREMENTS=requirements.txt

PYTHON=python3

MYPY=mypy --config-file=$(topsrcdir)/config/mypy.ini

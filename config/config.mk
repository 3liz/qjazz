
topsrcdir:=$(shell realpath $(DEPTH))

VERSION=0.2.0

ifdef CI_COMMIT_TAG
ifeq ($(shell echo $(CI_COMMIT_TAG) | head -c 8), release-)
	BUILD_RELEASE=$(shell date -u +%Y-%m-%dT%H-%M-%SZ)
endif
endif

REQUIREMENTS=requirements.txt

PYTHON=python3

MYPY=mypy --config-file=$(topsrcdir)/config/mypy.ini

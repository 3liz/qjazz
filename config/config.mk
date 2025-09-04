
topsrcdir:=$(shell realpath $(DEPTH))

VERSION=0.4.0

ifdef CI_COMMIT_TAG
ifeq ($(shell echo $(CI_COMMIT_TAG) | head -c 8), release-)
	BUILD_RELEASE=$(shell date -u +%Y-%m-%dT%H-%M-%SZ)
endif
endif

DIST=$(DEPTH)/dist

PYTHON=python3

ifdef VIRTUAL_ENV
# Always prefer active environment 
ACTIVE_VENV=--active
endif

UV_RUN=uv run $(ACTIVE_VENV)

MYPY=$(UV_RUN) mypy --config-file=$(topsrcdir)/config/mypy.ini
RUFF=$(UV_RUN) ruff
BANDIT=$(UV_RUN) bandit

-include .buildconfig

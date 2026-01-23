
topsrcdir:=$(shell realpath $(DEPTH))

-include $(topsrcdir)/config/build.mk

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

# See https://docs.astral.sh/uv/reference/environment/#rust_log
ifdef UV_DEBUG
	export RUST_LOG=uv=debug
endif

RUN=uv run $(ACTIVE_VENV)

MYPY=$(RUN) mypy --config-file=$(topsrcdir)/config/mypy.ini
RUFF=$(RUN) ruff
BANDIT=$(RUN) bandit

# Local (not commited) configuration
BUILDCONFIG=$(DEPTH)/.localconfig.mk

-include $(BUILDCONFIG)

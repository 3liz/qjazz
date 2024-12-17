
DEPTH=../..

include $(DEPTH)/config/config.mk

OPTIONAL_DEPENDENCIES=celery

INSTALL_DEPENDENCIES=[celery]

PYTHON_PKG=qjazz_contrib

TESTDIR=tests

include $(topsrcdir)/config/rules.mk

build::
	# Create manifest
	@echo "{\"commit_id\": \"$(shell git rev-parse HEAD)\" }" > $(PYTHON_PKG)/core/manifest.json

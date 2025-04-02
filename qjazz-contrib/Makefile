
DEPTH=..

include $(DEPTH)/config/config.mk

OPTIONAL_DEPENDENCIES=celery

INSTALL_DEPENDENCIES=[celery]

PYTHON_PKG= \
	qjazz_contrib \
	qjazz_cache \
	qjazz_ogc \
	$(NULL)

TESTDIR=tests

include $(topsrcdir)/config/rules.mk

configure:: manifest

manifest:
	# Create manifest
	@echo "{\"commit_id\": \"$(shell git rev-parse HEAD)\" }" > qjazz_contrib/core/manifest.json

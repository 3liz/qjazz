
DEPTH=..

include $(DEPTH)/config/config.mk

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

BUILDDIR=build-$(QGIS_FLAVOR)

ifndef QJAZZ_NO_BUILD_EXT_INSTALL
build::
	rm -rf *.egg-info
	python setup.py build_ext -b $(BUILDDIR) -t $(BUILDDIR) --inplace 
	strip qjazz_contrib/core/qgis/*.so
endif

clean::
	rm -rf $(BUILDDIR)
	rm -f qjazz_contrib/core/qgis/*.so


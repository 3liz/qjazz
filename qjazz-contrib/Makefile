
DEPTH=..

include $(DEPTH)/config/config.mk

INSTALL_DEPENDENCIES=[celery]

PYTHON_PKG=src

TESTDIR=tests

dist::
	uv build --sdist --out-dir=$(DIST)

include $(topsrcdir)/config/rules.mk

manifest:
	# Create manifest
	@echo "{\"commit_id\": \"$(shell git rev-parse HEAD)\" }" > src/qjazz_core/manifest.json

BUILDDIR=build-$(QGIS_FLAVOR)

ifndef QJAZZ_NO_BUILD_EXT_INSTALL
build::
	rm -rf *.egg-info
	python setup.py build_ext -b $(BUILDDIR) -t $(BUILDDIR) --inplace 
	strip src/qjazz_core/qgis/*.so
endif

clean::
	rm -rf $(BUILDDIR)
	rm -f src/qjazz_core/qgis/*.so


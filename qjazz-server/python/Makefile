
DEPTH=../..

include $(DEPTH)/config/config.mk

DIRS= \
	src \
	$(NULL)

#
# Python
#
#
INSTALL_DEPENDENCIES=[minio]

PYTHON_PKG=src

TESTDIR=tests

dist::
	uv build --sdist --out-dir=$(DIST)

include $(topsrcdir)/config/rules.mk

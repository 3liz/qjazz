
DEPTH=..

include $(DEPTH)/config/config.mk

PYTHON_PKG=src

TESTDIR=tests

INSTALL_DEPENDENCIES=[server,minio,mail]

export PYTEST_ADDOPTS=-m "not services" 

SCAN_OPTS=-x qjazz_processes/tests

EXAMPLES=examples

dist::
	uv build --sdist --out-dir=$(DIST)

include $(topsrcdir)/config/rules.mk

doc:: 
	$(MAKE) -C doc

typing::
	$(MYPY) -p $(EXAMPLES)

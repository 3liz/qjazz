
DEPTH=..

include $(DEPTH)/config/config.mk

PYTHON_PKG=src

TESTDIR=tests

TEST_OPTS=-m "not services" 

SCAN_OPTS=-x qjazz_processes/tests

EXAMPLES=examples

dist::
	uv build  --wheel --out-dir=$(DIST)

include $(topsrcdir)/config/rules.mk

doc:: 
	$(MAKE) -C doc

typing::
	$(MYPY) -p $(EXAMPLES)

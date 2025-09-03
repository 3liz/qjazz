
DEPTH=..

include $(DEPTH)/config/config.mk

PYTHON_PKG= \
	qjazz_processes  \
	qjazz_processing \
	$(NULL)


TESTDIR=tests tests/plugins

INSTALL_DEPENDENCIES=[server,minio,mail]

export PYTEST_ADDOPTS=-m "not services" 

SCAN_OPTS=-x qjazz_processes/tests

EXAMPLES=examples

include $(topsrcdir)/config/rules.mk

typing::
	$(MYPY) -p $(EXAMPLES)

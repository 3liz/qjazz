
DEPTH=..

include $(DEPTH)/config/config.mk

PYTHON_PKG= \
	qjazz_processes   \
	$(NULL)


TESTDIR=tests tests/plugins

OPTIONAL_DEPENDENCIES=server minio

INSTALL_DEPENDENCIES=[server,minio]

export PYTEST_ADDOPTS=-m "not services" 

SCAN_OPTS=-x qjazz_processes/tests

include $(topsrcdir)/config/rules.mk


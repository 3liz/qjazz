
DEPTH=..

include $(DEPTH)/config/config.mk

PYTHON_PKG= \
	qjazz_processes   \
	qjazz_printserver \
	qjazz_wfsoutputserver \
	$(NULL)


TESTDIR=tests tests/plugins

OPTIONAL_DEPENDENCIES=server minio

INSTALL_DEPENDENCIES=[server,minio]

export PYTEST_ADDOPTS=-m "not services" 

test::
	$(MAKE) -C tests clean

include $(topsrcdir)/config/rules.mk


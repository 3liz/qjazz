
DEPTH=../..

include $(DEPTH)/config/config.mk


PYTHON_PKG=py_qgis_processes

TESTDIR=tests tests/plugins

OPTIONAL_DEPENDENCIES=server minio

INSTALL_DEPENDENCIES=[server,minio]

export PYTEST_ADDOPTS=-m "not services" 

include $(topsrcdir)/config/rules.mk



DEPTH=../../..

include $(DEPTH)/config/config.mk


PROJECT_NAME=py-qgis-processes

BUILDDIR=${shell pwd}/build

main: html

html:
	mkdir -p ${BUILDDIR}/html
	sphinx-build -b html ./  ${BUILDDIR}/html
  
pdf:
	mkdir -p ${BUILDDIR}/latex
	sphinx-build -b latex ./  ${BUILDDIR}/latex
	cd ${BUILDDIR}/latex && pdflatex ${PROJECT_NAME}.tex
  
md:
	mkdir -p ${BUILDDIR}/md
	sphinx-build -b markdown ./  ${BUILDDIR}/md

clean:
	rm -r ${BUILDDIR}

all: build main

build: configs

configs:
	@mkdir -p ./configs
	@echo "* Creating server configuration documentation"
	@qgis-processes-server config --schema --format toml > ./configs/server.toml
	$(PYTHON) -c "\
from py_qgis_processes.config import dump_worker_config; \
dump_worker_config() " > ./configs/worker.toml



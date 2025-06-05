
DEPTH=../..

include $(DEPTH)/config/config.mk


PROJECT_NAME=qjazz-processes

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
	rm -rf ${BUILDDIR}

.PHONY: build configs specs

all: build main

build: configs specs

configs:
	@mkdir -p ./configs
	@echo "* Creating server configuration documentation"
	$(PYTHON) -m qjazz_processes.server config --schema --format toml > ./configs/server.toml
	$(PYTHON) -c "\
from qjazz_processes.worker.config import dump_worker_config; \
dump_worker_config() " > ./configs/worker.toml
	$(PYTHON) -m qjazz_processes.callbacks.handlers.http > ./configs/callback_http.toml
	$(PYTHON) -m qjazz_processes.callbacks.handlers.mailto > ./configs/callback_http.toml


specs: 
	@mkdir -p ./specs
	@echo "* Creating openapi specifications"
	$(PYTHON) -m qjazz_processes.server openapi --yaml > ./specs/openapi.yml

export CI_PROJECT_NAME=qjazz-processes
deploy-ci:
	deploy-doc build/html/ doc.manifest

# Serve documentation
serve:
	python3 -m http.server -d ./build/html

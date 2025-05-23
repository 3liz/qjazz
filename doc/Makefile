SHELL=bash

PROJECT_NAME=qjazz-server

BUILDDIR=${shell pwd}/build

# Ref: https://docs.readthedocs.io/en/stable/index.html#

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

build::
	@echo "* Creating rpc config documentation"
	@python -m qjazz_rpc.doc schema --format toml > ./configs/rpc.toml
	@echo "* Creating proxy config documentation"
	@python -m qjazz_map config --schema --format toml > ./configs/server.toml
	@echo "* Creating admin config documentation"
	@qjazz-server-admin doc config --format toml > ./configs/management.toml


build::
	@echo "* Creating rpc server config schema specs"
	@python -m qjazz_rpc.doc schema > ./specs/rpc-config.json
	@echo "* Creating server config schema specs"
	@python -m qjazz_map config --schema > ./specs/server-config.json
	@echo "* Creating admin config schema specs"
	@qjazz-server-admin doc config  > ./specs/admin-config.json
	@echo "* Creating admin openapi specs (YAML)"
	@qjazz-server-admin doc openapi > ./specs/openapi-management.json
	@echo "* Creating admin openapi specs (JSON)"
	@qjazz-server-admin doc openapi --yaml > ./specs/openapi-management.yml


clean:
	rm -r ${BUILDDIR}

all: build main

serve:
	python3 -m http.server -d build/html

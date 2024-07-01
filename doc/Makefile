
PROJECT_NAME=py-qgis-server

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
	@qgis-server-rpc config --schema --format toml > ./configs/rpc.toml
	@echo "* Creating proxy config documentation"
	@qgis-server-http config --schema --format toml > ./configs/proxy.toml
	@echo "* Creating admin config documentation"
	@qgis-server-admin doc config --format toml > ./configs/managment.toml


build::
	@echo "* Creating rpc server config schema specs"
	@qgis-server-rpc config --schema > ./specs/rpc-config.json
	@echo "* Creating proxy config schema specs"
	@qgis-server-http config --schema > ./specs/proxy-config.json
	@echo "* Creating admin config schema specs"
	@qgis-server-admin doc config  > ./specs/admin-config.json
	@echo "* Creating admin openapi specs (YAML)"
	@qgis-server-admin doc openapi > ./specs/openapi-managment.json
	@echo "* Creating admin openapi specs (JSON)"
	@qgis-server-admin doc openapi --yaml > ./specs/openapi-managment.yml


clean:
	rm -r ${BUILDDIR}

all: build main

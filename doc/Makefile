
PROJECT_NAME=py-qgis-server

BUILDDIR=${shell pwd}/build

main: html

html: build
	mkdir -p ${BUILDDIR}/html
	sphinx-build -b html ./  ${BUILDDIR}/html
  
pdf: build
	mkdir -p ${BUILDDIR}/latex
	sphinx-build -b latex ./  ${BUILDDIR}/latex
	cd ${BUILDDIR}/latex && pdflatex ${PROJECT_NAME}.tex
  
md: build
	mkdir -p ${BUILDDIR}/md
	sphinx-build -b markdown ./  ${BUILDDIR}/md

config_doc:
	@echo "* Creating rpc config documentation"
	@qgis-server-rpc config --schema --format toml > ./configs/rpc.toml
	@echo "* Creating proxy config documentation"
	@qgis-server-http config --schema --format toml > ./configs/proxy.toml
	@echo "* Creating admin config documentation"
	@qgis-server-admin doc config --format toml > ./configs/managment.toml

build: 

clean:
	rm -r ${BUILDDIR}

all: config_doc build

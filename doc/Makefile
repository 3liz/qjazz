
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

build:

clean:
	rm -r ${BUILDDIR}


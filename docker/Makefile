SHELL:=bash
#
#
DEPTH=..

include $(DEPTH)/config/config.mk

NAME=qgis-services

BUILDID=$(shell date +"%Y%m%d%H%M")
COMMITID=$(shell git rev-parse --short HEAD)

REGISTRY_URL ?= 3liz
REGISTRY_PREFIX=$(REGISTRY_URL)/
BUILD_ARGS += --build-arg REGISTRY_PREFIX=$(REGISTRY_PREFIX)

QGIS_IMAGE=$(REGISTRY_PREFIX)qgis-platform:$(FLAVOR)

BUILDNAME=$(REGISTRY_PREFIX)$(NAME)
BUILDIMAGE=$(BUILDNAME):qgis-$(FLAVOR)-$(VERSION)

BUILDFRONTIMAGE=$(BUILDNAME):front-$(VERSION)

# CI build
ifdef PYPISERVER
PYPISERVER_SCHEME ?= https
PIP_OPTIONS="--extra-index-url=$(PYPISERVER_SCHEME)://$(PYPISERVER) --trusted-host=$(PYPISERVER)"
BUILD_ARGS += --build-arg PIP_OPTIONS=$(PIP_OPTIONS) $(DOCKER_BUILD_ARGS)
endif

FLAVOR:=release
BUILD_TARGET:=base

#BUILD_CACHE:=--force-rm --no-cache

build: manifest requirements
	docker build --rm $(BUILD_CACHE) $(BUILD_ARGS) --target $(BUILD_TARGET) \
		--build-arg QGIS_VERSION=$(FLAVOR) \
		-t $(BUILDIMAGE) -t $(BUILDNAME):qgis-$(FLAVOR)-eager  -f Dockerfile  ..

build-front:
	docker build --rm $(BUILD_CACHE) $(BUILD_ARGS) --target front \
		--build-arg QGIS_VERSION=$(FLAVOR) \
		-t $(BUILDFRONTIMAGE) -t $(BUILDNAME):front-eager  -f Dockerfile  ..


MANIFEST=factory.manifest

manifest:
	{ \
	set -e; \
	version=`docker run --rm -v $$(pwd)/scripts:/scripts $(QGIS_IMAGE)  /scripts/qgis-version.sh`; \
	echo name=$(NAME) > $(MANIFEST) && \
    echo version=qgis-$$version-$(VERSION) >> $(MANIFEST) && \
    echo version_short=qgis-$$version >> $(MANIFEST) && \
    echo release_tag=qgis-`echo $$version | cut -d- -f1 |cut -d. -f1-2` >> $(MANIFEST) && \
    echo buildid=$(BUILDID)   >> $(MANIFEST) && \
    echo commitid=$(COMMITID) >> $(MANIFEST); }


.PHONY: $(REQUIREMENTS)

# Merge requirement files
requirements: $(REQUIREMENTS)
	@cat $$(ls -1 ../python_modules/*/$<) | sort | uniq > ./$<


deliver: tag push

tag: 
	{ set -e; source $(MANIFEST); \
	docker tag $(BUILDIMAGE) $(REGISTRY_PREFIX)$(NAME):$$version; \
	docker tag $(BUILDIMAGE) $(REGISTRY_PREFIX)$(NAME):$$version_short; \
	docker tag $(BUILDIMAGE) $(REGISTRY_PREFIX)$(NAME):$$release_tag; \
	docker tag $(BUILDFRONTIMAGE) $(REGISTRY_PREFIX)$(NAME):front; \
	}

push:
	{ set -e; source $(MANIFEST); \
	docker push $(REGISTRY_URL)/$(NAME):$$version; \
	docker push $(REGISTRY_URL)/$(NAME):$$version_short; \
	docker push $(REGISTRY_URL)/$(NAME):$$release_tag; \
	docker push $(BUILDFRONTIMAGE); \
	docker push $(REGISTRY_URL)/$(NAME):front; \
	}



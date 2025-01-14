SHELL:=bash
#
#
DEPTH=..

include $(DEPTH)/config/config.mk

NAME=qjazz

BUILDID=$(shell date +"%Y%m%d%H%M")
COMMITID=$(shell git rev-parse --short HEAD)

REGISTRY_URL ?= 3liz
REGISTRY_PREFIX=$(REGISTRY_URL)/
BUILD_ARGS += --build-arg REGISTRY_PREFIX=$(REGISTRY_PREFIX)

QGIS_IMAGE=$(REGISTRY_PREFIX)qgis-platform:$(FLAVOR)

BUILDNAME=$(REGISTRY_PREFIX)$(NAME)
BUILDIMAGE=$(BUILDNAME):qgis-$(FLAVOR)-$(VERSION)


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
	$(MAKE) -C .. configure
	docker build --rm $(BUILD_CACHE) $(BUILD_ARGS) --target $(BUILD_TARGET) \
		--build-arg QGIS_VERSION=$(FLAVOR) \
		-t $(BUILDIMAGE) -t 3liz/$(NAME):qgis-$(FLAVOR)-eager  -f Dockerfile  ..


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
	@echo "Merging requirements files"
	@cat $$(ls -1 ../python_modules/*/$<) ../qjazz-process/$< ../qjazz-server/python/$< | sort | uniq > ./$<


deliver: tag push

tag: 
	{ set -e; source $(MANIFEST); \
	docker tag $(BUILDIMAGE) $(BUILDNAME):$$version; \
	docker tag $(BUILDIMAGE) $(BUILDNAME):$$version_short; \
	docker tag $(BUILDIMAGE) $(BUILDNAME):$$release_tag; \
	}

push:
	{ set -e; source $(MANIFEST); \
	docker push $(BUILDNAME):$$version; \
	docker push $(BUILDNAME):$$version_short; \
	docker push $(BUILDNAME):$$release_tag; \
	}

# =============
# Front build
# =============

BUILDFRONTIMAGE=$(BUILDNAME):front-$(VERSION)

FRONT_BUILD_TARGET:=front

build-front: front-manifest
	docker build --rm $(BUILD_CACHE) $(BUILD_ARGS) --target $(FRONT_BUILD_TARGET) \
		--build-arg QGIS_VERSION=$(FLAVOR) \
		-t $(BUILDFRONTIMAGE) -t 3liz/$(NAME):front-eager  -f Dockerfile  ..

FRONT_MANIFEST=front.manifest

front-manifest:
	{ \
	set -e; \
	echo name=$(NAME) > $(FRONT_MANIFEST) && \
    echo version=front-$(VERSION) >> $(FRONT_MANIFEST) && \
    echo version_short=front-$(VERSION_SHORT) >> $(FRONT_MANIFEST) && \
    echo release_tag=front-latest >> $(FRONT_MANIFEST) && \
    echo buildid=$(BUILDID)   >> $(FRONT_MANIFEST) && \
    echo commitid=$(COMMITID) >> $(FRONT_MANIFEST); }

deliver-front: tag-front push-front

tag-front:
	{ set -e; source $(FRONT_MANIFEST); \
	docker tag $(BUILDFRONTIMAGE) $(BUILDNAME):$$version; \
	docker tag $(BUILDFRONTIMAGE) $(BUILDNAME):$$version_short; \
	docker tag $(BUILDFRONTIMAGE) $(BUILDNAME):$$release_tag; \
	}

push-front:
	{ set -e; source $(FRONT_MANIFEST); \
	docker push $(BUILDNAME):$$version; \
	docker push $(BUILDNAME):$$version_short; \
	docker push $(BUILDNAME):$$release_tag; \
	}

#
# Push eager to docker-hub
#
push-eager:
	docker push 3liz/$(NAME):qgis-$(FLAVOR)-eager

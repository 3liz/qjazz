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

BUILDIMAGE=$(NAME):$(FLAVOR)

FLAVOR:=release

build: manifest
	docker build --rm --force-rm --no-cache $(BUILD_ARGS) -t $(BUILDIMAGE) -f Dockerfile  ..

MANIFEST=factory.manifest

manifest:
	{ \
	set -e; \
	version=`docker run --rm -v $$(pwd)/scripts:/scripts $(QGIS_IMAGE)   /scripts/qgis-version.sh`; \
	echo name=$(NAME) > $(MANIFEST) && \
    echo version=$$version-$(VERSION) >> $(MANIFEST) && \
    echo version_short=$$version >> $(MANIFEST) && \
    echo release_tag=`echo $$version | cut -d- -f1 |cut -d. -f1-2` >> $(MANIFEST) && \
    echo buildid=$(BUILDID)   >> $(MANIFEST) && \
    echo commitid=$(COMMITID) >> $(MANIFEST); }

deliver: tag push

tag: 
	{ set -e; source $(MANIFEST); \
	docker tag $(BUILDIMAGE) $(REGISTRY_PREFIX)$(NAME):$$version; \
	docker tag $(BUILDIMAGE) $(REGISTRY_PREFIX)$(NAME):$$version_short; \
	docker tag $(BUILDIMAGE) $(REGISTRY_PREFIX)$(NAME):$$release_tag;
	}

push:
	{ set -e; source $(MANIFEST); \
	docker push $(REGISTRY_URL)/$(NAME):$$version; \
	docker push $(REGISTRY_URL)/$(NAME):$$version_short; \
	docker push $(REGISTRY_URL)/$(NAME):$${release_tag}; \
	}



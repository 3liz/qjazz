SHELL:=bash
#
#
DEPTH=..

include $(DEPTH)/config/config.mk

ifndef BUILD_RELEASE
QJAZZ_DEV_TAG=-dev0
endif

NAME=qjazz

BUILDID=$(shell date +"%Y%m%d%H%M")
COMMITID=$(shell git rev-parse --short HEAD)

REGISTRY_URL ?= 3liz
REGISTRY_PREFIX=$(REGISTRY_URL)/
BUILD_ARGS += --build-arg REGISTRY_PREFIX=$(REGISTRY_PREFIX)

QGIS_IMAGE=$(REGISTRY_PREFIX)qgis-platform:$(FLAVOR)

# CI build
ifdef PYPISERVER
PYPISERVER_SCHEME ?= https
PIP_OPTIONS="--extra-index-url=$(PYPISERVER_SCHEME)://$(PYPISERVER) --trusted-host=$(PYPISERVER)"
BUILD_ARGS += --build-arg PIP_OPTIONS=$(PIP_OPTIONS) $(DOCKER_BUILD_ARGS)
endif

FLAVOR:=release

ifeq ($(TARGET),lizcloud)
BUILD_TARGET=lizcloud
LIZCLOUD_TAG=-lizcloud
QJAZZ_VERSION_TAG=$(QJAZZ_DEV_TAG)$(LIZCLOUD_TAG)
MANIFEST=factory-$(FLAVOR)-lizcloud.manifest
else
BUILD_TARGET=base
MANIFEST=factory-$(FLAVOR).manifest
QJAZZ_VERSION_TAG=$(QJAZZ_DEV_TAG)
endif

BUILDNAME=$(REGISTRY_PREFIX)$(NAME)
BUILDIMAGE=$(BUILDNAME):qgis-$(FLAVOR)-$(VERSION)$(QJAZZ_VERSION_TAG)

#BUILD_CACHE:=--force-rm --no-cache

main:
	@echo "No default rule"

build-all: build noqgis-build tag noqgis-tag

build: manifest
	$(MAKE) -C ../qjazz-contrib/  manifest
	{ \
	source $(MANIFEST); \
	docker build --rm $(BUILD_CACHE) $(BUILD_ARGS) --target $(BUILD_TARGET) \
		--build-arg QGIS_FLAVOR=${FLAVOR} \
		--label org.opencontainers.image.version=$$version \
		-t $(BUILDIMAGE) -t 3liz/$(NAME):qgis-$(FLAVOR)-eager$(LIZCLOUD_TAG)  -f Dockerfile  ..;\
	}


manifest:
	# Update the Qjazz build manifest
	$(MAKE) -C $(topsrcdir)/qjazz-contrib manifest
	@{ \
	set -e; \
	version=`docker run --rm -v $$(pwd)/scripts:/scripts $(QGIS_IMAGE)  /scripts/qgis-version.sh`; \
	echo name=$(NAME) > $(MANIFEST) && \
    echo version=qgis-$$version-$(VERSION)$(QJAZZ_VERSION_TAG) >> $(MANIFEST) && \
    echo version_short=qgis-`echo $$version | cut -d- -f1 |cut -d. -f1-2`$(QJAZZ_VERSION_TAG) >> $(MANIFEST) && \
    echo buildid=$(BUILDID)   >> $(MANIFEST) && \
    echo commitid=$(COMMITID) >> $(MANIFEST); }
	@cat $(MANIFEST)

deliver: tag push

ifndef BUILD_RELEASE
tag: 
	{ set -e; source $(MANIFEST); \
	docker tag $(BUILDIMAGE) $(BUILDNAME):$$version_short; \
	docker tag $(BUILDIMAGE) $(BUILDNAME):qgis-$(FLAVOR)$(QJAZZ_VERSION_TAG); \
	}
push:
	{ set -e; source $(MANIFEST); \
	docker push $(BUILDNAME):$$version_short; \
	docker push $(BUILDNAME):qgis-$(FLAVOR)$(QJAZZ_VERSION_TAG); \
	}
else
tag: 
	{ set -e; source $(MANIFEST); \
	docker tag $(BUILDIMAGE) $(BUILDNAME):$$version; \
	docker tag $(BUILDIMAGE) $(BUILDNAME):$$version_short; \
	docker tag $(BUILDIMAGE) $(BUILDNAME):qgis-$(FLAVOR)$(LIZCLOUD_TAG); \
	}
push:
	{ set -e; source $(MANIFEST); \
	docker push $(BUILDNAME):$$version; \
	docker push $(BUILDNAME):$$version_short; \
	docker push $(BUILDNAME):qgis-$(FLAVOR)$(LIZCLOUD_TAG); \
	}
endif
#
# Push eager to docker-hub
#
push-eager:
	docker push 3liz/$(NAME):qgis-$(FLAVOR)-eager

# =============
# No QGIS build
# =============

BUILDNOQGISIMAGE=$(BUILDNAME):noqgis-$(VERSION)$(QJAZZ_VERSION_TAG)

ifeq ($(TARGET),lizcloud)
NOQGIS_BUILD_TARGET=noqgis-lizcloud
NOQGIS_MANIFEST=factory-noqgis-lizcloud.manifest
else
NOQGIS_BUILD_TARGET=noqgis
NOQGIS_MANIFEST=factory-noqgis.manifest
endif

noqgis-build: noqgis-manifest
	{ \
	source $(NOQGIS_MANIFEST); \
	docker build --rm $(BUILD_CACHE) $(BUILD_ARGS) --target $(NOQGIS_BUILD_TARGET) \
		--build-arg QGIS_FLAVOR=$(FLAVOR) \
		--label org.opencontainers.image.version=$$version \
		-t $(BUILDNOQGISIMAGE) -t 3liz/$(NAME):noqgis-eager$(LIZCLOUD_TAG)  -f Dockerfile  ..;\
	}


noqgis-manifest:
	@{ \
	set -e; \
	echo name=$(NAME) > $(NOQGIS_MANIFEST) && \
	echo version=noqgis-$(VERSION)$(QJAZZ_VERSION_TAG) >> $(NOQGIS_MANIFEST) && \
    echo version_short=noqgis$(QJAZZ_VERSION_TAG)  >> $(NOQGIS_MANIFEST) && \
    echo buildid=$(BUILDID)   >> $(NOQGIS_MANIFEST) && \
    echo commitid=$(COMMITID) >> $(NOQGIS_MANIFEST); }
	@cat $(NOQGIS_MANIFEST)

noqgis-deliver: noqgis-tag noqgis-push

ifndef BUILD_RELEASE
noqgis-tag:
	docker tag $(BUILDNOQGISIMAGE) $(BUILDNAME):noqgis$(QJAZZ_VERSION_TAG)
noqgis-push:
	docker push $(BUILDNAME):noqgis$(QJAZZ_VERSION_TAG)
else
noqgis-tag:
	{ set -xe; source $(NOQGIS_MANIFEST); \
	docker tag $(BUILDNOQGISIMAGE) $(BUILDNAME):$$version; \
	docker tag $(BUILDNOQGISIMAGE) $(BUILDNAME):$$version_short; \
	}
noqgis-push:
	{ set -xe; source $(NOQGIS_MANIFEST); \
	docker push $(BUILDNAME):$$version; \
	docker push $(BUILDNAME):$$version_short; \
	}
endif

#
# Push eager to docker-hub
#
noqgis-push-eager:
	docker push 3liz/$(NAME):noqgis-eager

#
# CI image build
# 

CI_IMAGE=$(REGISTRY_PREFIX)factory-ci-runner:qjazz-$(FLAVOR)

build-ci:
	docker build --rm $(BUILD_CACHE) $(BUILD_ARGS) --target ci \
	--build-arg QGIS_FLAVOR=$(FLAVOR) \
	--build-arg factory_runner_uid=$$(id -u) \
	--label org.opencontainers.image.version=$(VERSION_TAG) \
	-t $(CI_IMAGE) -f Dockerfile ..


deliver-ci: 
	docker push $(CI_IMAGE) 


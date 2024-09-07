SHELL:=bash
.ONESHELL:

.PHONY: env

DEPTH=../../..

include $(DEPTH)/config/config.mk

start: 
	docker compose up -d

stop:
	docker compose --profile=web down -v --remove-orphans

FLAVOR:=release

WEB_PORT:=4100

env: workdir
	@mkdir -p .local
	echo "Creating environment file for docker-compose"
	cat <<-EOF > .env
		USER_ID=$(shell id -u)
		GROUP_ID=$(shell id -g)
		QGIS_IMAGE=3liz/qgis-platform:$(FLAVOR)
		COMPOSE_PROJECT_NAME=test-py-qgis-server
		SRCDIR=/src/python_modules/py-qgis-server
		WEB_PORT=$(WEB_PORT)
		EOF
	cat .env

up: env
	docker compose up -d -V --quiet-pull --remove-orphans

up-%: env
	docker compose --profile=$* up -d -V --quiet-pull \
		--remove-orphans


# Recreate service
restart-%: 
	docker compose up -d --force-recreate $*



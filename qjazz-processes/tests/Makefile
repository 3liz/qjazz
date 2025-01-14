SHELL:=bash
.ONESHELL:

.PHONY: env

DEPTH=../../..

include $(DEPTH)/config/config.mk

start: 
	docker compose up -d

stop:
	docker compose --profile=all down -v --remove-orphans


LOGLEVEL:=info


workdir:
	@mkdir -p __workdir__


clean:
	rm -r __workdir__/*

FLAVOR:=release

WEB_PORT:=4100

env: workdir
	@echo "Creating environment file for docker-compose"
	mkdir -p .local
	cat <<-EOF > .env
		USER_ID=$(shell id -u)
		GROUP_ID=$(shell id -g)
		QGIS_IMAGE=3liz/qgis-platform:$(FLAVOR)
		COMPOSE_PROJECT_NAME=test-qjazz-processes
		SRCDIR=/src/python_modules/qjazz-processes
		WEB_PORT=$(WEB_PORT)
		EOF
	cat .env

up: env
	docker compose $(COMPOSE_OPTS) up -d -V --quiet-pull --remove-orphans \
		--force-recreate

DOCKER_COMPOSE:=docker compose

# Run test stack
run: export COMPOSE_OPTS=--profile worker
run: up
	$(DOCKER_COMPOSE) logs -f worker

run-all: export COMPOSE_OPTS=--profile all
run-all: up
	$(DOCKER_COMPOSE) logs -f web

# Restart worker
restart-worker: 
	$(DOCKER_COMPOSE) up -d --force-recreate worker

# Equivalent run using celery config
run-celery: export PY_QGIS_PROCESSES_CONFIG=$(CURDIR)/worker-config.toml
run-celery: workdir
	celery -A qjazz_processes.jobs  worker -l $(LOGLEVEL) --hostname dev1@%h -Ofair $(CELERY_ARGS)

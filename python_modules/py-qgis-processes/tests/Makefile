SHELL:=bash
.ONESHELL:

.PHONY: env

DEPTH=../../..

include $(DEPTH)/config/config.mk

start: 
	docker compose up -d

stop:
	docker compose down -v


LOGLEVEL:=info


workdir:
	@mkdir -p __workdir__


FLAVOR:=release

env: workdir
	@mkdir -p .local
	echo "Creating environment file for docker-compose"
	cat <<-EOF > .env
		USER_ID=$(shell id -u)
		GROUP_ID=$(shell id -g)
		QGIS_IMAGE=3liz/qgis-platform:$(FLAVOR)
		COMPOSE_PROJECT_NAME=test-py-qgis-processes
		SRCDIR=/src/python_modules/py-qgis-processes
		EOF
	cat .env

stop:
	docker compose down -v --remove-orphans

up: env
	docker compose up -d -V --quiet-pull --remove-orphans \
		--force-recreate

# Run test stack
run: up
	docker compose logs -f worker

# Restart worker
restart: 
	docker compose up -d --force-recreate worker

# Equivalent run using celery config
export PY_QGIS_PROCESSES_CONFIG=$(CURDIR)/worker-config.toml
run-celery: workdir
	celery -A py_qgis_processes.jobs  worker -l $(LOGLEVEL) --hostname dev1@%h -Ofair $(CELERY_ARGS)

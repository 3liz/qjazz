SHELL:=bash
.ONESHELL:

.PHONY: env

DEPTH=../..

include $(DEPTH)/config/config.mk

start: 
	docker compose up -d

stop:
	docker compose --profile=all down -v --remove-orphans


LOGLEVEL:=info


workdir:
	@mkdir -p __workdir__


clean:
	rm -rf __workdir__/*

FLAVOR:=release

WEB_PORT:=4100

env: workdir
	@echo "Creating environment file for docker-compose"
	mkdir -p .local
	cat <<-EOF > .env
		COMPOSE_PROJECT_NAME=test-qjazz-processes
		EOF
	cat .env





start: 
	docker compose up -d

stop:
	docker compose down -v


LOGLEVEL:=info

PROCESSES_CONFIG=$(CURDIR)/worker-config.toml

workdir:
	@mkdir -p __workdir__

run: workdir
	pthon -m py_qgis_processes -C $(PROCESSES_CONFIG) -l $(LOGLEVEL)

# Equivalent run using celery config
export PY_QGIS_PROCESSES_CONFIG=$(PROCESSES_CONFIG)
run-celery: workdir
	celery -A py_qgis_processes.jobs  worker -l $(LOGLEVEL) --hostname dev1@%h -Ofair $(CELERY_ARGS)

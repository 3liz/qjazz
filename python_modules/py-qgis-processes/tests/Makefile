


start: 
	docker compose up -d

stop:
	docker compose down -v


APP:=py_qgis_processes.jobs

LOGLEVEL:=info

export PY_QGIS_PROCESSES_WORKER_CONFIG=$(CURDIR)/config.toml
run:
	celery -A $(APP) worker -l $(LOGLEVEL) --hostname dev1@%h -Ofair $(CELERY_ARGS)




start: 
	docker compose up -d

stop:
	docker compose down -v


APP:=py_qgis_processes.jobs

export CONF_WORKER__SERVICE_NAME=test
run:
	celery -A $(APP) worker -l debug --hostname dev@processing -Ofair

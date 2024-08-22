#
# Executor setup to use with 
# the test docker stack
#
# Assume that the ENV_NETWORK is set to `test-py-qgis-processes_default`
#
#
from py_qgis_processes.executor import (
    CeleryConfig,
    ExecutorConfig,
    Executor,
)
executor = Executor(
    ExecutorConfig(
        celery=CeleryConfig(
            broker_host='rabbitmq',
            backend_host='redis:6379/0',
        ),
    ),
)

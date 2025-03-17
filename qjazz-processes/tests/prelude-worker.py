import os

from qjazz_processes.worker import config, processing  # noqa F401

os.environ[config.CONFIG_ENV_PATH] = "tests/worker-config.toml"
os.environ["conf_worker__service_name"] = "Test_"

conf = config.load_configuration()

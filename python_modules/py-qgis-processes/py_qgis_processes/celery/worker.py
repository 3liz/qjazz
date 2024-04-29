import os
import types

from pathlib import Path

import celery
import celery.states

from pydantic import (
    ValidationError,
)
from typing_extensions import (
    ClassVar,
    Dict,
    Optional,
    TypeAlias,
)

# from as_core.storage import StorageClient, StorageCreds, storage_client
from py_qgis_contrib.core import logger
from py_qgis_contrib.core.utils import to_iso8601, utc_now

from ._celery import Celery
from .config import ProcessingConfig, confservice, load_configuration
from .runconfig import RunConfigSchema, create_job_run_config

#
#  Worker
#

JobContext: TypeAlias = types.SimpleNamespace


class Worker(Celery):

    def __init__(self, **kwargs):

        path = os.getenv("WORKER_CONFIG_PATH")
        if path:
            conf = load_configuration(Path(path))
        else:
            conf = confservice.conf

        super().__init__(conf.worker.service_name, conf.worker, **kwargs)

        # See https://docs.celeryq.dev/en/stable/userguide/routing.html
        # for task routing

        # We want each application with its own queue and exchange
        if conf.worker.routing_name:
            self.conf.task_default_queue = conf.worker.routing_name
            self.conf.task_default_exchange = conf.worker.routing_name

        self.__processing_config__ = conf.processing

        # Add the inspect command
        # See https://docs.celeryq.dev/en/stable/userguide/workers.html
        # #writing-your-own-remote-control-commands
        from celery.worker.control import inspect_command
        inspect_command()(_run_configs)

    def job(
        self,
        name: str,
        *args,
        **kwargs,
    ) -> celery.Task:
        """ Decorator for creating job tasks

            Extra options:

            'run_context: bool'
                If set to true
                the context metadata objet will be passed as the first
                positional argument.  The argument should be treated
                as a positional argument only (https://peps.python.org/pep-0570/)
                in order to not beeing included in the run config model.

            Exemple:
                @app.job(name='echo', bind=True, run_context=True)
                def main(self, ctx, /, *args, **kwargs):
                    return f"got customer id : {ctx.customer_id}"

        """
        return super().task(
            *args,
            name=f"{self.main}.{name}",
            base=Job,
            track_started=True,
            processing_config=self.__processing_config__,
            **kwargs,
        )


# Add our broadcast inspect command
# for returning run configs in a format nicer
# then the 'registered' inspect command
def _run_configs(_) -> Dict:
    return Job.RUN_CONFIGS.copy()


# Create a dict class on wich we can
# add attributes
class _Dict(dict):
    pass


#
# Celery task override
#

class Job(celery.Task):

    RUN_CONFIGS: ClassVar[Dict[str, RunConfigSchema]] = {}

    # Set in decorator
    processing_config: ClassVar[Optional[ProcessingConfig]] = None

    # To be set in decorator
    run_context: bool = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Analyse argument and build the
        # run config schema

        self.typing = False  # Disable argument type checking

        models, schema = create_job_run_config(self.__wrapped__)

        self.__config__ = models
        self.__metadata__ = None

        Job.RUN_CONFIGS[self.name] = schema.model_dump(by_alias=True, mode='json')

    def __call__(self, *args, **kwargs):
        #
        # Override the call method in order to validate
        # the json input
        #
        _, outputs = self.__config__

        meta = kwargs.pop('__meta__')  # Remove metadata from arguments

        if self.run_context:
            args = (meta.__context__,)
        else:
            args = ()

        out = self.run(*args, **meta.__run_config__.dict())
        # Return output as json compatible format
        return outputs.dump_python(out, mode='json')

    def before_start(self, task_id, args, kwargs):
        #
        # We expect the following as arguments:
        #
        #  A '__metadata__' dictionary that hold metadata informations
        #  for tasks.
        #
        #  A '__meta__' entry that will
        #  add update infos stored in the backend into the 'kwargs' key.
        #
        #  A '__run_config__' dictionary holding task arguments, they
        #  will accesible a namespace with the 'metadata' attribute
        #
        # Encode metadata into kwargs; they will be
        # stored in the backend
        # This is a workaround for adding extra metadata
        # the the stored backend data.
        metadata = kwargs.pop('__metadata__', {})
        metadata.update(
            processing=self.processing_config,
        )

        meta = kwargs.pop('__meta__', {})
        meta.update(
            started=utc_now(),
        )

        meta = _Dict(meta)

        run_config = kwargs.pop('__run_config__', kwargs)
        # Validate arguments
        #
        # We do not validate arguments in __call__ because
        # we want the error being stored as json object
        # in the __meta__ (see above) and not as a textual
        # dump of the raised exception in the 'result' field.
        try:
            # Store as meta attributes so that they wont be visible
            # as kwargs in backend data
            inputs, _ = self.__config__
            meta.__run_config__ = inputs.model_validate(run_config)
            logger.debug("%s: run config: %s", task_id, meta.__run_config__)
            meta.__context__ = JobContext(**metadata)
            # Replace kw arguments by the run configuration
            if kwargs is not run_config:
                kwargs.clear()
                kwargs.update(run_config)
        except ValidationError as e:
            errors = [d for d in e.errors(include_url=False, include_input=False)]
            meta.update(errors=errors)
            logger.error("Invalid arguments for %s: %s:", task_id, errors)
            raise ValueError("Invalid arguments")
        finally:
            kwargs.update(__meta__=meta)

    def set_progress(
        self,
        percent_done: Optional[float] = None,
        message: Optional[str] = None,
    ):
        """ Update progress info
            percent: the process percent betwee 0. and 1.
        """
        self.update_state(
            state=Worker.STATE_UPDATED,
            meta=dict(
                progress=int(percent_done * 100.0) if percent_done is not None else None,
                message=message,
                updated=to_iso8601(utc_now()),
            ),
        )

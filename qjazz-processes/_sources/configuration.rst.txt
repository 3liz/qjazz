.. _configuration_settings:

Configuration Settings
======================

Configuration can be done either by using a `toml <https://toml.io/en/>`_ configuration file,
environnement variable or secret files.

The configuration framework is based on the `pydantic settings <https://docs.pydantic.dev/latest/concepts/pydantic_settings/?query=Settings>`_ package which provides strong validation for configuration
data.


Environment variables
---------------------

The mapping of configuration values follows the following pattern:

* Environment variable names are case-insensitive.
* Environment variables must be prefixed with ``CONF_``
* Nested settings are separated by ``__`` (double underscore)
* List and dictionnaries are populated from environnement by
  treating the environnement variable's value as JSON-encoded strinf.

Example:

    Consider the following the toml configuration:

    .. code-block:: toml

        [logging]
        level = "DEBUG"

        [worker]
        service_name = "MyService"
        broker_host = "rabbitmq"
        broker_backend = "redis:6370/0"

        [processing]
        workdir = "/qgis-workdir"

        [processing.plugins]
        paths = ["/qgis-plugins"]

        [processing.projects.search_paths]
        '/' = "/qgis-projects"
        

    And the corresponding configuration with  environment variables::

        CONF_LOGGING__LEVEL=DEBUG
        CONF_WORKER__SERVICE_NAME=MyService
        CONF_WORKER__BROKER_HOST=rabbitmq
        CONF_WORKER__BACKEND_HOST=redis:6379/0
        CONF_PROCESSING__WORKDIR=/qgis-workdir
        CONF_PROCESSING__PLUGINS__PATHS='["/qgis-plugins"]'
        CONF_PROCESSING__PROJECTS__SEARCH_PATHS: '{"/":"/qgis-projects"}'
 

Secret files
------------

Instead of using exposed environment variables or configuration files, 
values may be stored in files that contains a single value and where the name of 
the file is the configuration.

A common usecase is to allow for storing sensitive values in Docker encrypted
secret files.

        
Configuration precedence
------------------------

Configuration precedence is (by decreasing priority):

- Configuration file
- Environment variables
- Secret files
- Default values


.. _worker_configuration:

Worker configuration
--------------------

.. literalinclude:: configs/worker.toml
   :language: toml
   :linenos:


.. _server_configuration:

Server configuration
--------------------

.. literalinclude:: configs/server.toml
   :language: toml
   :linenos:


Callbacks
=========

Callbacks requirements are `specified by OGC standards <https://docs.ogc.org/is/18-062r2/18-062r2.html#toc52>`_. 

It allows to set up a push based mechanism for processes results to others services.

Originally, only http POST requests are considered but Qjazz processes support arbitrary
uri schemes.

Callbacks handlers are declared in worker configuration under the ``[callbacks."<scheme,...>"]``
section along with their configuration and the import string to the class implementing the
callback support.

Qjazz implement natively 'http' and 'mailto' scheme callbacks. 


HTTP Callback configuration
---------------------------

.. literalinclude:: configs/callback_http.toml
   :language: toml
   :linenos:

.. note::

    For serving both http and https use ``[callbacks."http,https"]``.



MailTo Callback configuration
-----------------------------

Allow sending e-mail with callbacks.

.. literalinclude:: configs/callback_http.toml
   :language: toml
   :linenos:



.. highlight:: text

.. _adv_management:

Advanced management
===================

`qjazz` come with management tools for Qgis service clusters.

It allows you to:

* Retrieve infos about running Qgis clusters
* Synchronize cache between instances of the same Qgis pools
* Manage cache for each instances.
* Get plugin's infos
* List project's catalog
* Watch health status 
* Serve REST management api


Running management from CLI
---------------------------

You may run the management tool from CLI::

    > pip install qjazz-admin
    > python3 -m qjazz_admin --help
    Usage: python -m qjazz_admin [OPTIONS] COMMAND [ARGS]...

    Options:
      --help  Show this message and exit.

    Commands:
      cache    Cache management
      catalog  Print catalog for 'host'
      conf     Configuration management
      doc      Manage documentation
      plugins  List backend's loaded plugins
      pools    List all pools
      serve    Run admin server
      stats    Output qgis gRPC services stats
      watch    Watch a cluster of qgis gRPC services


or from the docker image::

    docker run -it --rm  -v <path/to/configfile>:/etc/qjazz-server-admin.toml \
        -e PY_QGIS_SERVER_ADMIN_CONFIGFILE=/etc/qjazz-server-admin.toml \
        3liz/qjazz:ltr qjazz-server-admin


Management from REST api
------------------------

Management may also be handler using REST api with the `serve` command::

    > qjazz-server-admin serve

From this you can use your own dashboard for managing your Qgis clusters.


Api specification
^^^^^^^^^^^^^^^^^

See the :doc:`management-api`
or download the :download:`Json specs <specs/openapi-management.json>`.


Configuration
-------------

Configuration is read from toml file or from remote http url.

The configuration define Qgis backend's pool with `resolvers` that describe
how to access the pools - actually only DNS résolution and unix socket are
supported.

The following example define the `qgis-rpc` host as a DNS endpoint for a cluster
of qgis services pool.
    
.. code-block:: toml

    [resolvers]

    [[resolvers.pools]]
    label = "basic"
    type = "dns"
    host = "qgis-rpc"
    port = 23456

If you are using the :ref:`basic docker-compose example <docker_compose_setup>` and your
running admin container is attached to the compose network stack, then your configuration
will point to the `qgis-rpc` services.

Examples::

    > qjazz-server-admin pools
    Pool  1. basic           qgis-rpc:23456    backends: 3
    * 172.25.0.5:23456
    * 172.25.0.2:23456
    * 172.25.0.6:23456

    > qjazz-server-admin stats --host qgis-rpc
    [
        {
            "address": "172.25.0.2:23456",
            "numWorkers": 1,
            "requestPressure": 0.0,
            "status": "ok",
            "stoppedWorkers": 0,
            "uptime": 6217,
            "workerFailurePressure": 0.0
        },
        {
            "address": "172.25.0.5:23456",
            "numWorkers": 1,
            "requestPressure": 0.0,
            "status": "ok",
            "stoppedWorkers": 0,
            "uptime": 132,
            "workerFailurePressure": 0.0
        },
        {
            "address": "172.25.0.6:23456",
            "numWorkers": 1,
            "requestPressure": 0.0,
            "status": "ok",
            "stoppedWorkers": 0,
            "uptime": 131,
            "workerFailurePressure": 0.0
        }
    ]




.. _admin_configuration_schema:

Configuration schema
--------------------

When reading configuration from file, the format is TOML
by default. 

The configuration schema may be output as different format using the `doc` command
from the CLI: the `json` or `yaml` format may be used for validation. 


.. literalinclude:: configs/management.toml
     :language: toml


Case scenarios
==============

.. _admin_cache_sync:

Synchronizing pool cache
------------------------

In pool of Qgis services, cache may be desynchronized for different reasons:

* Scaling up the pool
* Using the `load_project_on_request`
* Updating container in a orchestrated environment

The :ref:`cache restoration mechanism <rpc_cache_restoration>` may prevent most
of desynchronization mechanism, it may be required to manually resync caches:

The cli management tool provide the `sync` command while the REST api provides the
http method:

.. http:patch:: /v1/pools/{Id}/cache

   Synchronize and update cache between all pool instances


.. _admin_config_reload:

Adding, modifying or removing pool to management service
--------------------------------------------------------

If you add or remove resolver's you will need to reload the configuration.

The REST api provide a method for reloading the configuration:

   .. http:patch:: /v1/config

   Reload the configuration and resync all pools.

All pools will be resynced according to the new resolvers
    

.. _admin_pools_sync:

Resyncing with rpc pools when rescaling rpc services
----------------------------------------------------

If you have scaled your rpc services of if some resolvers are handling with dynamic 
configuration, your will only need to resync with the resolvers in order to take 
the changes into account.

   .. http:patch:: /vi/pools

   Resync all pools with resolvers.

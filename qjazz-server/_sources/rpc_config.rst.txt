
.. _rpc_services:

QGIS RPC services
=================

RPC services runs QGIS server processes and expose `gRPC <https://grpc.io/>`_ interfaces.
for requesting and managing the QGIS processes.

Workers may be grouped by *pools* that share the exact same configuration and network
address.

For examples, scaling a docker container with a running rpc-server in a docker compose
stack automatically create a *pool* of workers.

That is, a pool is addressed by a gRPC client as a single endpoint. (i.e `qgis-rpc` like in
the :ref:`Docker compose setup <docker_compose_setup>` example.

QGIS processes
--------------

A worker may run a configurable number of QGIS processes.  Incoming QGIS requests
to the gRPC service are distributed with a fair-queuing dispatching algorithm to 
the child QGIS server processes.

You may increase or decrease the number of processes but another strategy is to 
scale the number of worker services while keeping the number of sub-processes relatively
small. 

Depending of the situation it may be better to choose one or another strategy.

Life cycle and pressure conditions
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If a processes crash, the worker is then in a *degraded* 
state that can be monitored. 

In *degraded state*, the RPC service will try to restore dead workers so as to keep
the number of live QGIS processes constante.

In some situation the number of dead process exceed some limite will
stop with an error code.

There is one condition for a worker to deliberately exit
with a error condition: the *process failure pressure*.

The process failure pressure is the ratio of failed processes over the initial
number of configured processes. If this ratio raise above some configured limit,
then the service will exit with critical error condition.


Process timeout
^^^^^^^^^^^^^^^

A process may be deliberately killed (and thus increase the pressure) on long
running requests.

If the response time exceed the request `server.timeout` then the process processing the request
is considered as stalled and asked to abort gracefully the request. 
The grace timeout is controlled by the `worker.cancel_timeout`; if the process fail to abort
the request then process is killed, which will increase the failure 
pressure. 

.. note::
   | When a worker die, the service will try to maintain the initial number of workers.
     Nevertheless, if too many workers die in a short amount the pressure can increase
     too much and the worker will exit.
   | If this occurs, this is usually because there is something wrong with the treatment of 
     the  qgis request that must be investigated.
   | On production, Monitoring workers lifecycle may be useful to detect such situations.


.. _rpc_configuration:

Configuration
-------------

When reading configuration from file, the format is TOML
by default. 

Check the :download:`configuration json schema <specs/rpc-config.json>`.

.. _rpc_configuration_toml:

TOML configuration
^^^^^^^^^^^^^^^^^^


.. literalinclude:: configs/rpc.toml
     :language: toml


Dynamic configuration setup
^^^^^^^^^^^^^^^^^^^^^^^^^^^

This is only available if you are running the service through the official docker image.

The configuration may be set dynamically at startup by running an executable returning 
a configuration in *JSon* format.

The executable is controlled by the `QJAZZ_CONFIG_EXEC` variable.

The default settings allow you to define a remote URL for downloading the configuration at startup.
See the `basic-with-config-server` example for an example of remote configuration setup. 

.. note::
   | You may define your own config setup by inheriting from the official Docker image
     and define a setting a custom QJAZZ_CONFIG_EXEC executable.
   | This may be useful if your are using alternate storage for your configuration settings.


.. _rpc_cache_overview:

Qgis project's cache overview
=============================

Each processes manage its own cache. This is due to a limitation in Qgis that
prevent sharing resources between different processes and the fact that Qgis server
runtime is essentially single threaded.

The cache in Qgis services do not use the default internal cache of Qgis server but
its own caching system based on `QgsProjectStorage` objects. This ensure that any
storage backends implemented or added in Qgis with plugins is supported.

Project's access is *uniform*: the cache configuration define search paths which are indirection
to the corresponding backends:

.. code-block:: toml

   [worker.projects.search_paths]
   '/a_path' = "/path/to/projects/"                  # Path to files volume
   '/another/path' = "file:///other/projects/"       # With explicit scheme
   '/path/to/postgres' = "postgres://?service=name"  # projects stored in postgres

Any following subpath to a search path is considered as the relative project's path
or the projects name user for url resolution::

    /path/to/postgres/projname

will be resolved to::

    postgres://?service=name&project=projname

From client perspective, a project is always referred by its search path followed by the (relative)
project's path or name::

    /<search_path>/<project_path>


Dynamic paths
-------------

Dynamic paths allows to define templated path stems that will by be substituted in the
final path resolution::

    "/{user}/{theme}" = "/path/to/{user}/projects/{theme}" 

and ``/alice/forests/coolmap.qgs`` will be resolved to::

    "/path/to/alice/projects/forests/coolmap.qgis"

.. note::

   | Dynamic paths may have restrictions that depends on the underlying handler.
   | For example, the s3 storage handler does not allow you to template the bucket
     name and set different configuration the same bucker with templated prefix.


Managing cache
---------------

.. highlight:: sh

.. note::

    | As with the `load_project_on_request` option, there is an eviction strategy implemented 
      in worker cache only for projects loaded *on the fly*. Managed cache entries are not
      subject to eviction.
    | This is not the recommended option if your projects are bigs (many layers) and you should 
      always prefer managed cache for such projects.  
    | This is mainly because Qgis projects are not simple static resource but instead
      heavily dynamic resource with a lot of side effects (connecting to external source,
      loading metadata, ...) and this makes sense if you think in term of a publishing process.
    

Cache can be managed with the :ref:`service cli command <managing_rpc_services>`::

    Usage: qjazz-server-cli cache [OPTIONS] COMMAND [ARGS]...

      Commands for cache management

    Options:
      --help  Show this message and exit.

    Commands:
      catalog   List available projects from search paths
      checkout  CheckoutProject PROJECT from cache
      clear     Clear cache
      drop      Drop PROJECT from cache
      info      Return info from PROJECT in cache
      list      List projects from cache
      update    Synchronize cache between processes

.. highlight:: txt

Project checkout
----------------

Whenever a project is checked out from cache, a cache status is returned

:NEW: Project exists and is not loaded in cache
:NEEDUPDATE: Project is already loaded and need to be updated because source storage has been modified
:UNCHANGED: Project is loaded and is up to date
:REMOVED: Project is loaded but has been removed from storage
:NOTFOUND: Project does not exists


You may *pull* the project to make it change state depending on its initial state:

.. list-table:: Pull state changes
   :header-rows: 1

   * - Initial state
     - State after *pull*
     - Action
   * - NEW
     - UNCHANGED
     - Project is loaded in cache
   * - NEEDUPDATE
     - UNCHANGED
     - Cached project is updated with new version
   * - UNCHANGED
     - UNCHANGED
     - No action
   * - REMOVED
     - NOTFOUND
     - Project is removed from cache
   * - NOTFOUND
     - NOTFOUND
     - No action


.. _rpc_cache_restoration:

Cache restoration
-----------------

Projects loaded with the cache management api are `pinned` in the cache: they cannot leave the cache
except if removed explicitly.

Operations on cache are recorded internally and a when a QGIS processes is restored, all pinned
projects are loaded.

The cache may be restored at startup either from the `worker.restore_projects` setting
(or the `CONF_WORKER__RESTORE_PROJECTS` env variables).

Dynamic cache restoration
^^^^^^^^^^^^^^^^^^^^^^^^^

Dynamic restoration is only available with the official Docker image.

The cache restoration configuration may be set from remote location and independently of
the remote configuration setup using the `QJAZZ_RESTORE_PROJECTS_EXEC` env variable.
The executable must return a comma separated list of projects to load at startup (internally
it use the `CONF_WORKER__RESTORE_PROJECTS`).

.. note::
   | By default, the restoration list may by downloaded from a remote URL given by 
     `QJAZZ_REMOTE_RESTORE_PROJECTS_URL` env variable. 
   | You may define your own restoration setup by inheriting from the official Docker image
     and define a setting a custom QJAZZ_REMOTE_RESTORE_PROJECTS_EXEC  executable.
     This may be useful if your are using alternate storage for your restoration settings.

.. note::
    | Using a dynamic cache restoration could be useful when synchronizing cache from a pool
      of RPC services: if you keep a live version of the cache configuration accessible from 
      a remote location then all rpc services of your pool will by synchronized at startup.











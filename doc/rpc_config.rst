
.. _rpc_services:

Qgis RPC services
=================

RPC services runs qgis server processes and expose `gRPC <https://grpc.io/>`_ interfaces.
for requesting and managing the Qgis processes.

The unit of Qgis services is a *worker* wihch is a running instance
of a gRPC service.  

Workers are grouped by *pools* that share the exact same configuration.

For examples, scaling a docker container with a running rpc-server in a docker compose
stack automatically create a *pool* of workers.

That is, a pool is addressed by a gRPC client as a single endpoint. (i.e `qgis-rpc` like in
the :ref:`Docker compose setup <docker_compose_setup>` example.

Qgis processes
--------------

A worker may run a configurable number of Qgis processes.  Incoming Qgis requests
to the gRPC service are distributed with a fair-queuing dispatching algorithm to 
the embedded Qgis server processes.

You may increase or decrease the number of processes but another strategy is to 
scale the number of worker services while keeping the number of sub-processes relatively
small. 

Depending of the situation it may be better to choose one or another strategy.

Life cycle and pressure conditions
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If a processes crash, the worker is then in a *degraded*
state that can be monitored. When the number of dead process exceed some limite will
stop with an error code.

There is one condition for a worker to deliberatly exit 
with a error condition: the *process failure pressure*.

The process failure pressure is the ratio of failed processes over the initial
number of configured processes. If this ratio raise above some configured limit,
then the worker exit with critical error condition.

.. warning::
    In order not to let the worker degrade itself slowly
    the number of worker should be kept low (from 2 to 3)
    or keep a relatively low 'max_processes_failure_pressure'.


Process timeout
^^^^^^^^^^^^^^^

A process may be deliberatly killed (and thus increase the pressure) on long
running requests.

If the response time exceed the `process_timeout` then the procces processing the request
is considered as stalled and killed. If terminating the process increase the failure 
pressure too much then the worker will exit with an error condition. 


.. note::
   | The `worker.rescale_period` configuration setting allow to periodically restore the
     initial number of worker. Nevertherless, if too many workers die in a short amount 
     of time less that the rescale period the ressure can increase too much and the worker 
     will exit.
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


.. _rpc_cache_overview:

Qgis project's cache overview
=============================

Each processes manage its own cache. This is due to a limitation in Qgis that
prevent sharing resources between differents processes and the fact that Qgis server 
runtime is essentialy single threaded.

The cache in Qgis services do not use the default internal cache of Qgis server but
its own caching system based on `QgisProjectStorage` objects. This ensure that any
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

From client perspective, a project is always refered by its search path followed by the (relative)
project's path or name::

    /<search_path>/<project_path>


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

    Usage: qgis-server-cli cache [OPTIONS] COMMAND [ARGS]...

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


You may *pull* the project to make it change state depending on its inital state:

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

Cache restoration occurs under some condtions when a service instance is restarted or 
new instance is created when scaling services.

There is several restoration types:

   * :tmp:  | The list of cached projects is dynamically updated when projects are loaded explicitely
              with the cache managment api; i.e, projects loaded dynamically with the 
              `load_project_on_request` option will no be restored. 
            | The list is saved on disk in a tmp directory and restored when the instance restart.
   * :http: The list is downloaded from http remote url, it can be considired as a static configuration
            and no update is done. 
   * :https: Same as `http` with SSL configuration
   * :none: No restoration


.. code-block:: toml
    
   # Cache restoration configuration
   [restore_cache]
   restore_type = "none" # one of "tmp", "http", "https" or "none"
   # External cache url  if the restore_type is "http" or "https"
   url = "https://..."

   # SSL configuration for https restoration type
   [restore_cache.ssl]
   # CA file
   #cafile =   	# Optional
   #
   # SSL/TLS  key
   #
   # Path to the SSL key file
   #certfile =   	# Optional
   #
   # SSL/TLS Certificat
   #
   # Path to the SSL certificat file
   #keyfile =   	# Optional


.. note::

    With `tmp` restoration type, the directory where the config is stored may be specified with 
    the `CONF_TMPDIR` environment variable (by default it is saved in the `/tmp` directory).

    For preserving `tmp` cache restoration from container update or scaling update, you may use
    a persistent docker volume which will be available for any new created container.


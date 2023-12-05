
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

The purpose of these processes is not to scale but to ensure some fault-tolerance system up
to some limit.

Life cycle and pressure conditions
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If a processes crash, the worker is then in a *degraded*
state that can be monitored. When the last process exit the worker will
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
   | There is no mecanism for restarting dead processes in worker instance 
     and performance can degrade quickly if the processes exit abnormally.
   | Scaling and resilience are achieved in a much more effective way by using 
     the scaling capabilities of Docker compose, swarm or other container orchestrator 
     or even SystemD.


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

    | There is no cache removal strategy implemented in worker cache: cache is totally 
      managed using api call.

    | This is mainly because Qgis projects are not simple static resource but instead
      heavily dynamic resource with a lot of side effects (connecting to external source,
      loading metadata, ...).
    | This makes sense if you think in term of a publishing process.
    
    | Note that by default, projects are loaded as they are requested (this is a configurable
      option). This is convenient if your organize your storage and search path so as to get
      only publishable projects.

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
^^^^^^^^^^^^^^^^

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

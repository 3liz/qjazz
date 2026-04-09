.. _rpc_configuration:

RPC Configuration
=================

.. _rpc_configuration_toml:

TOML configuration
------------------


.. literalinclude:: configs/rpc.toml
     :language: toml


Dynamic configuration setup
---------------------------

This is only available if you are running the service through the official docker image.

The configuration may be set dynamically at startup by running an executable returning 
a configuration in *JSon* format.

The executable is controlled by the `QJAZZ_CONFIG_EXEC` variable.

The default settings allow you to define a remote URL for downloading the configuration at startup.
Se the `basic-with-config-server` example for an example of remote configuration setup. 

.. note::
   | You may define your own config setup by inheriting from the official Docker image
     and define a setting a custom QJAZZ_CONFIG_EXEC executable.
   | This may be useful if your are using alternate storage for your configuration settings.



Check the :download:`configuration json schema <specs/rpc-config.json>`.


Hot Configuration
-----------------

Configuration can be updated at runtime using the :ref:`rpc_cli`:

.. code-block:: bash

    qjazz-rpc-client config set '{"logging": {"level": "debug"}}'
    qjazz-rpc-client  config log info



   
.. _rpc_cache_overview:

Qgis project's cache overview
-----------------------------

Each processes manage its own cache. This is due to a limitation in Qgis that
prevent sharing resources between different processes and the fact that Qgis server
runtime is essentially single threaded.

The cache in Qgis services do not use the default internal cache of Qgis server but
its own caching system based on `QgsProjectStorage` objects. This ensure that any
storage backends implemented or added in Qgis with plugins is supported.

It supports various storage backends including:

- Local filesystem
- PostgreSQL (via ``postgres://`` scheme)
- S3 object storage
- Custom backends via plugins

Cache Search Paths
^^^^^^^^^^^^^^^^^^

Project's access is *uniform*: Projects are accessed through configured search paths
that act as  indirection to storage backends:

.. code-block:: toml

    [worker.qgis.projects.search_paths]
    '/public' = "/path/to/projects/"                        # Path to files volume
    '/db' = "postgres://?service=myproject&schema=public"   # Projects stored in postgres
    '/s3' = "s3://mybucket/projects/"                       # S3 storage

Any following subpath to a search path is considered as the relative project's path
or the projects name user for url resolution::

    /path/to/postgres/projname

will be resolved to::

    postgres://?service=name&project=projname

From client perspective, a project is always referred by its search path followed by the (relative)
project's path or name::

    /<search_path>/<project_path>


Dynamic paths
^^^^^^^^^^^^^

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
^^^^^^^^^^^^^^

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

    Usage: qjazz-rpc-client cache [OPTIONS] COMMAND [ARGS]...

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
^^^^^^^^^^^^^^^^^

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




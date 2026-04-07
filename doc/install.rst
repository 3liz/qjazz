.. highlight:: text

.. _installation:

Installation and Principles
===========================

This documentation is intended for system administrators who will:

- Install and configure QJazz services
- Deploy QJazz in production environments
- Manage and monitor QJazz infrastructure
- Troubleshoot deployment issues

Prerequisites
-------------

Hardware Requirements
^^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - Component
     - Requirement
   * - CPU
     - Multi-core recommended.
   * - RAM
     - 4 GB minimum
   * - Disk
     - Fast SSD for project storage and temp files
   * - Network
     - 1 Gbps for internal gRPC communication

.. note::

   Numbers above are only indicatives. Usually the RAM needed will hihly depends
   of the nature of the QGIS projects loaded.  

   You have to be aware that projects are NOT shared across workers since each worker
   is an independant QGIS process.

Software Requirements
^^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - OS
     - Linux
   * - Software 
     - QGIS 3.34+ (3.40+ recommended)
   * - Docker
     - 20.10+ with docker compose v2
   * - Python
     - 3.12+ (provided by Docker image)

.. note::
    QJazz is primarily deployed using Docker. Direct installation on bare metal or VMs
    is possible but requires building from source. See :ref:`source_installation` for details.


Architecture Overview
---------------------

QJazz is a QGIS server framework composed of multiple services that work together to provide
scalable geospatial services. The architecture follows a microservices pattern with clear separation
of concerns.

Process Pool architecture
^^^^^^^^^^^^^^^^^^^^^^^^^

The RPC service uses a Rust-based process pool to manage Python worker 
subprocesses. This architecture provides:

- **Isolation**: Each QGIS process runs in its own subprocess
- **Fault tolerance**: Failed processes are automatically restarted
- **Resource control**: Fine-grained control over process lifecycle
- **Fair scheduling**: Incoming requests are distributed using a fair-queuing algorithm


The following diagram shows the relationship between QJazz components:

.. code-block:: text

    ┌─────────────────────────────────────────────────────────────────┐
    │                      Client Applications                        │
    │  (Web browsers, GIS clients, API consumers)                     │
    └───────────────────────────┬─────────────────────────────────────┘
                                │ HTTP/WMS/WFS/WCS/...
                                ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │                    qjazz-map (HTTP Frontend)                    │
    │  • Route requests to backend pools                              │
    │  • Load balancing                                               │
    │  • CORS handling                                                │
    │  • TLS termination                                              │
    └───────────────────────────┬─────────────────────────────────────┘
                                │ gRPC
                                ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │                    qjazz-rpc (gRPC Service)                     │
    │  ┌───────────────────────────────────────────────────────────┐  │
    │  │                 qjazz-pool (Process Manager)              │  │
    │  │  • Spawn/manage QGIS worker processes                     │  │
    │  │  • Fair-queuing request distribution                      │  │
    │  │  • Failure detection and recovery                         │  │
    │  └───────────────────────────────────────────────────────────┘  │
    │  ┌─────────┐  ┌─────────┐  ┌─────────┐                          │
    │  │ Worker  │  │ Worker  │  │ Worker  │  (Python + QGIS Server)  │
    │  │   1     │  │   2     │  │   N     │                          │
    │  │ ┌─────┐ │  │ ┌─────┐ │  │ ┌─────┐ │                          │
    │  │ │QGIS │ │  │ │QGIS │ │  │ │QGIS │ │                          │
    │  │ │Proc │ │  │ │Proc │ │  │ │Proc │ │                          │
    │  │ └─────┘ │  │ └─────┘ │  │ └─────┘ │                          │
    │  └─────────┘  └─────────┘  └─────────┘                          │
    └───────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │                    Project Storage Backends                     │
    │  ┌─────────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐   │
    │  │  Local      │  │PostgreSQL │  │   S3      │  │  Custom   │   │
    │  │  Filesystem │  │           │  │   Storage │  │  (plugin) │   │
    │  └─────────────┘  └───────────┘  └───────────┘  └───────────┘   │
    └─────────────────────────────────────────────────────────────────┘


.. _rpc_services:

QGIS RPC services
=================

RPC services runs QGIS server processes and expose `gRPC <https://grpc.io/>`_ interfaces.
for requesting and managing the QGIS processes.


Life cycle and pressure conditions
----------------------------------

If a process crashes, the worker is then in a *degraded* 
state that can be monitored. 

In *degraded state*, the RPC service will try to restore dead workers so as to keep
the number of live QGIS processes constante.

In some situation the number of dead processes exceed some limite will
stop with an error code.

There is one condition for a worker to deliberately exit
with a error condition: the *process failure pressure*.

The process failure pressure is the ratio of failed processes over the initial
number of configured processes. If this ratio raise above some configured limit,
then the service will exit with critical error condition.


Workers are monitored for:

- **Process crashes**: Automatically detected and restarted
- **Request timeouts**: Configurable via ``server.timeout`` and ``worker.cancel_timeout``
- **Failure pressure**: Ratio of failed processes vs configured processes

.. note::
    If the failure pressure exceeds the configured limit (``max_failure_pressure``),
    the service exits with a critical error. This prevents degraded services from
    continuing to serve requests.

Process timeout
---------------

A process may be deliberately killed (and thus increase the pressure) on long
running requests.

If the response time exceed the request `server.timeout` then the process processing the request
is considered as stalled and asked to abort gracefully the request. 
The grace timeout is controlled by the `worker.cancel_timeout`; if the process fail to abort
the request then the process is killed, which will increase the failure 
pressure. 

.. note::
   | When a worker die, the service will try to maintain the initial number of workers.
     Nevertheless, if too many workers die in a short amount the pressure can increase
     too much and the worker will exit.
   | If this occurs, this is usually because there is something wrong with the treatment of 
     the  qgis request that must be investigated.
   | On production, Monitoring workers lifecycle may be useful to detect such situations.


Worker Pools
------------

Workers can be grouped into pools that share the same configuration and network
address. In Docker environments, scaling containers automatically creates pools.

For examples, scaling a docker container with a running rpc-server in a docker compose
stack automatically create a *pool* of workers.

That is, a pool is addressed by a gRPC client as a single endpoint. (i.e `qgis-rpc` like in
the :ref:`Docker compose setup <docker_compose_setup>` example.

Pool Characteristics:

- **Single endpoint**: Addressed as one gRPC endpoint by clients
- **Shared configuration**: All workers in a pool have identical settings
- **Automatic scaling**: Docker ``--scale`` creates additional workers
- **Load balancing**: Requests distributed via round-robin

You may increase or decrease the number of processes but another strategy is to 
scale the number of worker services while keeping the number of sub-processes relatively
small. 

Depending of the situation it may be better to choose one or another strategy.

Fault Tolerance
---------------

The system implements several fault tolerance mechanisms:

1. **Process supervision**: Dead processes are automatically restarted
2. **Graceful degradation**: Services continue with reduced capacity under failure pressure
3. **Health checks**: Built-in gRPC health checking protocol
4. **Cache restoration**: Pinned projects are restored on worker restart


Deployment Options
------------------

Standalone QGIS Server
^^^^^^^^^^^^^^^^^^^^^^

Deploy only the RPC service for direct gRPC access:

.. code-block:: yaml

    services:
      qgis-rpc:
        image: 3liz/qjazz:qgis-3.40
        environment:
          CONF_WORKER__NAME: gis-worker
          CONF_WORKER__QGIS__PROJECTS__SEARCH_PATHS: >-
            { "/": "/qgis-projects" }
        volumes:
        - ./projects:/qgis-projects:ro
        command: ["qjazz-rpc", "serve"]

Scaled Deployment
^^^^^^^^^^^^^^^^^

Scale workers horizontally:

.. code-block:: bash

    docker compose up -d --scale qgis-rpc=4

The HTTP frontend automatically detects and uses all workers.

With QGIS Plugins
^^^^^^^^^^^^^^^^^

Mount plugin directories:

.. code-block:: yaml

    services:
      qgis-rpc:
        image: 3liz/qjazz:qgis-ltr-eager
        environment:
          CONF_WORKER__NAME: worker
          CONF_WORKER__QGIS__PLUGINS__PATHS: >-
            "/plugins"
        volumes:
        - ./projects:/qgis-projects:ro
        - ./plugins:/plugins:ro
        command: ["qjazz-rpc", "serve"]

With TLS
^^^^^^^^

Enable TLS on both frontend and RPC services:

.. code-block:: yaml

    services:
      qgis-rpc:
        image: 3liz/qjazz:qgis-ltr-eager
        environment:
          CONF_GRPC_USE_TLS: "yes"
          CONF_GRPC_TLS_KEYFILE: /certs/rpc.key
          CONF_GRPC_TLS_CERTFILE: /certs/rpc.crt
          CONF_GRPC_TLS_CAFILE: /certs/ca.crt
        volumes:
        - ./certs:/certs:ro
        command: ["qjazz-rpc", "serve"]
      
      web:
        image: 3liz/qjazz:qgis-ltr-eager
        environment:
          CONF_SERVER__ENABLE_TLS: "yes"
          CONF_SERVER__TLS_KEY_FILE: /certs/web.key
          CONF_SERVER__TLS_CERT_FILE: /certs/web.crt
        volumes:
        - ./certs:/certs:ro
        ports:
        - "443:9080"
        command: ["qjazz-map", "serve"]


Security Considerations
-----------------------

.. note::
    Key security settings administrators should be aware of:

- **enable_python_embedded**: Disabled by default (``false``). Enables Python macros in projects.
- **allow_direct_path_resolution**: Disabled by default. Allows raw filesystem paths in requests.
- **enable_tls**: Should be enabled in production environments.


Configuration System
====================

QJazz uses a layered configuration system:


1. **Configuration file**: TOML format by default (JSON/YAML also supported)
2. **Environment variables**: Override file settings with ``CONF_`` prefix
3. **Remote configuration**: Fetch from URL at startup (Docker only)

Configuration precedence (highest to lowest):

1. Command-line arguments
2. Environment variables
3. Configuration file
4. Default values

When reading configuration from file, the format is TOML
by default. 


See :ref:`rpc_configuration` for the full
RPC service configuration schema and :ref:`server_config` for the frontend proxy.


Using configuration file
------------------------

You may specify a configuration file with the `--conf` or `-C` option:
        
.. code-block:: bash

    qjazz-rpc serve -C path/to/config/file.toml

Using environment variables
---------------------------

Configuration defaults may by overridden by environment variables.

This is useful for playing nicely with docker-compose with small
configuration settings.

Configuration structure may be composed of simple values but also of more nested  
complex type. 

All configuration variables will start with the prefix `CONF_` followed by the field
name (or toml section). Nested fields are separated by '__' and so on.

If the nested type is too complex, the environment variable may contains the Json
representation of the field.

Examples:

Environment variables::
    
    CONF_LOGGING__LEVEL=trace
    CONF_WORKER__NAME=worker
    CONF_WORKER__QGIS__PROJECTS__SEARCH_PATHS='{ "/": "/qgis-projects/france_parts" }'

Which gives the toml equivalent:

.. code-block:: toml

    [loggin]
    level = "debug"

    [worker]
    name = "worker"

    [worker.projects.search_paths]
    '/' = "/qgis-projects/france_parts"

Directory Structure
-------------------

Typical deployment layout:

.. code-block:: text

    deployment/
    ├── docker-compose.yml
    ├── config/
    │   ├── rpc.toml
    │   └── server.toml
    ├── projects/
    │   ├── public/
    │   │   └── project.qgs
    │   └── restricted/
    ├── plugins/
    │   └── my_plugin/
    └── certs/
        ├── server.key
        └── server.crt

Volumes
^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Volume
     - Description
   * - ``/qgis-projects``
     - QGIS project files (read-only recommended)
   * - ``/qgis-plugins``
     - QGIS plugin directories

.. _source_installation:


Testing the Installation
------------------------

After deployment, verify the installation:

1. **Health Check**

   .. code-block:: bash

       docker compose exec qgis-rpc qjazz-rpc-client healthcheck

2. **List Cached Projects**

   .. code-block:: bash

       docker compose exec qgis-rpc qjazz-rpc-client cache catalog

3. **Test WMS Request**

   .. code-block:: bash

       curl "http://localhost:9080/?MAP=/public/project.qgs&SERVICE=WMS&REQUEST=GetCapabilities"

4. **View Logs**

   .. code-block:: bash

       docker compose logs -f qgis-rpc

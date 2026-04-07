.. highlight:: text

.. _rpc_cli:

RPC client CLI Reference
========================

The ``qjazz-rpc-client`` command provides a command-line interface for interacting with
QJazz gRPC services. It allows you to manage caches, send requests, configure services,
and monitor worker status.

Installation
------------

The CLI is available as the ``qjazz-rpc-client`` command when QJazz is installed:

.. code-block:: bash

    qjazz-rpc-client --help

Or inside a Docker container:

.. code-block:: bash

    docker compose exec qgis-rpc qjazz-rpc-client --help

Environment Variables
---------------------

The CLI uses the following environment variables to connect to the gRPC server:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Variable
     - Description
   * - ``QGIS_GRPC_HOST``
     - Address of the gRPC server (default: ``localhost:23456``)
   * - ``CONF_GRPC_USE_TLS``
     - Set to ``1``, ``yes``, or ``true`` to enable TLS
   * - ``CONF_GRPC_TLS_KEYFILE``
     - Path to the TLS client key file
   * - ``CONF_GRPC_TLS_CERTFILE``
     - Path to the TLS client certificate file
   * - ``CONF_GRPC_TLS_CAFILE``
     - Path to the CA server certificate file


Command Groups
--------------

The CLI is organized into the following command groups:

* ``request`` - Send QGIS requests
* ``cache`` - Manage project cache
* ``plugin`` - Retrieve QGIS plugin information
* ``config`` - Manage server configuration
* ``state`` - Control service state
* Direct commands - ping, healthcheck, stats, etc.


Request Commands
----------------

Send QGIS requests to the server.

.. _request_ows:

request ows
^^^^^^^^^^^

Send an OWS (Open Web Services) request to the QGIS server.

.. code-block:: bash

    qjazz-rpc-client request ows PROJECT [OPTIONS]

**Arguments:**

* ``PROJECT`` - The QGIS project path or URI

**Options:**

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Option
     - Description
   * - ``--service``, ``-s``
     - OWS service name (required). 
       
       Examples: ``WMS``, ``WFS``, ``WCS``
   * - ``--request``, ``-r``
     - OWS request name (required). 
       
       Examples: ``GetCapabilities``, ``GetMap``, ``DescribeFeatureType``
   * - ``--version``
     - OWS service version (optional). 
       
       Example: ``1.3.0`` for WMS
   * - ``--param``, ``-p KEY=VALUE``
     - Additional request parameters. 
       
       Can be specified multiple times
   * - ``--headers``, ``-H``
     - Show response headers
   * - ``--url``
     - Origin URL for the request
   * - ``--output``, ``-o FILE``
     - Write output to file instead of stdout

**Examples:**

Get WMS capabilities:

.. code-block:: bash

    qjazz-rpc-client request ows /path/to/project.qgs \
        --service WMS \
        --request GetCapabilities

Get a map image:

.. code-block:: bash

    qjazz-rpc-client request ows /path/to/project.qgs \
        --service WMS \
        --request GetMap \
        --param LAYERS=my_layer \
        --param BBOX=0,0,100,100 \
        --param CRS=EPSG:4326 \
        -o map.png


.. _request_api:

request api
^^^^^^^^^^^

Send a QGIS API request.

.. code-block:: bash

    qjazz-rpc-client request api [OPTIONS]

**Options:**

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Option
     - Description
   * - ``--name``
     - API name (required). Example: ``processi``, ``wfs``
   * - ``--path``
     - API path (default: ``/``)
   * - ``--target``
     - Target QGIS project
   * - ``--param``, ``-p KEY=VALUE``
     - Query parameters. Can be specified multiple times
   * - ``--headers``, ``-H``
     - Show response headers
   * - ``--url``
     - Origin URL for the request
   * - ``--output``, ``-o FILE``
     - Write output to file instead of stdout

**Examples:**

Execute an OGC Features (OAPIF) request:

.. code-block:: bash

    qjazz-rpc-client request api \
        --name OAPIF \
        --path /collections.json \
        --target /route/to/project.qgs \


Cache Commands
--------------

Manage the QGIS project cache.

.. _cache_checkout:

cache checkout
^^^^^^^^^^^^^^

Checkout a project from the cache. If ``--pull`` is specified, the project is loaded
into the cache as a pinned item.

.. code-block:: bash

    qjazz-rpc-client cache checkout PROJECT [OPTIONS]

**Arguments:**

* ``PROJECT`` - The project path or URI to checkout

**Options:**

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Option
     - Description
   * - ``--pull``
     - Load the project into cache as a pinned item

**Examples:**

Preview a project without caching:

.. code-block:: bash

    qjazz-rpc-client cache checkout /path/to/project.qgs

Load and cache a project:

.. code-block:: bash

    qjazz-rpc-client cache checkout /path/to/project.qgs --pull


.. _cache_drop:

cache drop
^^^^^^^^^^

Remove a project from the cache.

.. code-block:: bash

    qjazz-rpc-client cache drop PROJECT

**Arguments:**

* ``PROJECT`` - The project path or URI to remove

**Example:**

.. code-block:: bash

    qjazz-rpc-client cache drop /path/to/project.qgs


.. _cache_clear:

cache clear
^^^^^^^^^^^

Clear the entire cache, removing all cached projects.

.. code-block:: bash

    qjazz-rpc-client cache clear

**Example:**

.. code-block:: bash

    qjazz-rpc-client cache clear


.. _cache_list:

cache list
^^^^^^^^^^

List all projects in the static (pinned) cache.

.. code-block:: bash

    qjazz-rpc-client cache list

**Example:**

.. code-block:: bash

    qjazz-rpc-client cache list


.. _cache_update:

cache update
^^^^^^^^^^^^

Update cache item states. This refreshes the metadata of cached projects.

.. code-block:: bash

    qjazz-rpc-client cache update

**Example:**

.. code-block:: bash

    qjazz-rpc-client cache update


.. _cache_info:

cache info
^^^^^^^^^^

Get detailed information about a specific project in the cache.

.. code-block:: bash

    qjazz-rpc-client cache info PROJECT

**Arguments:**

* ``PROJECT`` - The project path or URI

**Example:**

.. code-block:: bash

    qjazz-rpc-client cache info /path/to/project.qgs


.. _cache_catalog:

cache catalog
^^^^^^^^^^^^^

List available projects from configured search paths.

.. code-block:: bash

    qjazz-rpc-client cache catalog [OPTIONS]

**Options:**

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Option
     - Description
   * - ``--location``
     - Filter projects by location

**Example:**

.. code-block:: bash

    qjazz-rpc-client cache catalog

List projects from a specific location:

.. code-block:: bash

    qjazz-rpc-client cache catalog --location /projects/europe


.. _cache_dump:

cache dump
^^^^^^^^^^

Dump the complete cache state and configuration for all backend workers.
This is a "stop the world" operation that waits for all workers to be available.
Use only for debugging purposes.

.. code-block:: bash

    qjazz-rpc-client cache dump

**Example:**

.. code-block:: bash

    qjazz-rpc-client cache dump

**Warning:** This command may disrupt normal operations as it halts all workers.


Plugin Commands
---------------

.. _plugin_list:

plugin list
^^^^^^^^^^^

List all installed QGIS plugins.

.. code-block:: bash

    qjazz-rpc-client plugin list

**Example:**

.. code-block:: bash

    qjazz-rpc-client plugin list

**Output format:**

Each plugin is displayed as a JSON object containing:

* ``name`` - Plugin name
* ``path`` - Plugin directory path
* ``pluginType`` - Plugin type
* ``metadata`` - Plugin metadata (parsed from metadata.txt)


Config Commands
---------------

Manage server configuration.

.. _config_get:

config get
^^^^^^^^^^

Retrieve the current server configuration.

.. code-block:: bash

    qjazz-rpc-client config get

**Example:**

.. code-block:: bash

    qjazz-rpc-client config get


.. _config_set:

config set
^^^^^^^^^^

Set server configuration. Accepts JSON configuration directly or from a file.

.. code-block:: bash

    qjazz-rpc-client config set CONFIG [OPTIONS]

**Arguments:**

* ``CONFIG`` - JSON configuration string, or ``@filename`` to read from file

**Examples:**

Set configuration directly:

.. code-block:: bash

    qjazz-rpc-client config set '{"logging": {"level": "debug"}}'

Set configuration from a file:

.. code-block:: bash

    qjazz-rpc-client config set @/path/to/config.json


.. _config_log:

config log
^^^^^^^^^^

Quick command to set the logging level.

.. code-block:: bash

    qjazz-rpc-client config log LEVEL

**Arguments:**

* ``LEVEL`` - Log level: ``trace``, ``debug``, ``info``, ``warning``, ``error``

**Examples:**

Set debug logging:

.. code-block:: bash

    qjazz-rpc-client config log debug

Set error logging:

.. code-block:: bash

    qjazz-rpc-client config log error


State Commands
--------------

Control and query the gRPC service state.

.. _state_env:

state env
^^^^^^^^^

Get the current environment status of the service.

.. code-block:: bash

    qjazz-rpc-client state env

**Example:**

.. code-block:: bash

    qjazz-rpc-client state env


.. _state_disable:

state disable
^^^^^^^^^^^^^

Disable the server from serving requests.

.. code-block:: bash

    qjazz-rpc-client state disable

**Example:**

.. code-block:: bash

    qjazz-rpc-client state disable

After running this command, the server will respond with a "not serving" status
to all incoming requests.


.. _state_enable:

state enable
^^^^^^^^^^^^

Enable the server to start serving requests.

.. code-block:: bash

    qjazz-rpc-client state enable

**Example:**

.. code-block:: bash

    qjazz-rpc-client state enable


Direct Commands
---------------

ping
^^^^

Ping the gRPC service to check connectivity and response time.

.. code-block:: bash

    qjazz-rpc-client ping [OPTIONS]

**Options:**

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Option
     - Description
   * - ``--count``, ``-n N``
     - Number of ping requests to send (default: 1)
   * - ``--server``
     - Ping the QGIS server service instead of the admin service

**Examples:**

Single ping:

.. code-block:: bash

    qjazz-rpc-client ping

Multiple pings with 1-second interval:

.. code-block:: bash

    qjazz-rpc-client ping -n 5

Ping the QGIS server service:

.. code-block:: bash

    qjazz-rpc-client ping --server


healthcheck
^^^^^^^^^^^

Check and monitor the health status of the gRPC server.

.. code-block:: bash

    qjazz-rpc-client healthcheck [OPTIONS]

**Options:**

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Option
     - Description
   * - ``--watch``, ``-w``
     - Watch mode: continuously monitor status changes
   * - ``--set-error``
     - Exit with error code (1) if server is not serving

**Examples:**

Single health check:

.. code-block:: bash

    qjazz-rpc-client healthcheck

Watch mode:

.. code-block:: bash

    qjazz-rpc-client healthcheck -w

Exit with error if not healthy (useful for health checks in containers):

.. code-block:: bash

    qjazz-rpc-client healthcheck --set-error


stats
^^^^^

Display information about service processes.

.. code-block:: bash

    qjazz-rpc-client stats [OPTIONS]

**Options:**

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Option
     - Description
   * - ``--watch``, ``-w``
     - Watch mode: continuously display stats
   * - ``--interval``, ``-i SECONDS``
     - Interval between stats updates in watch mode (default: 1)

**Examples:**

Get current stats:

.. code-block:: bash

    qjazz-rpc-client stats

Watch stats with 5-second interval:

.. code-block:: bash

    qjazz-rpc-client stats -w -i 5


sleep
^^^^^

Execute a cancelable request with a configurable delay. Useful for testing
request cancellation behavior.

.. code-block:: bash

    qjazz-rpc-client sleep [OPTIONS]

**Options:**

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Option
     - Description
   * - ``--delay``, ``-d SECONDS``
     - Response delay in seconds (default: 3)

**Example:**

.. code-block:: bash

    qjazz-rpc-client sleep -d 5

Press ``Ctrl+C`` to cancel the request.


reload
^^^^^^

Reload QGIS processes. This gracefully restarts the QGIS worker processes
without interrupting the gRPC service.

.. code-block:: bash

    qjazz-rpc-client reload

**Example:**

.. code-block:: bash

    qjazz-rpc-client reload


Usage Examples
--------------

Checking Service Health
^^^^^^^^^^^^^^^^^^^^^^^

To verify a service is running correctly:

.. code-block:: bash

    # Check if service is serving
    qjazz-rpc-client healthcheck

    # Watch for status changes
    qjazz-rpc-client healthcheck -w

    # Exit with error if not healthy (for container orchestrators)
    qjazz-rpc-client healthcheck --set-error


Managing Projects
^^^^^^^^^^^^^^^^^

To manage QGIS projects in the cache:

.. code-block:: bash

    # List cached projects
    qjazz-rpc-client cache list

    # Catalog available projects
    qjazz-rpc-client cache catalog

    # Checkout and cache a project
    qjazz-rpc-client cache checkout /path/to/project.qgs --pull

    # Get project info
    qjazz-rpc-client cache info /path/to/project.qgs

    # Drop from cache when done
    qjazz-rpc-client cache drop /path/to/project.qgs


Sending Requests
^^^^^^^^^^^^^^^^

To test QGIS requests directly:

.. code-block:: bash

    # Get WMS capabilities
    qjazz-rpc-client request ows /path/to/project.qgs \
        --service WMS \
        --request GetCapabilities \
        -o capabilities.xml

    # Get a map image
    qjazz-rpc-client request ows /path/to/project.qgs \
        --service WMS \
        --request GetMap \
        --param LAYERS=my_layer \
        --param BBOX=0,0,100,100 \
        --param CRS=EPSG:4326 \
        -o map.png


Service Configuration
^^^^^^^^^^^^^^^^^^^^^

To adjust service behavior:

.. code-block:: bash

    # View current configuration
    qjazz-rpc-client config get

    # Quick log level change
    qjazz-rpc-client config log debug

    # Update full configuration
    qjazz-rpc-client config set '{"logging": {"level": "debug"}}'


Docker/Container Usage
^^^^^^^^^^^^^^^^^^^^^^^

Execute commands inside a running container:

.. code-block:: bash

    # Basic health check
    docker compose exec qgis-rpc qjazz-rpc-client healthcheck

    # Change log level remotely
    docker compose exec qgis-rpc qjazz-rpc-client config log info

    # List cached projects
    docker compose exec qgis-rpc qjazz-rpc-client cache list

    # Watch stats
    docker compose exec qgis-rpc qjazz-rpc-client stats -w -i 5

Accessing a remote service:

.. code-block:: bash

    # Connect to a remote gRPC server
    QGIS_GRPC_HOST=remote-server:23456 qjazz-rpc-client healthcheck

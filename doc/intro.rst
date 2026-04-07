.. highlight:: text

.. _project_description:

Description
===========

QJazz is a suite of QGIS based services including:

- QGIS server as microservice
- OGC Processes server on top of QGIS processing

This is as set of modules for deploying QGIS based servers and processing services
as OGC processes compliant API

It aims to provide support for scalable deployment of QGIS based services 
on medium or large infrastructure and has been developed to solve some issues
when dealing with large numbers of projects.

The services are implemented as  wrappers around the QGIS Server api 
and the Processing QGIS api and because of this, it supports all 
QGIS Server features and options.

The qjazz-server setup is split in 3 different services:
    
- Services using gRCP protocols for running qgis servers processes
- Middleware asynchronous HTTP proxy for routing requests to different worker backends
- Admin tools and service for inspecting worker's pool and health checking.

Overview
--------

.. code-block::

    --------------------                 -------------------
    |                  | n             n |                 |
    |  HTTP            |<--------------->|   QGIS RPC      |
    |  frontend/proxy  |                 |   service pools |
    |                  |                 |                 |
    --------------------                 -------------------

.. _project_features:

Features
--------

These services have been designed after experimenting with version 1.x of 
`qjazz-server <https://https://github.com/3liz/qjazz-server>`_ 
on production infrastructure.

It aims at bringing better scaling management, cache management and healthcheck/fault tolerance
support.

Integrated features:

- Standalone Qgis server as microservice over gRPC protocol
- Managed project's cache that may be synchronized between Qgis services from the same pool.
- SSL support between all components
- Hot scaling with Docker stack (no restart needed)
- Hot (re)configuration from remote or local config



.. _quick_setup:

Quick Start with Docker
=======================

.. _docker_compose_setup:


The fastest way to deploy QJazz is using Docker Compose and official QJazz image from
`Docker hub <https://https://hub.docker.com/r/3liz/qjazz>`_

Minimal Setup
-------------

Create a ``docker-compose.yml`` file:



Docker compose setup
--------------------

This is the recommended way to install and run the services:

Note that most of the examples in this documentation assumes
docker deployment.

All services are runnable from a single image: 
`3liz/qjazz <https://hub.docker.com/3liz/qjazz>`_

Running workers with docker compose:

The simplest configuration for basic working installation is the following

Create a ``docker-compose.yml`` file:

.. code-block:: yaml

    services:
      #
      # The worker service run the grpc service that run 
      # qgis server
      #
      qgis-rpc:
        image: 3liz/qjazz:qgis-3.40
        environment:
          CONF_DISPLAY_XVFB: ON
          CONF_LOGGING__LEVEL: debug
          CONF_WORKER__NAME: basic_worker
          CONF_WORKER__NUM_PROCESSES: "2"
          CONF_WORKER__QGIS__PROJECTS__SEARCH_PATHS: >-
            { 
              "/":"/qgis-projects" 
            }
        volumes:
        - { type: bind, source: "/path/to/qgis/projects/", target: /qgis-projects } 
        command: ["qjazz-rpc", "serve"]
      web:
        #
        # The web service communicate to (multiple) backends and route
        # request to the appropriate backend.
        #
        image: 3liz/qjazz:qgis-3.40
        environment:
          CONF_LOGGING__LEVEL: debug
          CONF_BACKENDS__BASIC__TITLE: "QGIS Services"
          CONF_BACKENDS__BASIC__HOST: "qgis-rpc"
          CONF_BACKENDS__BASIC__ROUTE: "/"
        ports:
        - 127.0.0.1:9080:9080
        command: ["qjazz-map", "serve"]

Start the services:

.. code-block:: bash

    docker compose up -d

Access the service at: ``http://localhost:9080/``

From here, open your navigator at http://localhost:9080/?MAP=/my_project&SERVICE=WMS&REQUEST=GetCapabilities
in order to get the WMS Capabilities if your project is wms-enabled.

See the working example in `examples/basic-qgis-services`


.. _docker_scaling:

Scaling your services
---------------------

Scaling Qgis services
^^^^^^^^^^^^^^^^^^^^^

You may scale the Qgis services with the following command::

    docker compose up -d --scale qgis-rpc=2

*Note*: you may run this command while your stack is up, increasing or decreasing the numbers
of backend workers without any service interruption.

This will set up 2 new workers from the previous single worker state.  

The web service will automatically detect and handle the new backends and will round-robin
the requests to them.

.. 

Scaling the web service
^^^^^^^^^^^^^^^^^^^^^^^

In the same way you may scale the web service. Take care that you cannot publish directly on host
with multiple instances, you will need a load-balancer handling dns resolution with multiple ips.

.. _managing_rpc_services:

Managing Qgis services
-----------------------

Managing individual service
^^^^^^^^^^^^^^^^^^^^^^^^^^^

One way to manage workers individually is to use cli commands 
from inside running containers::

    docker compose exec [--index=n] qgis-rpc qjazz-rpc-client

The `qjazz-rpc-client` enables you to retrieve various information 
about the running service:

- Get environment state
- Monitor healthcheck
- Issue request directly to qgis
- List plugins
- Set and get configuration live
- Display and manage project's cache 

Note that this command only manage one qgis services at a time.
In order to manage multiple backend pools you will need another
tool dedicated to this purpose.

You may also run this command outside the service container by
defining the `QGIS_GRPC_HOST` variable with the remote worker instance
address.


.. highlight:: python
.. highlight:: sh

.. _project_description:

Description
===========

Py-qgis-server2 is a set of services for serving Qgis 3 server requests.

The py-qgis-server2 setup is splitted in 3 different services: 
    
- Workers using gRCP protocols for running qgis servers processes
- Middleware asynchronous HTTP proxy for routing requests to differents worker backends
- Admin tools and service for inspectings worker's pool and health checking.


.. _project_features:

Features
--------

These services have been designed after experimenting with `py-qgis-server <https://https://github.com/3liz/py-qgis-server` on several years on real infrastructure with more that hundreds of customers. From this experiences, we have totally re-designed some base features:

- Totaly separate Qgis server worker's as microservice and use gRPC protocel to communicate 
- Project's cache is now totally managed and can be synchronized between workers from the same pool.
- SSL support between all components
- Hot scaling with Docker stack (no restart needed)
- Hot (re)configuration (no restart needed)


.. _project_requirements:

Requirements
------------

- OS: Unix/Posix variants (Linux or OSX) (Windows not officially supported)
- Python >= 3.10
- QGIS >= 3.22 installed


.. _project_installation:

Installation
============


.. _project_pip_install:

Install in existing environment
-------------------------------

The py-qgis-server2 project is splitted into several python packages that can
be installed independently::

    pip install py-qgis-wo


.. _project_docker_run:

Docker deployment
=================


The `py-qgis-server2 <https://hub.docker.com/3liz/qgis-map-server2>` image bundle
all packages for running qgis services


Running workers with docker compose:

.. code-block:: yaml

    version: "3.9"
    services:
      image: 3liz/qgis-map-server2
      volumes:
      - { type: bind, source: "/path/to/projects/", target: /qgis-projects } 
      - { type: bind, source: "/path/to/config.toml", target: /etc/qgis-services/config.toml } 
      command: ["qgis-server-rpc", "serve", "-C", "/etc/qgis-services/config.toml"]

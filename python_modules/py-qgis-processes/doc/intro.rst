.. highlight:: python

.. _server_description:

Description
===========

|ProjectName| is an **draft** implementation of the `OGC Processes api <https://www.ogc.org/standard/ogcapi-processes/>`_ standards Open Geospatial Consortium based on the QGIS Processing API.

This implementation allows you to expose and run on a server:
* QGIS Processing models and scripts
* QGIS plugins having a Processing provider according to their `metadata.txt` file

.. _server_requirements:


The service is built on top of the  `Celery <https://github.com/celery/celery>`_  framework

How it works
------------

.. code-block::

   --------------                       --------------------
   |            | *                   * |                  |
   | Http       |<--------------------->| Celery Qgis      |
   | frontend   |                       | processingworker |
   |            |                       |                  |
   --------------                       --------------------


|ProjectName| allows you to deploy Celery workers executing Qgis processing algorithm.

A |ProjectName| Celery  worker expose the following tasks:

* TODO





Requirements and limitations
----------------------------

- Python 3.10+ only
- Windows not officially supported
- Redis server
- RabbitMQ server

.. _server_features:

Features
--------

- Asynchronous requests and parallel tasks execution
- Scalable

.. _server_installation:


Quick start
===========

First of all, you need Redis running instance and a RabbitMQ
running instance (see).

The |ProjectName| takes care of configuring Celery for using Redis and RabbitMQ so
should never have to deal directly with the Celery setup.

For more details, refer to  https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/rabbitmq.html and https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html 
for how they are configured with Celery


Run as Docker containers
------------------------



Running the server
==================

**pyqgiswps** [*options*]


Options
-------

.. program: pyqgiswps

.. option:: -d, --debug

    Force debug mode. This is the same as setting the :ref:`LOGGING_LEVEL <LOGGING_LEVEL>` option to ``DEBUG``

.. option:: -c, --config path

    Use the configuration file located at ``path``

.. option:: --dump-config

    Dump the configuration and exit


All in one
----------

Run as single server instance.

This mode of operation runs the front end and the worker together.


Running multiple workers
------------------------

You may run frontend and workers as different services on different
enviroments.

This enable running workers in different environments and infrastructure
according to your requirements.

* You may for example have a worker running intensive Jobs on a dedicated pool of 
  machine/vm while  other jobs may be run on smallest architecture.

* Some wokers may run on specific environments likes different Qgis versions
  or using specific libraries




# QJazz - QGIS as a service

## Description

QJazz is a suite of QGIS based services including:

* QGIS server as microservice
* OGC Processes server on top of QGIS processing

This is as set of modules for deploying QGIS based servers and processing services
as OGC processes compliant API

It aims to provide support for scalable deployment of QGIS based services 
on medium or large infrastructure and has been developed to solve some issues
when dealing with large numbers of projects.

The services are implemented as  wrappers around the QGIS Server api 
and the Processing QGIS api and because of this, it supports all 
QGIS Server features and options.

### Features

- Qgis server as microservice over gRPC protocol
- Enhanced scalability support
- Hot (re)configuration from remote or local config
- *OGC Api Map* support with STAC compliance
- *OGC Api Processes* support 
- REST admin api on project's cache
- Managed project's cache synchronized between workers
- S3 storage supports for projects
- Full TLS support for server and client authentification on all components

### Organize and distribute your QGIS servers

The QJazz support for QGIS server includes:

* A gRPC service wrapping embedded QGIS server processes pool 
* A frontend proxy for routing your requests to distributed gRPC workers.

The gRPC service manage Projects synchronization between all QGIS instances of the pool, 
automatic plugin installation and full control over loaded projects with a using dedicated 
service.

The frontend handle disconnection/reconnection of backend services, api delegation,
*OGC Map* api supports. 

The frontend HTTP/S server and the gRPC services are written in [Rust](https://www.rust-lang.org/) for
efficiency, stability and security.

### OGC *Processes* for QGIS Processing

Qjazz is designed for distributed environment and provide all-in-a-box setup for
deploying execution of QGIS processing algorithms behind a compliant OGC *Processes* 
api.

It enables leverage your algorithms and models designed with QGIS desktop with a full
compliant OGC *Processes* api without *any* modifications.

It use the [Celery](https://docs.celeryq.dev/en/stable/) framework for distributing
your jobs to multiples set of services and QGIS versions.

It allows for deploying custom QGIS based services by implementing your own QGIS based 
Celery workers.


### Requirements

- Python 3.12+
- Qgis 3.34+
- Linux/Posix based platform

If you plan to use the processing services then the following extra services are
required:

- [Redis](https://redis.io/) version 6+.
- [RabbitMQ](https://www.rabbitmq.com/) version 3+


Note that support for Windows or OSX are *not* planned. If you want to deploy
Qjazz on these platforms, consider using VMs or containers.

### Documentation

Look at the latest documentation:

* [Qjazz server documetation](https://docs.3liz.org/qjazz/qjazz-server/index.html)
* [Qjazz processes documentation](https://docs.3liz.org/qjazz/qjazz-processes/index.html)


### Getting started 

Have a look to the [examples](./examples) on how to use the services using our published Docker
images.


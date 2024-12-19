
# QJazz - QGIS as a service

**NOTE: This is a work in progress**

## Description

QJazz is a suite of QGIS based services including:

* QGIS server as microservices and proxy
* OGC Processes server on top of  QGIS processing
* QGIS print server

This is as set of modules for deploying QGIS based servers and processing services
as OGC processes compliant API

The services are implemented as  wrappers around the QGIS Server api 
and the Processing QGIS  api and because of this, it supports all 
QGIS Server features and options.

It aims to provide support for scalable deployment of QGIS based services 
on medium or large infrastructure and has been developped to solve some issues
when dealing with large numbers of projects.

### Features

- Qgis server as microservice over gRPC protocol
- Enhanced scalability support
- Hot (re)configuration from remote or local config
- REST admin api on project's cache
- Managed project's cache synchronized between workers.
- S3 storage supports for projects
- SSL support

### Requirements

- Python 3.12+
- Qgis 3.34+
- Linux based platform

If you plan to use the processing services then the following extra services are
required:

- [Redis](https://redis.io/) version 6+.
- [RabbitMQ](https://www.rabbitmq.com/) version 3+


Note that no direct support for Windows or OSX are *not* planned as we do not use these platforms
for deployment. 
So if it appears not to work on these platforms, consider using VM or containers.


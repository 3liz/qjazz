
# QGIS as a service

**NOTE: This is a work in progress**

## Description

This is as set of modules for deploying QGIS based servers and processing services
as OGC processes compliant API

The services are implemented as  wrappers around the QGIS Server api 
and the Processing QGIS  api and because of this, it supports all 
QGIS Server features and options.

It aims to provide support for scalable deployment of QGIS based services 
on medium or large infrastructure and has been developped to solve some issues
when dealing with large numbers of projects.


## When should I **not** use Py-QGIS-Services

* If you need a simple server with for serving a handfull of projects and you don't need
  to scale to hundreds or thousands of server instances or complex routing rules and 
  project's cache management, then you  probably don't need to use Py-Qgis-Services.

* If you don't have some experience in infrastructure management and administration with
  Docker or other containerization framework, then you probably shouldn't use 
  Py-Qgis-Services.

Instead, you should go along with the *qgis-mapserver* fcgi server provided with the 
QGIS distributions which do a great job in many situations.


### Features

- Qgis server as microservice over gRPC protocol
- SSL support
- Enhanced scalability support
- Hot (re)configuration from remote or local config
- REST admin api 
- Managed project's cache synchronized between workers.
- S3 storage supports for projects


### Requirements and limitations

- Python 3.10+
- Qgis 3.34+
- Linux platform or Posix compliant platform

If you plan to use the processing services then the following extra services are
required:

- [Redis](https://redis.io/) version 6+.
- [RabbitMQ](https://www.rabbitmq.com/) version 3+


Note that no direct support for Windows or OSX are *not* planned as we do not use these platforms
for deployment. 
So if it appears not to work on these platforms, consider using VM or containers.



# Qgis server as a service

## Description

This is as set of services for deploying Qgis server(s)

- Qgis server's as microservice over gRPC protocol
- Managed project's cache that may be synchronized between workers from the same pool.
- SSL support between all components
- Hot scaling with Docker stack
- Hot (re)configuration from remote or local config

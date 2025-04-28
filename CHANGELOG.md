# Changelog

<!--
All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).
-->

## Unreleased

### Added 

* [docker] Define `QGIS_SERVER_CACHE_DIRECTORY` in entrypoint
* [server] Add option for disabling catalog listing
* [server] Allow passing location prefix in catalog 
* Implement dynamic paths for cache manager search paths
* Add OCI annotations in docker images

### Fixed

* [rpc] Fix configuration patching
* [rpc] Fix undefined checkout status on cache manager exception
* [rpc] Be consistent in get/set config command
* Prevent concurrent access to QGIS profile data in QGIS initialization
* Fix configuration issues
* Fix catalog update logic
* [rpc] Fix configuration update not applied on worker on first time

## 0.1.0 - 2025-04-11

### Added

* First release




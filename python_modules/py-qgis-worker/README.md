# Qgis server as gRPC service

Implements a Qgis server gRPC service

## Features

* Asynchronous
* Multiple Qgis server processes
* Full Cache control api

## Run

```
python -m py_qgis_worker serve [--conf FILE] [--num-processes n]
```

Run `n` concurrent Qgis processes. 

The gRCP api execute asynchronously a fair-queuing dispatch 
of messages to the Qgis processes.


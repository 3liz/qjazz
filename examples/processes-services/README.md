# Processes services

Run a *Processes* server service with a QGIS Processing service

## Running the example

Start the service stack: `docker compose up -d`

Execute the a jobs by sending an *OGC Processes* execution request 
to the processes server:

```sh
curl -v -X POST \
   http://localhost:9180/processes/processes_test:testcopylayer/execution?map=france/france_parts \
   -d '{ "inputs": { "INPUT": "france_parts", "OUTPUT": "france_parts2" }}' 
```

The response should be something like:

```json
{
  "OUTPUT": {
    "type": "application/x-ogc-wms+xml",
    "title": "Output",
    "description": "Output Layer",
    "templated": false,
    "href":"ows://57eef467-4005-4e43-b50e-d5037be88ac3/processes_test_testcopylayer&SERVICE=WMS&REQUEST=GetCapabilities&LAYERS=france_parts2"
  }
}
```



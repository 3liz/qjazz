# Processes services with map server

This is an example of Qjazz services working together: the Qjazz 
processes services executes processing jobs and store results locally

Because of the adverised url configuration, references  returned in the processing results
target the OWS services exposed by the Qjazz map service. 

The Qjazz map server allow requesting services on job results.

This examples run the following services:

* Qjazz map frontend http server
* Qjazz QGIS rpc service (QGIS server pool)
* Qjazz processes server
* Qjazz processing service
* RabbitMQ (Celery)
* Redis (Celery)

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
    "href":"http://localhost:9080/results/?MAP=57eef467-4005-4e43-b50e-d5037be88ac3/processes_test_testcopylayer&SERVICE=WMS&REQUEST=GetCapabilities&LAYERS=france_parts2"
  }
}
```

Go to: http://localhost:9080/catalogs and navigate to the results using the *OGC Map* api

Request an *OWS GetMap GetCapabilities* from the reference in the returned result of the *Processes*
request.


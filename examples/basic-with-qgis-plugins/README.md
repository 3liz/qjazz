# Basic docker compose 

This example install the lizmap plugin and defines two apis endpoint:

* `/lizmap` endpoint 
* `/features` endpont which is a mapping to the QGIS wfs3 api

run:

```
docker compose up
```

Then go to:

* http://localhost:9080/lizmap/server.json
* http://localhost:9080/features?map=france_parts



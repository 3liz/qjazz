#!/bin/bash

if [[ "$1" == "stop" ]]; then
    docker stop swagger
else
    docker run -p 9875:8080 -d --rm --name swagger \
        -e SWAGGER_JSON=/doc/specs/openapi-managment.json \
        -v $(pwd)/doc:/doc \
        swaggerapi/swagger-ui 

    sleep 1
    python3 -m webbrowser -t "http://localhost:9875"
    echo "Pour arrêter le serveur swagger, exécuter './swagger.sh stop'"
fi

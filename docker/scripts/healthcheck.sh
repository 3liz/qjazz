#!/bin/bash
#
# Healtcheck script for rpc and map server
#

if [ -f /tmp/.qjazz-rpc-running ]; then
    # QJazz RPC is running
    qjazz-rpc-client ping
elif [ -f /tmp/.qjazz-map-running ]; then
    # QJazz map server is running 
    [ `curl -I -A "Healtcheck" -o /dev/null -s -w '%{http_code}' 'http://localhost:9080/'` == 200 ]
else
    # Nothing running, not ready yet
    exit 1
fi

#!/bin/bash

set -eu

# Installing plugins
if [ -n ${QJAZZ_CONFIG_FILE:-""} ]; then
    INSTALL_ARGS="-C $QJAZZ_CONFIG_FILE"
elif [ -f /etc/qjazz/config.toml ]; then
    INSTALL_ARGS="-C /etc/qjazz/config.toml"
else
    INSTALL_ARGS=
fi
 
qjazz-config install-plugins $INSTALL_ARGS

read conf_patch <<EOF
{ "worker": { "qgis": { "plugins": { "install": $CONF_WORKER__QGIS__PLUGINS__INSTALL }}}}
EOF

# Update configuration
echo "Patching configuration"
qjazz-rpc-client config set "$conf_patch"

# Reload workers
echo "Reloading QGIS workers"
qjazz-rpc-client reload

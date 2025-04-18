#!/bin/bash

set -e

# Qgis need a HOME
export HOME=/home/qgis
export QGIS_HOME=$HOME

#
# Copy Qgis configuration into the container so that
# multiple instances don't mess with the same config
#
copy_qgis_configuration() {
    mkdir -p $HOME/profiles/default
    QGIS_CUSTOM_CONFIG_PATH=${QGIS_CUSTOM_CONFIG_PATH:-$QGIS_OPTIONS_PATH}
    if [[ -n $QGIS_CUSTOM_CONFIG_PATH ]]; then
        echo "Copying Qgis configuration: $QGIS_CUSTOM_CONFIG_PATH"
        # Create config path as default profiles
        cp -RL $QGIS_CUSTOM_CONFIG_PATH/* $HOME/profiles/default/
    fi
    # Qgis initialization rely on this
    export QGIS_CUSTOM_CONFIG_PATH=$HOME
    export QGIS_OPTIONS_PATH=$HOME

    # Create plugin dir
    export QGIS_PLUGINPATH=$QJAZZ_VOLUME/plugins
    mkdir -p $QGIS_PLUGINPATH
}

#
# Set QGIS cache directory
#
create_qgis_cache_directory() {
    mkdir -p $QJAZZ_VOLUME/cache
    export QGIS_SERVER_CACHE_DIRECTORY=$QJAZZ_VOLUME/cache
}

# Check for uid (running with --user)
if [[ "$UID" != "0" ]]; then 
    CONF_USER=$UID:$(id -g)
else    
    CONF_USER=${CONF_USER:-"1001:1001"}
fi

if [[ "$CONF_USER" =~ ^root:? ]] || [[ "$CONF_USER" =~ ^0:? ]]; then
    echo "CONF_USER must no be root !"
    exit 1 
fi

if [ "$(id -u)" = '0' ]; then
    # Delete any actual Xvfb lock file
    # Because it can only be removed as root
    rm -rf /tmp/.X99-lock

    if [[ "$(stat -c '%u' $HOME)" == "0" ]] ; then
        chown $CONF_USER $HOME
        chmod 750 $HOME
    fi
 
    if [[ "$(stat -c '%u' $QJAZZ_VOLUME)" == "0" ]] ; then
        chown $CONF_USER $QJAZZ_VOLUME
        chmod 750 $QJAZZ_VOLUME
    fi
    
    REUID=`echo $CONF_USER|cut -d: -f1`
    REGID=`echo $CONF_USER|cut -d: -f2` 
    exec setpriv --clear-groups --reuid=$REUID --regid=$REGID "$BASH_SOURCE" "$@"
fi


if [[ "$(id -g)" == "0" ]]; then
    echo "SECURITY WARNING: running as group 'root'"
fi

# Check if HOME is available
if [[ ! -d $HOME ]]; then
    echo "ERROR: Qgis require a HOME directory (default to $HOME)"
    echo "ERROR: You must mount the corresponding volume directory"
    exit 1
fi
# Check if HOME is writable
if [[ ! -w $HOME ]]; then
    echo "ERROR: $HOME must be writable for user:group $CONF_USER"
    echo "ERROR: You should consider the '--user' Docker option"
    exit 1
fi

CONF_DISPLAY_XVFB=${CONF_DISPLAY_XVFB:-OFF}
#
# Set up xvfb
# https://www.x.org/archive/X11R7.6/doc/man/man1/Xvfb.1.xhtml
# see https://www.x.org/archive/X11R7.6/doc/man/man1/Xserver.1.xhtml
#
if [[ "$CONF_DISPLAY_XVFB" == "ON" ]]; then
 if [ -f /tmp/.X99-lock ]; then
     echo "ERROR: An existing lock file will prevent Xvfb to start"
     echo "If you expect restarting the container with '--user' option"
     echo "consider mounting /tmp with option '--tmpfs /tmp'"
     exit 1
 fi

 XVFB_DEFAULT_ARGS="-screen 0 1024x768x24 -ac +extension GLX +render -noreset"
 XVFB_ARGS=${CONF_XVFB_ARGS:-":99 $XVFB_DEFAULT_ARGS"}

 # RUN Xvfb in the background
 echo "Running Xvfb"
 nohup /usr/bin/Xvfb $XVFB_ARGS >/tmp/xvfb.log 2>&1 &
 export DISPLAY=":99"
fi

copy_qgis_configuration
create_qgis_cache_directory

exec $@


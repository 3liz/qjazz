 # syntax=docker/dockerfile:1
 # vim: ft=dockerfile
 ARG REGISTRY_PREFIX=''
 ARG QGIS_VERSION=release

#
# Qgis platform
# 

FROM  ${REGISTRY_PREFIX}qgis-platform:${QGIS_VERSION} AS base
LABEL Description="QGIS py-qgis services" Vendor="3liz.org"
LABEL org.opencontainers.image.authors="David Marteau <david.marteau@3liz.com>"

RUN apt-get update -y \
    && export DEBIAN_FRONTEND=noninteractive \
    && apt-get install -y --fix-missing --no-install-recommends \
        bash-completion \
        jq \
        less \
        ${NULL}

COPY python_modules docker/requirements.txt /python_modules

# Create virtualenv for installing modules
RUN mkdir -p /opt/local/ \
    && python3 -m venv --system-site-packages /opt/local/qgisserver \
    && cd /usr/local/bin \
    && /opt/local/qgisserver/bin/pip install -U --no-cache-dir pip setuptools wheel \
    && /opt/local/qgisserver/bin/pip install --no-cache-dir -r /python_modules/requirements.txt \
    && /opt/local/qgisserver/bin/pip install --no-cache-dir --no-deps \
        -e /python_modules/py-qgis-contrib \
        -e /python_modules/py-qgis-cache \
        -e /python_modules/py-qgis-server \
        -e /python_modules/py-qgis-processes \
        -e /python_modules/py-qgis-scripts \
    && ln -s /opt/local/qgisserver/bin/qgis-server-rpc \
    && ln -s /opt/local/qgisserver/bin/qgis-server-admin \
    && ln -s /opt/local/qgisserver/bin/qgis-server-http \
    && ln -s /opt/local/qgisserver/bin/qgis-server-cli \
    && ln -s /opt/local/qgisserver/bin/qgis-processes \
    ${NULL}

# Install qgis-plugin-manager
# Note: hit by https://github.com/pypa/setuptools/issues/4501
# because packaging is installed system wide
RUN mkdir -p /opt/local/ \
    && python3 -m venv --system-site-packages /opt/local/plugin-manager \
    && cd /usr/local/bin \
    && /opt/local/plugin-manager/bin/pip install -U --upgrade-strategy=eager \
        --no-cache-dir pip setuptools wheel packaging \
    && /opt/local/plugin-manager/bin/pip install -U --upgrade-strategy=eager \
         --no-cache-dir qgis-plugin-manager \
    && cd /usr/local/bin && ln -s /opt/local/plugin-manager/bin/qgis-plugin-manager

COPY docker/scripts/ /usr/local/bin/
RUN chmod 0755 /usr/local/bin/qgis-docker-entrypoint.sh && mkdir -p /home/qgis && chmod 777 /home/qgis

# Set uid root on Xvfb
# Allow us to run Xvfb when the container runs with '-u' option
RUN chmod u+s /usr/bin/Xvfb

EXPOSE 23456 9080 9443 9876

ENTRYPOINT ["/usr/local/bin/qgis-docker-entrypoint.sh"]

CMD ["/usr/bin/bash","--rcfile","/usr/local/bin/bashrc","-i"]

# =========
# CI build
# =========
FROM base AS ci_build

ARG PIP_OPTIONS

RUN /opt/local/qgisserver/bin/pip install --no-cache-dir $PIP_OPTIONS \
    "py-amqp-client>=2.0.0"

#
# Server only installation (no-qgis)
#

FROM ubuntu:24.04 AS front

RUN apt-get update -y \
    && export DEBIAN_FRONTEND=noninteractive \
    && apt-get install -y --fix-missing --no-install-recommends \
        python3-venv \
        python3-psutil \
        iputils-ping \
        bash-completion \
        jq \
        less \
        ${NULL}

COPY --from=base /python_modules /python_modules
COPY --from=base /opt/local/qgisserver /opt/local/qgisserver

RUN cd /usr/local/bin \
    && ln -s /opt/local/qgisserver/bin/qgis-server-admin \
    && ln -s /opt/local/qgisserver/bin/qgis-server-http \
    && ln -s /opt/local/qgisserver/bin/qgis-server-cli \
    && ln -s /opt/local/qgisserver/bin/qgis-processes \
    ${NULL}

COPY docker/scripts/ /usr/local/bin/

EXPOSE 9443 9080 9876

CMD ["/usr/bin/bash","--rcfile","/usr/local/bin/bashrc","-i"]

# ===================
# Front amqp supports
# ===================
FROM front AS ci_front

ARG PIP_OPTIONS

RUN /opt/local/qgisserver/bin/pip install --no-cache-dir $PIP_OPTIONS \
    "py-amqp-client>=2.0.0"



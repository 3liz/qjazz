 # syntax=docker/dockerfile:1
 # vim: ft=dockerfile
 ARG REGISTRY_PREFIX=''
 ARG QGIS_VERSION=release

FROM  ${REGISTRY_PREFIX}qgis-platform:${QGIS_VERSION} as base
MAINTAINER David Marteau <david.marteau@3liz.com>
LABEL Description="QGIS gRCP" Vendor="3liz.org"

RUN apt-get update -y \
    && export DEBIAN_FRONTEND=noninteractive \
    && apt-get install -y --fix-missing --no-install-recommends \
        bash-completion \
        jq \
        less \
        ${NULL}

ARG CACHEBUST="23.11.08"

COPY python_modules /python_modules

# Create virtualenv for installing modules
RUN mkdir -p /opt/local/ \
    && python3 -m venv --system-site-packages /opt/local/qgisserver \
    && cd /usr/local/bin \
    && /opt/local/qgisserver/bin/pip install -U --no-cache-dir pip setuptools wheel \
    && /opt/local/qgisserver/bin/pip install --no-cache-dir \
        -e /python_modules/py-qgis-contrib \
        -e /python_modules/py-qgis-cache \
        -e /python_modules/py-qgis-worker \
        -e /python_modules/py-qgis-admin \
        -e /python_modules/py-qgis-scripts \
        -e /python_modules/py-qgis-http \
        -e /python_modules/py-qgis-html \
    && ln -s /opt/local/qgisserver/bin/qgis-server-rpc \
    && ln -s /opt/local/qgisserver/bin/qgis-server-admin \
    && ln -s /opt/local/qgisserver/bin/qgis-server-http \
    && ln -s /opt/local/qgisserver/bin/qgis-server-cli

COPY docker/scripts/ /usr/local/bin/
RUN chmod 0755 /usr/local/bin/docker-entrypoint.sh && mkdir -p /home/qgis && chmod 777 /home/qgis

# Set uid root on Xvfb
# Allow us to run Xvfb when the container runs with '-u' option
RUN chmod u+s /usr/bin/Xvfb

EXPOSE 23456 80 9876

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

CMD ["/usr/bin/bash","--rcfile","/usr/local/bin/bashrc","-i"]

# =========
# CI build
# =========
FROM base as ci_build

ARG PIP_OPTIONS

RUN /opt/local/qgisserver/bin/pip install --no-cache-dir $PIP_OPTIONS \
    "py-amqp-client>=2.0.0" \
    && /opt/local/qgisserver/bin/pip install --no-cache-dir \
        -e /python_modules/py-qgis-metrics


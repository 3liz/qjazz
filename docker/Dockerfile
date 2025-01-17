# syntax=docker/dockerfile:1
# vim: ft=dockerfile
ARG REGISTRY_PREFIX=''
ARG QGIS_VERSION=release

#
# Qgis platform
# 

FROM  ${REGISTRY_PREFIX}qgis-platform:${QGIS_VERSION} AS base
LABEL Description="QJazz QGIS services" Vendor="3liz.org"
LABEL org.opencontainers.image.authors="David Marteau <david.marteau@3liz.com>"

RUN apt-get update -y \
    && export DEBIAN_FRONTEND=noninteractive \
    && apt-get install -y --fix-missing --no-install-recommends \
        bash-completion \
        jq \
        less \
        ${NULL}

COPY docker/requirements.txt /python_modules/
COPY qjazz-contrib /python_modules/qjazz-contrib
COPY qjazz-processes /python_modules/qjazz-processes
COPY qjazz-server/python /python_modules/qjazz-server/

# Create virtualenv for installing modules
RUN mkdir -p /opt/local/ \
    && python3 -m venv --system-site-packages /opt/local/qjazz \
    && cd /usr/local/bin \
    && /opt/local/qjazz/bin/pip install -U --no-cache-dir pip setuptools wheel requests \
    && /opt/local/qjazz/bin/pip install --no-cache-dir -r /python_modules/requirements.txt \
    && /opt/local/qjazz/bin/pip install --no-cache-dir --no-deps \
        -e /python_modules/qjazz-contrib \
        -e /python_modules/qjazz-processes \
        -e /python_modules/qjazz-server \
    && ln -s /opt/local/qjazz/bin/qjazz-server-admin \
    && ln -s /opt/local/qjazz/bin/qjazz-server-http \
    && ln -s /opt/local/qjazz/bin/qjazz-processes \
    && ln -s /opt/local/qjazz/bin/qjazz-printserver \
    && ln -s /opt/local/qjazz/bin/qjazz-config \
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

# Install binaries
COPY qjazz-server/target/release/qjazz-rpc /usr/local/bin/qjazz-rpc-bin

# Set path to the python executable
ENV PYTHON_EXEC=/opt/local/qjazz/bin/python

# Set uid root on Xvfb
# Allow us to run Xvfb when the container runs with '-u' option
RUN chmod u+s /usr/bin/Xvfb

ENV CONF_SERVER__LISTEN__ADDRESS='[::]:23456'
ENV CONF_HTTP__LISTEN='["0.0.0.0", 9080]'
ENV CONF_ADMIN_HTTP__LISTEN='["0.0.0.0", 9876]'

EXPOSE 23456 9080 9443 9876

ENTRYPOINT ["/usr/local/bin/qgis-docker-entrypoint.sh"]

VOLUME /home/qgis

CMD ["/usr/bin/bash","--rcfile","/usr/local/bin/bashrc","-i"]

# =========
# CI build
# =========
FROM base AS ci_build

ARG PIP_OPTIONS

RUN /opt/local/qjazz/bin/pip install --no-cache-dir $PIP_OPTIONS \
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
COPY --from=base /opt/local/qjazz /opt/local/qjazz

RUN cd /usr/local/bin \
    && ln -s /opt/local/qjazz/bin/qjazz-server-admin \
    && ln -s /opt/local/qjazz/bin/qjazz-server-http \
    && ln -s /opt/local/qjazz/bin/qjazz-processes \
    ${NULL}

COPY docker/scripts/ /usr/local/bin/

ENV CONF_HTTP__LISTEN='["0.0.0.0", 9080]'
ENV CONF_ADMIN_HTTP__LISTEN='["0.0.0.0", 9876]'

EXPOSE 9443 9080 9876

CMD ["/usr/bin/bash","--rcfile","/usr/local/bin/bashrc","-i"]

# ===================
# Front amqp supports
# ===================
FROM front AS ci_front

ARG PIP_OPTIONS

RUN /opt/local/qjazz/bin/pip install --no-cache-dir $PIP_OPTIONS \
    "py-amqp-client>=2.0.0"



# syntax=docker/dockerfile:1
# vim: ft=dockerfile
ARG REGISTRY_PREFIX=''
ARG QGIS_FLAVOR=release

FROM  ${REGISTRY_PREFIX}qgis-platform:${QGIS_FLAVOR} AS build

RUN apt-get update -y \
    && export DEBIAN_FRONTEND=noninteractive \
    && apt-get install -y --no-install-recommends \
        curl

#Instal uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && cd /usr/local/bin \
    && ln -s $HOME/.local/bin/uv \
    && uv --version \
    && mkdir -p /opt/local

# Install qjazz in virtualenv
RUN --mount=type=bind,target=/src,rw \
    --mount=type=cache,target=/.python-cache \
    uv venv --system-site-packages /opt/local/qjazz \
    && uv pip install --python=/opt/local/qjazz/bin/python --compile-bytecode \
        --cache-dir=/.python-cache --link-mode=copy pip \
    && uv pip install --python=/opt/local/qjazz/bin/python --compile-bytecode \
        --cache-dir=/.python-cache --link-mode=copy \
        -r /src/requirements.txt \
    && uv pip install --python=/opt/local/qjazz/bin/python \
        --cache-dir=/.python-cache --no-deps --compile-bytecode \
        /src/qjazz-contrib \
        /src/qjazz-processes \
        /src/qjazz-server/python \
    && uv pip install --python=/opt/local/qjazz/bin/python \
        --cache-dir=/.python-cache --compile-bytecode \
        qgis-plugin-manager

# ==============
# QJazz platform
# ==============
FROM  ${REGISTRY_PREFIX}qgis-platform:${QGIS_FLAVOR} AS base
LABEL org.opencontainers.image.vendor="3liz"
LABEL org.opencontainers.image.title="Qjazz"
LABEL org.opencontainers.image.description="QJazz, QGIS as services."
LABEL org.opencontainers.image.authors="David Marteau <david.marteau@3liz.com>"
LABEL org.opencontainers.image.source="https://github.com/3liz/qjazz"
LABEL org.opencontainers.image.ref.name="3liz/qjazz"

RUN apt-get update -y \
    && export DEBIAN_FRONTEND=noninteractive \
    && apt-get install -y --fix-missing --no-install-recommends \
        bash-completion \
        jq \
        less \
    && apt-get clean

COPY --from=build /opt/local/qjazz /opt/local/qjazz

RUN cd /usr/local/bin \
    && ln -s /opt/local/qjazz/bin/qjazz-processes \
    && ln -s /opt/local/qjazz/bin/qjazz-processing \
    && ln -s /opt/local/qjazz/bin/qgis-plugin-manager \
    ${NULL}

COPY docker/scripts/ /usr/local/bin/
RUN chmod 0755 /usr/local/bin/qgis-docker-entrypoint.sh \
    && mkdir -p /home/qgis && chmod 777 /home/qgis \
    && mkdir -p /var/qjazz && chmod 777 /var/qjazz \
    && mkdir -p /etc/qjazz && chmod 755 /etc/qjazz 

# Install binaries
COPY qjazz-server/target/release/qjazz-rpc-bin \
     qjazz-server/target/release/qjazz-map-bin \
    /usr/local/bin/

# Set path to the python executable
ENV PYTHON_EXEC=/opt/local/qjazz/bin/python

# Set uid root on Xvfb
# Allow us to run Xvfb when the container runs with '-u' option
RUN chmod u+s /usr/bin/Xvfb

ENV CONF_HTTP__LISTEN='["0.0.0.0", 9080]'

EXPOSE 23456 9080 9443

ENTRYPOINT ["/usr/local/bin/qgis-docker-entrypoint.sh"]

VOLUME /home/qgis
VOLUME /var/qjazz

ENV QJAZZ_VOLUME=/var/qjazz
ENV PATH=/opt/local/qjazz/bin:$PATH

# Define here so that commands run with `docker exec`
# may access the variable
ENV QGIS_PLUGINPATH=/var/qjazz/plugins

CMD ["/usr/bin/bash","--rcfile","/usr/local/bin/bashrc","-i"]

# ================
# Lizcloud support 
# ================
FROM base AS lizcloud

ARG PIP_OPTIONS

RUN /opt/local/qjazz/bin/pip install --no-cache-dir $PIP_OPTIONS "qjazz-lizcloud"

# ==================================
# Server only installation (no-qgis)
# ==================================
FROM ubuntu:24.04 AS noqgis
LABEL org.opencontainers.image.vendor="3liz"
LABEL org.opencontainers.image.title="Qjazz"
LABEL org.opencontainers.image.description="QJazz, QGIS as services."
LABEL org.opencontainers.image.authors="David Marteau <david.marteau@3liz.com>"
LABEL org.opencontainers.image.source="https://github.com/3liz/qjazz"
LABEL org.opencontainers.image.ref.name="3liz/qjazz"

RUN apt-get update -y \
    && export DEBIAN_FRONTEND=noninteractive \
    && apt-get install -y --fix-missing --no-install-recommends \
        python3-psutil \
        iputils-ping \
        bash-completion \
        jq \
        less \
    && apt-get clean

COPY --from=build /opt/local/qjazz /opt/local/qjazz

RUN cd /usr/local/bin \
    && ln -s /opt/local/qjazz/bin/qjazz-processes \
    ${NULL}

# Install binaries
COPY qjazz-server/target/release/qjazz-map-bin /usr/local/bin/

RUN mkdir -p /etc/qjazz && chmod 755 /etc/qjazz

COPY docker/scripts/ /usr/local/bin/

ENV CONF_HTTP__LISTEN='["0.0.0.0", 9080]'
ENV CONF_ADMIN_HTTP__LISTEN='["0.0.0.0", 9876]'

EXPOSE 9443 9080 9876

CMD ["/usr/bin/bash","--rcfile","/usr/local/bin/bashrc","-i"]

# =======================
# NoQGIS Lizcloud support 
# =======================
FROM noqgis AS noqgis-lizcloud

ARG PIP_OPTIONS

RUN /opt/local/qjazz/bin/pip install --no-cache-dir $PIP_OPTIONS "qjazz-lizcloud"


# ==================================
# CI dev environment
#
# Build an image usable as CI image for 
# testing qjazz based services 
# ==================================
FROM  ${REGISTRY_PREFIX}factory-ci-runner:qgis-${QGIS_FLAVOR} AS ci

# Install the dev environment
RUN --mount=type=bind,target=/src,rw \
    cd src && uv sync --all-extras --frozen --active \
        --no-cache \
        --link-mode=copy \
        --no-editable \
        --compile-bytecode

# Does not exists but could prevent errors
ENV QJAZZ_HOME=/python_modules
ENV PATH=/opt/local/qjazz/bin:$PATH
    



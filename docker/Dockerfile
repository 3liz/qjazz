# syntax=docker/dockerfile:1
# vim: ft=dockerfile
ARG REGISTRY_PREFIX=''
ARG QGIS_FLAVOR=ltr

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
    export UV_PROJECT_ENVIRONMENT=/opt/local/qjazz UV_LINK_MODE=copy \
    && uv venv --system-site-packages /opt/local/qjazz \
    && export UV_PYTHON=$UV_PROJECT_ENVIRONMENT/bin/python \
    && uv pip install --compile-bytecode --cache-dir=/.python-cache \
        -r /src/requirements.txt \
    && uv pip install --no-deps --cache-dir=/.python-cache --compile-bytecode \
        `ls -1 /src/dist/qjazz_contrib-*.whl` \
        `ls -1 /src/dist/qjazz_map-*.whl` \
        `ls -1 /src/dist/qjazz_rpc-*.whl` \
        `ls -1 /src/dist/qjazz_processes-*.whl` \
    && uv pip install --no-deps --cache-dir=/.python-cache --compile-bytecode \
        qgis-plugin-manager


ARG LIZCLOUD=''

# Install lizcloud support
RUN --mount=type=bind,target=/src,rw \
    --mount=type=cache,target=/.python-cache \
    if [ "$LIZCLOUD" = "yes" ]; then \
        uv pip install --extra-index-url=https://packages.3liz.org/pub/whl/ \
        --python=/opt/local/qjazz/bin/python \
        --cache-dir=/.python-cache --compile-bytecode \
        --link-mode=copy \
        qjazz-lizcloud; \
    fi

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
        curl \
    && apt-get clean

COPY --from=build /opt/local/qjazz /opt/local/qjazz

RUN cd /usr/local/bin \
    && ln -s /opt/local/qjazz/bin/qjazz-rpc-bin \
    && ln -s /opt/local/qjazz/bin/qjazz-map-bin \
    && ln -s /opt/local/qjazz/bin/qjazz-processes \
    && ln -s /opt/local/qjazz/bin/qjazz-processing \
    && ln -s /opt/local/qjazz/bin/qgis-plugin-manager \
    ${NULL}

COPY docker/scripts/ /usr/local/bin/
RUN chmod 0755 /usr/local/bin/qgis-docker-entrypoint.sh \
    && mkdir -p /home/qgis && chmod 777 /home/qgis \
    && mkdir -p /var/qjazz && chmod 777 /var/qjazz \
    && mkdir -p /etc/qjazz && chmod 755 /etc/qjazz 

# Set path to the python executable
ENV PYTHON_EXEC=/opt/local/qjazz/bin/python

# Set uid root on Xvfb
# Allow us to run Xvfb when the container runs with '-u' option
RUN chmod u+s /usr/bin/Xvfb

ENV CONF_HTTP__LISTEN='["0.0.0.0", 9080]'

EXPOSE 23456 9080 9443

ENTRYPOINT ["/usr/local/bin/qgis-docker-entrypoint.sh"]

HEALTHCHECK --interval=30s --timeout=30s --start-interval=5s --start-period=30s \
    CMD /usr/local/bin/healthcheck.sh

# Create qgis user
RUN set -eux; useradd qgis --home-dir=/home/qgis;

USER qgis

VOLUME /home/qgis
VOLUME /var/qjazz

ENV HOME=/home/qgis
ENV QJAZZ_VOLUME=/var/qjazz
ENV PATH=/opt/local/qjazz/bin:$PATH

# Define here so that commands run with `docker exec`
# may access the variable
ENV QGIS_PLUGINPATH=/var/qjazz/plugins

CMD ["/usr/bin/bash","--rcfile","/usr/local/bin/bashrc","-i"]

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
        curl \
    && apt-get clean

COPY --from=build /opt/local/qjazz /opt/local/qjazz

RUN cd /usr/local/bin \
    && ln -s /opt/local/qjazz/bin/qjazz-processes \
    ${NULL}

RUN cd /usr/local/bin && ln -s /opt/local/qjazz/bin/qjazz-map-bin 
 
RUN mkdir -p /etc/qjazz && chmod 755 /etc/qjazz

COPY docker/scripts/ /usr/local/bin/

ENV CONF_HTTP__LISTEN='["0.0.0.0", 9080]'
ENV CONF_ADMIN_HTTP__LISTEN='["0.0.0.0", 9876]'

EXPOSE 9443 9080 9876

HEALTHCHECK --interval=30s --timeout=30s --start-interval=5s --start-period=30s \
    CMD /usr/local/bin/healthcheck.sh

# Create qgis user
RUN set -eux; useradd -M qgis; 

USER qgis

CMD ["/usr/bin/bash","--rcfile","/usr/local/bin/bashrc","-i"]

# ==================================
# CI dev environment
#
# Build an image usable as CI image for 
# testing qjazz based services 
# ==================================
FROM  ${REGISTRY_PREFIX}factory-ci-runner:qgis-${QGIS_FLAVOR} AS ci

# Install the dev environment
RUN --mount=type=bind,target=/src,rw \
    uv pip install --compile-bytecode --no-cache \
        -r /src/requirements.txt \
        -r /src/requirements/dev.txt \
    && uv pip install --no-deps --compile-bytecode \
        -e /src/qjazz-contrib \
        -e /src/qjazz-processes 

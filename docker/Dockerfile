# syntax=docker/dockerfile:1
# vim: ft=dockerfile
ARG REGISTRY_PREFIX=''
ARG QGIS_FLAVOR=release

#
# Qgis platform
# 

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

COPY docker/requirements.txt /python_modules/
COPY qjazz-contrib /python_modules/qjazz-contrib
COPY qjazz-processes /python_modules/qjazz-processes
COPY qjazz-server/python /python_modules/qjazz-server/

# Create virtualenv for installing modules
RUN --mount=type=cache,target=/.python-cache \
    mkdir -p /opt/local/ \
    && python3 -m venv --system-site-packages /opt/local/qjazz \
    && cd /usr/local/bin \
    && /opt/local/qjazz/bin/pip install -U --cache-dir=/.python-cache \
        pip setuptools wheel requests \
    && /opt/local/qjazz/bin/pip install --cache-dir=/.python-cache -r /python_modules/requirements.txt \
    && export QJAZZ_NO_BUILD_EXT_INSTALL=1 \
    && /opt/local/qjazz/bin/pip install --cache-dir=/.python-cache --no-deps \
        -e /python_modules/qjazz-contrib \
        -e /python_modules/qjazz-processes \
        -e /python_modules/qjazz-server \
    && ln -s /opt/local/qjazz/bin/qjazz-server-admin \
    && ln -s /opt/local/qjazz/bin/qjazz-processes \
    && ln -s /opt/local/qjazz/bin/qjazz-processing \
    && ln -s /opt/local/qjazz/bin/qjazz-config \
    && ln -s /opt/local/qjazz/bin/qjazz-rpc-client \
    && rm -r /python_modules/**/*.egg-info \
    ${NULL}

# Install qgis-plugin-manager
# Note: hit by https://github.com/pypa/setuptools/issues/4501
# because packaging is installed system wide
RUN --mount=type=cache,target=/.python-cache mkdir -p /opt/local/ \
    && python3 -m venv --system-site-packages /opt/local/plugin-manager \
    && cd /usr/local/bin \
    && /opt/local/plugin-manager/bin/pip install -U --upgrade-strategy=eager \
        --cache-dir=/.python-cache pip setuptools wheel packaging \
    && /opt/local/plugin-manager/bin/pip install -U --upgrade-strategy=eager \
        --cache-dir=/.python-cache qgis-plugin-manager \
    && cd /usr/local/bin && ln -s /opt/local/plugin-manager/bin/qgis-plugin-manager

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

# Define here so that commands run with `docker exec`
# may access the variable
ENV QGIS_PLUGINPATH=/var/qjazz/plugins

CMD ["/usr/bin/bash","--rcfile","/usr/local/bin/bashrc","-i"]


#
# Server only installation (no-qgis)
#

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
        python3-venv \
        python3-psutil \
        iputils-ping \
        bash-completion \
        jq \
        less \
    && apt-get clean

COPY --from=base /python_modules /python_modules
COPY --from=base /opt/local/qjazz /opt/local/qjazz
COPY --from=base /usr/local/bin/qjazz-map-bin /usr/local/bin/qjazz-map-bin

RUN cd /usr/local/bin \
    && ln -s /opt/local/qjazz/bin/qjazz-server-admin \
    && ln -s /opt/local/qjazz/bin/qjazz-server-http \
    && ln -s /opt/local/qjazz/bin/qjazz-processes \
    && mkdir -p /etc/qjazz && chmod 755 /etc/qjazz \
    ${NULL}

COPY docker/scripts/ /usr/local/bin/

ENV CONF_HTTP__LISTEN='["0.0.0.0", 9080]'
ENV CONF_ADMIN_HTTP__LISTEN='["0.0.0.0", 9876]'

EXPOSE 9443 9080 9876

CMD ["/usr/bin/bash","--rcfile","/usr/local/bin/bashrc","-i"]

#
# CI dev environment
#
# Build an image usable as CI image for 
# testing qjazz based services 
#
FROM  ${REGISTRY_PREFIX}qgis-platform:${QGIS_FLAVOR} AS ci

RUN apt-get update -y \
    && export DEBIAN_FRONTEND=noninteractive \
    && apt-get install -y --fix-missing --no-install-recommends \
        git \
        make \
    && apt-get clean

# XXX See values in ansible
ARG factory_runner_uid=2024
ARG factory_gid=2011
ARG operator_uid=2001

# Create runner user
RUN useradd --uid=${factory_runner_uid} --home-dir=/home/factory-runner factory-runner \
    && groupadd -g ${factory_gid} factory \
    && groupadd -g ${operator_uid} devel \
    && /usr/sbin/usermod -a -G factory,devel factory-runner \
    && mkdir -p /home/factory-runner \
    && chown -R factory-runner:factory-runner /home/factory-runner \
    ${NULL}

COPY --from=base --chown=factory-runner:factory-runner /python_modules /python_modules
COPY --from=base --chown=factory-runner:factory-runner /opt/local/qjazz /opt/local/qjazz

USER factory-runner 

COPY dev-requirements.txt /dev-requirements.txt
RUN --mount=type=cache,target=/.python-cache \
    /opt/local/qjazz/bin/pip install --cache-dir=/.python-cache -r /dev-requirements.txt

ENV QJAZZ_HOME=/python_modules
ENV PATH=/opt/local/qjazz/bin:$PATH
    



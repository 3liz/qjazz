 # syntax=docker/dockerfile:1
 # vim: ft=dockerfile
 ARG REGISTRY_PREFIX=''
 ARG QGIS_VERSION=release

FROM  ${REGISTRY_PREFIX}qgis-platform:${QGIS_VERSION}
MAINTAINER David Marteau <david.marteau@3liz.com>
LABEL Description="QGIS gRCP" Vendor="3liz.org"

ARG CACHEBUST="23.09.2"

COPY python_modules /python_modules

# Create virtualenv for installing modules
RUN mkdir -p /opt/local/ \
    && python3 -m venv --system-site-packages /opt/local/qgisserver \
    && cd /usr/local/bin \
    && /opt/local/qgisserver/bin/pip install -U --no-cache-dir pip setuptools wheel \
    && /opt/local/qgisserver/bin/pip install --no-cache-dir \
        -e /python_modules/py-qgis-contrib \
        -e /python_modules/py-qgis-project-cache \
        -e /python_modules/py-qgis-worker \
        -e /python_modules/py-qgis-scripts \
    && ln -s /opt/local/qgisserver/bin/qgis-server-rpc   

COPY docker/docker-entrypoint.sh /usr/local/bin/
RUN chmod 0755 /usr/local/bin/docker-entrypoint.sh && mkdir -p /home/qgis && chmod 777 /home/qgis

# Set uid root on Xvfb
# Allow us to run Xvfb when the container runs with '-u' option
RUN chmod u+s /usr/bin/Xvfb

EXPOSE 23456

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

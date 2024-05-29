#
# Copyright 2018-2023 3liz
#

""" Start qgis application
"""
import os
import sys

from typing import Dict, Iterator, Optional, no_type_check

import qgis

from .. import logger
from ..condition import assert_precondition


def setup_qgis_paths(prefix: str) -> None:
    """ Init qgis paths
    """
    qgis_pluginpath = os.path.join(
        prefix,
        os.getenv('QGIS3_PLUGINPATH', '/usr/share/qgis/python/plugins/'),
    )
    sys.path.append(qgis_pluginpath)


# We need to keep a reference instance of the qgis_application object
# and not make this object garbage collected
qgis_application: Optional['qgis.core.QgsApplication'] = None


def qgis_initialized():
    global qgis_application
    return qgis_application is not None


def exit_qgis_application():
    global qgis_application
    if qgis_application:
        # print("\nTerminating Qgis application", file=sys.stderr, flush=True)
        qgis_application.exitQgis()
        qgis_application = None


@no_type_check
def setup_qgis_application(
    cleanup: bool = True,
    logprefix: str = 'Qgis:',
) -> 'qgis.core.QgsApplication':
    """ Start qgis application

         :param boolean cleanup: Register atexit hook to close qgisapplication on exit().
             Note that prevents qgis to segfault when exiting. Default to True.
    """
    global qgis_application
    assert_precondition(qgis_application is None, "Qgis application already initialized")

    os.environ['QGIS_NO_OVERRIDE_IMPORT'] = '1'
    os.environ['QGIS_DISABLE_MESSAGE_HOOKS'] = '1'

    qgis_prefix = os.environ.get('QGIS3_HOME', '/usr')
    setup_qgis_paths(qgis_prefix)

    from qgis.core import Qgis, QgsApplication

    if Qgis.QGIS_VERSION_INT < 30000:
        raise RuntimeError(f"You need QGIS3 (found {Qgis.QGIS_VERSION_INT})")

    logger.info("Starting Qgis application: %s", Qgis.QGIS_VERSION)

    #  We MUST set the QT_QPA_PLATFORM to prevent
    #  Qt trying to connect to display in containers
    display = os.environ.get('DISPLAY')
    if display is None:
        logger.info("Setting offscreen mode")
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    else:
        logger.info(f"Using DISPLAY: {display}")

    # XXX Set QGIS_PREFIX_PATH, it seems that setPrefixPath
    # does not do the job correctly
    os.environ['QGIS_PREFIX_PATH'] = qgis_prefix

    qgis_application = QgsApplication([], False)
    qgis_application.setPrefixPath(qgis_prefix, True)

    if cleanup:
        # Closing QgsApplication on exit will
        # prevent our app to segfault on exit()
        import atexit

        logger.info(f"{logprefix} Installing cleanup hook")

        @atexit.register
        def exitQgis():
            exit_qgis_application()

    # Install logger hook
    install_logger_hook(logprefix)

    logger.info("Qgis application configured......")

    return qgis_application


def install_logger_hook(logprefix: str) -> None:
    """ Install message log hook
    """
    from qgis.core import Qgis, QgsApplication

    # Add a hook to qgis  message log

    def writelogmessage(message, tag, level):
        arg = f'{logprefix} {tag}: {message}'
        if level == Qgis.Warning:
            logger.warning(arg)
        elif level == Qgis.Critical:
            logger.error(arg)
        else:
            # Qgis may be somehow very noisy
            logger.trace(arg)

    messageLog = QgsApplication.messageLog()
    messageLog.messageReceived.connect(writelogmessage)


def init_qgis_application(settings: Optional[Dict] = None):
    setup_qgis_application()

    from qgis.core import QgsApplication
    from qgis.PyQt.QtCore import QCoreApplication

    # From qgis server
    # Will enable us to read qgis setting file
    QCoreApplication.setOrganizationName(QgsApplication.QGIS_ORGANIZATION_NAME)
    QCoreApplication.setOrganizationDomain(QgsApplication.QGIS_ORGANIZATION_DOMAIN)
    QCoreApplication.setApplicationName(QgsApplication.QGIS_APPLICATION_NAME)

    qgis_application.initQgis()  # type: ignore [union-attr]

    optpath = os.getenv('QGIS_OPTIONS_PATH') or os.getenv('QGIS_CUSTOM_CONFIG_PATH')
    if optpath:
        # Log qgis settings
        load_qgis_settings(optpath)

    if settings:
        # Initialize settings
        from qgis.core import QgsSettings
        qgsettings = QgsSettings()
        for k, v in settings.items():
            qgsettings.setValue(k, v)


def init_qgis_processing() -> None:
    """ Initialize processing
    """
    from processing.core.Processing import Processing

    from qgis.analysis import QgsNativeAlgorithms
    from qgis.core import QgsApplication

    # Update the network configuration
    # XXX: At the time the settings are read, the networkmanager is already
    # initialized, but with the wrong settings
    set_proxy_configuration()

    QgsApplication.processingRegistry().addProvider(QgsNativeAlgorithms())
    Processing.initialize()


def init_qgis_server(**kwargs) -> 'qgis.server.QgsServer':
    """ Init Qgis server
    """
    setup_qgis_application(**kwargs)

    from qgis.server import QgsServer
    server = QgsServer()

    # Update the network configuration
    # XXX: At the time the settings are read, the neworkmanager is already
    # initialized, but with the wrong settings
    set_proxy_configuration()

    return server


def load_qgis_settings(optpath):
    """ Load qgis settings
    """
    from qgis.core import QgsSettings
    from qgis.PyQt.QtCore import QSettings

    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, optpath)
    logger.info("Settings loaded from %s", QgsSettings().fileName())


def set_proxy_configuration() -> None:
    """ Display proxy configuration
    """
    from qgis.core import QgsNetworkAccessManager
    from qgis.PyQt.QtNetwork import QNetworkProxy

    nam = QgsNetworkAccessManager.instance()
    nam.setupDefaultProxyAndCache()

    proxy = nam.fallbackProxy()
    proxy_type = proxy.type()
    if proxy_type == QNetworkProxy.NoProxy:
        return

    logger.info(
        "QGIS Proxy configuration enabled: %s:%s, type: %s",
        proxy.hostName(), proxy.port(),
        {
            QNetworkProxy.DefaultProxy: 'DefaultProxy',
            QNetworkProxy.Socks5Proxy: 'Socks5Proxy',
            QNetworkProxy.HttpProxy: 'HttpProxy',
            QNetworkProxy.HttpCachingProxy: 'HttpCachingProxy',
            QNetworkProxy.HttpCachingProxy: 'FtpCachingProxy',
        }.get(proxy_type, 'Undetermined'),
    )


def print_qgis_version(verbose: bool = False) -> None:
    """ Output the qgis version
    """
    from qgis.core import QgsCommandLineUtils

    print(QgsCommandLineUtils.allVersions())

    if verbose:
        init_qgis_application()
        print(qgis_application.showSettings())  # type: ignore
        sys.exit(1)


def show_all_versions() -> Iterator[str]:
    from qgis.core import QgsCommandLineUtils
    versions = QgsCommandLineUtils.allVersions().split('\n')
    return (v for v in versions if v)


def show_qgis_settings() -> str:
    global qgis_application
    if qgis_application:
        return qgis_application.showSettings()
    else:
        return ""

#
# Copyright 2018-2023 3liz
#

"""Start qgis application"""

import os
import sys

from pathlib import Path
from typing import TYPE_CHECKING, Iterator, Optional, no_type_check

from qgis.core import Qgis

if TYPE_CHECKING:
    from qgis.core import QgsApplication
    from qgis.server import QgsServer

from .. import logger
from ..condition import assert_not_none, assert_precondition

QGIS_VERSION_INT = Qgis.versionInt()
QGIS_VERSION_3 = QGIS_VERSION_INT < 40000

QGIS_MINIMUM_VERSION_INT = 34000
QGIS_MINIMUM_VERSION = "3.40"


def setup_qgis_paths(prefix: str) -> None:
    """Init qgis paths"""
    qgis_pluginpath = os.path.join(  # noqa PTH118
        prefix,
        os.getenv("QGIS3_PLUGINPATH", "/usr/share/qgis/python/plugins/"),
    )
    sys.path.append(qgis_pluginpath)


# We need to keep a reference instance of the qgis_application object
# and not make this object garbage collected
qgis_application: Optional["QgsApplication"] = None


def current_qgis_application() -> Optional["QgsApplication"]:
    return qgis_application


def qgis_initialized():
    global qgis_application
    return qgis_application is not None


def exit_qgis_application():
    global qgis_application
    if qgis_application:
        # print("\nTerminating QGIS application", file=sys.stderr, flush=True)
        qgis_application.exitQgis()
        qgis_application = None


@no_type_check
def setup_qgis_application(
    *,
    settings: Optional[dict[str, str]] = None,
    cleanup: bool = False,
    logprefix: str = "Qgis:",
    server_settings: bool = False,
    allow_python_embedded: bool = False,
    timeout: int = 20,
) -> str:
    """Setup qgis application

    :param boolean cleanup: Register atexit hook to close qgisapplication on exit().
        Note that prevents qgis to segfault when exiting. Default to True.
    """
    from qjazz_core.semaphore import semaphore
    from qjazz_core.timer import Instant

    global qgis_application
    assert_precondition(qgis_application is None, "Qgis application already initialized")

    os.environ["QGIS_NO_OVERRIDE_IMPORT"] = "1"
    os.environ["QGIS_DISABLE_MESSAGE_HOOKS"] = "1"

    qgis_prefix = os.environ.get("QGIS3_HOME", "/usr")
    setup_qgis_paths(qgis_prefix)

    from qgis.core import Qgis, QgsApplication
    from qgis.PyQt.QtCore import QCoreApplication

    if QGIS_VERSION_INT < QGIS_MINIMUM_VERSION_INT:
        raise RuntimeError(f"You need QGIS {QGIS_MINIMUM_VERSION} minimum (found {Qgis.version()})")

    #  We MUST set the QT_QPA_PLATFORM to prevent
    #  Qt trying to connect to display in containers
    display = os.environ.get("DISPLAY")
    if display is None:
        logger.debug("Setting offscreen mode")
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    else:
        logger.debug(f"Using DISPLAY: {display}")

    # NOTE: Set QGIS_PREFIX_PATH, it seems that setPrefixPath
    # does not do the job correctly
    os.environ["QGIS_PREFIX_PATH"] = qgis_prefix

    # From qgis server
    # Will enable us to read qgis setting file
    QCoreApplication.setOrganizationName(QgsApplication.QGIS_ORGANIZATION_NAME)
    QCoreApplication.setOrganizationDomain(QgsApplication.QGIS_ORGANIZATION_DOMAIN)
    QCoreApplication.setApplicationName(QgsApplication.QGIS_APPLICATION_NAME)

    # Initialize configuration settings
    options_path = load_qgis_settings(
        settings,
        server_settings=server_settings,
        allow_python_embedded=allow_python_embedded,
    )

    instant = Instant()

    logger.info("Starting QGIS application: %s", Qgis.QGIS_VERSION)

    # NOTE: Setting the platform to anything else than
    # 'external' will prevent loading Grass and OTB providers
    # But this has side-effects when used with QgsServer

    # Apparently QGIS does not support well concurrent access to
    # profile files and data at startup. The posix semaphore will
    # prevent this.
    # The semaphore is not unlinked: this is on purpose and does
    # not really matter since it is named after the unique path
    # of the profile.
    # Furthemore it does not appear to leak through containers (tested)
    with semaphore(options_path, timeout=timeout):
        qgis_application = QgsApplication(
            [],
            False,
            platformName="qjazz-application",
        )

    logger.debug("QGIS application initialized in %s ms", instant.elapsed_ms)

    qgis_application.setPrefixPath(qgis_prefix, True)

    if cleanup:
        import atexit
        # NOTE: this is not called on signal !
        # see https://docs.python.org/3/library/atexit.html

        @atexit.register
        def exitQgis():
            # Closing QgsApplication on exit will
            # prevent our app to segfault on exit()
            # NOTE: Doesn't seem necessary anymore
            if cleanup:
                logger.debug(f"{logprefix} Installing cleanup hook")
                exit_qgis_application()

    # Install logger hook
    install_logger_hook(logprefix)

    logger.debug("QGIS application configured......")

    return options_path


def install_logger_hook(logprefix: str) -> None:
    """Install message log hook"""
    from qgis.core import Qgis, QgsApplication

    # Add a hook to qgis  message log

    def writelogmessage(message, tag, level, *args):
        arg = f"{logprefix} {tag}: {message}"
        if level == Qgis.Warning:
            logger.warning(arg)
        elif level == Qgis.Critical:
            logger.error(arg)
        else:
            # Qgis may be somehow very noisy
            logger.debug(arg)

    messageLog = assert_not_none(QgsApplication.messageLog())
    if QGIS_VERSION_3:
        messageLog.messageReceived.connect(writelogmessage)
    else:
        # NOTE: see https://github.com/python/mypy/issues/19892
        # There is actually no way to typecheck conditionally
        messageLog.messageReceivedWithFormat.connect(writelogmessage)  # type: ignore [attr-defined]


def init_qgis_application(**kwargs):
    setup_qgis_application(**kwargs)
    qgis_application.initQgis()  # type: ignore [union-attr]


def init_qgis_processing() -> None:
    """Initialize processing"""
    from processing.core.Processing import Processing

    Processing.initialize()


def init_qgis_server(**kwargs) -> "QgsServer":
    """Init QGIS server"""
    from qgis.server import QgsServer

    setup_qgis_application(server_settings=True, **kwargs)

    server = QgsServer()

    # Update the network configuration
    # NOTE: At the time the settings are read, the networkmanager is already
    # initialized, but with the wrong settings
    set_proxy_configuration()

    return server


def load_qgis_settings(
    settings: Optional[dict[str, str]],
    *,
    server_settings: bool = False,
    allow_python_embedded: bool = False,
) -> str:
    """Load QGIS settings"""
    from qgis.core import Qgis, QgsSettings
    from qgis.PyQt.QtCore import QSettings

    options_path = os.getenv("QGIS_CUSTOM_CONFIG_PATH")
    if not options_path:
        # Set config path in current directory
        path = Path.cwd().joinpath(".qjazz-settings")
        # InitQgis use settings in 'profiles/default'
        settings_path = path.joinpath("profiles", "default")
        settings_path.mkdir(parents=True, exist_ok=True)
        options_path = str(path)
        os.environ["QGIS_CUSTOM_CONFIG_PATH"] = options_path
        os.environ["QGIS_OPTIONS_PATH"] = options_path
    else:
        settings_path = Path(options_path).joinpath("profiles", "default")
        if not settings_path.is_dir():
            raise FileNotFoundError(f"{settings_path}")

    # NOTE: if we call initQgis then the settings used will be located in
    # $QGIS_OPTIONS_PATH/profiles/default - while server will use the designated
    # path.
    #
    # This is because it is not possible to set together 'platformName' and 'profileFolder'
    # with initQgis :-(
    #
    if server_settings:
        # Use default profile as main config path (for server)
        options_path = str(settings_path)
        os.environ["QGIS_CUSTOM_CONFIG_PATH"] = options_path
        os.environ["QGIS_OPTIONS_PATH"] = options_path

    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(settings_path))

    qgssettings = QgsSettings()
    logger.debug("Settings loaded from %s", qgssettings.fileName())

    if settings:
        # Initialize custom parameters settings
        for k, v in settings.items():
            qgssettings.setValue(k, v)

    if not allow_python_embedded:
        # Disable python embedded and override previous settings
        logger.info("Disabling Python Embedded in QGIS")
        # NOTE: Missing QgsSettings.setEnumValue in QGIS python .pyi
        qgssettings.setEnumValue("qgis/enablePythonEmbedded", Qgis.PythonEmbeddedMode.Never)  # type: ignore [attr-defined]

    return options_path


def set_proxy_configuration() -> None:
    """Display proxy configuration"""
    from qgis.core import QgsNetworkAccessManager
    from qgis.PyQt.QtNetwork import QNetworkProxy

    nam = assert_not_none(QgsNetworkAccessManager.instance())
    nam.setupDefaultProxyAndCache()

    proxy = nam.fallbackProxy()
    if proxy is None:
        logger.warning("No fallback proxy defined")
        return

    proxy_type = proxy.type()

    ProxyType = QNetworkProxy.ProxyType
    if proxy_type == ProxyType.NoProxy:
        return

    logger.info(
        "QGIS Proxy configuration enabled: %s:%s, type: %s",
        proxy.hostName(),
        proxy.port(),
        {
            ProxyType.DefaultProxy: "DefaultProxy",
            ProxyType.Socks5Proxy: "Socks5Proxy",
            ProxyType.HttpProxy: "HttpProxy",
            ProxyType.HttpCachingProxy: "HttpCachingProxy",
            ProxyType.HttpCachingProxy: "FtpCachingProxy",
        }.get(proxy_type, "Undetermined"),
    )


def print_qgis_version(verbose: bool = False) -> None:
    """Output the qgis version"""
    from qgis.core import QgsCommandLineUtils

    print(QgsCommandLineUtils.allVersions())

    if verbose:
        init_qgis_application()
        print(qgis_application.showSettings())  # type: ignore
        sys.exit(1)


def show_all_versions() -> Iterator[str]:
    from qgis.core import QgsCommandLineUtils

    versions = QgsCommandLineUtils.allVersions().split("\n")
    return (v for v in versions if v)


def show_qgis_settings() -> str:
    global qgis_application
    if qgis_application:
        return qgis_application.showSettings()
    return ""

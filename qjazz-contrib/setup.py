import os

if os.getenv("QJAZZ_NO_BUILD_EXT_INSTALL") is None:
    from setuptools import Extension, setup
    from qgis.core import Qgis

    if Qgis.versionInt() < 40000:
        include_dirs = [
            "/usr/include/qgis",
            "/usr/include/x86_64-linux-gnu/qt5",
            "/usr/include/x86_64-linux-gnu/qt5/QtCore",
            "/usr/include/x86_64-linux-gnu/qt5/QtGui",
            "/usr/include/x86_64-linux-gnu/qt5/QtXml",
            "/usr/include/x86_64-linux-gnu/qt5/QtWidgets",
        ]
        PYQT_SIP_C_API='"PyQt5.sip._C_API"'
    else:
        include_dirs = [
            "/usr/include/qgis",
            "/usr/include/x86_64-linux-gnu/qt6",
            "/usr/include/x86_64-linux-gnu/qt6/QtCore",
            "/usr/include/x86_64-linux-gnu/qt6/QtGui",
            "/usr/include/x86_64-linux-gnu/qt6/QtXml",
            "/usr/include/x86_64-linux-gnu/qt6/QtWidgets",
        ]
        PYQT_SIP_C_API='"PyQt6.sip._C_API"'
    setup(
        package_dir={'': 'src'},
        packages=["qjazz_core"],
        ext_modules=[
            Extension(
                name = "qjazz_core.qgis.qgis_binding",
                sources = ["src/qjazz_core/qgis/qgis_binding.cpp"],
                include_dirs = include_dirs,
                define_macros = [("PYQT_SIP_C_API", PYQT_SIP_C_API)],
                libraries = [
                    "qgis_core",
                    "qgis_server",
                ]
            ),
        ],
    )
else:
    from setuptools import setup
    setup(packages=["qjazz_core"]),
    print("NOTE: Building of extension disabled...")

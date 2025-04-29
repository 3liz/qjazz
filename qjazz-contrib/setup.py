import os

if os.getenv("QJAZZ_NO_BUILD_EXT_INSTALL") != "1":
    from setuptools import Extension, setup
    setup(
        ext_modules=[
            Extension(
                name = "qjazz_contrib.core.qgis.qgis_binding",
                sources = ["qjazz_contrib/core/qgis/qgis_binding.cpp"],
                include_dirs = [
                    "/usr/include/qgis",
                    "/usr/include/x86_64-linux-gnu/qt5",
                    "/usr/include/x86_64-linux-gnu/qt5/QtCore",
                    "/usr/include/x86_64-linux-gnu/qt5/QtGui",
                    "/usr/include/x86_64-linux-gnu/qt5/QtXml",
                    "/usr/include/x86_64-linux-gnu/qt5/QtWidgets",
                ],
                libraries = [
                    "qgis_core",
                    "qgis_server",
                ]
            ),
        ],
    )
else:
    from setuptools import setup
    setup()
    print("NOTE: Building of extension disabled...")

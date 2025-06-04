Building QJazz
==============

QJazz involves components in Python and Rust.

Requirements
------------

* The GNU `make` command 
* [A recent rust toolchain](https://www.rust-lang.org/tools/install)
* Python 3.12 with the following modules:
    - setuptools
    - build >= 1.2.2  
* Define the environment variable `QJAZZ_NO_BUILD_EXT_INSTALL=1` unless you feel
  adventurous.


Note that if your target platform has no Python 3.12 installed by default then you probalbly
wont be able to install QGIS with python 3.12 support on it - unlees you compile QGIS
explicitely with the Python 3.12 support. 


Building
--------

To build binary components run:

```sh
make build
```

Running tests
-------------

Running tests requires a QGIS 3.34+ (3.40+ recommended) installation.

**IMPORTANT**: It is highly recommended that you use a virtual env (venv) before messing
with your python installation: running and testing QJazz requires eager versions of some
packages and **do not use pip on your distribution installation**.


Install required packages and install qjazz modules in dev mode: 

```sh
make install-dev install
```

Run tests:

```sh
make bin-test test 
```

Create release packages
------------------------

```sh
make dist
```

The command will build binary components in release for your platforme 
and build Python distribution packages and copy them in the `dist/release`
folder at the root of the repository.



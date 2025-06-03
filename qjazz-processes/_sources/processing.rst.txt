.. _qgis_processing:

Running QGIS Algorithms
=======================

.. _layer_mapping:

Input/output layer mapping
------------------------------

With QGIS desktop , QGIS processing algorithms usually apply on a QGIS source project and computed layers are displayed in the same context as the source project.

|ProjectName| works the same way: a qgis project will be used as a source of input layers.
The difference is that, when an algorithm runs, it creates a qgis destination project associated 
to the current task and register computed layers to it.

The created project may be used as OWS/WFS3 source with QGIS Server.

Output layers are returned as OWS url's holding a reference to a WMS/WFS/WMTS/WCS 
url that can be used directly with QGIS server. 

The uri template is configurable using the ``processing.advertised_services_url`` 
configuration setting.


.. _source_project:

Source project
--------------

Process parameters may be associated with a source project using the ``map`` query param. 
If a `map` parameters is given when doing a `describe` requests, allowed values 
for input layers will be taken from the qgis source project according the type 
of the input layers.

Some algorithms requires a source project, in that case the description metadata should
have a  role``RequiresProject`` with value set to ``true```.

.. note::

   When implmenting algorithm, you should always set the Qgis  processing  
   ``RequiresProject`` algorithm flag if a project is needed to run the
   algorithm.

Any attempt to execute an algorithm that requires a project with no map parameter
will result in a execution error.

If you need to pass data to your algorithm from client-side, prefer inputs file parameter 
and small payloads.


Accessing Qgis projects
------------------------

Beside QGIS project files (*.qgs*, *.qgz*), |ProjectName| support all 
``QgsProjectStorage`` backends in Qgis.

Project's access is *uniform*: the configuration settings define search paths which are indirection
to the corresponding backends:

.. code-block:: toml

   [prcessing.projects.search_paths]
   '/a_path' = "/path/to/projects/"                  # Path to files volume
   '/another/path' = "file:///other/projects/"       # With explicit scheme
   '/path/to/postgres' = "postgres://?service=name"  # projects stored in postgres

Any following subpath to a search path is considered as the relative project's path
or the projects name user for url resolution::

    /path/to/postgres/projname

will be resolved to::

    postgres://?service=name&project=projname

From client perspective, a project is always refered by its search path followed by the (relative)
project's path or name::

    /<search_path>/<project_path>


.. _exposing_algorithms:

Exposing processing algorithms
==============================

Plugins locations
-----------------

The processing provider modules are searched in the path given by the 
``processing.projects.search_paths`` configuration setting.

The search is not recursive, subdirectories  must be set explicitely


Registering providers
---------------------

There is nothing special to do for using a Qgis plugin with |ProjectName|. 

As for Qgis desktop, |ProjectName| expect the a pluging to follow
the same rules as for any other plugins `implementing processing 
providers <https://docs.qgis.org/testing/en/docs/pyqgis_developer_cookbook/processing.html>`_`. 

As regular QGIS plugin, a metadata.txt file must be present with the variable
``hasProcessingProvider=yes`` indicating that the plugin is available as a processing 
service provider factory.

The object returned by the ``classFactory`` function must implement the ``initProcessing``
method.

.. note::

   The ``initProcessing`` method will be the one and only one method called by
   |ProjectName|.       

|ProjectName| use the same entrypoint a Qgis desktop plugin except that
not ``QgsInterface`` is provided.


.. warning::

    | The ``iface: QgsInterface`` parameter is used for initializing Gui component 
      of the plugin in Qgis desktop.  This parameter will be set to ``None`` when
      loaded from |ProjectName|.
    | Implementors should take care to check the value of the ``iface`` parameter
      and drop all gui initialization if not set.
    | The only thing to do is to register the providers the same way as for 
      using in Qgis Desktop.   


Example::

    from qgis.core import QgsApplication

    from .provider import TestAlgorithmProvider


    class Test:
        def __init__(self):
            pass

        def initProcessing(self):
            reg = QgsApplication.processingRegistry()

            # XXX we *MUST* keep instance of provider
            self._provider = TestAlgorithmProvider()
            reg.addProvider(self._provider)


    def classFactory(iface: QgsInterface|None) -> Test:
        if iface is not None:
            # Initialize GUI
            ... 

        return Test()


Using scripts and models
------------------------

|ProjectName| works with scripts and models. First creates a ``models/`` and a ``scripts/`` directory
in the folder given by the ``processing.plugins.paths``` setting.

If your configuration is 

.. code-block:: toml

   [processing.plugins]
   paths = ["/path/to/plugin_dir"]
   ...

Your processing module directory should be something like::

    ├── plugin_dir
    │   ├── models
    │   │    └── <your '.model3' files here>
    │   └── scripts
    │        └── <your '.py' scripts here>


Then simple drop your ``.model3`` in the ``models/`` folder and the  python scripts in the ``scripts/`` folder.
After restarting the workers you should see the corresponding algorithms in the list of published WPS jobs.

Controlling what is exposed
---------------------------

* Algorithms with the flag `FlagHideFromToolbox <https://qgis.org/pyqgis/master/gui/Qgis.html#qgis.gui.Qgis.ProcessingAlgorithmFlag>`_ set will not be exposed as a process.

* Algorithms with the flag `Deprecated <https://qgis.org/pyqgis/master/gui/Qgis.html#qgis.gui.Qgis.ProcessingAlgorithmFlag>`_  are controlled by the ``processing.expose_deprecated_algorithms`` setting.

* Parameters with the flag `FlagHidden <https://qgis.org/pyqgis/master/gui/Qgis.html#qgis.gui.Qgis.ProcessingAlgorithmFlag>`_ set wont be exposed as input parameter in the process description.






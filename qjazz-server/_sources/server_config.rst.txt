
.. _server_service:

HTTP frontend
=============

The http frontend is a middleware proxy for routing  requests to
Qgis worker pool backends. 

Each backend is a gRPC client that will route incoming requests to the
configured backend by defining a path root prefix similar to the `root`
directive of a proxy server.


.. _server_routing:

Routing requests to Qgis pools
----------------------------------

Each backend is configured with a :ref:`backend.\<id\> <server_config>` settings.

.. code-block:: toml

    [backends.pool1]
    route = "/gis"
    host = "qgis-rpc-pool1"
    port = 23456


.. note::

    Project may be specified in two ways:

    * Use `MAP` parameter::

       https://test.com/gis?MAP=/search_path/project_path&SERVICE=...

    * Or specify the full project's search path  with the **X-Qgis-Project** header.


Api endpoints
-------------

Qgis api endpoints must be declared explicitly in order to be requested by client::
    
    [[backends.test.api]]
    endpoint = "wfs3"
    name = "Feature OGC Api (WFS3 Draft)

.. note::

    Project is specified the same way as for OWS endpoints
    
    With the `MAP` parameter::

        https://test.com/route_path/api/path/>?MAP=/search_path/project_path
    
    or the **X-Qgis-Project** header.

    If you want to pass the project full search path in the url path, it must be done
    in a way to disambiguate the api path from the project's path. This is achieved
    by separating the search path from the api path with a `_`:: 
        
        https://test.com/route_path/search_path/project_path/_/api/path


.. _server_config:

Service configuration
---------------------

.. literalinclude:: configs/server.toml
     :language: toml



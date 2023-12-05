
.. _proxy_service:

HTTP frontend
=============

The http frontend is a middleware proxy for routing  requests to
Qgis worker pool backends. 

Each backend is a gRPC client that will route incoming requests to the
configured backend by defining a path root prefix similar to the `root`
directive of a proxy server.


.. _proxy_routing:

Routing OWS requests to Qgis pools
----------------------------------

Each backend is configured with a :ref:`backend.\<id\> <proxy_config>` settings.

Passing request for a particular backend is done with the route as leading path::

    [backend.pool1]
    route = "/route_path"


.. note::

    Project may be specified in serveral way:

    * Use `MAP` parameter::

       https://test.com/route_path?MAP=/search_path/project_path&SERVICE=...

    * Add project's search path to url path::
        
       https//test.com/route_path/search_path/#/project_path?SERVICE=...

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


.. _proxy_config:

Service configuration
---------------------

.. literalinclude:: configs/proxy.toml
     :language: toml


Configuration and backends managment api
----------------------------------------

The http service has a configuration which allow push configuration fragments or 
reloading the configuration (local or remote).



Backends
^^^^^^^^


.. http:get:: /backend/{Id}

   Return the backend configuration for {Id}

   :statuscode 200: no error
   :statuscode 404: the backend {Id} does not exist

.. http:post:: /backend/{id}


.. http:put:: /backend/{id}


.. http:delete:: /backend/{id}



Config
^^^^^^

.. http:get:: /config

   Return the current configuration





Scalability:
------------

The proxy service may be scaled as long as you provide load balancing facility (like the `ingress`
mode in Docker Swarm)


Inputs and Outputs
==================

Parameters description
----------------------

Process description uses `JSON Schema <https://json-schema.org/draft/2020-12/json-schema-core>`_
framents te define the inputs and outputs parameters as description in the 
`OGC process description <https://docs.ogc.org/is/18-062r2/18-062r2.html#toc35` document.

This makes the task more complicated for api client to implement generic client since
the variability of JSON schema is much more important than what was proposed by the WPS
standards, but there is some invrariant rules.

|ProjectName| map `QgsProcessingParameterDefinition <https://api.qgis.org/api/classQgsProcessingParameterDefinition.html>_` and `QgsProcessingOutputDefinition  <https://api.qgis.org/api/classQgsProcessingOutputDefinition.html>`_ to JSON Schema. 

The currrent implementation follow the schemas described in the `actual unreleased version of the standard <https://github.com/opengeospatial/ogcapi-processes/tree/master>`_.

That means that it may not be compliant for most of actual OGC api compliance validators which
are strictly based on the version 1.0.0 of the standards.
 

Literals and complex types
--------------------------

Most of the parameters are *literals* or array of *literals*  types associated with constraints

Most of the time, there will be a ``format`` specification as described in 
:ref:`additional formats <additional_formats>`
thal will give you hints for the format of the parameter.

*Literals* will come with allowed values constraint expressed as JSON schema as 
`enumerated values <https://json-schema.org/understanding-json-schema/reference/enum>`_

This will be the case for `QgisProcessingParameterEnum <https://api.qgis.org/api/classQgsProcessingParameterEnum.html>`_  or layer names constrained by a :ref:`source project <source_project>`.

*Complex* input types will have :ref:`media types <media_types>` associated with them, 
allowing the client to select the type of input.

.. warning::

   Input with content media types should always be sent as `qualified values <:ref:qualified_values>`_.


Compliance to OGC standards
---------------------------

The currrent implementation follow the schemas described in the `actual unreleased version of the standard <https://github.com/opengeospatial/ogcapi-processes/tree/master>`_.

That means that it may not be compliant for most of actual OGC api compliance validators which
are strictly based on the version 1.0.0 of the standards.
     
Notes on schemas
----------------

Inputs and outputs value descriptions are described as json schemas. That is, the schema
determines completely the syntax of the value. 

produced schemas are compliant to the following specifications

* `JSON Schema Draft 2020-12 <https://json-schema.org/draft/2020-12/release-notes>`_
* `OpenAPI Specification v3.1.0 <https://github.com/OAI/OpenAPI-Specification>`_


Value passing and transmission mode
-----------------------------------

The value passing method is bound to each input with the :code:`valuePassing` property. 

.. note::
   | The current implementation does not allow client to specify the transmission mode for outputs.
   | That means that the :code:`transmissionMode` property is ignored in output specification in `execute` 
     requests.
   | Instead each output individually requires to be passed either by value or by reference as 
     as server-side decision. 

For informative purpose, a non-standard optional :code:`valuePassing` property may be added to the output description.

In all cases, references use `links <https://github.com/opengeospatial/ogcapi-processes/blob/master/openapi/schemas/common-core/link.yaml>`_ as output value.

Inlines output value are returned either directly as described by their schema or as qualified value.


.. _qualified_values:

Qualified input and output values
---------------------------------

`Qualified values <https://github.com/opengeospatial/ogcapi-processes/blob/master/openapi/schemas/processes-core/qualifiedInputValue.yaml>`_ are used for encoding non Json strings.

For input values: a qualified value **must** be returned if the input schema has the `contentMediaType <https://json-schema.org/understanding-json-schema/reference/non_json_data#contentmediatype>`_ keyword.

For output values: a qualified value **will** be returned if the output schema has the `contentMediaType <https://json-schema.org/understanding-json-schema/reference/non_json_data#contentmediatype>`_ keyword.


.. _media_types:

Multiple media types
--------------------

Inputs and outputs may describe multiple media types an inputs and outputs in `oneOf <https://json-schema.org/understanding-json-schema/reference/combining#oneOf>`_ composite schema.

Consider the following example for return a geometry:

Example::

    "schema": {
      "anyOf": [
        {
          "type": "string",
          "contentMediaType": "application/wkt"
        },
        {
          "type": "string",
          "contentMediaType": "application/gml+xml"
        },
        {
          "format": "geojson-geometry"
          "$ref": "http://schemas.opengis.net/ogcapi/features/part1/1.0/openapi/schemas/geometryGeoJSON.yaml"
        },
      ]
    }    
    
One possible response would be::
    
    {
      "value": "....."
      "mediaType": "application/wkt"
    }

.. warning::
    In the example above, the geojson response **must not** be returned as qualified value since it deos
    not have a :code:`contentMediaType` annotation.


Formats
-------

In the example above we have used the keyword :code:`format` in the geojson schema description.


The :code:`format` keyword is used for providing additonal semantic context that can help
the interpretation and validation of process input or output in an :code:`execute` request.

While the JsonSchema specification use the :code:`format` keyword for strings only, the OGC
standards extend its usage to any object.

Check the `built-in json schemas formats <https://json-schema.org/understanding-json-schema/reference/string#format>`_

The OGC standards defines additional formats:

:geojson-feature-collection: Indicates that the object is an instance of a GeoJSON feature collection
:geojson-feature: Indicates that the object is an instance of a GeoJSON feature
:geojson-geometry: Indicates that the object is an instance of a GeoJSON geometry 
:ogc-bbox: Indicates that the object is an instance of an `OGC bounding box <https://github.com/opengeospatial/ogcapi-processes/blob/master/openapi/schemas/processes-core/bbox.yaml>`_

.. _additional_formats:

Additional formats
------------------

According to JsonSchema specification, additional schema
properties start with an :code:`x-*` prefix

Additional OGC specific properties are prefixed with :code:`x-ogc-*`.

Using :code:`x-ogc-*` is a OGC standart proposal described in https://github.com/opengeospatial/ogcapi-features/issues/838 for the `features` api.

The following additional formats are used in |ProjectName|:

:x-ogc-crs: Indicate that an string or object is a `CRS definition <https://github.com/opengeospatial/ogcapi-processes/blob/master/openapi/schemas/common-geodata/crs.yaml>`_
:x-range: A 2-tuple of numbers indicating a inclusive range
:x-range-exclude: A 2-tuple of numbers indicating a exclusive range
:x-range-exclude-left: 2-tuple of numbers indicating a left exclusive range
:x-range-exclude-right: A 2-tuple of numbers indicating a right exclusive range
:x-feature-source: A source name with optional attributes for selecting features


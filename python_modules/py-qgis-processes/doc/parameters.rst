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

Literals and complex types
^^^^^^^^^^^^^^^^^^^^^^^^^^

Most of the parameters are *literals* or array of *literals*  types associated with constraints

Most of the time, there will be a ``format`` specification as described in 
`additional formats <:ref:additional_formats>`_
thal will give you hints for the format of the parameter.

*Literals* will come with allowed values constraint expressed as JSON schema as 
`enumerated values <https://json-schema.org/understanding-json-schema/reference/enum>`_

This will be the case for `QgisProcessingParameterEnum <https://api.qgis.org/api/classQgsProcessingParameterEnum.html>`_  or layer names constrained by a `source project <:ref:source_project>`_.

*Complex* input types will have `media types <:ref:media types>`_ associated with them, 
allowing the client to select the type of input.

.. warning::

   Input with content media types should always be sent as `qualified values <:ref:qualified_values>`_.


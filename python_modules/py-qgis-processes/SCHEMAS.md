
# Additional schema properties

According to JsonSchema specification, additional schema
properties start with an `x-*` prefix.

## OGC additional propertise

Additional OGC properties are prefixed  with `x-ogc-*`

Using `x-ogc-*` is a OGC standart proposal described  in https://github.com/opengeospatial/ogcapi-features/issues/838 for the `features` api

## keywords used in Py-Qgis-Processes

* `x-ogc-uom`: unit of measure for a numerical value, either as a UCUM code or as a URI
* `x-ogc-definition`: URI of semantic definition for the property represented by the JSON member
        Single names will refer to https://www.opengis.net/dataType/1.1/ vocabulary

Ref: see https://github.com/opengeospatial/ogcapi-features/issues/838

## Extra `format` specification:

Additionally to OGC `schema` and standard JsonSchema keywords to the standard OGC schema formats,

These keywords will be used when there is no OGC alternative for complex data structure:

* `x-qgis-parameter-<name>` Where `<name>` is the name of an input/output QgisParameterDefinition
   class (ex: `enum` for `QgisProcessingParameterEnum`, `range` for `QgisProcessingParameterRange`,
   ...).
   Corresponding definitions will be provided with the documentation.

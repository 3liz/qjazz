
Job execution
=============

.. _prefer_header:

The `Prefer` header
-------------------

Job execution may be controlled is some aspects with the 
`Prefer header <https://docs.ogc.org/is/18-062r2/18-062r2.html#toc32>`_.

Qjazz processes supports the following ``Prefer`` parameters:

* :respond-async: Prefer async response compliant to `RFC 7240 <https://www.rfc-editor.org/rfc/rfc7240.txt>`_.
* :wait: Upper bound to time in seconds to wait for response before returning asynchronous response (HTTP code 202). Compliant to `RFC 7240 <https://www.rfc-editor.org/rfc/rfc7240.txt>`_
* :priority: Priority of job execution from 0 to 9. Only apply if job realm is disabled or for admin realm. 
* :delay: Delay in seconds to wait before executing job. This apply only for asynchronous requests.


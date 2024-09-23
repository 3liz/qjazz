.. _job_access:

Job access
==========

In production environment where multiple users may run jobs, it may be desirable
that jobs can be accessed only by those who executed them.

.. note::

    This has not be confused with access control to execution of processes which is handled
    by *access policies*.

Limiting access to jobs may be enforced by using realm token associated to jobs.

When a job is created a token (a *realm*) may be associated to with it: this token
will be required used in subsequent requests  for accessing job's status and results 
or executing *dismiss* opération.

This feature is optional and is activated with the ``job_realm`` configuration setting.


Using realm token
------------------

By default, when a job is created, a realm token is created and associated to the job.

This token is either defined implicitly by creating a unique *uuid* and returning the value
in the ``X-Job-Realm`` header of the execution response or set explicitly using the same header
in the request.

This token may then be inspected by the client and used in subsequent requests  for
accessing job's status and results or executing *dismiss* opération.

Typical usage is to have a middleware proxy that sets the ``X-Job-Realm`` header together with specified authentification procedure.


Administrative realms
---------------------

When enabling realm, administrator tokens may be defined. 
Requesting job's control using an admin token will give full access to job control.

Admin tokens are defined with the ``job_realm.admin_tokens`` configuration setting.

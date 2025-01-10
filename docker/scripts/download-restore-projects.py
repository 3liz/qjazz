#!/opt/local/qjazz/bin/python 

""" Downlead configuration from url and return the 
    location of the config file.
"""
import os

CONF_URL = os.getenv('QJAZZ_REMOTE_RESTORE_PROJECTS_URL')

if CONF_URL:
    import json
    import sys
    import tempfile
   
    import requests

    from typing import Dict, List
    from pydantic import BaseModel

    kwargs: Dict = {}

    class Restore(BaseModel):
        projects: List[str]

    # CA file
    ca = os.getenv('QJAZZ_REMOTE_CAFILE')
    if ca:
        kwargs.update(verify=ca)
    # Client certificats
    client_cert = os.getenv('QJAZZ_REMOTE_CLIENT_CERTFILE')
    client_key = os.getenv('QJAZZ_REMOTE_CLIENT_KEYFILE')
    if client_cert and client_key:
        kwargs.update(cert=(client_cert, client_key))

    resp = requests.get(CONF_URL, **kwargs)
    if resp.status_code == 200:
        restore = Restore.model_validate(resp.json())
        print(",".join(restore.projects))
    else:
        print("CRITICAL: Failed to get restore configuration at", CONF_URL, file=sys.stderr)
        sys.exit(1)
else:
    print("")

#!/opt/local/qjazz/bin/python 

""" Downlead configuration from url and return the 
    location of the config file.
"""
import os

CONF_URL = os.getenv('QJAZZ_REMOTE_CONFIG_URL')

if CONF_URL:
    import json
    import sys
    import tempfile
   
    import requests

    kwargs: dict = {}

    print("Loading remote config from", CONF_URL, file=sys.stderr)

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
        print(json.dumps(resp.json()))
    else:
        print("CRITICAL: Failed to get configuration at", CONF_URL, file=sys.stderr)
        sys.exit(1)
else:
    print("{}")

#!/usr/bin/env python3
# vim: ft=python
#
# Get required packages for optional dependencies
#
import sys

try:
    # Python 3.11+
    import tomllib as toml  # type: ignore
except ModuleNotFoundError:
    import tomli as toml

import re
from pathlib import Path

options = sys.argv[1:]
project = toml.load(Path("pyproject.toml").open('rb'))

optional_dependencies = project['project'].get('optional-dependencies')

def packages():
    yield project['project']['name']
    if not optional_dependencies:
        return 
    for option in options:
        dependencies=optional_dependencies.get(option)
        if dependencies:
            for dep in dependencies:
                yield re.match(r"^([^\>\=\<\s]*)", dep).groups()[0]

print(",".join(f'{dep}' for dep in packages()))





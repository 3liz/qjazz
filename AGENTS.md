# AGENTS.md — QJazz Development Guide

This file is intended for AI coding agents operating in this repository.

## Project Overview

QJazz is a QGIS server framework built as a uv workspace monorepo with:

- **qjazz-contrib**: Core Python library — config system, logger, component manager, QGIS C++ binding
- **qjazz-processes**: OGC Processes implementation — Celery workers, aiohttp server, QGIS Processing integration
- **qjazz-server**: Mixed Rust + Python — gRPC server, HTTP proxy, worker pool manager
- **Python 3.12+** required throughout
- **C++ extension** built via `setup.py` in `qjazz-contrib/` (Qt5/PyQt5 and Qt6/PyQt6)
- **Rust workspace** at `qjazz-server/Cargo.toml` (4 crates: rpc, map, mon, pool)
- **gRPC/protobuf** code generation outputs go to `_grpc/` directories (excluded from linting)

Key reference files:
- `config/ruff.toml` — shared ruff linting and formatting rules
- `config/mypy.ini` — shared mypy configuration
- `config/python.mk` — shared Makefile targets for Python projects
- `config/rules.mk` — top-level Makefile target definitions

---

## Build Commands

### Configure (required before install)
```
make configure
```
Generates `pyproject.toml` from `.in` template (substitutes version variables).

### Install / Upgrade
```
make install              # install packages in development mode
make reinstall            # reinstall
make upgrade              # upgrade all dependencies
```

### Build
```
make build                # build C++ extension + install packages
make build dist           # build C++ extension + create sdist
make manifest             # (qjazz-contrib) create manifest.json with commit ID
```

---

## Lint, Format & Typecheck Commands

All tools are invoked via `uv run` from `config/python.mk`.

### Linting
```
make lint                 # ruff check + mypy (default)
make lint-preview         # ruff --preview checks
make lint-fix             # ruff auto-fix
make lint-fix-preview     # ruff --preview --fix
make typecheck            # mypy only
```

### Formatting
```
make format               # ruff format
make format-diff          # show formatting diff without modifying
```

### Security & Dead Code
```
make scan                 # bandit security scan
make deadcode             # vulture dead code detection
```

### Pre-commit Gate
```
make prepare_commit        # runs: lint scan test (blocks on failure)
```

---

## Test Commands

### Running Tests
```
make test                 # runs pytest -v $(TEST_OPTS) $(TESTDIR)
```

### Running a Single Test File
```
make test TESTDIR=tests/test_config.py
```

### Running a Single Test by Name
```
make test TESTDIR=tests/ TEST_OPTS="-k test_name"
```

### Skipping Slow/Special Tests
```
make test TESTDIR=tests/ TEST_OPTS="-m 'not minio'"     # skip MinIO tests
make test TESTDIR=tests/ TEST_OPTS="-m 'not services'"  # skip Celery service tests
```

### Coverage
```
make coverage              # runs coverage + generates HTML report
```

### Per-Package Test Configuration
Each sub-package sets its own `TESTDIR` and `TEST_OPTS` in its `Makefile`:
- `qjazz-contrib`: `TESTDIR=tests`, `TEST_OPTS=-m "not minio"`
- `qjazz-processes`: same defaults
- `qjazz-server/python`: same defaults

All test directories have a `pytest.ini` with `asyncio_mode=auto`, `log_cli=1`, and `markers` definitions.

---

## Code Style

### Ruff (linting + formatting)
- **Line length**: 110 characters
- **Target Python**: 3.12
- **Indentation**: spaces
- **Formatter**: docstring code formatting enabled
- **Key rule sets**: `E`, `F`, `I` (isort), `ANN` (annotations), `W`, `T`, `COM`, `RUF`, `C4`, `SIM`, `TC`, `RET`
- **Disabled rules**: `ANN002`, `ANN003`, `ANN401` (Any is permitted), `COM812`, `SIM108`, `SIM102`
- **Test files**: `T201` (bare `print`) is allowed in `tests/*`

### mypy
- **Python version**: 3.12
- **Plugin**: `pydantic.mypy` enabled
- **`allow_redefinition = true`**
- All packages having no type hints available  (QGIS, gRPC, Celery, etc.) use `ignore_missing_imports = true`

### Import Conventions
**Absolute imports** are used throughout. **Relative imports** are used within a package.

Import order (enforced by ruff/isort, `lines-between-types = 1`):
1. `__future__`
2. Standard library (`os`, `sys`, `pathlib`, `typing`, etc.)
3. Third-party (`pydantic`, `aiohttp`, `celery`, etc.)
4. `qgis` section (`qgis`, `processing` modules — custom isort section)
5. First-party (`qjazz_core`, `qjazz_cache`, `qjazz_rpc`, etc.)
6. Local folder (relative imports)

Use `TYPE_CHECKING` guards to avoid circular imports:
```python
if TYPE_CHECKING:
    from pathlib import Path
```

### Type Annotations
- **All function signatures** must be annotated (return type + parameters), enforced by ruff `ANN` rules
- **PEP 695 generic syntax** is used: `type X[T: Bound] = ...`
- **Type aliases**: `PascalCase` names (`HttpCORS`, `JobStatusCode`)
- **`Protocol` classes** for structural typing without inheritance
- **`py.typed`** marker files are present in every package
- `Optional[T]` and `T | None` both appear (newer code prefers union syntax)

### Naming Conventions
| Element             | Convention          | Example                          |
|---------------------|---------------------|----------------------------------|
| Modules/packages    | `snake_case`        | `qjazz_core`, `componentmanager` |
| Classes             | `PascalCase`        | `ConfBuilder`, `ConfigProxy`      |
| Functions/methods   | `snake_case`        | `load_configuration()`            |
| Variables           | `snake_case`        | `conf_service`, `rendez_vous`     |
| Constants           | `UPPER_SNAKE_CASE`  | `DEFAULT_INTERFACE`, `SERVER_HEADER` |
| Private helpers     | leading `_`          | `_validate_netinterface()`        |
| Internal attrs      | leading `_`          | `self._celery`, `self._conf`      |
| Type aliases        | `PascalCase`         | `HttpCORS`, `ServiceDict`         |

---

## Error Handling

### Custom Exception Hierarchies
Each package defines its own base exception:
- `QJazzException(Exception)` — `qjazz_core`
- `ProcessesException(Exception)` — `qjazz_processes` → `DismissedTaskError`, `ServiceNotAvailable`, `ProcessNotFound`, etc.
- `ComponentManagerError(Exception)` — `qjazz_core` → `FactoryNotFoundError`, `NoRegisteredFactoryError`

### Patterns
- **`raise ... from None`**: use when re-raising to suppress exception chaining
- **`assert_precondition()` / `assert_postcondition()`**: prefer these over bare `assert` (avoids `-O` flag issues)
- **`assert_never()` + `match`/`case`**: use for exhaustiveness checking in match expressions, with `case _ as unreachable: assert_never(unreachable)` as the final branch
- **HTTP errors**: use `web.HTTPException` subclasses in aiohttp handlers
- **Middleware catch-all**: unhandled exceptions are caught by middleware and returned as structured JSON errors

---

## Architecture Notes

### Component Manager (Contract IDs)
Services register with URI-style IDs: `"@3liz.org/config-service;1"`. The `ComponentManager` resolves these at runtime, enabling loose coupling.

### Configuration System
Pydantic models with `@section("name")` decorator. `ConfBuilder` assembles configurations incrementally. `ConfigProxy[T]` provides live access to sub-configurations.

### Protocol-Based Structural Typing
`Protocol` classes (e.g., `ConfigProto`, `RendezVous`, `ExecutorProtocol`) define interfaces used in type annotations without requiring inheritance.

### Rust + Python Process Pool
`qjazz-pool` (Rust) manages Python worker subprocesses via `msgpack`-encoded pipe communication. Workers signal state via a named pipe at `RENDEZ_VOUS`.

### gRPC Layer
`qjazz-rpc` (Rust) is the gRPC server that spawns Python worker processes. The `qjazz_rpc` Python package provides the worker-side implementation.

### OGC Processes (Celery)
Workers self-register via Celery broadcast/control. The `Executor` aggregates presence replies to route jobs to available workers.

---

## Directory Structure

```
qjazz/
├── Makefile                      # top-level orchestrator (includes config/*.mk)
├── config/
│   ├── config.mk                 # shared Makefile vars (uv, ruff, mypy, bandit)
│   ├── python.mk                 # shared Python targets (lint, test, format, etc.)
│   ├── rules.mk                  # top-level target definitions
│   ├── ruff.toml                 # ruff linting/formatting config
│   └── mypy.ini                  # mypy config
├── qjazz-contrib/
│   ├── Makefile                  # TESTDIR=tests, TEST_OPTS=-m "not minio"
│   ├── setup.py                  # C++ extension build
│   ├── src/qjazz_core/           # config, logger, component manager
│   ├── src/qjazz_cache/          # QGIS project cache
│   ├── src/qjazz_ogc/            # OGC catalog/collections
│   └── src/qjazz_store/          # S3/MinIO object store
├── qjazz-processes/
│   ├── Makefile
│   └── src/
│       ├── qjazz_processes/      # HTTP server, executor, schemas, worker
│       └── qjazz_processing/      # QGIS Processing integration
├── qjazz-server/
│   ├── qjazz-rpc/               # Rust: gRPC server (tonic)
│   ├── qjazz-map/               # Rust: HTTP frontend proxy
│   ├── qjazz-mon/               # Rust: monitoring
│   ├── qjazz-pool/              # Rust: worker pool
│   └── python/
│       └── src/
│           ├── qjazz_rpc/       # Python: gRPC worker
│           ├── qjazz_admin/      # Admin API
│           └── qjazz_map/        # Map server Python components
└── tests/                        # integration/client tests
```

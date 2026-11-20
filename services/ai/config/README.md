# Configuration Files

I file di configurazione sono organizzati come segue:

## Root Level
- `pyproject.toml` - Metadati del progetto e dichiarazione delle dipendenze
- `uv.lock` - Risoluzione riproducibile usata da sviluppo, CI e Docker

## config/ Directory
- `pytest.ini` - Pytest test framework configuration
- `mypy.ini` - MyPy static type checking configuration
- `setup.cfg` - Flake8 linting and setuptools configuration

## Why?
- `pyproject.toml` e `uv.lock` devono stare nella root del servizio per `uv sync --locked`.
- Gli altri file di configurazione possono stare in config/ directory
- I riferimenti ai file sono configurati in pyproject.toml

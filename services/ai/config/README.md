# Configuration Files

I file di configurazione sono organizzati come segue:

## Root Level
- `pyproject.toml` - Project metadata and dependencies (deve rimanere qui per pip install)

## config/ Directory
- `pytest.ini` - Pytest test framework configuration
- `mypy.ini` - MyPy static type checking configuration
- `setup.cfg` - Flake8 linting and setuptools configuration

## Why?
- `pyproject.toml` deve stare in root per pip install -e .
- Gli altri file di configurazione possono stare in config/ directory
- I riferimenti ai file sono configurati in pyproject.toml

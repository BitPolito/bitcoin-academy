"""Regression guard for issue #160 — every QVAC call site must resolve its
endpoint through app.core.config.settings / app.services.qvac_router, not by
reading the QVAC_SERVICE_URL environment variable directly.

A module that reads os.getenv("QVAC_SERVICE_URL", ...) (or os.environ[...])
bypasses the inference ladder: it will NOT pick up a diverging
QVAC_LOCAL_URL / QVAC_SERVER_URL value. app/core/config.py is the single
place allowed to read it, since that is where settings.QVAC_SERVICE_URL (and
its QVAC_LOCAL_URL / QVAC_SERVER_URL siblings) are defined.
"""
import re
from pathlib import Path

import pytest

_APP_DIR = Path(__file__).resolve().parents[2] / "app"
_ALLOWED_FILE = _APP_DIR / "core" / "config.py"

# Matches os.getenv("QVAC_SERVICE_URL", ...) / os.environ["QVAC_SERVICE_URL"]
# / os.environ.get("QVAC_SERVICE_URL", ...), with either quote style.
_DIRECT_ENV_READ = re.compile(
    r"""os\.(?:getenv|environ\.get)\(\s*["']QVAC_SERVICE_URL["']"""
    r"""|os\.environ\[\s*["']QVAC_SERVICE_URL["']\s*\]"""
)


def _python_files():
    return sorted(p for p in _APP_DIR.rglob("*.py") if p.is_file())


@pytest.mark.unit
def test_no_module_outside_config_reads_qvac_service_url_directly():
    violations = []
    for path in _python_files():
        if path == _ALLOWED_FILE:
            continue
        text = path.read_text(encoding="utf-8")
        if _DIRECT_ENV_READ.search(text):
            violations.append(str(path.relative_to(_APP_DIR.parent)))

    assert not violations, (
        "Found direct QVAC_SERVICE_URL environment reads outside "
        f"app/core/config.py: {violations}. Resolve the endpoint through "
        "settings / app.services.qvac_router.resolve(task_type) instead."
    )


@pytest.mark.unit
def test_config_py_still_defines_qvac_service_url():
    """Sanity check that the guard above is actually exercising something —
    config.py should still be the one place that reads the env var."""
    text = _ALLOWED_FILE.read_text(encoding="utf-8")
    assert _DIRECT_ENV_READ.search(text)

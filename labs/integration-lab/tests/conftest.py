"""Pytest configuration to ensure tests use isolated settings.

The test suite uses SQLite in-memory databases, but pydantic-settings
inherits validation_alias from the parent Settings class, which causes
DATABASE_URL and GITHUB_TOKEN environment variables to leak into tests.
This conftest removes those env vars before test collection.
"""
import os
import sys

# Remove env vars that pydantic-settings would read before test collection
for _var in ("DATABASE_URL", "GITHUB_TOKEN", "GITHUB_BASE_URL"):
    os.environ.pop(_var, None)

# Clear the lru_cache on get_settings so it doesn't return stale configs
try:
    import integration_lab.config as _cfg
    _cfg.get_settings.cache_clear()
except ImportError:
    # If the module isn't on the path yet, add it manually
    import pathlib
    src_path = pathlib.Path(__file__).parent.parent / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    import integration_lab.config as _cfg
    _cfg.get_settings.cache_clear()

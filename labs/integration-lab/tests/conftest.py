"""Pytest configuration to ensure tests use isolated settings.

The test suite uses SQLite in-memory databases, but pydantic-settings
inherits validation_alias from the parent Settings class, which causes
DATABASE_URL and GITHUB_TOKEN environment variables to leak into tests.
This conftest removes those env vars before test collection.
"""
import os

# Remove env vars that pydantic-settings would read before test collection
for _var in ("DATABASE_URL", "GITHUB_TOKEN", "GITHUB_BASE_URL",
             "MODEL_PROVIDER", "MODEL_NAME", "MODEL_BASE_URL", "MODEL_API_KEY"):
    os.environ.pop(_var, None)

# Also clear the lru_cache on get_settings so it doesn't return stale configs
import integration_lab.config as _cfg
_cfg.get_settings.cache_clear()

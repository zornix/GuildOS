"""Mark the process as a test run before api.config is imported (F-007)."""
import os

os.environ.setdefault("APP_ENV", "test")

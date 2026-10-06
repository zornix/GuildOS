"""The tracked configuration reference lists exactly the supported names."""
import re
from pathlib import Path

from api.config import Settings


def test_env_example_matches_settings():
    example = Path(__file__).resolve().parents[2] / ".env.example"
    names = set(re.findall(r"^\s*#?\s*([A-Z][A-Z0-9_]*)=", example.read_text(), re.M))
    fields = set(Settings.model_fields)
    assert fields - names == set(), f"Missing setting names: {sorted(fields - names)}"
    assert names - fields - {"TEST_DATABASE_URL", "SUPABASE_DB_URL", "PROD_DATABASE_URL"} == set()

"""Test environment isolation.

The test suite must run fully offline against the in-memory store (see the
"Runs with zero API keys" section of the README), regardless of what
backend/.env holds locally for manual testing (e.g. real Supabase
credentials) — otherwise pytest would silently read from and write test
conversations into a real project.

pydantic-settings gives real environment variables priority over the .env
file, so setting these here (before any test module imports app.config)
reliably forces the offline in-memory path no matter what's in .env.
"""
import os

os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""

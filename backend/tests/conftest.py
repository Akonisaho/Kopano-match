"""Tests never reach a real AI or email provider, whatever keys are in backend/.env.

Otherwise a developer who has added a Gemini or Brevo key would send live requests, and real
emails to test addresses, every time the suite runs. Tests that need AI output patch the client.
"""

import pytest

from app.config import settings


@pytest.fixture(autouse=True, scope="session")
def _offline_providers():
    saved = (settings.email_provider, settings.llm_provider, settings.gemini_api_key)
    settings.email_provider = "log"
    settings.llm_provider = "none"
    settings.gemini_api_key = ""
    yield
    settings.email_provider, settings.llm_provider, settings.gemini_api_key = saved

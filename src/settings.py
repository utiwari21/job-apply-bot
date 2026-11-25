from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

from src.models import ROOT


load_dotenv(ROOT / ".env")


def load_yaml(rel: str) -> dict:
    path = ROOT / rel
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def gmail_address() -> str:
    return os.environ.get("GMAIL_ADDRESS", "").strip()


def gmail_app_password() -> str:
    return os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "")


def gemini_api_key() -> str:
    return os.environ.get("GEMINI_API_KEY", os.environ.get("OPENAI_API_KEY", "")).strip()


def gemini_model() -> str:
    return os.environ.get("GEMINI_MODEL", os.environ.get("OPENAI_MODEL", "gemini-2.5-flash")).strip()


def openai_api_key() -> str:
    return gemini_api_key()


def openai_model() -> str:
    return gemini_model()

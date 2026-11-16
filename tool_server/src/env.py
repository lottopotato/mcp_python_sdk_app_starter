"""Typed readers for settings in the environment / `.env` (loaded once on import)."""
from __future__ import annotations

from typing import Optional

import os

from dotenv import load_dotenv

load_dotenv()


def get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    if value is None or value.strip() == '':
        return default
    return value.strip()


def get_env_int(name: str, default: int) -> int:
    value = get_env(name)
    return int(value) if value is not None else default


def get_env_float(name: str, default: float) -> float:
    value = get_env(name)
    return float(value) if value is not None else default


def get_env_bool(name: str, default: bool = False) -> bool:
    value = get_env(name)
    if value is None:
        return default
    return value.lower() in ('1', 'true', 'yes', 'on')


def get_env_list(name: str, default: Optional[list[str]] = None) -> list[str]:
    value = get_env(name)
    if value is None:
        return list(default or [])
    return [item.strip() for item in value.split(',') if item.strip()]

"""Vendored Math@Home logic: catalogue, checkers, submission format, scrubber.

Refreshed from the app by its tools/sync_hub.py; do not edit the copies here.
"""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def catalog() -> dict:
  return json.loads((HERE / "catalog.json").read_text(encoding="utf-8"))


def problems() -> dict[str, dict]:
  return {item["id"]: item for item in catalog()["problems"]}


def points_rules() -> dict:
  return catalog()["points"]

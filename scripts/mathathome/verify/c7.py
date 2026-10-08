"""Independent sets in strong powers of the 7-cycle.

Two words u, v of length k are confusable (adjacent in C₇^⊠k) when every
coordinate differs by 0 or ±1 modulo 7. A set with no confusable pair of
distinct words gives Θ(C₇) ≥ N^(1/k).
"""

from __future__ import annotations

from decimal import Decimal, localcontext
from itertools import product

_PURE_PYTHON_LIMIT = 6_000_000  # words × 3^k neighbourhood probes


def _value(size: int, power: int) -> Decimal:
  with localcontext() as ctx:
    ctx.prec = 50
    return (Decimal(size).ln() / Decimal(power)).exp()


def _confusable_numpy(words: list[tuple[int, ...]]):
  import numpy as np

  arr = np.asarray(words, dtype=np.int16)
  total = arr.shape[0]
  block = max(1, min(512, 20_000_000 // max(1, total * arr.shape[1])))
  for start in range(0, total, block):
    chunk = arr[start:start + block]
    diff = (chunk[:, None, :] - arr[None, :, :]) % 7
    close = ((diff <= 1) | (diff == 6)).all(axis=2)
    for offset in range(chunk.shape[0]):
      close[offset, start + offset] = False
    hits = np.argwhere(close)
    if hits.size:
      i, j = hits[0]
      return words[start + int(i)], words[int(j)]
  return None


def _confusable_pure(words: list[tuple[int, ...]], power: int):
  members = set(words)
  steps = [step for step in product((-1, 0, 1), repeat=power) if any(step)]
  for word in words:
    for step in steps:
      other = tuple((a + d) % 7 for a, d in zip(word, step))
      if other in members:
        return word, other
  return None


def check(spec: dict, certificate: dict) -> dict:
  power = certificate.get("power")
  if isinstance(power, bool) or not isinstance(power, int) or not 1 <= power <= int(spec.get("max_power", 8)):
    return {"status": "invalid", "value": None, "detail": f"power must be a whole number from 1 to {spec.get('max_power', 8)}."}
  raw = certificate.get("words")
  if not isinstance(raw, list) or not raw:
    return {"status": "invalid", "value": None, "detail": "words must be a non-empty list."}
  limit = int(spec.get("max_words", 20000))
  if len(raw) > limit:
    return {
      "status": "unsupported",
      "value": None,
      "detail": f"More than {limit} words: too large for the built-in checker. Submit it as a claim with your own checker.",
    }
  words = []
  for item in raw:
    if not isinstance(item, (list, tuple)) or len(item) != power:
      return {"status": "invalid", "value": None, "detail": f"Every word must have exactly {power} symbols."}
    word = []
    for symbol in item:
      if isinstance(symbol, bool) or not isinstance(symbol, int) or not 0 <= symbol <= 6:
        return {"status": "invalid", "value": None, "detail": "Symbols must be whole numbers 0–6."}
      word.append(symbol)
    words.append(tuple(word))
  if len(set(words)) != len(words):
    return {"status": "invalid", "value": None, "detail": "Some words are repeated."}
  try:
    clash = _confusable_numpy(words)
  except ImportError:
    if len(words) * (3 ** power) > _PURE_PYTHON_LIMIT:
      return {
        "status": "unsupported",
        "value": None,
        "detail": "Too large to check without numpy on this Möbius. Submit it as a claim.",
      }
    clash = _confusable_pure(words, power)
  if clash:
    u, v = clash
    return {
      "status": "invalid",
      "value": None,
      "detail": f"Not independent: {list(u)} and {list(v)} are confusable (each coordinate differs by at most 1 mod 7).",
    }
  value = _value(len(words), power)
  shown = f"{value:.10f}"
  record = Decimal(str(spec.get("record_value", "0")))
  margin = Decimal(str(spec.get("record_margin", "0")))
  if value > record + margin:
    return {
      "status": "record",
      "value": shown,
      "detail": f"Independent set of {len(words)} words in C₇^⊠{power}: Θ(C₇) ≥ {shown}, above the record {record}.",
    }
  return {
    "status": "valid",
    "value": shown,
    "detail": f"Independent set of {len(words)} words in C₇^⊠{power}: Θ(C₇) ≥ {shown} (record {record}).",
  }

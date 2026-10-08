"""Ruzsa's classical square-difference-free construction.

If m is square-free and R ⊆ ℤ_m has no two distinct elements whose difference
(in either order) is congruent to a square mod m, base-m expansions with digits
from R in alternate positions give r(N) ≥ N^(½(1 + log|R| / log m)).
"""

from __future__ import annotations

from decimal import Decimal, localcontext


def _square_free(m: int) -> bool:
  d = 2
  while d * d <= m:
    if m % (d * d) == 0:
      return False
    d += 1
  return True


def check(spec: dict, certificate: dict) -> dict:
  m = certificate.get("modulus")
  if isinstance(m, bool) or not isinstance(m, int) or not 2 <= m <= int(spec.get("max_modulus", 2_000_000)):
    return {"status": "invalid", "value": None, "detail": "modulus must be a whole number from 2 to 2,000,000."}
  if not _square_free(m):
    return {"status": "invalid", "value": None, "detail": f"{m} is not square-free."}
  raw = certificate.get("residues")
  if not isinstance(raw, list) or len(raw) < 2:
    return {"status": "invalid", "value": None, "detail": "residues must list at least two residues."}
  residues = []
  for item in raw:
    if isinstance(item, bool) or not isinstance(item, int) or not 0 <= item < m:
      return {"status": "invalid", "value": None, "detail": f"Residues must be whole numbers 0…{m - 1}."}
    residues.append(item)
  if len(set(residues)) != len(residues):
    return {"status": "invalid", "value": None, "detail": "Some residues are repeated."}
  is_square = bytearray(m)
  for x in range(m):
    is_square[x * x % m] = 1
  for r in residues:
    for s in residues:
      if r != s and is_square[(r - s) % m]:
        return {
          "status": "invalid",
          "value": None,
          "detail": f"{r} − {s} ≡ {(r - s) % m} is a square mod {m}.",
        }
  with localcontext() as ctx:
    ctx.prec = 40
    exponent = (1 + Decimal(len(residues)).ln() / Decimal(m).ln()) / 2
  shown = f"{exponent:.8f}"
  record = Decimal(str(spec.get("record_value", "1")))
  side = Decimal(str(spec.get("side_record_value", "1")))
  detail = f"m = {m}, |R| = {len(residues)}: exponent ½(1 + log|R|/log m) = {shown}"
  if exponent > record:
    return {"status": "record", "value": shown, "detail": detail + f", above the overall record {record}."}
  if exponent > side + Decimal("0.000000001"):
    return {"status": "side_record", "value": shown, "detail": detail + f", beating the classical record {side:.6f}."}
  return {"status": "valid", "value": shown, "detail": detail + f" (classical record {side:.6f}, overall {record})."}

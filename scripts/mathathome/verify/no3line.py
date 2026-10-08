"""No-three-in-line: 2n grid points with no three on a common line."""

from __future__ import annotations

from math import gcd


def _integer(value, name: str) -> int:
  if isinstance(value, bool) or not isinstance(value, int):
    raise ValueError(f"{name} must be a whole number")
  return value


def check(spec: dict, certificate: dict) -> dict:
  n = _integer(certificate.get("n"), "n")
  if not 2 <= n <= int(spec.get("max_n", 400)):
    return {"status": "invalid", "value": None, "detail": f"n must be between 2 and {spec.get('max_n', 400)}."}
  raw = certificate.get("points")
  if not isinstance(raw, list):
    return {"status": "invalid", "value": None, "detail": "points must be a list of [x, y] pairs."}
  points = []
  for item in raw:
    if not isinstance(item, (list, tuple)) or len(item) != 2:
      return {"status": "invalid", "value": None, "detail": "Every point must be a pair [x, y]."}
    x, y = _integer(item[0], "x"), _integer(item[1], "y")
    if not (1 <= x <= n and 1 <= y <= n):
      return {"status": "invalid", "value": None, "detail": f"Point {[x, y]} is outside the {n} × {n} grid (use 1…{n})."}
    points.append((x, y))
  if len(set(points)) != len(points):
    return {"status": "invalid", "value": None, "detail": "Some points are repeated."}
  if len(points) != 2 * n:
    return {
      "status": "invalid",
      "value": None,
      "detail": f"Expected exactly {2 * n} points for n = {n}, got {len(points)}.",
    }
  lines: dict[tuple[int, int, int], set[int]] = {}
  for i in range(len(points)):
    x1, y1 = points[i]
    for j in range(i + 1, len(points)):
      x2, y2 = points[j]
      a, b = y2 - y1, x1 - x2
      g = gcd(a, b)
      a, b = a // g, b // g
      if a < 0 or (a == 0 and b < 0):
        a, b = -a, -b
      key = (a, b, a * x1 + b * y1)
      members = lines.setdefault(key, set())
      members.add(i)
      members.add(j)
      if len(members) >= 3:
        trio = sorted(members)[:3]
        return {
          "status": "invalid",
          "value": str(n),
          "detail": "Three points are collinear: " + ", ".join(str(list(points[k])) for k in trio) + ".",
        }
  open_n = set(spec.get("open_n", []))
  open_from = spec.get("open_from")
  if n in open_n or (isinstance(open_from, int) and n >= open_from):
    return {
      "status": "record",
      "value": str(n),
      "detail": f"Valid: {2 * n} points on the {n} × {n} grid, no three collinear — no configuration of this size was known.",
    }
  return {
    "status": "valid",
    "value": str(n),
    "detail": f"Valid: {2 * n} points on the {n} × {n} grid, no three collinear (this size was already solved).",
  }

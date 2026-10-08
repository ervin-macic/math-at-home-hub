"""Keep credentials and personal details out of anything that leaves this Möbius.

Used twice: by the app before it prepares a public submission, and by the
community hub on every incoming submission (a vendored copy). Matching is
deliberately broad for credentials, because a false positive costs a
redacted word while a miss would publish someone's key.
"""

from __future__ import annotations

import re

REDACTED = "[redacted]"

# Credential shapes. Each must stay specific enough not to match the hex
# fingerprints and number lists that certificates legitimately contain.
CREDENTIAL_PATTERNS = [
  re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}"),
  re.compile(r"\bsk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_\-]{20,}"),
  re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
  re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}"),
  re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
  re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
  re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"),
  re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"),
  re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/\-]{16,}=*"),
  re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|$)"),
  re.compile(
    r"(?i)\b(?:api[_\-]?key|secret|token|passw(?:or)?d|access[_\-]?key|auth[_\-]?key|client[_\-]?secret)"
    r"\b[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9/+_\-.~]{12,}"
  ),
  re.compile(r"(?i)\b(?:AGENT_TOKEN|APP_TOKEN|ANTHROPIC_API_KEY|OPENAI_API_KEY|GITHUB_TOKEN|GH_TOKEN)\b\s*[:=]\s*\S+"),
]

# Personal or machine details that are not credentials but are nobody's business.
PERSONAL_PATTERNS = [
  (re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"), "[email removed]"),
  (re.compile(r"(?<![\w.])/(?:data|home|root|Users|tmp|var|etc|app)/[^\s\"'`)>\]]+"), "[local path]"),
  (re.compile(r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0)(?::\d+)?[^\s\"'`)>\]]*"), "[local address]"),
]


def find_credentials(text: str) -> list[str]:
  """Names of credential patterns present in ``text`` (empty when clean)."""
  if not isinstance(text, str) or not text:
    return []
  return [pattern.pattern[:24] for pattern in CREDENTIAL_PATTERNS if pattern.search(text)]


def scrub(text: str) -> tuple[str, int]:
  """Redact credentials and personal details. Returns the text and a count."""
  if not isinstance(text, str) or not text:
    return text, 0
  count = 0
  for pattern in CREDENTIAL_PATTERNS:
    text, n = pattern.subn(REDACTED, text)
    count += n
  for pattern, replacement in PERSONAL_PATTERNS:
    text, n = pattern.subn(replacement, text)
    count += n
  return text, count


def scrub_tree(value):
  """Scrub every string inside a JSON-like value. Returns (value, count)."""
  if isinstance(value, str):
    return scrub(value)
  if isinstance(value, list):
    total, items = 0, []
    for item in value:
      cleaned, n = scrub_tree(item)
      items.append(cleaned)
      total += n
    return items, total
  if isinstance(value, dict):
    total, result = 0, {}
    for key, item in value.items():
      cleaned, n = scrub_tree(item)
      result[key] = cleaned
      total += n
    return result, total
  return value, 0

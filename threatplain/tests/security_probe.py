#!/usr/bin/env python3
"""
ThreatPlain Security Probe
Red-team script — run against a live server.

Usage:
  python tests/security_probe.py                    # default: http://localhost:8000
  python tests/security_probe.py http://host:8000   # custom target
"""
import sys
import time

import httpx

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8000"

# ── ANSI colours ──────────────────────────────────────────────────────────────
RESET  = "\033[0m"
GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
BOLD   = "\033[1m"

_results: list[tuple[str, bool, bool, str]] = []  # (name, passed, warn, detail)


def check(name: str, passed: bool, detail: str = "", warn: bool = False) -> None:
    _results.append((name, passed, warn, detail))
    if warn:
        label = f"{YELLOW}WARN{RESET}"
    elif passed:
        label = f"{GREEN}PASS{RESET}"
    else:
        label = f"{RED}FAIL{RESET}"
    print(f"  [{label}] {name}")
    if detail:
        print(f"         ↳ {detail}")


def post_lookup(value: str, **kwargs) -> httpx.Response:
    return httpx.post(
        f"{BASE}/api/lookup",
        json={"value": value},
        timeout=10,
        **kwargs,
    )


# ══════════════════════════════════════════════════════════════════════════════
print(f"\n{BOLD}ThreatPlain Security Probe{RESET}")
print(f"Target: {BASE}\n")


# ── 0. Connectivity ──────────────────────────────────────────────────────────
print(f"{BOLD}Connectivity{RESET}")
try:
    _ping = httpx.get(BASE, timeout=5)
    check("Server reachable", _ping.status_code in (200, 404, 422))
except Exception as exc:
    check("Server reachable", False, str(exc))
    print(f"\n{RED}Cannot reach {BASE} — is the server running?{RESET}\n")
    sys.exit(1)


# ── 1. Security headers ──────────────────────────────────────────────────────
print(f"\n{BOLD}Security Headers{RESET}")
_hdrs = httpx.get(BASE, timeout=5).headers
check(
    "X-Content-Type-Options: nosniff",
    _hdrs.get("x-content-type-options", "").lower() == "nosniff",
)
check(
    "X-Frame-Options present",
    "x-frame-options" in _hdrs,
    _hdrs.get("x-frame-options", "(missing)"),
)
check(
    "Content-Security-Policy present",
    "content-security-policy" in _hdrs,
)
check(
    "Referrer-Policy present",
    "referrer-policy" in _hdrs,
    _hdrs.get("referrer-policy", "(missing)"),
)


# ── 2. Input validation ──────────────────────────────────────────────────────
print(f"\n{BOLD}Input Validation{RESET}")

r = post_lookup("")
check("Empty string → 400 or 422", r.status_code in (400, 422), f"Got {r.status_code}")

r = httpx.post(f"{BASE}/api/lookup", json={}, timeout=10)
check("Missing 'value' field → 422", r.status_code == 422, f"Got {r.status_code}")

r = post_lookup("A" * 200_000)
check(
    "200 KB payload → 422 or 413 (not 500)",
    r.status_code in (413, 422),
    f"Got {r.status_code}",
)

r = post_lookup("8.8.8.8\x00injected")
check(
    "Null byte in value → handled (not 500)",
    r.status_code != 500,
    f"Got {r.status_code}",
)

r = httpx.post(
    f"{BASE}/api/lookup",
    content="value=test",
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    timeout=10,
)
check(
    "Form-encoded body → 422 or 415 (not 500)",
    r.status_code in (415, 422),
    f"Got {r.status_code}",
)


# ── 3. Error message disclosure ──────────────────────────────────────────────
print(f"\n{BOLD}Error Message Disclosure{RESET}")

r = post_lookup("not a recognisable indicator at all")
body = r.text
check(
    "422 response doesn't expose internal env var names",
    "API_KEY" not in body and "VIRUSTOTAL" not in body,
    f"Body: {body[:120]}" if ("API_KEY" in body or "VIRUSTOTAL" in body) else "",
)
check(
    "422 response doesn't contain Python tracebacks",
    "Traceback" not in body and 'File "' not in body,
    f"Body: {body[:120]}" if "Traceback" in body else "",
)
check(
    "500 responses don't expose internal details",
    "Internal Server Error" not in body or len(body) < 300,
    detail="",
    warn=True,  # informational
)


# ── 4. Result ID security ────────────────────────────────────────────────────
print(f"\n{BOLD}Result ID Handling{RESET}")

r = httpx.get(f"{BASE}/api/result/" + "a" * 500, timeout=10)
check(
    "500-char result_id → 404 or 422 (not 500)",
    r.status_code in (404, 422),
    f"Got {r.status_code}",
)

r = httpx.get(f"{BASE}/api/result/doesnotexist", timeout=10)
check("Non-existent valid-format ID → 404", r.status_code == 404, f"Got {r.status_code}")

# SQLi in result_id — parameterized queries should handle this
r = httpx.get(f"{BASE}/api/result/'; DROP TABLE lookups; --", timeout=10)
check(
    "SQL injection in result_id → not 500",
    r.status_code != 500,
    f"Got {r.status_code}",
)


# ── 5. SQL injection via lookup value ────────────────────────────────────────
print(f"\n{BOLD}SQL Injection via Lookup Value{RESET}")

_sqli_payloads = [
    "' OR '1'='1",
    "1; DROP TABLE lookups; --",
    "' UNION SELECT id,input,input_type,raw_results,synthesis,created_at FROM lookups --",
    "\\'; --",
]
for payload in _sqli_payloads:
    r = post_lookup(payload)
    check(
        f"SQLi payload handled safely: {payload[:35]}…",
        r.status_code in (200, 400, 422) and r.status_code != 500,
        f"Got {r.status_code}",
    )


# ── 6. Rate limiting ─────────────────────────────────────────────────────────
print(f"\n{BOLD}Rate Limiting{RESET}")
print("  (firing 15 rapid requests — this takes ~2 seconds)")

_statuses: list[int] = []
for _ in range(15):
    _r = post_lookup("not-a-real-indicator-at-all")
    _statuses.append(_r.status_code)

_got_429 = 429 in _statuses
check(
    "Rate limiter returns 429 after burst of 15",
    _got_429,
    f"Statuses seen: {sorted(set(_statuses))}",
)
check(
    "Non-429 requests get a useful response (not 500)",
    all(s != 500 for s in _statuses),
    f"500s seen: {_statuses.count(500)}",
)


# ── 7. CORS ──────────────────────────────────────────────────────────────────
print(f"\n{BOLD}CORS Policy{RESET}")

r = httpx.get(BASE, headers={"Origin": "https://evil.example.com"}, timeout=10)
acao = r.headers.get("access-control-allow-origin", "")
check(
    "No wildcard CORS (Access-Control-Allow-Origin: *)",
    acao != "*",
    f"ACAO: {acao or '(not set)'}",
)


# ── 8. API key exposure ──────────────────────────────────────────────────────
print(f"\n{BOLD}API Key Exposure{RESET}")

_key_patterns = [
    "ANTHROPIC_API_KEY", "VIRUSTOTAL_API_KEY",
    "ABUSEIPDB_API_KEY", "URLSCAN_API_KEY",
]
for endpoint in ["/", "/api/result/nonexistent"]:
    r = httpx.get(f"{BASE}{endpoint}", timeout=10)
    leaked = [p for p in _key_patterns if p in r.text]
    check(
        f"No API key names leaked in {endpoint}",
        not leaked,
        f"Found: {leaked}" if leaked else "",
    )


# ── 9. Result ID entropy (spot-check new IDs) ────────────────────────────────
print(f"\n{BOLD}Result ID Quality{RESET}")

# We can't generate IDs without doing real lookups, but we can check
# that the format validation rejects short IDs
r = httpx.get(f"{BASE}/api/result/ab", timeout=10)   # 2 chars → too short
check(
    "2-char result_id rejected (below minimum entropy threshold)",
    r.status_code in (404, 422),
    f"Got {r.status_code}",
)


# ── Summary ──────────────────────────────────────────────────────────────────
_total   = len(_results)
_passed  = sum(1 for _, p, w, _ in _results if p and not w)
_warned  = sum(1 for _, _, w, _ in _results if w)
_failed  = sum(1 for _, p, w, _ in _results if not p and not w)

print(f"\n{'─' * 55}")
print(
    f"{BOLD}Results:{RESET} "
    f"{GREEN}{_passed} passed{RESET}  "
    f"{YELLOW}{_warned} warned{RESET}  "
    f"{RED}{_failed} failed{RESET}  "
    f"/ {_total} total"
)

if _failed:
    print(f"\n{RED}Failures to investigate:{RESET}")
    for name, passed, warn, detail in _results:
        if not passed and not warn:
            line = f"  • {name}"
            if detail:
                line += f"\n    {detail}"
            print(line)

print()
sys.exit(0 if _failed == 0 else 1)

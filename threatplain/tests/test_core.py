"""
Unit tests for ThreatPlain pure functions.
No server, no API keys, no network required.

Run: pytest tests/test_core.py -v
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import db as db_module
from detect import InputType, detect_input_type
from lookup import (
    _extract_abuse_summary,
    _extract_urlscan_summary,
    _extract_vt_summary,
    _is_private_ip,
    _parse_email_headers,
)
from synthesize import _parse_response


# ─── detect.py ────────────────────────────────────────────────────────────────

class TestDetect:
    @pytest.mark.parametrize("value,expected", [
        # IPs
        ("8.8.8.8",                   InputType.IP),
        ("1.1.1.1",                   InputType.IP),
        ("192.168.1.1",               InputType.IP),
        ("0.0.0.0",                   InputType.IP),
        ("255.255.255.255",           InputType.IP),
        ("2001:4860:4860::8888",      InputType.IP),
        # URLs
        ("https://example.com",       InputType.URL),
        ("http://example.com/path?q=1", InputType.URL),
        ("https://x.y.z/a/b/c",      InputType.URL),
        ("example.com",               InputType.URL),
        ("sub.example.co.uk",         InputType.URL),
        # Hashes
        ("a" * 32,                    InputType.HASH),  # MD5
        ("a" * 40,                    InputType.HASH),  # SHA-1
        ("a" * 64,                    InputType.HASH),  # SHA-256
        ("A" * 64,                    InputType.HASH),  # uppercase
        ("aAbBcCdD" * 8,             InputType.HASH),  # mixed case SHA-256
        # Unknown
        ("not anything special",      InputType.UNKNOWN),
        ("12345",                     InputType.UNKNOWN),
        ("",                          InputType.UNKNOWN),
    ])
    def test_known_types(self, value, expected):
        assert detect_input_type(value) == expected

    def test_email_headers_detected(self):
        headers = (
            "Received: from x.com [1.2.3.4]\n"
            "From: a@b.com\n"
            "Subject: hi\n"
            "DKIM-Signature: v=1"
        )
        assert detect_input_type(headers) == InputType.EMAIL_HEADER

    def test_email_headers_require_two_signals(self):
        # Only one signal — should NOT be detected as email header
        assert detect_input_type("From: a@b.com") == InputType.UNKNOWN

    def test_hash_wrong_length_is_unknown(self):
        assert detect_input_type("a" * 33) == InputType.UNKNOWN
        assert detect_input_type("a" * 63) == InputType.UNKNOWN

    def test_non_hex_same_length_is_unknown(self):
        assert detect_input_type("g" * 32) == InputType.UNKNOWN  # 'g' is not hex

    def test_strip_whitespace(self):
        assert detect_input_type("  8.8.8.8  ") == InputType.IP
        assert detect_input_type("  https://example.com  ") == InputType.URL


# ─── lookup.py — field extractors ─────────────────────────────────────────────

_VT_FULL = {
    "data": {
        "attributes": {
            "last_analysis_stats": {
                "malicious": 12, "suspicious": 3, "harmless": 55, "undetected": 7
            },
            "reputation": -50,
            "as_owner": "EVIL-ASN",
            "country": "XX",
            "meaningful_name": "trojan.exe",
            "type_description": "PE32",
        }
    }
}


class TestVTSummary:
    def test_detection_counts(self):
        r = _extract_vt_summary(_VT_FULL)
        assert r["malicious"] == 12
        assert r["suspicious"] == 3
        assert r["total"] == 77

    def test_metadata_fields(self):
        r = _extract_vt_summary(_VT_FULL)
        assert r["as_owner"] == "EVIL-ASN"
        assert r["meaningful_name"] == "trojan.exe"

    def test_error_passthrough(self):
        r = _extract_vt_summary({"error": "API key not configured"})
        assert "error" in r

    def test_empty_dict(self):
        r = _extract_vt_summary({})
        assert "error" in r

    def test_analysis_stats_fallback(self):
        # Analysis endpoint uses "stats", not "last_analysis_stats"
        raw = {"data": {"attributes": {"stats": {"malicious": 5, "harmless": 60}}}}
        r = _extract_vt_summary(raw)
        assert r["malicious"] == 5
        assert r["total"] == 65

    def test_no_stats_gives_zero_total(self):
        raw = {"data": {"attributes": {"reputation": 0}}}
        r = _extract_vt_summary(raw)
        assert r["total"] == 0
        assert r["malicious"] == 0

    def test_clean_result(self):
        raw = {"data": {"attributes": {
            "last_analysis_stats": {"malicious": 0, "suspicious": 0, "harmless": 72, "undetected": 0}
        }}}
        r = _extract_vt_summary(raw)
        assert r["malicious"] == 0
        assert r["total"] == 72


class TestAbuseSummary:
    def test_normal_response(self):
        raw = {"data": {
            "abuseConfidenceScore": 94,
            "totalReports": 23,
            "isp": "BadISP",
            "countryCode": "CN",
            "usageType": "Data Center",
            "domain": "evil.com",
            "isTor": False,
        }}
        r = _extract_abuse_summary(raw)
        assert r["abuse_confidence"] == 94
        assert r["total_reports"] == 23
        assert r["isp"] == "BadISP"
        assert r["is_tor"] is False

    def test_error_passthrough(self):
        r = _extract_abuse_summary({"error": "API key not configured"})
        assert "error" in r

    def test_empty_dict(self):
        r = _extract_abuse_summary({})
        assert "error" in r

    def test_missing_data_key(self):
        r = _extract_abuse_summary({"data": {}})
        assert r["abuse_confidence"] is None


class TestURLScanSummary:
    def test_malicious_with_screenshot(self):
        raw = {
            "verdicts": {"overall": {
                "verdict": "malicious", "score": 100,
                "malicious": True, "phishing": False,
            }},
            "task": {"screenshotURL": "https://urlscan.io/screenshots/abc.png"},
            "page": {"domain": "evil.com", "title": "Fake Bank"},
        }
        r = _extract_urlscan_summary(raw)
        assert r["malicious"] is True
        assert r["screenshot_url"] == "https://urlscan.io/screenshots/abc.png"
        assert r["verdict"] == "malicious"
        assert r["domain"] == "evil.com"

    def test_safe_result(self):
        raw = {
            "verdicts": {"overall": {"verdict": "safe", "score": 0, "malicious": False, "phishing": False}},
            "task": {},
            "page": {"domain": "google.com"},
        }
        r = _extract_urlscan_summary(raw)
        assert r["malicious"] is False
        assert r.get("screenshot_url") is None

    def test_pending_scan(self):
        r = _extract_urlscan_summary({"status": "scan_pending", "uuid": "abc123"})
        assert r["status"] == "pending"
        assert r["uuid"] == "abc123"

    def test_error(self):
        r = _extract_urlscan_summary({"error": "submission failed: 429"})
        assert "error" in r

    def test_empty(self):
        r = _extract_urlscan_summary({})
        assert "error" in r


# ─── lookup.py — private IP filter ────────────────────────────────────────────

class TestPrivateIP:
    @pytest.mark.parametrize("ip,is_priv", [
        ("10.0.0.1",          True),
        ("10.255.255.255",    True),
        ("172.16.0.1",        True),
        ("172.31.255.255",    True),
        ("192.168.0.1",       True),
        ("192.168.255.255",   True),
        ("127.0.0.1",         True),
        ("127.255.255.255",   True),
        ("169.254.1.1",       True),   # link-local
        ("8.8.8.8",           False),
        ("1.1.1.1",           False),
        ("93.184.216.34",     False),
        ("not-an-ip",         True),   # unparseable → skip
    ])
    def test_classification(self, ip, is_priv):
        assert _is_private_ip(ip) == is_priv

    def test_public_range_172_outside_private(self):
        # 172.15.x.x is NOT private (private is 172.16–172.31)
        assert _is_private_ip("172.15.0.1") is False
        assert _is_private_ip("172.32.0.1") is False


# ─── lookup.py — email header parser ──────────────────────────────────────────

_PHISH_HEADERS = (
    "Received: from evil.com (evil.com [8.8.8.8])\n"
    "        by mail.example.com with ESMTP\n"
    "Received: from [192.168.1.1] by mail.example.com\n"
    "X-Originating-IP: 1.2.3.4\n"
    "From: attacker@evil.com\n"
    "Return-Path: <bounce@evil.com>\n"
    "Subject: You won the lottery!\n"
    "Authentication-Results: mx.google.com;\n"
    "   spf=fail smtp.mailfrom=evil.com;\n"
    "   dkim=fail header.i=@evil.com;\n"
    "   dmarc=fail"
)


class TestEmailParser:
    def test_extracts_public_ips(self):
        p = _parse_email_headers(_PHISH_HEADERS)
        assert "8.8.8.8" in p["ips"]
        assert "1.2.3.4" in p["ips"]

    def test_filters_private_ips(self):
        p = _parse_email_headers(_PHISH_HEADERS)
        assert "192.168.1.1" not in p["ips"]

    def test_spf_dkim_dmarc_fail(self):
        p = _parse_email_headers(_PHISH_HEADERS)
        assert p["auth"]["spf"] == "fail"
        assert p["auth"]["dkim"] == "fail"
        assert p["auth"]["dmarc"] == "fail"

    def test_sender_fields(self):
        p = _parse_email_headers(_PHISH_HEADERS)
        assert "evil.com" in p["from"]
        assert "evil.com" in p["return_path"]
        assert "lottery" in p["subject"]

    def test_no_auth_header(self):
        headers = "Received: from x.com [8.8.8.8]\nFrom: a@b.com\nSubject: hi"
        p = _parse_email_headers(headers)
        assert p["auth"] == {}

    def test_spf_pass(self):
        headers = (
            "Received: from good.com [8.8.8.8]\nFrom: a@b.com\n"
            "Authentication-Results: mx.google.com; spf=pass; dkim=pass; dmarc=pass"
        )
        p = _parse_email_headers(headers)
        assert p["auth"]["spf"] == "pass"
        assert p["auth"]["dmarc"] == "pass"

    def test_ip_deduplication(self):
        # Same IP in both bracket and bare positions — should only appear once
        headers = (
            "Received: from x.com (x.com [8.8.8.8])\nFrom: a@b.com\nSubject: hi"
        )
        p = _parse_email_headers(headers)
        assert p["ips"].count("8.8.8.8") == 1

    def test_no_ips_returns_empty_list(self):
        headers = "From: a@b.com\nSubject: test\nTo: b@c.com"
        p = _parse_email_headers(headers)
        assert p["ips"] == []


# ─── db.py ────────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(db_module, "DB_PATH", db_file)
    db_module.init_db()
    return db_file


class TestDB:
    def test_store_and_retrieve(self, tmp_db):
        raw = {"input_type": "ip", "sources": {"virustotal": {"malicious": 0}}}
        syn = {"threat_level": "SAFE", "what_is_this": "Google DNS."}
        rid = db_module.store_result("8.8.8.8", raw, syn)
        result = db_module.get_result(rid)
        assert result is not None
        assert result["input"] == "8.8.8.8"
        assert result["input_type"] == "ip"
        assert result["synthesis"]["threat_level"] == "SAFE"

    def test_missing_id_returns_none(self, tmp_db):
        assert db_module.get_result("doesnotexist") is None

    def test_raw_results_roundtrip(self, tmp_db):
        raw = {"input_type": "url", "sources": {"virustotal": {"malicious": 5, "total": 72}}}
        syn = {"threat_level": "HIGH"}
        rid = db_module.store_result("https://evil.com", raw, syn)
        result = db_module.get_result(rid)
        assert result["raw_results"]["sources"]["virustotal"]["malicious"] == 5

    def test_unique_ids(self, tmp_db):
        raw = {"input_type": "ip"}
        syn = {"threat_level": "UNKNOWN"}
        ids = {db_module.store_result(f"1.2.3.{i}", raw, syn) for i in range(50)}
        assert len(ids) == 50

    def test_id_length_is_16_chars(self, tmp_db):
        # token_urlsafe(12) → 16-char base64url
        raw = {"input_type": "ip"}
        syn = {"threat_level": "UNKNOWN"}
        rid = db_module.store_result("1.2.3.4", raw, syn)
        assert len(rid) == 16


# ─── synthesize.py — response parser ──────────────────────────────────────────

_FULL_RESPONSE = """THREAT_LEVEL: HIGH

WHAT_IS_THIS:
This is a malicious IP address associated with phishing campaigns.

WHAT_IT_DOES:
It attempts to steal your login credentials via a fake sign-in page.

WHAT_IT_TOUCHES:
- Browser cookies stored on disk
- Saved passwords in your browser
- Session tokens

WHAT_TO_DO:
- Block this IP in your firewall.
- Change any passwords you entered.
- Run a full antivirus scan.
"""


class TestParseResponse:
    def test_all_sections_parsed(self):
        r = _parse_response(_FULL_RESPONSE)
        assert r["threat_level"] == "HIGH"
        assert "malicious IP" in r["what_is_this"]
        assert "credentials" in r["what_it_does"]
        assert "cookies" in r["what_it_touches"]
        assert "Block" in r["what_to_do"]

    def test_all_valid_threat_levels(self):
        for level in ("SAFE", "LOW", "MEDIUM", "HIGH", "CRITICAL"):
            r = _parse_response(f"THREAT_LEVEL: {level}\n")
            assert r["threat_level"] == level

    def test_unknown_is_default(self):
        r = _parse_response("No threat level here.\n\nWHAT_IS_THIS:\nSomething.\n")
        assert r["threat_level"] == "UNKNOWN"

    def test_invalid_threat_level_ignored(self):
        r = _parse_response("THREAT_LEVEL: NUCLEAR\n")
        assert r["threat_level"] == "UNKNOWN"

    def test_case_insensitive_level(self):
        r = _parse_response("THREAT_LEVEL: high\n")
        assert r["threat_level"] == "HIGH"

    def test_missing_section_uses_default(self):
        r = _parse_response("THREAT_LEVEL: LOW\n\nWHAT_IS_THIS:\nA thing.\n")
        assert "Insufficient" in r["what_it_does"]
        # what_it_touches has its own distinct default message
        assert "No specific system changes" in r["what_it_touches"]

    def test_empty_response(self):
        r = _parse_response("")
        assert r["threat_level"] == "UNKNOWN"
        assert r["what_is_this"] != ""  # falls back to default

    def test_multiline_section_content(self):
        r = _parse_response(_FULL_RESPONSE)
        # what_it_touches has bullets — make sure multi-line is preserved
        assert "Session tokens" in r["what_it_touches"]

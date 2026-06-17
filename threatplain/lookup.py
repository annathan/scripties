import asyncio
import base64
import ipaddress
import os
import re
from email.parser import HeaderParser

import httpx

from detect import InputType, detect_input_type

VIRUSTOTAL_KEY = os.getenv("VIRUSTOTAL_API_KEY", "")
ABUSEIPDB_KEY = os.getenv("ABUSEIPDB_API_KEY", "")
URLSCAN_KEY = os.getenv("URLSCAN_API_KEY", "")

VT_BASE = "https://www.virustotal.com/api/v3"
ABUSE_BASE = "https://api.abuseipdb.com/api/v2"
URLSCAN_BASE = "https://urlscan.io/api/v1"

RECEIVED_IP_RE = re.compile(r"\[(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\]")
BARE_IP_RE = re.compile(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b")
URL_IN_TEXT_RE = re.compile(r"https?://[^\s<>\"']+")

# Ranges that are never useful to query threat intel APIs for
_SKIP_NETS = [
    ipaddress.ip_network(n) for n in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "fc00::/7",
        "::1/128",
    )
]


# ─── Utilities ─────────────────────────────────────────────────────────────────

def _is_private_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return addr.is_loopback or any(addr in net for net in _SKIP_NETS)
    except ValueError:
        return True


# ─── Field extractors (produce compact dicts for Claude + frontend) ─────────────

def _extract_vt_summary(raw: dict) -> dict:
    if not raw or "error" in raw:
        return {"error": raw.get("error", "No data")} if raw else {"error": "No data"}

    attrs = raw.get("data", {}).get("attributes", {})
    # Analysis objects use "stats"; file/url/ip objects use "last_analysis_stats"
    stats = attrs.get("last_analysis_stats") or attrs.get("stats") or {}
    total = sum(stats.values()) if stats else 0

    return {
        "malicious": stats.get("malicious", 0),
        "suspicious": stats.get("suspicious", 0),
        "harmless": stats.get("harmless", 0),
        "total": total,
        "reputation": attrs.get("reputation"),
        "last_analysis_date": attrs.get("last_analysis_date"),
        # file fields
        "meaningful_name": attrs.get("meaningful_name"),
        "type_description": attrs.get("type_description"),
        # IP fields
        "country": attrs.get("country"),
        "asn": attrs.get("asn"),
        "as_owner": attrs.get("as_owner"),
        # URL fields
        "categories": attrs.get("categories"),
        "last_final_url": attrs.get("last_final_url"),
    }


def _extract_abuse_summary(raw: dict) -> dict:
    if not raw or "error" in raw:
        return {"error": raw.get("error", "No data")} if raw else {"error": "No data"}

    data = raw.get("data", {})
    return {
        "abuse_confidence": data.get("abuseConfidenceScore"),
        "total_reports": data.get("totalReports"),
        "isp": data.get("isp"),
        "country": data.get("countryCode"),
        "usage_type": data.get("usageType"),
        "domain": data.get("domain"),
        "is_tor": data.get("isTor"),
    }


def _extract_urlscan_summary(raw: dict) -> dict:
    if not raw:
        return {"error": "No data"}
    if "error" in raw:
        return {"error": raw["error"]}
    if raw.get("status") == "scan_pending":
        return {"status": "pending", "uuid": raw.get("uuid")}

    verdicts = raw.get("verdicts", {}).get("overall", {})
    task = raw.get("task", {})
    page = raw.get("page", {})

    return {
        "verdict": verdicts.get("verdict"),
        "score": verdicts.get("score"),
        "malicious": verdicts.get("malicious", False),
        "phishing": verdicts.get("phishing", False),
        "screenshot_url": task.get("screenshotURL"),
        "domain": page.get("domain"),
        "page_title": page.get("title"),
        "country": page.get("country"),
        "ip": page.get("ip"),
    }


# ─── Email header parsing ──────────────────────────────────────────────────────

def _parse_email_headers(text: str) -> dict:
    msg = HeaderParser().parsestr(text)

    # Collect IPs from all Received headers (bracketed and bare)
    ips: list[str] = []
    for received in (msg.get_all("Received") or []):
        ips.extend(RECEIVED_IP_RE.findall(received))
        ips.extend(BARE_IP_RE.findall(received))

    # X-Originating-IP often has a bare IP
    ips.extend(BARE_IP_RE.findall(msg.get("X-Originating-IP", "")))

    # Deduplicate, skip private/loopback
    seen: set[str] = set()
    public_ips: list[str] = []
    for ip in ips:
        if ip not in seen and not _is_private_ip(ip):
            seen.add(ip)
            public_ips.append(ip)

    # Authentication-Results: parse SPF/DKIM/DMARC verdicts
    auth_header = msg.get("Authentication-Results", "")
    auth: dict[str, str] = {}
    for proto in ("spf", "dkim", "dmarc"):
        m = re.search(rf"\b{proto}=(\w+)", auth_header, re.IGNORECASE)
        if m:
            auth[proto] = m.group(1).lower()

    return {
        "from": msg.get("From", ""),
        "return_path": msg.get("Return-Path", ""),
        "subject": msg.get("Subject", ""),
        "message_id": msg.get("Message-ID", ""),
        "ips": public_ips[:5],
        "urls": list(dict.fromkeys(URL_IN_TEXT_RE.findall(text)))[:3],
        "auth": auth,
    }


# ─── VirusTotal ────────────────────────────────────────────────────────────────

def _vt_hdrs() -> dict:
    return {"x-apikey": VIRUSTOTAL_KEY}


async def _vt_ip(client: httpx.AsyncClient, ip: str) -> dict:
    if not VIRUSTOTAL_KEY:
        return {"error": "VIRUSTOTAL_API_KEY not configured"}
    r = await client.get(f"{VT_BASE}/ip_addresses/{ip}", headers=_vt_hdrs())
    return r.json()


async def _vt_hash(client: httpx.AsyncClient, file_hash: str) -> dict:
    if not VIRUSTOTAL_KEY:
        return {"error": "VIRUSTOTAL_API_KEY not configured"}
    r = await client.get(f"{VT_BASE}/files/{file_hash}", headers=_vt_hdrs())
    return r.json()


async def _vt_url(client: httpx.AsyncClient, url: str) -> dict:
    if not VIRUSTOTAL_KEY:
        return {"error": "VIRUSTOTAL_API_KEY not configured"}

    url_id = base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")
    r = await client.get(f"{VT_BASE}/urls/{url_id}", headers=_vt_hdrs())

    if r.status_code == 200:
        return r.json()

    if r.status_code == 404:
        submit = await client.post(
            f"{VT_BASE}/urls", headers=_vt_hdrs(), data={"url": url}
        )
        if submit.status_code not in (200, 201):
            return {"error": f"VT submission failed: {submit.status_code}"}

        analysis_id = submit.json().get("data", {}).get("id")
        if not analysis_id:
            return submit.json()

        for _ in range(4):
            await asyncio.sleep(8)
            ar = await client.get(f"{VT_BASE}/analyses/{analysis_id}", headers=_vt_hdrs())
            if ar.status_code == 200:
                data = ar.json()
                if data.get("data", {}).get("attributes", {}).get("status") == "completed":
                    return data
        return {"status": "analysis_pending", "analysis_id": analysis_id}

    return {"error": f"VT request failed: {r.status_code}"}


# ─── AbuseIPDB ─────────────────────────────────────────────────────────────────

async def _abuseipdb(client: httpx.AsyncClient, ip: str) -> dict:
    if not ABUSEIPDB_KEY:
        return {"error": "ABUSEIPDB_API_KEY not configured"}
    r = await client.get(
        f"{ABUSE_BASE}/check",
        headers={"Key": ABUSEIPDB_KEY, "Accept": "application/json"},
        params={"ipAddress": ip, "maxAgeInDays": 90},
    )
    return r.json()


# ─── URLScan.io ────────────────────────────────────────────────────────────────

async def _urlscan(client: httpx.AsyncClient, url: str) -> dict:
    if not URLSCAN_KEY:
        return {"error": "URLSCAN_API_KEY not configured"}

    submit = await client.post(
        f"{URLSCAN_BASE}/scan/",
        headers={"API-Key": URLSCAN_KEY, "Content-Type": "application/json"},
        json={"url": url, "visibility": "unlisted"},
    )
    if submit.status_code not in (200, 201):
        return {"error": f"URLScan submission failed: {submit.status_code}", "detail": submit.text}

    scan_uuid = submit.json().get("uuid")
    if not scan_uuid:
        return {"error": "No UUID in URLScan response"}

    for _ in range(6):
        await asyncio.sleep(8)
        r = await client.get(f"{URLSCAN_BASE}/result/{scan_uuid}/")
        if r.status_code == 200:
            return r.json()
        if r.status_code != 404:
            return {"error": f"URLScan result error: {r.status_code}"}

    return {
        "status": "scan_pending",
        "uuid": scan_uuid,
        "result_url": f"https://urlscan.io/result/{scan_uuid}/",
    }


# ─── Main pipeline ─────────────────────────────────────────────────────────────

async def run_lookup(value: str) -> dict:
    input_type = detect_input_type(value)
    result: dict = {"input_type": input_type, "input": value}

    async with httpx.AsyncClient(timeout=httpx.Timeout(90.0)) as client:
        try:
            if input_type == InputType.IP:
                vt_raw, abuse_raw = await asyncio.gather(
                    _vt_ip(client, value),
                    _abuseipdb(client, value),
                    return_exceptions=True,
                )
                vt_raw = vt_raw if not isinstance(vt_raw, Exception) else {"error": str(vt_raw)}
                abuse_raw = abuse_raw if not isinstance(abuse_raw, Exception) else {"error": str(abuse_raw)}
                result["sources"] = {
                    "virustotal": _extract_vt_summary(vt_raw),
                    "abuseipdb": _extract_abuse_summary(abuse_raw),
                }

            elif input_type == InputType.URL:
                url = value if value.startswith("http") else f"https://{value}"
                vt_raw, us_raw = await asyncio.gather(
                    _vt_url(client, url),
                    _urlscan(client, url),
                    return_exceptions=True,
                )
                vt_raw = vt_raw if not isinstance(vt_raw, Exception) else {"error": str(vt_raw)}
                us_raw = us_raw if not isinstance(us_raw, Exception) else {"error": str(us_raw)}
                us_summary = _extract_urlscan_summary(us_raw)
                result["sources"] = {
                    "virustotal": _extract_vt_summary(vt_raw),
                    "urlscan": us_summary,
                }
                result["screenshot_url"] = us_summary.get("screenshot_url")

            elif input_type == InputType.HASH:
                vt_raw = await _vt_hash(client, value)
                result["sources"] = {
                    "virustotal": _extract_vt_summary(vt_raw),
                }

            elif input_type == InputType.EMAIL_HEADER:
                parsed = _parse_email_headers(value)

                ip_data: dict = {}
                for ip in parsed["ips"]:
                    vt_raw, abuse_raw = await asyncio.gather(
                        _vt_ip(client, ip),
                        _abuseipdb(client, ip),
                        return_exceptions=True,
                    )
                    ip_data[ip] = {
                        "virustotal": _extract_vt_summary(
                            vt_raw if not isinstance(vt_raw, Exception) else {"error": str(vt_raw)}
                        ),
                        "abuseipdb": _extract_abuse_summary(
                            abuse_raw if not isinstance(abuse_raw, Exception) else {"error": str(abuse_raw)}
                        ),
                    }

                url_summary = None
                if parsed["urls"]:
                    try:
                        url_raw = await _vt_url(client, parsed["urls"][0])
                        url_summary = _extract_vt_summary(url_raw)
                    except Exception as exc:
                        url_summary = {"error": str(exc)}

                result["sources"] = {
                    "email_context": {
                        "from": parsed["from"],
                        "return_path": parsed["return_path"],
                        "subject": parsed["subject"],
                    },
                    "email_auth": parsed["auth"],
                    "urls_found": parsed["urls"],
                    "ip_analysis": ip_data,
                    "url_analysis": url_summary,
                }

            else:
                result["error"] = (
                    "Could not identify this input. "
                    "Please paste a URL, IPv4/IPv6 address, MD5/SHA1/SHA256 hash, or raw email headers."
                )

        except Exception as exc:
            result["pipeline_error"] = str(exc)

    return result

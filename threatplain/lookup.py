import asyncio
import base64
import os
import re

import httpx

from detect import InputType, detect_input_type

VIRUSTOTAL_KEY = os.getenv("VIRUSTOTAL_API_KEY", "")
ABUSEIPDB_KEY = os.getenv("ABUSEIPDB_API_KEY", "")
URLSCAN_KEY = os.getenv("URLSCAN_API_KEY", "")

VT_BASE = "https://www.virustotal.com/api/v3"
ABUSE_BASE = "https://api.abuseipdb.com/api/v2"
URLSCAN_BASE = "https://urlscan.io/api/v1"

RECEIVED_IP_RE = re.compile(r"\[(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\]")
URL_IN_TEXT_RE = re.compile(r"https?://[^\s<>\"']+")


# ─── VirusTotal ────────────────────────────────────────────────────────────────

def _vt_headers() -> dict:
    return {"x-apikey": VIRUSTOTAL_KEY}


async def _vt_ip(client: httpx.AsyncClient, ip: str) -> dict:
    if not VIRUSTOTAL_KEY:
        return {"error": "VIRUSTOTAL_API_KEY not configured"}
    r = await client.get(f"{VT_BASE}/ip_addresses/{ip}", headers=_vt_headers())
    return r.json()


async def _vt_hash(client: httpx.AsyncClient, file_hash: str) -> dict:
    if not VIRUSTOTAL_KEY:
        return {"error": "VIRUSTOTAL_API_KEY not configured"}
    r = await client.get(f"{VT_BASE}/files/{file_hash}", headers=_vt_headers())
    return r.json()


async def _vt_url(client: httpx.AsyncClient, url: str) -> dict:
    if not VIRUSTOTAL_KEY:
        return {"error": "VIRUSTOTAL_API_KEY not configured"}

    url_id = base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")
    r = await client.get(f"{VT_BASE}/urls/{url_id}", headers=_vt_headers())

    if r.status_code == 200:
        return r.json()

    if r.status_code == 404:
        submit = await client.post(
            f"{VT_BASE}/urls", headers=_vt_headers(), data={"url": url}
        )
        if submit.status_code not in (200, 201):
            return {"error": f"VT submission failed: {submit.status_code}"}

        analysis_id = submit.json().get("data", {}).get("id")
        if not analysis_id:
            return submit.json()

        for _ in range(4):
            await asyncio.sleep(8)
            ar = await client.get(f"{VT_BASE}/analyses/{analysis_id}", headers=_vt_headers())
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


# ─── Email header helpers ──────────────────────────────────────────────────────

def _extract_ips(text: str) -> list[str]:
    return list(dict.fromkeys(RECEIVED_IP_RE.findall(text)))


def _extract_urls(text: str) -> list[str]:
    return list(dict.fromkeys(URL_IN_TEXT_RE.findall(text)))


# ─── Main pipeline ─────────────────────────────────────────────────────────────

async def run_lookup(value: str) -> dict:
    input_type = detect_input_type(value)
    result: dict = {"input_type": input_type, "input": value}

    timeout = httpx.Timeout(90.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            if input_type == InputType.IP:
                vt, abuse = await asyncio.gather(
                    _vt_ip(client, value),
                    _abuseipdb(client, value),
                    return_exceptions=True,
                )
                result["virustotal"] = vt if not isinstance(vt, Exception) else {"error": str(vt)}
                result["abuseipdb"] = abuse if not isinstance(abuse, Exception) else {"error": str(abuse)}

            elif input_type == InputType.URL:
                url = value if value.startswith("http") else f"https://{value}"
                vt, us = await asyncio.gather(
                    _vt_url(client, url),
                    _urlscan(client, url),
                    return_exceptions=True,
                )
                result["virustotal"] = vt if not isinstance(vt, Exception) else {"error": str(vt)}
                result["urlscan"] = us if not isinstance(us, Exception) else {"error": str(us)}

            elif input_type == InputType.HASH:
                vt = await _vt_hash(client, value)
                result["virustotal"] = vt

            elif input_type == InputType.EMAIL_HEADER:
                ips = _extract_ips(value)[:3]
                urls = _extract_urls(value)[:2]
                result["extracted_ips"] = ips
                result["extracted_urls"] = urls

                ip_data: dict = {}
                for ip in ips:
                    vt, abuse = await asyncio.gather(
                        _vt_ip(client, ip),
                        _abuseipdb(client, ip),
                        return_exceptions=True,
                    )
                    ip_data[ip] = {
                        "virustotal": vt if not isinstance(vt, Exception) else {"error": str(vt)},
                        "abuseipdb": abuse if not isinstance(abuse, Exception) else {"error": str(abuse)},
                    }
                result["ip_analysis"] = ip_data

                if urls:
                    try:
                        result["url_analysis"] = await _vt_url(client, urls[0])
                    except Exception as exc:
                        result["url_analysis"] = {"error": str(exc)}

            else:
                result["error"] = (
                    "Could not identify this input. "
                    "Please paste a URL, IPv4/IPv6 address, MD5/SHA1/SHA256 hash, or raw email headers."
                )

        except Exception as exc:
            result["pipeline_error"] = str(exc)

    return result

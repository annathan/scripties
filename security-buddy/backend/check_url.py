from __future__ import annotations

import json
import os
import re

import httpx
from anthropic import AsyncAnthropic

SAFE_BROWSING_URL = "https://safebrowsing.googleapis.com/v4/threatMatches:find"

CLAUDE_PROMPT = """\
You are a web safety checker for an app used by children and senior citizens.

URL: {url}
Page title: {page_title}

Answer in this exact JSON format — no extra text, no markdown:
{{"safe": true/false, "reason": "one sentence, plain language", "risk_level": "low/medium/high"}}

Rules:
- Well-known trusted sites (Google, Wikipedia, BBC, NHS, YouTube, Amazon, Facebook, Microsoft, Apple) → safe=true
- Any domain impersonating a trusted brand (g00gle.com, amaz0n-deals.net) → safe=false
- Random-looking domain, many hyphens, looks like a fake login page → safe=false
- Unknown domain you've never heard of → safe=false, err on the side of caution
- reason: NO technical jargon. Never say "malware", "phishing", "SSL", "certificate", "suspicious domain".
  Instead say: "dangerous website", "pretending to be a real company", "might steal your information", "not a safe place to visit".
  Keep it under 20 words and use plain, friendly language.
"""

_anthropic = AsyncAnthropic()


async def _check_safe_browsing(url: str) -> bool | None:
    api_key = os.environ.get("GOOGLE_SAFE_BROWSING_API_KEY", "")
    if not api_key:
        return None  # not configured — skip to Claude

    payload = {
        "client": {"clientId": "safety-buddy", "clientVersion": "1.0"},
        "threatInfo": {
            "threatTypes": ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE", "POTENTIALLY_HARMFUL_APPLICATION"],
            "platformTypes": ["ANY_PLATFORM"],
            "threatEntryTypes": ["URL"],
            "threatEntries": [{"url": url}],
        },
    }
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.post(f"{SAFE_BROWSING_URL}?key={api_key}", json=payload)
            r.raise_for_status()
            data = r.json()
            if data.get("matches"):
                return False  # known threat
            return None  # clean result — still inconclusive (not a definitive safe)
    except Exception:
        return None  # network error — move to Claude


async def _check_with_claude(url: str, page_title: str) -> dict:
    prompt = CLAUDE_PROMPT.format(url=url, page_title=page_title or "")
    try:
        msg = await _anthropic.messages.create(
            model="claude-haiku-4-5",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
        # Strip any accidental markdown fences
        text = re.sub(r"^```json?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        result = json.loads(text)
        # Validate shape
        if not isinstance(result.get("safe"), bool):
            raise ValueError("missing 'safe' boolean")
        return {
            "safe": result["safe"],
            "reason": str(result.get("reason", "This website looks suspicious."))[:200],
            "risk_level": result.get("risk_level", "medium"),
            "source": "claude",
        }
    except Exception:
        # Fail safe — block unknown
        return {
            "safe": False,
            "reason": "We could not check this website. It might not be safe to visit.",
            "risk_level": "medium",
            "source": "error",
        }


async def check_url(url: str, page_title: str = "", use_claude: bool = True) -> dict:
    sb_result = await _check_safe_browsing(url)

    if sb_result is False:
        # Confirmed threat by Safe Browsing
        return {
            "safe": False,
            "reason": "This website has been reported as dangerous by Google's safety system.",
            "risk_level": "high",
            "source": "safe_browsing",
        }

    if not use_claude:
        # Lifetime plan with expired API checking — Safe Browsing passed, report safe
        return {
            "safe": True,
            "reason": "",
            "risk_level": "low",
            "source": "safe_browsing_only",
        }

    return await _check_with_claude(url, page_title)

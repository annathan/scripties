import re
from enum import Enum


class InputType(str, Enum):
    URL = "url"
    IP = "ip"
    HASH = "hash"
    EMAIL_HEADER = "email_header"
    UNKNOWN = "unknown"


EMAIL_HEADER_SIGNALS = (
    "Received:", "From:", "To:", "Subject:", "Return-Path:",
    "DKIM-Signature:", "Authentication-Results:", "X-Originating-IP:",
    "Message-ID:", "Content-Type:", "MIME-Version:",
)

IPV4_RE = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")
IPV6_RE = re.compile(r"^[0-9a-fA-F]{0,4}(:[0-9a-fA-F]{0,4}){2,7}$")
MD5_RE = re.compile(r"^[0-9a-fA-F]{32}$")
SHA1_RE = re.compile(r"^[0-9a-fA-F]{40}$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
DOMAIN_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,}(/.*)?$")


def detect_input_type(value: str) -> InputType:
    stripped = value.strip()

    if "\n" in stripped:
        lines = stripped.splitlines()
        hits = sum(1 for line in lines if any(line.startswith(sig) for sig in EMAIL_HEADER_SIGNALS))
        if hits >= 2:
            return InputType.EMAIL_HEADER

    if re.match(r"^https?://", stripped, re.IGNORECASE):
        return InputType.URL

    if IPV4_RE.match(stripped):
        parts = stripped.split(".")
        if all(0 <= int(p) <= 255 for p in parts):
            return InputType.IP

    if IPV6_RE.match(stripped) and ":" in stripped:
        return InputType.IP

    if MD5_RE.match(stripped) or SHA1_RE.match(stripped) or SHA256_RE.match(stripped):
        return InputType.HASH

    if DOMAIN_RE.match(stripped):
        return InputType.URL

    return InputType.UNKNOWN

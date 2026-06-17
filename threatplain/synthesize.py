import json
import os

import anthropic

MODEL = "claude-sonnet-4-20250514"

SYSTEM_PROMPT = """\
You are a cybersecurity analyst. Your job is to read raw threat-intelligence data \
and write a clear, jargon-free threat card for a non-technical person — \
imagine a worried family member with no IT background.

You will always respond in this exact format (no deviations):

THREAT_LEVEL: <SAFE|LOW|MEDIUM|HIGH|CRITICAL|UNKNOWN>

WHAT_IS_THIS:
<2–4 sentences. What is this thing? A website, an IP address, a file, an email? \
Where does it come from? Who or what operates it?>

WHAT_IT_DOES:
<2–4 sentences. What happens if someone clicks it, opens it, or receives it? \
If it appears benign, say so clearly. Be honest about uncertainty.>

WHAT_IT_TOUCHES:
<A short paragraph or 3–6 bullet points. \
List known files, folders, registry keys, processes, or system changes. \
If none are known for this type of indicator, say: \
"No specific system changes are known for this type of indicator.">

WHAT_TO_DO:
<3–5 bullet points. Specific, actionable steps a non-technical person can take right now.>

Rules:
- Never invent information not in the data.
- If data is insufficient for a section, write: "Insufficient data to determine this."
- Do not use technical jargon without a plain-English explanation in parentheses.
- THREAT_LEVEL must be exactly one of the five values listed.\
"""


def _parse_response(text: str) -> dict:
    fields = {
        "threat_level": "UNKNOWN",
        "what_is_this": "Insufficient data to determine this.",
        "what_it_does": "Insufficient data to determine this.",
        "what_it_touches": "No specific system changes are known for this type of indicator.",
        "what_to_do": "Consult your IT department or a cybersecurity professional.",
    }

    section_map = {
        "WHAT_IS_THIS:": "what_is_this",
        "WHAT_IT_DOES:": "what_it_does",
        "WHAT_IT_TOUCHES:": "what_it_touches",
        "WHAT_TO_DO:": "what_to_do",
    }

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("THREAT_LEVEL:"):
            level = stripped.split(":", 1)[1].strip().upper()
            if level in ("SAFE", "LOW", "MEDIUM", "HIGH", "CRITICAL", "UNKNOWN"):
                fields["threat_level"] = level

    current_key = None
    buffer: list[str] = []

    for line in text.splitlines():
        header = line.strip().upper()
        matched = False
        for marker, key in section_map.items():
            if header.startswith(marker):
                if current_key:
                    fields[current_key] = "\n".join(buffer).strip()
                current_key = key
                buffer = []
                matched = True
                break
        if not matched and current_key:
            buffer.append(line)

    if current_key and buffer:
        fields[current_key] = "\n".join(buffer).strip()

    return fields


async def synthesize_threat(input_value: str, raw_data: dict) -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {
            "threat_level": "UNKNOWN",
            "what_is_this": "ANTHROPIC_API_KEY is not configured.",
            "what_it_does": "Cannot generate analysis without an Anthropic API key.",
            "what_it_touches": "Cannot generate analysis without an Anthropic API key.",
            "what_to_do": "Set the ANTHROPIC_API_KEY environment variable and restart the server.",
        }

    client = anthropic.AsyncAnthropic(api_key=api_key)

    # Use the pre-extracted, compact summaries — avoids truncation problems
    # with large raw API payloads and gives Claude the signal it actually needs.
    intel = raw_data.get("sources") or raw_data
    user_message = (
        f"Indicator submitted: {input_value}\n\n"
        f"Threat intelligence data:\n{json.dumps(intel, indent=2)}\n\n"
        "Write the threat card now."
    )

    message = await client.messages.create(
        model=MODEL,
        max_tokens=1200,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    return _parse_response(message.content[0].text)

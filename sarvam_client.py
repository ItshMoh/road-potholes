"""Sarvam AI calls: pothole check (gemma4), complaint letter (sarvam-105b), translation (mayura:v1)."""
import base64
import json
import os
import re
from functools import lru_cache

import httpx
from dotenv import load_dotenv
from sarvamai import SarvamAI
from sarvamai.core.api_error import ApiError

load_dotenv()

VISION_MODEL = "gemma4"
WRITER_MODEL = "sarvam-105b"
TRANSLATE_MODEL = "mayura:v1"
MAX_TRANSLATE_CHARS = 1000
# The SDK retries 408/409/429/5xx with backoff by itself; the spec wants one retry.
REQUEST_OPTIONS = {"max_retries": 1, "timeout_in_seconds": 90}

HINGLISH = "hinglish"
# Dropdown label -> translate() target. None = English only.
LANGUAGES = {
    "English only": None,
    "Hindi": "hi-IN",
    "Hinglish (Roman script)": HINGLISH,
    "Bengali": "bn-IN",
    "Gujarati": "gu-IN",
    "Kannada": "kn-IN",
    "Malayalam": "ml-IN",
    "Marathi": "mr-IN",
    "Odia": "od-IN",
    "Punjabi": "pa-IN",
    "Tamil": "ta-IN",
    "Telugu": "te-IN",
}

_STATUS_MESSAGES = {
    401: "Sarvam API key is invalid. Check SARVAM_API_KEY in .env.",
    403: "Sarvam API key is invalid. Check SARVAM_API_KEY in .env.",
    402: "Your Sarvam account is out of credits. Top up and try again.",
    429: "Sarvam rate limit reached. Wait a minute and try again.",
    503: "Sarvam service is busy right now. Try again shortly.",
}

POTHOLE_PROMPT = """You are inspecting a road photo for a civic complaint.
Decide if the photo clearly shows a pothole or damaged road surface.
Severity: low = small/shallow, medium = noticeable/slows traffic,
high = deep or large, dangerous for two-wheelers or pedestrians.
Describe only what is visible. Do not guess the location."""

POTHOLE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "pothole_check",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "is_pothole": {"type": "boolean"},
                "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                "description": {
                    "type": "string",
                    "description": "1-2 sentences: size, depth, water, position on road",
                },
            },
            "required": ["is_pothole", "severity", "description"],
            "additionalProperties": False,
        },
    },
}

COMPLAINT_PROMPT = """You write formal, polite and concise complaint emails from Indian citizens
to municipal or highway authorities about road potholes.
Use ONLY the facts given. Never invent names, complaint numbers,
officer names, dates or locations.
Do NOT write GPS coordinates or links; they are added separately.
Body under 180 words. Include: the problem, where it is (address + landmark),
severity and safety risk, a clear request for repair, and the reporter's
name and phone. End with "Yours sincerely, <name>"."""

COMPLAINT_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "complaint_email",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {"subject": {"type": "string"}, "body": {"type": "string"}},
            "required": ["subject", "body"],
            "additionalProperties": False,
        },
    },
}


class SarvamError(Exception):
    """A failure whose message can be shown to the user as-is."""


def _client() -> SarvamAI:
    key = os.getenv("SARVAM_API_KEY", "").strip()
    if not key:
        raise SarvamError("SARVAM_API_KEY is missing.")
    return _client_for(key)


@lru_cache(maxsize=1)
def _client_for(key: str) -> SarvamAI:
    """Cached per key, so an updated key (e.g. edited Streamlit secrets) is picked up without a restart."""
    return SarvamAI(api_subscription_key=key)


def _call(fn, **kwargs):
    try:
        return fn(**kwargs, request_options=REQUEST_OPTIONS)
    except ApiError as e:
        message = _STATUS_MESSAGES.get(e.status_code, f"Sarvam API error {e.status_code}: {e.body}")
        raise SarvamError(message) from e
    except httpx.HTTPError as e:
        raise SarvamError(f"Could not reach Sarvam: {e}") from e


def _json_reply(response, required: tuple[str, ...]) -> dict | None:
    """Parsed JSON object from message.content (reasoning_content is ignored), or None if invalid."""
    content = (response.choices[0].message.content or "").strip()
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content)
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or any(k not in data for k in required):
        return None
    return data


def check_pothole(image_bytes: bytes) -> dict:
    """{is_pothole, severity, description} for a resized JPEG (see photo.resize_photo)."""
    data_uri = "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode()
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": POTHOLE_PROMPT},
                {"type": "image_url", "image_url": {"url": data_uri}},
            ],
        }
    ]
    for _ in range(2):  # retry once on invalid JSON
        response = _call(
            _client().chat.completions_v2,
            model=VISION_MODEL,
            messages=messages,
            temperature=0.1,
            response_format=POTHOLE_FORMAT,
        )
        result = _json_reply(response, ("is_pothole", "severity", "description"))
        if result:
            return {
                "is_pothole": bool(result["is_pothole"]),
                "severity": str(result["severity"]).lower(),
                "description": str(result["description"]).strip(),
            }
    raise SarvamError("Couldn't check the photo, try again.")


def write_complaint(facts: dict) -> dict:
    """{subject, body} written by sarvam-105b from the given facts only (no coordinates)."""
    messages = [
        {"role": "system", "content": COMPLAINT_PROMPT},
        {"role": "user", "content": "Facts:\n" + json.dumps(facts, ensure_ascii=False, indent=2)},
    ]
    for _ in range(2):  # retry once on invalid JSON
        response = _call(
            _client().chat.completions,
            model=WRITER_MODEL,
            messages=messages,
            temperature=0.3,
            reasoning_effort=None,  # thinking off: faster, and max_tokens isn't spent on reasoning
            max_tokens=1024,
            response_format=COMPLAINT_FORMAT,
        )
        result = _json_reply(response, ("subject", "body"))
        if result and result["body"].strip():
            return {"subject": result["subject"].strip(), "body": result["body"].strip()}
    raise SarvamError("Couldn't write the complaint, try again.")


def _chunks(text: str, limit: int = MAX_TRANSLATE_CHARS) -> list[str]:
    """Split on sentence ends so every piece fits Mayura's per-request limit."""
    chunks = [""]
    for sentence in re.split(r"(?<=[.!?।])\s+", text):
        for piece in (sentence[i : i + limit] for i in range(0, len(sentence), limit)):
            if chunks[-1] and len(chunks[-1]) + 1 + len(piece) > limit:
                chunks.append(piece)
            else:
                chunks[-1] = f"{chunks[-1]} {piece}" if chunks[-1] else piece
    return [c for c in chunks if c.strip()]


def translate(text: str, target_lang: str) -> str:
    """Translate English text line by line (≤1000 chars per request), keeping the letter's layout.

    target_lang is a Sarvam language code like "hi-IN", or HINGLISH for Roman-script code-mixed Hindi.
    """
    if target_lang == HINGLISH:
        options = {"target_language_code": "hi-IN", "mode": "code-mixed", "output_script": "roman"}
    else:
        options = {"target_language_code": target_lang, "mode": "formal"}

    lines = []
    for line in text.split("\n"):
        if not line.strip():
            lines.append(line)
            continue
        parts = [
            _call(
                _client().text.translate,
                input=chunk,
                source_language_code="en-IN",
                model=TRANSLATE_MODEL,
                numerals_format="international",  # keep phone numbers and PIN as 0-9
                **options,
            ).translated_text
            for chunk in _chunks(line)
        ]
        lines.append(" ".join(parts))
    return "\n".join(lines)

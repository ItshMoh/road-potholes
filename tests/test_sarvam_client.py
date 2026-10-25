"""Offline tests: Sarvam calls are faked, so no API key or credits are needed."""
from types import SimpleNamespace

import pytest

import sarvam_client
from sarvam_client import HINGLISH, SarvamError, _chunks


def _reply(content):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


@pytest.fixture
def fake_sarvam(monkeypatch):
    """Replace the SDK with a queue of replies; records every call's kwargs."""
    calls, replies = [], []

    def fake_call(fn, **kwargs):
        calls.append(kwargs)
        return replies.pop(0) if replies else SimpleNamespace(translated_text=f"<{kwargs['input']}>")

    monkeypatch.setattr(sarvam_client, "_call", fake_call)
    monkeypatch.setattr(sarvam_client, "_client", lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=None, completions_v2=None), text=SimpleNamespace(translate=None)
    ))
    return SimpleNamespace(calls=calls, replies=replies)


def test_chunks_respect_limit():
    text = " ".join(["This is a sentence of moderate length."] * 60)
    chunks = _chunks(text, limit=200)
    assert all(len(c) <= 200 for c in chunks)
    assert " ".join(chunks) == text
    assert _chunks("x" * 450, limit=200) == ["x" * 200, "x" * 200, "x" * 50]


def test_translate_keeps_layout(fake_sarvam):
    out = sarvam_client.translate("Dear Sir,\n\nThe road is bad.\nYours sincerely,\nRam", "hi-IN")
    assert out == "<Dear Sir,>\n\n<The road is bad.>\n<Yours sincerely,>\n<Ram>"
    assert all(c["target_language_code"] == "hi-IN" and c["mode"] == "formal" for c in fake_sarvam.calls)


def test_translate_hinglish_options(fake_sarvam):
    sarvam_client.translate("Hello", HINGLISH)
    call = fake_sarvam.calls[0]
    assert (call["target_language_code"], call["mode"], call["output_script"]) == ("hi-IN", "code-mixed", "roman")
    assert call["model"] == "mayura:v1" and call["numerals_format"] == "international"


def test_check_pothole_retries_once_on_bad_json(fake_sarvam):
    fake_sarvam.replies += [
        _reply(""),
        _reply('{"is_pothole": true, "severity": "High", "description": "Deep pothole."}'),
    ]
    result = sarvam_client.check_pothole(b"jpeg")
    assert result == {"is_pothole": True, "severity": "high", "description": "Deep pothole."}
    assert len(fake_sarvam.calls) == 2
    assert fake_sarvam.calls[0]["model"] == "gemma4"
    image = fake_sarvam.calls[0]["messages"][0]["content"][1]["image_url"]["url"]
    assert image.startswith("data:image/jpeg;base64,")


def test_check_pothole_gives_up_after_two_bad_replies(fake_sarvam):
    fake_sarvam.replies += [_reply("nope"), _reply("{}")]
    with pytest.raises(SarvamError, match="Couldn't check the photo"):
        sarvam_client.check_pothole(b"jpeg")


def test_write_complaint_settings(fake_sarvam):
    fake_sarvam.replies.append(_reply('```json\n{"subject": " S ", "body": " B "}\n```'))
    assert sarvam_client.write_complaint({"city": "Varanasi"}) == {"subject": "S", "body": "B"}
    call = fake_sarvam.calls[0]
    assert call["model"] == "sarvam-105b"
    assert call["reasoning_effort"] is None and call["temperature"] == 0.3 and call["max_tokens"] == 1024
    assert call["response_format"]["type"] == "json_schema"

from __future__ import annotations

from repolens.redaction import redact_command, redact_payload


def test_redaction_policy_redacts_secret_metadata_and_commands_but_preserves_useful_names():
    payload = {
        "metadata": {
            "name": "api-tokenizer",
            "package": "@scope/secret-sauce",
            "token": "should-not-leak",
            "nested": {"private-key": "should-not-leak"},
        },
        "command": "TOKEN=abc npm test -- --token super-secret",
        "path": "src/secret_sauce.py",
        "symbol": "TokenBucket",
    }

    redacted = redact_payload(payload)

    assert redacted["metadata"]["name"] == "api-tokenizer"
    assert redacted["metadata"]["package"] == "@scope/secret-sauce"
    assert redacted["path"] == "src/secret_sauce.py"
    assert redacted["symbol"] == "TokenBucket"
    assert redacted["metadata"]["token"] == "redacted"
    assert redacted["metadata"]["nested"]["private-key"] == "redacted"
    assert "should-not-leak" not in str(redacted)
    assert "super-secret" not in redacted["command"]
    assert redacted["command"] == "TOKEN=<redacted> npm test -- --token <redacted>"


def test_redact_command_handles_equals_and_space_secret_options():
    command = "deploy --api-key=abc --otp 123 PASSWORD=hunter2"

    redacted = redact_command(command)

    assert redacted == "deploy --api-key=<redacted> --otp <redacted> PASSWORD=<redacted>"
    assert "abc" not in redacted
    assert "123" not in redacted
    assert "hunter2" not in redacted

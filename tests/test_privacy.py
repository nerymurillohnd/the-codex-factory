"""Redaction must preserve usable configuration while removing sensitive values."""

import json

import pytest
from agent_context_audit.privacy import redact


@pytest.mark.parametrize("suffix", [".md", ".json", ".toml"])
@pytest.mark.parametrize("secret", ["github_pat_" + "A" * 40, "Bearer SYNTHETIC123456789"])
def test_prose_credentials_are_masked_in_every_supported_format(suffix, secret):
    text = f"Example {secret}\n"
    if suffix == ".json":
        text = json.dumps({"note": text})
    elif suffix == ".toml":
        text = "note = " + json.dumps(text) + "\n"
    protected, _ = redact(text, suffix)
    assert secret not in protected
    assert protected.count("\n") == text.count("\n")
    if suffix == ".json":
        assert json.loads(protected)["note"].startswith("Example")


def test_embedded_private_key_block_is_removed_without_renumbering():
    original = (
        "Policy\n-----BEGIN PRIVATE KEY-----\nPRIVATE_CANARY\n-----END PRIVATE KEY-----\nEnd\n"
    )
    protected, changed = redact(original, ".md")
    assert "PRIVATE_CANARY" not in protected
    assert protected.splitlines()[0] == "Policy"
    assert protected.splitlines()[4] == "End"
    assert changed == [2, 3, 4]


@pytest.mark.parametrize("suffix", [".json", ".toml"])
def test_private_key_blocks_inside_structured_strings_stay_parseable(suffix):
    import tomllib

    body = (
        "Policy\n-----BEGIN PRIVATE KEY-----\nPRIVATE_STRUCTURED_CANARY\n"
        "-----END PRIVATE KEY-----\nEnd"
    )
    text = json.dumps({"note": body}) if suffix == ".json" else "note = " + json.dumps(body) + "\n"
    protected, _ = redact(text, suffix)
    assert "PRIVATE_STRUCTURED_CANARY" not in protected
    assert protected.count("\n") == text.count("\n")
    data = json.loads(protected) if suffix == ".json" else tomllib.loads(protected)
    assert data["note"].startswith("Policy\n") and data["note"].endswith("\nEnd")


def test_credential_bearing_url_paths_are_not_exposed():
    from urllib.parse import quote

    value = "sk-proj-" + "A" * 32
    for path in (value, quote(value, safe="").replace("sk-", "%73%6b%2d")):
        result, _ = redact("[private endpoint](https://example.test/" + path + ")", ".md")
        assert value not in result
        assert "%73%6b%2d" not in result


def test_json_env_values_are_redacted_without_losing_names() -> None:
    original = '{"env":{"ODD_NAME":"CANARY"},"model":"example"}'
    text, lines = redact(original, ".json")
    assert json.loads(text) == {"env": {"ODD_NAME": "<redacted>"}, "model": "example"}
    assert lines == [1]


def test_embedded_token_redaction_preserves_json_syntax() -> None:
    original = '{"note":"credential sk-proj-abcdefghijklmnopqrstuvwxyz is private"}'
    text, _ = redact(original, ".json")
    assert "sk-proj-" not in text
    assert json.loads(text)["note"] == "credential <redacted> is private"


def test_regular_policy_mentions_are_not_redacted() -> None:
    policy = "Never disclose API keys or secrets.\nUse signed commits.\n"
    assert redact(policy, ".md") == (policy, [])


def test_malformed_json_cannot_expose_unknown_environment_values() -> None:
    import pytest

    with pytest.raises(ValueError, match="safely redact"):
        redact('{"env":{"OPAQUE":"CANARY_PRIVATE",', ".json")


def test_multiline_toml_secret_is_fully_redacted() -> None:
    import tomllib

    original = '[mcp_servers.x.env]\nTOKEN = """\nCANARY_MULTILINE\nSECOND_SECRET_LINE\n"""\n'
    text, _ = redact(original, ".toml")
    assert "CANARY_MULTILINE" not in text and "SECOND_SECRET_LINE" not in text
    assert len(text.splitlines()) == len(original.splitlines())
    assert tomllib.loads(text)["mcp_servers"]["x"]["env"]["TOKEN"].startswith("<redacted>")


def test_inline_toml_environment_keeps_names_and_masks_values() -> None:
    import tomllib

    original = '[mcp_servers.x]\nenv = { OPAQUE = "CANARY_INLINE", COUNT = 42 }\n'
    text, _ = redact(original, ".toml")
    assert "CANARY_INLINE" not in text
    assert tomllib.loads(text)["mcp_servers"]["x"]["env"] == {
        "OPAQUE": "<redacted>",
        "COUNT": "<redacted>",
    }


def test_embedded_url_credentials_are_redacted() -> None:
    original = '{"url":"https://account:CANARY_PASSWORD@example.com/path?token=CANARY_QUERY"}'
    text, _ = redact(original, ".json")
    assert "CANARY_PASSWORD" not in text and "CANARY_QUERY" not in text
    assert json.loads(text)["url"].startswith("https://")

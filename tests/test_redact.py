import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "skills", "karpathy-jev", "scripts"))
import jev_client  # noqa: E402

mask = jev_client.mask_secrets


def test_env_assignment_keeps_name_masks_value():
    assert mask("+OPENAI_API_KEY=sk-abcdefghijklmnopqrstuv") == "+OPENAI_API_KEY=[secret]"
    assert mask("DB_PASSWORD: hunter2hunter2") == "DB_PASSWORD: [secret]"


def test_token_in_command_output_is_masked():
    out = mask("pushed with ghp_" + "a1B2" * 9 + " ok")
    assert "ghp_" not in out and out.endswith("[secret] ok")


def test_private_key_block_is_masked():
    text = "x\n-----BEGIN RSA PRIVATE KEY-----\nMIIabc\n-----END RSA PRIVATE KEY-----\ny"
    assert mask(text) == "x\n[secret]\ny"


def test_ordinary_code_and_hashes_are_unchanged():
    for line in ["+    sort_key = lambda h: h.file", "+    primary_key: int = 0",
                 "commit 3f2a9c1e0b7d4a6f8e5c2b1a0d9e8f7c6b5a4d3e", "+    return x * 2"]:
        assert mask(line) == line


def test_nested_state_is_walked():
    state = {"observed": {"hunks": [{"file": ".env", "added": ["GITHUB_TOKEN=abc123def456"]}], "n": 3}}
    assert mask(state) == {"observed": {"hunks": [{"file": ".env", "added": ["GITHUB_TOKEN=[secret]"]}], "n": 3}}

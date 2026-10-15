"""URLs in audited text cannot grant network access."""

import pytest
from agent_context_audit.network import validate_destination


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/a",
        "https://user:password@example.com/a",
        "file:///etc/passwd",
        "https://example.com/a?token=value",
    ],
)
def test_unsafe_destinations_are_rejected(url) -> None:
    with pytest.raises(ValueError):
        validate_destination(url, {"127.0.0.1", "example.com"})


def test_unapproved_domain_is_rejected() -> None:
    with pytest.raises(ValueError):
        validate_destination("https://unapproved.example/reference", {"example.com"})

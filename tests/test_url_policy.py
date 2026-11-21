from __future__ import annotations

import pytest

from apps.api.app.core.url_policy import (
    UrlPolicyError,
    canonicalize_url,
    validate_public_https_url,
    validate_redirect_url,
)
from tests.conftest import make_mock_dns_resolver


def test_url_policy_accepts_allowlisted_public_https_and_subdomains() -> None:
    resolver = make_mock_dns_resolver()
    allowed = {"approved.example"}
    res1 = validate_public_https_url(
        "https://approved.example:443/events/show?utm_source=x&id=42#top",
        allowed,
        resolver=resolver,
    )
    assert res1 == "https://approved.example/events/show?id=42"

    res2 = validate_public_https_url(
        "https://sub.approved.example/concerts/",
        allowed,
        resolver=resolver,
    )
    assert res2 == "https://sub.approved.example/concerts"


def test_url_policy_fails_closed_on_empty_allowlist() -> None:
    resolver = make_mock_dns_resolver()
    with pytest.raises(UrlPolicyError) as exc:
        validate_public_https_url("https://approved.example/test", set(), resolver=resolver)
    assert exc.value.error_code == "DOMAIN_NOT_ALLOWED"


@pytest.mark.parametrize(
    "bad_url,expected_code",
    [
        ("http://approved.example/event", "DOMAIN_NOT_ALLOWED"),
        ("file:///etc/passwd", "DOMAIN_NOT_ALLOWED"),
        ("https://user:pass@approved.example/event", "DOMAIN_NOT_ALLOWED"),
        ("https://approved.example:8443/event", "DOMAIN_NOT_ALLOWED"),
        ("https://approved.example.evil.test/event", "DOMAIN_NOT_ALLOWED"),
        ("https://evil.example/event", "DOMAIN_NOT_ALLOWED"),
        ("https://127.0.0.1/admin", "DNS_REJECTED"),
        ("https://[::1]/admin", "DNS_REJECTED"),
        ("https://rebind.approved.example/event", "DNS_REJECTED"),
        ("https://private.approved.example/event", "DNS_REJECTED"),
        ("https://linklocal.approved.example/latest/meta-data", "DNS_REJECTED"),
        ("https://ipv6mapped.approved.example/event", "DNS_REJECTED"),
    ],
)
def test_url_policy_rejects_unsafe_targets(bad_url: str, expected_code: str) -> None:
    resolver = make_mock_dns_resolver()
    allowed = {"approved.example"}
    with pytest.raises(UrlPolicyError) as exc:
        validate_public_https_url(bad_url, allowed, resolver=resolver)
    assert exc.value.error_code == expected_code


def test_redirect_policy_and_canonicalization() -> None:
    resolver = make_mock_dns_resolver()
    with pytest.raises(UrlPolicyError) as exc:
        validate_redirect_url("https://evil.example/redirected", {"approved.example"}, resolver=resolver)
    assert exc.value.error_code == "REDIRECT_NOT_ALLOWED"

    c1 = canonicalize_url("https://Approved.Example/e/?fbclid=abc&b=2&a=1&utm_medium=social")
    c2 = canonicalize_url("https://approved.example/e?a=1&b=2")
    assert c1 == c2 == "https://approved.example/e?a=1&b=2"

from __future__ import annotations

from ipaddress import IPv4Address, IPv6Address, ip_address
from socket import SOCK_STREAM, getaddrinfo
from typing import Callable, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAMS: frozenset[str] = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "utm_id",
        "fbclid",
        "gclid",
        "mc_cid",
        "mc_eid",
        "ref",
        "si",
    }
)

DnsResolver = Callable[[str], Iterable[str]]


class UrlPolicyError(ValueError):
    """Raised when a URL fails NeuralGrid server-side HTTPS/domain/DNS/IP policy."""

    def __init__(self, message: str, error_code: str = "DOMAIN_NOT_ALLOWED") -> None:
        super().__init__(message)
        self.error_code = error_code


def _default_dns_resolver(host: str) -> set[str]:
    infos = getaddrinfo(host, 443, type=SOCK_STREAM)
    return {str(item[4][0]) for item in infos if item and item[4]}


def canonicalize_url(raw_url: str) -> str:
    """Canonicalise a URL by stripping fragments, default :443 port, and tracking params."""
    parts = urlsplit(raw_url.strip())
    scheme = parts.scheme.lower()
    if not scheme or not parts.hostname:
        raise UrlPolicyError("Malformed URL missing scheme or hostname", error_code="INVALID_URL")

    try:
        host = parts.hostname.encode("idna").decode("ascii").lower().rstrip(".")
    except UnicodeError as exc:
        raise UrlPolicyError("Invalid internationalised hostname", error_code="INVALID_URL") from exc

    port = parts.port
    if (scheme == "https" and port == 443) or (scheme == "http" and port == 80) or port is None:
        netloc = host
    else:
        netloc = f"{host}:{port}"

    filtered_qs = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS
    ]
    filtered_qs.sort(key=lambda item: (item[0], item[1]))
    query = urlencode(filtered_qs, doseq=True)
    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return urlunsplit((scheme, netloc, path, query, ""))


def _is_ip_literal(host: str) -> bool:
    cleaned = host.strip("[]")
    try:
        ip_address(cleaned)
        return True
    except ValueError:
        return False


def _is_disallowed_ip(ip_obj: IPv4Address | IPv6Address) -> bool:
    if isinstance(ip_obj, IPv6Address) and ip_obj.ipv4_mapped is not None:
        ip_obj = ip_obj.ipv4_mapped
    return (
        not ip_obj.is_global
        or ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
    )


def validate_public_https_url(
    raw_url: str,
    allowed_domains: set[str],
    resolver: DnsResolver | None = None,
    is_redirect: bool = False,
) -> str:
    """Authoritative server-side HTTPS, allow-list, and DNS/IP validation (NFR-13)."""
    if not raw_url or not isinstance(raw_url, str):
        raise UrlPolicyError("URL must be a non-empty string", error_code="INVALID_URL")

    parts = urlsplit(raw_url.strip())
    domain_err_code = "REDIRECT_NOT_ALLOWED" if is_redirect else "DOMAIN_NOT_ALLOWED"

    if parts.scheme.lower() != "https":
        raise UrlPolicyError("Only HTTPS URLs are allowed", error_code=domain_err_code)
    if parts.username or parts.password or not parts.hostname:
        raise UrlPolicyError("URL userinfo or missing hostname is not allowed", error_code=domain_err_code)
    if parts.port not in (None, 443):
        raise UrlPolicyError("Only the default HTTPS port (443) is allowed", error_code=domain_err_code)

    try:
        host = parts.hostname.encode("idna").decode("ascii").lower().rstrip(".")
    except UnicodeError as exc:
        raise UrlPolicyError("Invalid hostname encoding", error_code="INVALID_URL") from exc

    if _is_ip_literal(host):
        raise UrlPolicyError("Direct IP literal URLs are not allowed", error_code="DNS_REJECTED")

    normalized_allowlist: set[str] = set()
    for d in allowed_domains:
        cleaned = d.strip().lower().rstrip(".")
        if not cleaned or cleaned == "replace-with-approved-domain-list":
            continue
        try:
            normalized_allowlist.add(cleaned.encode("idna").decode("ascii"))
        except UnicodeError:
            continue

    if not normalized_allowlist:
        raise UrlPolicyError("EventSense domain allow-list is empty (fail closed)", error_code=domain_err_code)

    if not any(host == allowed or host.endswith("." + allowed) for allowed in normalized_allowlist):
        raise UrlPolicyError(f"Host '{host}' is not on the configured allow-list", error_code=domain_err_code)

    resolve_fn = resolver or _default_dns_resolver
    try:
        addresses = {str(addr).strip() for addr in resolve_fn(host) if str(addr).strip()}
    except OSError as exc:
        raise UrlPolicyError(f"Hostname '{host}' could not be resolved", error_code="DNS_REJECTED") from exc

    if not addresses:
        raise UrlPolicyError(f"Hostname '{host}' resolved to no addresses", error_code="DNS_REJECTED")

    for addr in addresses:
        try:
            ip_obj = ip_address(addr.split("%")[0])
        except ValueError as exc:
            raise UrlPolicyError(f"Invalid resolved address '{addr}'", error_code="DNS_REJECTED") from exc
        if _is_disallowed_ip(ip_obj):
            raise UrlPolicyError(
                f"Private, loopback, link-local, or reserved address rejected ({addr})",
                error_code="DNS_REJECTED",
            )

    return canonicalize_url(parts._replace(netloc=host, fragment="").geturl())


def validate_redirect_url(
    raw_url: str,
    allowed_domains: set[str],
    resolver: DnsResolver | None = None,
) -> str:
    """Revalidate a redirect or final page URL against allow-list and DNS/IP policy."""
    return validate_public_https_url(
        raw_url=raw_url,
        allowed_domains=allowed_domains,
        resolver=resolver,
        is_redirect=True,
    )

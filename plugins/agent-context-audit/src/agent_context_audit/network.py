"""Explicitly authorized, public-only HTTP retrieval without credentials."""

import hashlib
import http.client
import ipaddress
import socket
import ssl
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit


@dataclass(frozen=True)
class Document:
    url: str
    status: int
    text: str
    sha256: str


def validate_destination(url: str, allowed_domains: set[str]) -> tuple[str, int, str]:
    parsed = urlsplit(url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise ValueError("Unsupported URL")
    if parsed.username or parsed.password or parsed.query:
        raise ValueError("Credentials and query strings are not allowed")
    host = parsed.hostname.encode("idna").decode("ascii").lower()
    if host not in {name.lower().strip(".") for name in allowed_domains}:
        raise ValueError("Domain has not been authorized")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if port not in {80, 443}:
        raise ValueError("Nonstandard network port is not allowed")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and (not address.is_global or address.is_multicast):
        raise ValueError("Private or reserved destination")
    if host in {"localhost", "localhost.localdomain"} or host.endswith((".localhost", ".local")):
        raise ValueError("Local destination")
    return host, port, parsed.path or "/"


class PinnedHTTPS(http.client.HTTPSConnection):
    """Pin a prevalidated IP while retaining TLS verification for the original host."""

    def __init__(self, host: str, address: str, port: int, timeout: float):
        self.address = address
        self.tls_context = ssl.create_default_context()
        super().__init__(host, port, timeout=timeout, context=self.tls_context)

    def connect(self) -> None:
        transport = socket.create_connection((self.address, self.port), self.timeout)
        self.sock = self.tls_context.wrap_socket(transport, server_hostname=self.host)


def fetch_document(
    url: str, allowed_domains: set[str], timeout: float = 10, max_bytes: int = 2 * 1024 * 1024
) -> Document:
    for _ in range(6):
        host, port, request_path = validate_destination(url, allowed_domains)
        addresses = {
            str(item[4][0]) for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        }
        if not addresses or any(
            not ipaddress.ip_address(ip).is_global or ipaddress.ip_address(ip).is_multicast
            for ip in addresses
        ):
            raise ValueError("DNS resolved to a private or reserved destination")
        address = sorted(addresses)[0]
        if urlsplit(url).scheme == "https":
            connection = PinnedHTTPS(host, address, port, timeout)
        else:
            connection = http.client.HTTPConnection(address, port, timeout=timeout)
        try:
            connection.request(
                "GET",
                request_path,
                headers={
                    "Host": host,
                    "Accept-Encoding": "identity",
                    "User-Agent": "AgentContextAudit/0.1.0",
                },
            )
            response = connection.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                location = response.getheader("Location")
                if not location:
                    raise ValueError("Redirect without a location")
                following = urljoin(url, location)
                if urlsplit(url).scheme == "https" and urlsplit(following).scheme != "https":
                    raise ValueError("TLS downgrade redirect")
                validate_destination(following, allowed_domains)
                url = following
                continue
            if response.getheader("Content-Encoding", "identity") not in {"", "identity"}:
                raise ValueError("Unexpected compressed response")
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise ValueError("Document exceeds bounded retrieval size")
            return Document(
                url,
                response.status,
                body.decode("utf-8", errors="replace"),
                hashlib.sha256(body).hexdigest(),
            )
        finally:
            connection.close()
    raise ValueError("Too many redirects")

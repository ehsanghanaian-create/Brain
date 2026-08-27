"""Tiny authenticated host proxy for Docker Desktop networks that cannot reach TLS directly.

It is intentionally limited to ports 80/443 and exists only to bridge containers
through the Windows host network. It does not inspect HTTPS payloads.
"""
from __future__ import annotations

import argparse
import base64
import select
import socket
import socketserver
import struct
from urllib.parse import urlsplit

USERNAME = "seo-brain"
PASSWORD = "local-docker"
EXPECTED_AUTH = "Basic " + base64.b64encode(f"{USERNAME}:{PASSWORD}".encode()).decode()
ALLOWED_PORTS = {80, 443}
UPSTREAM_SOCKS: tuple[str, int] | None = None


def _read_exact(sock: socket.socket, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise OSError("SOCKS proxy closed the connection")
        data.extend(chunk)
    return bytes(data)


def _connect(host: str, port: int, timeout: float = 30) -> socket.socket:
    """Connect directly or through the host VPN's local SOCKS5 endpoint."""
    if UPSTREAM_SOCKS is None:
        return socket.create_connection((host, port), timeout=timeout)

    try:
        upstream = socket.create_connection(UPSTREAM_SOCKS, timeout=timeout)
    except OSError:
        # VPN clients can switch from a local SOCKS listener to a system/TUN
        # route while this bridge is still running. Keep Docker traffic usable
        # through the host route instead of returning an opaque 502 forever.
        return socket.create_connection((host, port), timeout=timeout)
    try:
        upstream.sendall(b"\x05\x01\x00")  # SOCKS5, one method, no authentication
        if _read_exact(upstream, 2) != b"\x05\x00":
            raise OSError("SOCKS proxy rejected no-auth negotiation")

        encoded_host = host.encode("idna")
        if len(encoded_host) > 255:
            raise OSError("SOCKS destination hostname is too long")
        request = b"\x05\x01\x00\x03" + bytes([len(encoded_host)]) + encoded_host + struct.pack("!H", port)
        upstream.sendall(request)

        version, reply, _, address_type = _read_exact(upstream, 4)
        if version != 5 or reply != 0:
            raise OSError(f"SOCKS connect failed with reply {reply}")
        if address_type == 1:
            _read_exact(upstream, 4)
        elif address_type == 3:
            _read_exact(upstream, _read_exact(upstream, 1)[0])
        elif address_type == 4:
            _read_exact(upstream, 16)
        else:
            raise OSError(f"SOCKS proxy returned unknown address type {address_type}")
        _read_exact(upstream, 2)
        return upstream
    except Exception:
        upstream.close()
        raise


class ProxyHandler(socketserver.StreamRequestHandler):
    timeout = 30

    def _error(self, status: str, extra: str = "") -> None:
        self.wfile.write(f"HTTP/1.1 {status}\r\nConnection: close\r\n{extra}\r\n".encode())

    @staticmethod
    def _target(value: str, default_port: int) -> tuple[str, int]:
        parsed = urlsplit(value if "://" in value else "//" + value)
        if not parsed.hostname:
            raise ValueError("missing host")
        return parsed.hostname, parsed.port or default_port

    @staticmethod
    def _relay(client: socket.socket, upstream: socket.socket) -> None:
        sockets = [client, upstream]
        while sockets:
            readable, _, _ = select.select(sockets, [], [], 60)
            if not readable:
                return
            for source in readable:
                data = source.recv(65536)
                if not data:
                    return
                (upstream if source is client else client).sendall(data)

    def handle(self) -> None:
        try:
            request_line = self.rfile.readline(8192).decode("latin-1").strip()
            if not request_line:
                return
            method, target, version = request_line.split(" ", 2)
            headers: list[tuple[str, str]] = []
            auth = ""
            content_length = 0
            while True:
                line = self.rfile.readline(65536)
                if line in (b"\r\n", b"\n", b""):
                    break
                name, value = line.decode("latin-1").split(":", 1)
                value = value.strip()
                if name.lower() == "proxy-authorization":
                    auth = value
                elif name.lower() not in {"proxy-connection"}:
                    headers.append((name, value))
                if name.lower() == "content-length":
                    content_length = int(value)
            if auth != EXPECTED_AUTH:
                self._error("407 Proxy Authentication Required", 'Proxy-Authenticate: Basic realm="SEO Brain"\r\n')
                return

            if method.upper() == "CONNECT":
                host, port = self._target(target, 443)
                if port not in ALLOWED_PORTS:
                    self._error("403 Forbidden")
                    return
                with _connect(host, port) as upstream:
                    self.wfile.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                    self.wfile.flush()
                    self._relay(self.connection, upstream)
                return

            parsed = urlsplit(target)
            if not parsed.hostname:
                self._error("400 Bad Request")
                return
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            if port not in ALLOWED_PORTS:
                self._error("403 Forbidden")
                return
            path = parsed.path or "/"
            if parsed.query:
                path += "?" + parsed.query
            body = self.rfile.read(content_length) if content_length else b""
            outgoing = [f"{method} {path} {version}", *(f"{k}: {v}" for k, v in headers), "", ""]
            with _connect(parsed.hostname, port) as upstream:
                upstream.sendall("\r\n".join(outgoing).encode("latin-1") + body)
                self._relay(self.connection, upstream)
        except (OSError, ValueError):
            try:
                self._error("502 Bad Gateway")
            except OSError:
                pass


class ThreadingProxy(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> None:
    global UPSTREAM_SOCKS
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=18080, type=int)
    parser.add_argument(
        "--upstream-socks",
        metavar="HOST:PORT",
        help="route outbound connections through a local SOCKS5 proxy (for example 127.0.0.1:10808)",
    )
    args = parser.parse_args()
    if args.upstream_socks:
        socks_host, separator, socks_port = args.upstream_socks.rpartition(":")
        if not separator or not socks_host:
            parser.error("--upstream-socks must use HOST:PORT format")
        UPSTREAM_SOCKS = (socks_host, int(socks_port))
    with ThreadingProxy((args.host, args.port), ProxyHandler) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()

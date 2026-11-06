"""Ephemeral loopback TLS ingress for the original Connector, without wire edits."""
from datetime import datetime, timedelta, timezone
import ipaddress
from pathlib import Path
import socket
import socketserver
import ssl
import threading


class Ingress:
    def __init__(self, certificate, key, upstream):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(certificate, key)
        address = upstream.rsplit(":", 1)

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                try:
                    with context.wrap_socket(self.request, server_side=True) as secure:
                        with socket.create_connection((address[0], int(address[1])), timeout=15) as target:
                            target.settimeout(None)

                            def copy(source, destination):
                                try:
                                    while data := source.recv(65536):
                                        destination.sendall(data)
                                except (OSError, ssl.SSLError):
                                    pass
                                finally:
                                    try: destination.shutdown(socket.SHUT_WR)
                                    except OSError: pass

                            downstream = threading.Thread(target=copy, args=(target, secure), daemon=True)
                            downstream.start()
                            copy(secure, target)
                            downstream.join(timeout=5)
                except (OSError, ssl.SSLError):
                    pass

        class Server(socketserver.ThreadingTCPServer):
            daemon_threads = True
            allow_reuse_address = True

        self.server = Server(("127.0.0.1", 0), Handler)
        self.url = f"wss://127.0.0.1:{self.server.server_address[1]}/agents/v1/connect"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def certificate(directory):
    # Run with the locked Connector environment's existing cryptography wheel.
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Yuki isolated Connector test")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(key, hashes.SHA256()))
    (directory / "ingress.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (directory / "ingress-key.pem").write_bytes(key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))


if __name__ == "__main__":
    import sys
    certificate(Path(sys.argv[1]))

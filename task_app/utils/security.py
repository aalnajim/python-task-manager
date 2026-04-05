from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


PBKDF2_ITERATIONS = 390_000
ENCRYPTED_PREFIX = "enc:"


class SecurityManager:
    def __init__(self, key_path: Path):
        self.key_path = key_path
        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.key_path.exists():
            self.key_path.write_bytes(Fernet.generate_key())
            try:
                os.chmod(self.key_path, 0o600)
            except OSError:
                pass
        self._fernet = Fernet(self.key_path.read_bytes())

    def hash_password(self, password: str) -> str:
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            PBKDF2_ITERATIONS,
        )
        return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${base64.b64encode(digest).decode('ascii')}"

    def verify_password(self, password: str, stored_value: str) -> bool:
        if stored_value.startswith("pbkdf2_sha256$"):
            _algo, iterations_text, salt, encoded_digest = stored_value.split("$", 3)
            expected = base64.b64decode(encoded_digest.encode("ascii"))
            digest = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt.encode("utf-8"),
                int(iterations_text),
                dklen=len(expected),
            )
            return hmac.compare_digest(digest, expected)
        legacy = hashlib.sha256(password.encode("utf-8")).hexdigest()
        return hmac.compare_digest(legacy, stored_value)

    def needs_password_upgrade(self, stored_value: str) -> bool:
        return not stored_value.startswith("pbkdf2_sha256$")

    def encrypt_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        return ENCRYPTED_PREFIX + self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.startswith(ENCRYPTED_PREFIX):
            return value
        token = value[len(ENCRYPTED_PREFIX) :]
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Could not decrypt stored data with the current app key.") from exc

    def generate_user_keypair(self, password: str) -> tuple[str, str]:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")
        encrypted_private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.BestAvailableEncryption(password.encode("utf-8")),
        ).decode("utf-8")
        return public_pem, encrypted_private_pem

    def load_private_key(self, encrypted_private_pem: str, password: str):
        return serialization.load_pem_private_key(encrypted_private_pem.encode("utf-8"), password=password.encode("utf-8"))

    def encrypt_task_key_for_user(self, task_key: bytes, public_key_pem: str) -> str:
        public_key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
        encrypted = public_key.encrypt(
            task_key,
            padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
        )
        return base64.b64encode(encrypted).decode("ascii")

    def decrypt_task_key_for_user(self, encrypted_task_key: str, private_key) -> bytes:
        decoded = base64.b64decode(encrypted_task_key.encode("ascii"))
        return private_key.decrypt(
            decoded,
            padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
        )

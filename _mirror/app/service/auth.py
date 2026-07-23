import base64
import os
from typing import Optional

from cryptography.exceptions import InvalidKey
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from fastapi import Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


class AuthService:
    """Handles password verification and signed, stateless auth cookies."""

    def __init__(
        self,
        enabled: bool,
        username: Optional[str],
        password_hash: Optional[str],
        secret_key: Optional[str],
    ):
        # Auth is only actually usable when explicitly enabled AND all
        # required credentials/keys are present; otherwise treat as disabled
        # to avoid crashing on missing configuration
        self.enabled = (
            enabled and bool(secret_key) and bool(password_hash) and bool(username)
        )
        self._username = username
        self._password_hash = password_hash
        self._secret_key = secret_key
        self._serializer: Optional[URLSafeTimedSerializer] = None

    @property
    def _serializer_instance(self) -> URLSafeTimedSerializer:
        """Lazily builds the serializer only when auth is actually used, avoiding
        a crash on startup when secret_key is not configured."""
        serializer = self._serializer
        if serializer is None:
            if self._secret_key is None:
                raise RuntimeError("AuthService is not enabled: secret_key is missing")
            serializer = URLSafeTimedSerializer(
                secret_key=self._secret_key, salt="auth-cookie"
            )
            self._serializer = serializer

        return serializer

    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hashes a password using Scrypt with a random salt.

        Args:
            password: Plain-text password to hash

        Returns:
            Salt and derived hash, base64-encoded and joined with "$",
            so the result fits in a single .env value.
        """
        salt = os.urandom(16)
        kdf = Scrypt(salt=salt, length=32, n=16384, r=8, p=1)
        derived = kdf.derive(password.encode("utf-8"))
        return f"{base64.b64encode(salt).decode()}${base64.b64encode(derived).decode()}"

    def verify_credentials(self, username: str, password: str) -> bool:
        """Checks the given username/password against the configured values."""
        if not self.enabled or self._password_hash is None:
            # No credentials configured - nothing to verify against
            return False

        if username != self._username:
            return False

        salt_b64, hash_b64 = self._password_hash.split("$")
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)

        kdf = Scrypt(salt=salt, length=32, n=16384, r=8, p=1)
        try:
            # verify() performs a constant-time comparison internally
            kdf.verify(password.encode("utf-8"), expected)
            return True
        except InvalidKey:
            return False

    def create_auth_cookie(self, response: Response, username: str) -> None:
        """Signs a payload and sets it as an httpOnly cookie on the response."""
        cookie_max_age = 60 * 60 * 24 * 7  # 7 days, in seconds
        token = self._serializer_instance.dumps({"user": username})
        response.set_cookie(
            key="auth_session",
            value=token,
            max_age=cookie_max_age,
            httponly=True,
            samesite="lax",
            secure=False,  # site is served over both http and https
        )

    @staticmethod
    def clear_auth_cookie(response: Response) -> None:
        """Removes the auth cookie on logout."""
        response.delete_cookie(key="auth_session")

    def is_authenticated(self, request: Request) -> bool:
        """Checks whether the incoming request carries a valid, unexpired auth cookie."""
        token = request.cookies.get("auth_session")
        if not token:
            return False

        try:
            # max_age here re-validates expiration on every call, independent
            # of whatever value was used when the token was originally issued
            cookie_max_age = 60 * 60 * 24 * 7  # 7 days, in seconds
            self._serializer_instance.loads(token, max_age=cookie_max_age)
            return True
        except (BadSignature, SignatureExpired):
            return False

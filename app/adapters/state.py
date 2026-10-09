"""La foto del estado: cómo se convierte en bytes y dónde se guarda.

Formato: `ORC1 | huella del código (32) | guardada en (8) | HMAC-SHA256 (32) | pickle`.

pickle ejecuta código al leer, así que nunca se lee algo sin verificar antes:
1. La firma HMAC, con una clave derivada de PRESENTER_KEY. Quien pueda escribir el
   objeto en Cloud Storage pero no conozca la clave no puede colar una foto.
2. La huella del código de `domain` y `application`: una foto de otro código podría
   restaurar objetos con otra forma. Si no coincide, se empieza de cero.
3. La edad: una foto de una sesión de hace días no resucita en la siguiente charla.
"""
from __future__ import annotations

import hashlib
import hmac
import pickle  # noqa: S403 — solo se lee tras verificar la firma (ver arriba)
import struct
from pathlib import Path

import httpx

from .google_auth import AccessToken

MAGIC = b"ORC1"
HEADER = struct.Struct(">4s32sd32s")
APP = Path(__file__).parent.parent


def code_fingerprint() -> bytes:
    """SHA-256 del código cuyos objetos viajan en la foto."""
    h = hashlib.sha256()
    for path in sorted([*(APP / "domain").rglob("*.py"), *(APP / "application").rglob("*.py")]):
        h.update(path.relative_to(APP).as_posix().encode() + b"\0" + path.read_bytes())
    return h.digest()


class SignedPickle:
    def __init__(self, secret: str, fingerprint: bytes | None = None, max_age: float = 12 * 3600):
        if len(secret) < 32:
            raise ValueError("la foto del estado necesita una clave de al menos 32 caracteres")
        self.key = hashlib.sha256(b"oraculo-estado\0" + secret.encode()).digest()
        self.fingerprint = fingerprint if fingerprint is not None else code_fingerprint()
        self.max_age = max_age

    def _sign(self, fingerprint: bytes, saved_at: float, payload: bytes) -> bytes:
        return hmac.digest(self.key, fingerprint + struct.pack(">d", saved_at) + payload, "sha256")

    def dumps(self, state: dict, saved_at: float) -> bytes:
        payload = pickle.dumps(state, protocol=pickle.HIGHEST_PROTOCOL)
        mac = self._sign(self.fingerprint, saved_at, payload)
        return HEADER.pack(MAGIC, self.fingerprint, saved_at, mac) + payload

    def loads(self, blob: bytes, now: float) -> dict:
        if len(blob) < HEADER.size:
            raise ValueError("foto truncada")
        magic, fingerprint, saved_at, mac = HEADER.unpack_from(blob)
        payload = blob[HEADER.size:]
        if magic != MAGIC or not hmac.compare_digest(mac, self._sign(fingerprint, saved_at, payload)):
            raise ValueError("firma inválida: la foto no es de esta demo o cambió la clave")
        if fingerprint != self.fingerprint:
            raise ValueError("la foto es de otra versión del código")
        if now - saved_at > self.max_age:
            raise ValueError(f"la foto tiene {(now - saved_at) / 3600:.1f} h: es de otra sesión")
        return pickle.loads(payload)  # noqa: S301 — firma, código y edad verificados arriba


class GcsStateStore:
    """Un solo objeto en Cloud Storage. La cuenta de la API solo necesita escribir en ese bucket."""

    def __init__(self, bucket: str, name: str = "estado/sala.bin", timeout: float = 10.0):
        self.bucket = bucket
        self.name = name
        self.timeout = timeout
        self._token = AccessToken()

    async def load(self) -> bytes | None:
        token = await self._token.get()
        url = f"https://storage.googleapis.com/storage/v1/b/{self.bucket}/o/{self.name.replace('/', '%2F')}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(url, params={"alt": "media"}, headers={"Authorization": f"Bearer {token}"})
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.content

    async def save(self, blob: bytes) -> None:
        token = await self._token.get()
        url = f"https://storage.googleapis.com/upload/storage/v1/b/{self.bucket}/o"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(url, params={"uploadType": "media", "name": self.name}, content=blob,
                                  headers={"Authorization": f"Bearer {token}",
                                           "Content-Type": "application/octet-stream"})
        r.raise_for_status()


class MemoryStateStore:
    """Para los tests y para ensayar el apagado sin nube."""

    def __init__(self) -> None:
        self.blob: bytes | None = None
        self.saves = 0

    async def load(self) -> bytes | None:
        return self.blob

    async def save(self, blob: bytes) -> None:
        self.blob = blob
        self.saves += 1

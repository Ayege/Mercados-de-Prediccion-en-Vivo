"""Credenciales por defecto (ADC). Sin llaves: en Cloud Run es la cuenta de servicio."""
from __future__ import annotations

import asyncio

SCOPE = "https://www.googleapis.com/auth/cloud-platform"


class AccessToken:
    def __init__(self) -> None:
        self._creds = None

    def _get(self) -> str:
        import google.auth
        from google.auth.transport.requests import Request

        if self._creds is None:
            self._creds, _ = google.auth.default(scopes=[SCOPE])
        if not self._creds.valid:
            self._creds.refresh(Request())
        return self._creds.token

    async def get(self) -> str:
        return await asyncio.to_thread(self._get)


async def id_token(audience: str) -> str:
    """Token de identidad para invocar un servicio privado de Cloud Run.

    Funciona en Cloud Run (servidor de metadatos) o con una llave de cuenta de
    servicio. Con credenciales de usuario en local, falla: por eso el modo real
    está pensado para correr desplegado.
    """
    import google.oauth2.id_token
    from google.auth.transport.requests import Request

    return await asyncio.to_thread(google.oauth2.id_token.fetch_id_token, Request(), audience)


async def verify_google_oidc(token: str, audience: str, email: str) -> bool:
    """¿Es un token OIDC firmado por Google, para esta audiencia y de esta cuenta?

    Así se autentica Cloud Scheduler sin compartir ningún secreto: Google firma el
    token y aquí se verifican firma, expiración, audiencia y cuenta emisora.
    """
    import google.oauth2.id_token
    from google.auth.transport.requests import Request

    try:
        verify = google.oauth2.id_token.verify_oauth2_token
        claims = await asyncio.to_thread(verify, token, Request(), audience)
    except Exception:  # noqa: BLE001 — cualquier fallo de verificación es un "no"
        return False
    return claims.get("email") == email and bool(claims.get("email_verified"))

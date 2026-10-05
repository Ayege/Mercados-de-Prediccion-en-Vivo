"""Cliente mínimo de generateContent en Vertex AI, compartido por todos los adaptadores.

Sin llaves de API: usa las credenciales por defecto (ADC). En Cloud Run eso
es la cuenta de servicio del servicio, que solo necesita roles/aiplatform.user.
"""
from __future__ import annotations

import httpx

from .google_auth import AccessToken


class VertexClient:
    def __init__(self, project: str, location: str, model: str):
        self.project = project
        self.location = location
        self.model = model
        self._token = AccessToken()

    @property
    def endpoint(self) -> str:
        host = "aiplatform.googleapis.com"
        if self.location != "global":
            host = f"{self.location}-{host}"
        return (
            f"https://{host}/v1/projects/{self.project}/locations/{self.location}"
            f"/publishers/google/models/{self.model}:generateContent"
        )

    async def generate(self, body: dict, timeout: float = 90) -> dict:
        token = await self._token.get()
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(
                self.endpoint,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=body,
            )
        r.raise_for_status()
        return r.json()

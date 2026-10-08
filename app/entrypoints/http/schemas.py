from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class HeadlineIn(BaseModel):
    text: str = Field(min_length=8, max_length=200)
    source: str = Field(min_length=1, max_length=80)  # un medio real, o «titular de ensayo»
    url: str = Field("", max_length=500, pattern=r"^(https://\S+)?$")


class FramingIn(BaseModel):
    """Dos titulares sobre el mismo hecho: uno empuja al SÍ y el otro al NO."""

    pro_si: HeadlineIn
    pro_no: HeadlineIn


class NewMarket(BaseModel):
    question: str = Field(min_length=8, max_length=200)
    criteria: str = Field(min_length=8, max_length=600)
    b: float = Field(100, ge=10, le=1000)
    kind: Literal["presente", "futuro", "sala", "simulacion"] = "presente"
    threshold: float = Field(0.5, gt=0, lt=1)
    predicate: str | None = Field(None, max_length=40)
    framing: FramingIn | None = None


NAME = r"^[\w .-]{1,24}$"  # letras, dígitos, espacio, punto y guion: nada que parezca marcado


class Enter(BaseModel):
    name: str = Field(min_length=1, max_length=24, pattern=NAME)


class Trade(BaseModel):
    user: str = Field(min_length=1, max_length=24, pattern=NAME)
    outcome: Literal["YES", "NO"]
    amount: float = Field(gt=0, le=10_000)


class CensusAnswer(BaseModel):
    user: str = Field(min_length=1, max_length=24, pattern=NAME)
    answer: bool


class InjectFault(BaseModel):
    kind: Literal["caida_nodo", "latencia", "pico_demanda", "rumor"]
    target: str | None = Field(None, max_length=8, pattern=r"^a\d{2}$")


class RealFault(BaseModel):
    region: str = Field(min_length=3, max_length=40, pattern=r"^[a-z0-9-]+$")
    kind: Literal["latencia", "caida"]

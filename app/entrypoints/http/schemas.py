from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class NewMarket(BaseModel):
    question: str = Field(min_length=8, max_length=200)
    criteria: str = Field(min_length=8, max_length=600)
    b: float = Field(100, ge=10, le=1000)
    kind: Literal["presente", "futuro", "sala"] = "presente"
    threshold: float = Field(0.5, gt=0, lt=1)


class Trade(BaseModel):
    user: str = Field(min_length=1, max_length=24)
    outcome: Literal["YES", "NO"]
    amount: float = Field(gt=0, le=10_000)


class CensusAnswer(BaseModel):
    user: str = Field(min_length=1, max_length=24)
    answer: bool

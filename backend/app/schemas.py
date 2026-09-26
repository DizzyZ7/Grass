"""Strict client contracts. Client sends raw observations, never rewards."""
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class BatchIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    batch_id: UUID
    seq: int = Field(ge=1, le=10000)
    touches: int = Field(ge=1, le=80)
    duration_ms: int = Field(ge=0, le=30000)
    peak_combo: int = Field(ge=0, le=300)

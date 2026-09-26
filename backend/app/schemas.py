"""Strict client contracts. Client sends raw observations, never rewards."""
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict, StrictBool


class BatchIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    batch_id: UUID
    seq: int = Field(ge=1, le=10000)
    touches: int = Field(ge=1, le=80)
    duration_ms: int = Field(ge=0, le=30000)
    peak_combo: int = Field(ge=0, le=300)


class SelectWorldIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    code: str = Field(min_length=1, max_length=40, pattern=r'^[a-z][a-z0-9_]*$')


class PrivacyIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    show_public_profile: StrictBool

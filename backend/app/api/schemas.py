"""Shared request/response models."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import MEMORY_TYPES, SOURCE_TYPES


class TopicCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class TopicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class TopicDetailOut(TopicOut):
    source_count: int = 0
    memory_count: int = 0
    chunk_count: int = 0
    project_count: int = 0
    memory_types: dict[str, int] = Field(default_factory=dict)


class SourceCreate(BaseModel):
    type: str = Field(description=f"One of: {', '.join(SOURCE_TYPES)}")
    name: str = Field(min_length=1, max_length=512)
    uri: str | None = None
    metadata_json: dict = Field(default_factory=dict)
    # Convenience for pasted_text: stored into metadata_json["text"].
    text: str | None = None


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    topic_id: uuid.UUID
    type: str
    name: str
    uri: str | None
    status: str
    metadata_json: dict
    created_at: datetime
    updated_at: datetime


class MemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    topic_id: uuid.UUID
    project_id: uuid.UUID | None
    source_id: uuid.UUID | None
    type: str
    content: str
    confidence: float
    importance: float
    metadata_json: dict
    created_at: datetime


class MemorySearchRequest(BaseModel):
    query: str = Field(min_length=1)
    topic_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    types: list[str] | None = Field(default=None, description=f"Filter to: {', '.join(MEMORY_TYPES)}")
    limit: int = Field(default=10, ge=1, le=100)


class MemorySearchHit(BaseModel):
    memory: MemoryOut
    score: float
    similarity: float
    components: dict[str, float]


class MemorySearchResponse(BaseModel):
    query: str
    count: int
    weights: dict[str, float]
    results: list[MemorySearchHit]

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


# --- projects, tasks, runs, artifacts, approvals, decisions ---


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    goal: str | None = None
    topic_id: uuid.UUID | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    topic_id: uuid.UUID | None
    name: str
    goal: str | None
    status: str
    brief: str | None
    created_at: datetime
    updated_at: datetime


class ProjectDetailOut(ProjectOut):
    topic_name: str | None = None
    task_counts: dict[str, int] = Field(default_factory=dict)
    run_count: int = 0
    artifact_count: int = 0
    open_questions: int = 0
    pending_approvals: int = 0


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    description: str | None = None
    agent_role: str | None = None
    acceptance_criteria: list[str] = Field(default_factory=list)
    parent_task_id: uuid.UUID | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    agent_role: str | None = None
    status: str | None = None
    acceptance_criteria: list[str] | None = None
    evidence: list | None = None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    parent_task_id: uuid.UUID | None
    title: str
    description: str | None
    agent_role: str | None
    status: str
    acceptance_criteria: list
    evidence: list
    metadata_json: dict
    created_at: datetime
    updated_at: datetime


class AgentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID | None
    task_id: uuid.UUID | None
    agent_profile_id: uuid.UUID
    status: str
    input: dict
    output: dict | None
    error: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class ArtifactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    task_id: uuid.UUID | None
    type: str
    title: str
    content: str
    path: str | None
    created_at: datetime


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID | None
    task_id: uuid.UUID | None
    action_type: str
    action_summary: str
    risk_level: str
    status: str
    response: str | None
    metadata_json: dict
    created_at: datetime
    updated_at: datetime


class ApprovalResponse(BaseModel):
    status: str = Field(description="approved | rejected | cancelled")
    response: str | None = None


class DecisionCreate(BaseModel):
    question: str = Field(min_length=1)
    answer: str | None = None
    rationale: str | None = None
    decided_by: str | None = None


class DecisionAnswer(BaseModel):
    answer: str = Field(min_length=1)
    rationale: str | None = None
    decided_by: str = "human"


class DecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    question: str
    answer: str | None
    rationale: str | None
    decided_by: str | None
    metadata_json: dict
    created_at: datetime

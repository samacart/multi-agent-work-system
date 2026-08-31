"""Core data model for the Multi-Agent Work System.

Phase 1 creates every table in the brief so later phases only add behaviour,
not schema churn.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import get_settings
from app.db.base import Base, created_column, enum_column, pk_column, updated_column
from app.db.types import JSONType, Embedding

EMBEDDING_DIM = get_settings().embedding_dim

SOURCE_TYPES = (
    "local_folder",
    "local_file",
    "github_repo",
    "github_issue",
    "github_pr",
    "pasted_text",
    "url",
)
SOURCE_STATUSES = ("registered", "ingesting", "ingested", "failed")

MEMORY_TYPES = (
    "fact",
    "decision",
    "constraint",
    "risk",
    "architecture",
    "definition",
    "person",
    "system",
    "open_question",
    "lesson",
    "gotcha",
)

PROJECT_STATUSES = (
    "draft",
    "planning",
    "ready",
    "running",
    "blocked",
    "review",
    "delivered",
    "archived",
)

TASK_STATUSES = ("backlog", "ready", "in_progress", "blocked", "review", "verified", "done")

AGENT_ROLES = (
    "lead_pm",
    "architect",
    "developer",
    "qa",
    "code_reviewer",
    "security_reviewer",
    "domain_expert",
    "release_manager",
)

AGENT_RUN_STATUSES = ("pending", "running", "succeeded", "failed", "cancelled")

APPROVAL_STATUSES = ("pending", "approved", "rejected", "cancelled")
RISK_LEVELS = ("low", "medium", "high")

ARTIFACT_TYPES = (
    "project_brief",
    "architecture_plan",
    "task_breakdown",
    "test_report",
    "review_report",
    "security_report",
    "pr_description",
    "release_notes",
    "final_summary",
)


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[uuid.UUID] = pk_column()
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(sa.Text())
    created_at: Mapped[datetime] = created_column()
    updated_at: Mapped[datetime] = updated_column()

    sources: Mapped[list["Source"]] = relationship(back_populates="topic", cascade="all, delete-orphan")
    memories: Mapped[list["Memory"]] = relationship(back_populates="topic", cascade="all, delete-orphan")
    projects: Mapped[list["Project"]] = relationship(back_populates="topic")


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = pk_column()
    topic_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(enum_column("source_type", SOURCE_TYPES), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    uri: Mapped[str | None] = mapped_column(sa.Text())
    metadata_json: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(
        enum_column("source_status", SOURCE_STATUSES), default="registered", nullable=False
    )
    created_at: Mapped[datetime] = created_column()
    updated_at: Mapped[datetime] = updated_column()

    topic: Mapped[Topic] = relationship(back_populates="sources")
    chunks: Mapped[list["SourceChunk"]] = relationship(back_populates="source", cascade="all, delete-orphan")


class SourceChunk(Base):
    __tablename__ = "source_chunks"
    __table_args__ = (sa.UniqueConstraint("source_id", "content_hash", name="uq_source_chunk_hash"),)

    id: Mapped[uuid.UUID] = pk_column()
    source_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True)
    topic_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True)
    content: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    content_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Embedding(EMBEDDING_DIM))
    created_at: Mapped[datetime] = created_column()

    source: Mapped[Source] = relationship(back_populates="chunks")


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = pk_column()
    topic_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("sources.id", ondelete="SET NULL"))
    type: Mapped[str] = mapped_column(enum_column("memory_type", MEMORY_TYPES), nullable=False)
    content: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    confidence: Mapped[float] = mapped_column(sa.Float(), default=0.5, nullable=False)
    importance: Mapped[float] = mapped_column(sa.Float(), default=0.5, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Embedding(EMBEDDING_DIM))
    created_at: Mapped[datetime] = created_column()
    updated_at: Mapped[datetime] = updated_column()

    topic: Mapped[Topic] = relationship(back_populates="memories")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = pk_column()
    topic_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("topics.id", ondelete="SET NULL"), index=True)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    goal: Mapped[str | None] = mapped_column(sa.Text())
    status: Mapped[str] = mapped_column(enum_column("project_status", PROJECT_STATUSES), default="draft", nullable=False)
    brief: Mapped[str | None] = mapped_column(sa.Text())
    # The repository this project's agents work in. Global config forced a
    # server restart to point agents at a different directory, so two projects
    # could never target two repositories.
    workspace_path: Mapped[str | None] = mapped_column(sa.Text())
    created_at: Mapped[datetime] = created_column()
    updated_at: Mapped[datetime] = updated_column()

    topic: Mapped[Topic | None] = relationship(back_populates="projects")
    tasks: Mapped[list["Task"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    artifacts: Mapped[list["Artifact"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = pk_column()
    project_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("tasks.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text())
    agent_role: Mapped[str | None] = mapped_column(enum_column("agent_role", AGENT_ROLES))
    status: Mapped[str] = mapped_column(enum_column("task_status", TASK_STATUSES), default="backlog", nullable=False)
    acceptance_criteria: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    # Verification evidence attached by QA, one entry per criterion.
    evidence: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    # Planning metadata: task dependencies, originating run, and so on.
    metadata_json: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    created_at: Mapped[datetime] = created_column()
    updated_at: Mapped[datetime] = updated_column()

    project: Mapped[Project] = relationship(back_populates="tasks")
    subtasks: Mapped[list["Task"]] = relationship()


class AgentProfile(Base):
    __tablename__ = "agent_profiles"

    id: Mapped[uuid.UUID] = pk_column()
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False, unique=True)
    role: Mapped[str] = mapped_column(enum_column("agent_profile_role", AGENT_ROLES), nullable=False)
    system_prompt: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    allowed_tools_json: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    approval_rules_json: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    created_at: Mapped[datetime] = created_column()
    updated_at: Mapped[datetime] = updated_column()


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = pk_column()
    project_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("tasks.id", ondelete="SET NULL"), index=True)
    agent_profile_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("agent_profiles.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(enum_column("agent_run_status", AGENT_RUN_STATUSES), default="pending", nullable=False)
    input: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    output: Mapped[dict | None] = mapped_column(JSONType)
    error: Mapped[str | None] = mapped_column(sa.Text())
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = created_column()

    agent_profile: Mapped[AgentProfile] = relationship()


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[uuid.UUID] = pk_column()
    project_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    question: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    answer: Mapped[str | None] = mapped_column(sa.Text())
    rationale: Mapped[str | None] = mapped_column(sa.Text())
    decided_by: Mapped[str | None] = mapped_column(sa.String(255))
    # The options an agent offered and which one it recommends. A question
    # handed over without a view is work passed back, not a decision surfaced.
    metadata_json: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    created_at: Mapped[datetime] = created_column()


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id: Mapped[uuid.UUID] = pk_column()
    project_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("tasks.id", ondelete="SET NULL"))
    action_type: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    action_summary: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    risk_level: Mapped[str] = mapped_column(enum_column("risk_level", RISK_LEVELS), default="medium", nullable=False)
    status: Mapped[str] = mapped_column(enum_column("approval_status", APPROVAL_STATUSES), default="pending", nullable=False)
    requested_by_agent_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("agent_profiles.id", ondelete="SET NULL"))
    response: Mapped[str | None] = mapped_column(sa.Text())
    # A briefing on what is being approved: summary, recommendation, concerns.
    metadata_json: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    created_at: Mapped[datetime] = created_column()
    updated_at: Mapped[datetime] = updated_column()


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = pk_column()
    project_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("tasks.id", ondelete="SET NULL"))
    type: Mapped[str] = mapped_column(enum_column("artifact_type", ARTIFACT_TYPES), nullable=False)
    title: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    content: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    path: Mapped[str | None] = mapped_column(sa.Text())
    created_at: Mapped[datetime] = created_column()

    project: Mapped[Project] = relationship(back_populates="artifacts")

"""Top-level API router."""

from fastapi import APIRouter

from app.api.routes import agent_profiles, health, memory, projects, sources, system, topics

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(topics.router)
api_router.include_router(sources.router)
api_router.include_router(memory.router)
api_router.include_router(projects.router)
api_router.include_router(agent_profiles.router)
api_router.include_router(system.router)

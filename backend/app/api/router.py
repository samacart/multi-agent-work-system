"""Top-level API router."""

from fastapi import APIRouter

from app.api.routes import agent_profiles, health, system

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(agent_profiles.router)
api_router.include_router(system.router)

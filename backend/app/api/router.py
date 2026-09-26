from fastapi import APIRouter

from app.api import ambient, audio, hcps, health, intelligence, resources, sessions

api_router = APIRouter(prefix="/api")
for module in (health, hcps, resources, sessions, ambient, audio, intelligence):
    api_router.include_router(module.router)

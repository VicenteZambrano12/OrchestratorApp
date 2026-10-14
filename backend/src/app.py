from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from api.Endpoint.health import router as health_router
from api.Endpoint.chat import router as chat_router
from api.Endpoint.set_key import router as set_key_router
from api.Endpoint.users import router as users_router
from api.documentation import load_app_documentation


app = FastAPI(**load_app_documentation().model_dump())
app.include_router(health_router)
app.include_router(chat_router)
app.include_router(set_key_router)
app.include_router(users_router)
app.mount(
    "/database/images",
    StaticFiles(directory=Path(__file__).resolve().parents[2] / "database/images"),
    name="exercise-images",
)

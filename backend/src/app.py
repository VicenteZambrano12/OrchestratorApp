from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from api.Endpoint.health import router as health_router
from api.Endpoint.chat import router as chat_router
from api.Endpoint.set_key import router as set_key_router
from api.Endpoint.users import router as users_router
from api.Endpoint.active_routine import router as active_routine_router
from api.Endpoint.set_routine import router as set_routine_router
from api.Endpoint.register_user import router as register_user_router
from api.Endpoint.workouts import router as workouts_router
from api.documentation import load_app_documentation


app = FastAPI(**load_app_documentation().model_dump())
app.include_router(health_router)
app.include_router(chat_router)
app.include_router(set_key_router)
app.include_router(users_router)
app.include_router(active_routine_router)
app.include_router(set_routine_router)
app.include_router(register_user_router)
app.include_router(workouts_router)
app.mount(
    "/database/images",
    StaticFiles(directory=Path(__file__).resolve().parents[2] / "database/images"),
    name="exercise-images",
)

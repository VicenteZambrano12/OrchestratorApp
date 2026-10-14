from fastapi import FastAPI

from api.Endpoint.health import router as health_router
from api.Endpoint.chat import router as chat_router
from api.Endpoint.set_key import router as set_key_router
from api.documentation import load_app_documentation


app = FastAPI(**load_app_documentation().model_dump())
app.include_router(health_router)
app.include_router(chat_router)
app.include_router(set_key_router)

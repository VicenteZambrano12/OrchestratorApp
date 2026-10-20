"""Compose the FastAPI HTTP application for the AI orchestration backend.

This module is the application composition root: it configures logging, loads
validated OpenAPI metadata, installs request logging middleware, registers API
routers, and mounts exercise image storage. Importing the module performs this
initialization and exposes the ASGI application to the server.

The chat router delegates requests to the pipeline, which coordinates agent
selection and execution. Conversation context, LLM invocations, system prompt
assembly, and subsystem tool execution belong to downstream components rather
than this entry point. The remaining routers expose health, session-key, user,
routine, workout, and training-day operations.

Request body schemas, validation rules, endpoint summaries, and HTTP response
codes are defined by the registered routers and their Pydantic models. Global
API metadata is loaded through ``load_app_documentation``; this module does not
override endpoint contracts or translate their errors. Exercise images are
served separately at ``/database/images`` using the configured storage provider.

Attributes:
    app (FastAPI): ASGI application containing the registered API routes,
        request logging middleware, and exercise-image mount.

Initialization failures propagate to the importing server instead of exposing
a partially configured application. These include unreadable or invalid API
metadata and invalid image-storage configuration.
"""

from fastapi import FastAPI

from obervability.http import RequestLoggingMiddleware
from obervability.logger import Logger


# 1. Configure logging before router imports can initialize backend components.
Logger.configure()

from api.Endpoint.health import router as health_router
from api.Endpoint.chat import router as chat_router
from api.Endpoint.set_key import router as set_key_router
from api.Endpoint.users import router as users_router
from api.Endpoint.active_routine import router as active_routine_router
from api.Endpoint.set_routine import router as set_routine_router
from api.Endpoint.register_user import router as register_user_router
from api.Endpoint.workouts import router as workouts_router
from api.Endpoint.get_user_days import router as get_user_days_router
from api.documentation import load_app_documentation
from api.image_files import create_image_files


# 2. Validate global OpenAPI metadata before constructing the HTTP application.
app = FastAPI(**load_app_documentation().model_dump())
# 3. Apply request logging across the API and mounted image service.
app.add_middleware(RequestLoggingMiddleware)
# 4. Compose domain routers while preserving their validation and error contracts.
app.include_router(health_router)
app.include_router(chat_router)
app.include_router(set_key_router)
app.include_router(users_router)
app.include_router(active_routine_router)
app.include_router(set_routine_router)
app.include_router(register_user_router)
app.include_router(workouts_router)
app.include_router(get_user_days_router)
# 5. Select image storage at initialization, independently of agent execution.
app.mount(
    "/database/images",
    create_image_files(),
    name="exercise-images",
)
# 6. Record completion only after all routes and the image mount are registered.
Logger.get_logger(__name__).info("Backend application initialized")

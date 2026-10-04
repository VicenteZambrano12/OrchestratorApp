from fastapi import FastAPI

from api.Endpoint.health import router


app = FastAPI(title="OrchestratorApp")
app.include_router(router)

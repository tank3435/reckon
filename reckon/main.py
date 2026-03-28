from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from reckon.api.assessment import router as assessment_router
from reckon.api.assessments import router as assessments_router
from reckon.api.indicators import router as indicators_router
from reckon.api.ingestion import router as ingestion_router
from reckon.api.locations import router as locations_router
from reckon.db import engine
from reckon.models import *  # noqa: F401,F403 — ensure models are registered
import reckon.db as db_module


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup (use Alembic migrations in production)
    async with engine.begin() as conn:
        await conn.run_sync(db_module.Base.metadata.create_all)
    yield


app = FastAPI(
    title="Reckon",
    description="How bad is it, really? Empirical risk grounding across four tiers.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(assessment_router, prefix="/api")
app.include_router(assessments_router)
app.include_router(indicators_router, prefix="/api")
app.include_router(ingestion_router)
app.include_router(locations_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}

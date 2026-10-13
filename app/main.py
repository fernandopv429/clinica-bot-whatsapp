import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import db, scheduler
from app.webhook import router as webhook_router

logging.basicConfig(level=logging.INFO, format="[clinica] %(asctime)s %(name)s %(levelname)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    scheduler.start()
    yield
    scheduler.stop()
    await db.disconnect()


app = FastAPI(title="Clínica Bot WhatsApp", lifespan=lifespan)
app.include_router(webhook_router)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}

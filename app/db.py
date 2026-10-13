import logging
from pathlib import Path

import asyncpg

from app.config import DATABASE_URL

log = logging.getLogger("clinica.db")

_pool: asyncpg.Pool | None = None


async def connect() -> None:
    global _pool
    _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
    schema = (Path(__file__).resolve().parent.parent / "schema.sql").read_text()
    async with _pool.acquire() as conn:
        await conn.execute(schema)
    log.info("conectado ao banco e schema aplicado")


async def disconnect() -> None:
    if _pool is not None:
        await _pool.close()


def pool() -> asyncpg.Pool:
    assert _pool is not None, "db.connect() ainda não foi chamado"
    return _pool

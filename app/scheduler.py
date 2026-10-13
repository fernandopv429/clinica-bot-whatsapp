"""Módulo 2 (parte ativa): varre a agenda em segundo plano e dispara o lembrete de 24h."""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app import evolution, repo
from app.config import REMINDER_INTERVAL_MINUTES, TZ_NAME

log = logging.getLogger("clinica.scheduler")
_tz = ZoneInfo(TZ_NAME)

_scheduler: AsyncIOScheduler | None = None


async def job_lembrete_24h() -> None:
    agora = datetime.now(_tz)
    amanha = agora.date() + timedelta(days=1)
    inicio = datetime.combine(amanha, datetime.min.time(), tzinfo=_tz)
    fim = datetime.combine(amanha, datetime.max.time(), tzinfo=_tz)

    consultas = await repo.get_consultas_para_lembrete(inicio, fim)
    for c in consultas:
        texto = (
            f"Olá, {c['paciente_nome']}! Passando para lembrar da sua consulta amanhã às "
            f"{c['data_hora'].astimezone(_tz).strftime('%H:%M')} com Dr(a). "
            f"{c['profissional_nome'] or 'nossa equipe'}. "
            f"Responda 1 para Confirmar ou 2 se precisar reagendar."
        )
        await evolution.send_text(c["instancia_whatsapp"], c["paciente_telefone"], texto)
        await repo.mark_lembrete_enviado(c["id"])
        log.info("lembrete enviado para consulta %s", c["id"])


def start() -> None:
    global _scheduler
    _scheduler = AsyncIOScheduler(timezone=_tz)
    _scheduler.add_job(job_lembrete_24h, "interval", minutes=REMINDER_INTERVAL_MINUTES, id="lembrete_24h")
    _scheduler.start()
    log.info("scheduler iniciado (lembrete a cada %s min)", REMINDER_INTERVAL_MINUTES)


def stop() -> None:
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)

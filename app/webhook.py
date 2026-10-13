import logging
import re

from fastapi import APIRouter, BackgroundTasks, Request

from app import ai_monitor, reply_handler, repo

log = logging.getLogger("clinica.webhook")
router = APIRouter()


def _extrair_texto(mensagem: dict) -> str | None:
    if not mensagem:
        return None
    if "conversation" in mensagem:
        return mensagem["conversation"]
    if "extendedTextMessage" in mensagem:
        return mensagem["extendedTextMessage"].get("text")
    return None


async def _processar_evento(payload: dict) -> None:
    if payload.get("event") != "messages.upsert":
        return

    instancia = payload.get("instance")
    data = payload.get("data") or {}
    key = data.get("key") or {}
    remote_jid = key.get("remoteJid", "")

    if not instancia or not remote_jid or remote_jid.endswith("@g.us"):
        return  # sem instância conhecida, ou mensagem de grupo — fora do escopo

    texto = _extrair_texto(data.get("message"))
    if not texto:
        return  # mídia, figurinha etc. — nada a monitorar

    clinica = await repo.get_clinica_by_instancia(instancia)
    if clinica is None:
        log.warning("webhook recebido de instância não cadastrada: %s", instancia)
        return

    telefone = re.sub(r"\D", "", remote_jid.split("@")[0])
    from_me = bool(key.get("fromMe"))
    conversa_id = remote_jid

    if not from_me:
        tratado = await reply_handler.tratar_resposta_paciente(clinica, telefone, texto)
        if tratado:
            return

    await repo.add_mensagem_contexto(
        clinica["id"], conversa_id, "atendente" if from_me else "paciente", texto
    )
    await ai_monitor.analisar_conversa(clinica, conversa_id, telefone)


@router.post("/webhook/evolution")
async def webhook_evolution(request: Request, background_tasks: BackgroundTasks):
    payload = await request.json()
    # processa em background pra responder rápido ao Evolution API (ele reenvia se demorar/der erro)
    background_tasks.add_task(_processar_evento, payload)
    return {"ok": True}

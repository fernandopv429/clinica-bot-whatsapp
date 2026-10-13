import logging

import httpx

from app.config import EVOLUTION_API_KEY, EVOLUTION_API_URL

log = logging.getLogger("clinica.evolution")


async def send_text(instancia: str, telefone: str, mensagem: str) -> None:
    """Envia uma mensagem de texto via Evolution API para o número informado."""
    url = f"{EVOLUTION_API_URL}/message/sendText/{instancia}"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    payload = {"number": telefone, "text": mensagem}
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()
        except httpx.HTTPError as e:
            log.error("falha ao enviar mensagem via Evolution API (%s -> %s): %s", instancia, telefone, e)

"""Módulo 2 (parte reativa): trata a resposta do paciente ao lembrete de 24h.
Também dá prioridade a uma oferta de vaga da lista de espera, se houver uma pendente."""

import logging

from app import evolution, repo, waitlist

log = logging.getLogger("clinica.reply_handler")

CONFIRMAR_TOKENS = {"1", "confirmar", "confirmo", "sim", "ok"}
CANCELAR_TOKENS = {"2", "cancelar", "reagendar", "não posso", "nao posso", "não vou poder", "nao vou poder"}


async def tratar_resposta_paciente(clinica, telefone: str, texto: str) -> bool:
    """Retorna True se a mensagem foi tratada por um fluxo determinístico (lembrete ou
    lista de espera) — nesse caso o monitor de IA não precisa olhar pra ela."""

    if await waitlist.tratar_resposta(clinica, telefone, texto):
        return True

    consulta = await repo.get_consulta_pendente_confirmacao(clinica["id"], telefone)
    if consulta is None:
        return False

    resposta = texto.strip().lower()

    if resposta in CONFIRMAR_TOKENS:
        await repo.update_consulta_status(consulta["id"], "confirmado")
        await evolution.send_text(clinica["instancia_whatsapp"], telefone, "Consulta confirmada! Te esperamos. ✅")
        return True

    if resposta in CANCELAR_TOKENS:
        await repo.update_consulta_status(consulta["id"], "cancelado")
        await evolution.send_text(
            clinica["instancia_whatsapp"], telefone,
            "Tudo bem, vamos reagendar. Nossa equipe vai entrar em contato com novos horários.",
        )
        if clinica["telefone_recepcao"]:
            await evolution.send_text(
                clinica["instancia_whatsapp"], clinica["telefone_recepcao"],
                f"⚠️ Paciente (tel. {telefone}) cancelou/pediu reagendamento da consulta de "
                f"{consulta['data_hora'].strftime('%d/%m às %H:%M')}.",
            )
        await waitlist.avisar_vaga_liberada(clinica, consulta["profissional_id"], consulta["data_hora"])
        return True

    return False

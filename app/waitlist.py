"""Módulo 3: aviso de horário disponível (encaixe e lista de espera)."""

import logging
from datetime import datetime

from app import evolution, repo

log = logging.getLogger("clinica.waitlist")

RESPOSTAS_SIM = {"sim", "s", "quero", "aceito", "1"}


async def avisar_vaga_liberada(clinica, profissional_id, data_hora: datetime) -> None:
    candidato = await repo.claim_next_waitlist(clinica["id"], profissional_id, data_hora)
    if candidato is None:
        log.info("vaga liberada na clínica %s mas a lista de espera está vazia", clinica["id"])
        return

    profissional = await repo.get_profissional(profissional_id) if profissional_id else None
    nome_profissional = profissional["nome"] if profissional else "nossa equipe"
    paciente_row = await repo.get_paciente(candidato["paciente_id"])
    if paciente_row is None:
        log.warning("paciente %s da lista de espera não encontrado", candidato["paciente_id"])
        return

    texto = (
        f"Olá, {paciente_row['nome']}! Surgiu um horário de última hora hoje/amanhã às "
        f"{data_hora.strftime('%H:%M')} com Dr(a). {nome_profissional}. "
        f"Você tem interesse em ocupar essa vaga? Responda SIM para aceitar."
    )
    await evolution.send_text(clinica["instancia_whatsapp"], paciente_row["telefone"], texto)
    log.info(
        "vaga de %s oferecida ao paciente %s (clínica %s)",
        data_hora.strftime("%d/%m às %H:%M"), paciente_row["id"], clinica["id"],
    )


async def tratar_resposta(clinica, telefone: str, texto: str) -> bool:
    """Se houver uma oferta de vaga pendente para esse telefone e a resposta for positiva,
    converte em consulta oficial. Retorna True se tratou a mensagem aqui (pra não cair
    em nenhum outro fluxo)."""
    pendente = await repo.get_waitlist_contatado_por_telefone(clinica["id"], telefone)
    if pendente is None:
        return False

    if texto.strip().lower() not in RESPOSTAS_SIM:
        return False

    consulta = await repo.convert_waitlist_to_consulta(pendente, clinica["id"])
    await evolution.send_text(
        clinica["instancia_whatsapp"], telefone,
        f"Perfeito! Sua consulta foi confirmada para {pendente['horario_oferecido'].strftime('%d/%m às %H:%M')}. Até lá!",
    )
    log.info("vaga convertida em consulta %s (clínica %s)", consulta["id"], clinica["id"])
    return True

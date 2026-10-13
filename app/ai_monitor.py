"""Módulo 1: IA Passiva (Monitor). Lê o histórico da conversa e, só quando identifica um
agendamento fechado, chama a função que grava a consulta no banco."""

import json
import logging
import re
from datetime import datetime

from openai import AsyncOpenAI

from app import repo
from app.config import CONTEXT_WINDOW_MESSAGES, MONITOR_SYSTEM_PROMPT, OPENAI_MODEL

log = logging.getLogger("clinica.ai_monitor")

REGISTRAR_CONSULTA_TOOL = {
    "type": "function",
    "function": {
        "name": "registrar_consulta",
        "description": "Registra uma consulta médica/odontológica que acabou de ser fechada na conversa.",
        "parameters": {
            "type": "object",
            "properties": {
                "nome_paciente": {"type": "string", "description": "Nome completo do paciente"},
                "telefone": {"type": "string", "description": "Telefone do paciente, com DDD"},
                "data_hora": {
                    "type": "string",
                    "description": "Data e hora combinadas da consulta, em ISO 8601 (ex: 2026-10-20T14:30:00-03:00)",
                },
                "profissional": {"type": "string", "description": "Nome do médico, dentista ou especialista combinado"},
            },
            "required": ["nome_paciente", "telefone", "data_hora", "profissional"],
        },
    },
}


def _montar_transcricao(mensagens) -> str:
    linhas = []
    for m in mensagens:
        quem = "Atendente" if m["remetente"] == "atendente" else "Paciente"
        linhas.append(f"{quem}: {m['conteudo']}")
    return "\n".join(linhas)


async def analisar_conversa(clinica, conversa_id: str, telefone_paciente: str) -> None:
    mensagens = await repo.get_contexto(clinica["id"], conversa_id, CONTEXT_WINDOW_MESSAGES)
    if not mensagens:
        return
    transcricao = _montar_transcricao(mensagens)

    client = AsyncOpenAI(api_key=clinica["openai_api_key"])
    try:
        resposta = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": MONITOR_SYSTEM_PROMPT},
                {"role": "user", "content": f"Histórico da conversa:\n\n{transcricao}"},
            ],
            tools=[REGISTRAR_CONSULTA_TOOL],
            tool_choice="auto",
        )
    except Exception:
        log.exception("falha ao chamar a OpenAI para a clínica %s", clinica["id"])
        return

    tool_calls = resposta.choices[0].message.tool_calls or []
    for call in tool_calls:
        if call.function.name != "registrar_consulta":
            continue
        try:
            args = json.loads(call.function.arguments)
        except json.JSONDecodeError:
            log.warning("argumentos inválidos do function call: %s", call.function.arguments)
            continue
        await _salvar_consulta(clinica, args, telefone_paciente)


async def _salvar_consulta(clinica, args: dict, telefone_fallback: str) -> None:
    nome_paciente = (args.get("nome_paciente") or "").strip()
    telefone = re.sub(r"\D", "", args.get("telefone") or "") or re.sub(r"\D", "", telefone_fallback)
    nome_profissional = (args.get("profissional") or "").strip()

    try:
        data_hora = datetime.fromisoformat(args["data_hora"])
    except (KeyError, ValueError):
        log.warning("data_hora inválida vinda da IA: %r (clínica %s)", args.get("data_hora"), clinica["id"])
        return

    if not nome_paciente or not telefone:
        log.warning("IA sinalizou agendamento sem nome/telefone suficiente (clínica %s): %r", clinica["id"], args)
        return

    paciente = await repo.upsert_paciente(clinica["id"], nome_paciente, telefone)

    profissional = None
    if nome_profissional:
        profissional = await repo.find_profissional_by_nome(clinica["id"], nome_profissional)
        if profissional is None:
            log.warning(
                "profissional '%s' não encontrado no cadastro da clínica %s — consulta será salva sem vínculo",
                nome_profissional, clinica["id"],
            )

    consulta = await repo.create_consulta(
        clinica["id"], paciente["id"], profissional["id"] if profissional else None, data_hora
    )
    log.info("consulta %s registrada pela IA para a clínica %s", consulta["id"], clinica["id"])

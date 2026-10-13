"""Acesso a dados. Cada função abre sua própria conexão do pool — sem ORM, só SQL direto."""

from datetime import datetime

import asyncpg

from app.db import pool


async def get_clinica_by_instancia(instancia: str) -> asyncpg.Record | None:
    return await pool().fetchrow(
        "SELECT * FROM clinicas WHERE instancia_whatsapp = $1 AND ativa = true", instancia
    )


async def get_clinica(clinica_id) -> asyncpg.Record | None:
    return await pool().fetchrow("SELECT * FROM clinicas WHERE id = $1", clinica_id)


async def upsert_paciente(clinica_id, nome: str, telefone: str) -> asyncpg.Record:
    return await pool().fetchrow(
        """
        INSERT INTO pacientes (clinica_id, nome, telefone)
        VALUES ($1, $2, $3)
        ON CONFLICT (clinica_id, telefone) DO UPDATE SET nome = EXCLUDED.nome
        RETURNING *
        """,
        clinica_id, nome, telefone,
    )


async def get_paciente(paciente_id) -> asyncpg.Record | None:
    return await pool().fetchrow("SELECT * FROM pacientes WHERE id = $1", paciente_id)


async def get_paciente_by_telefone(clinica_id, telefone: str) -> asyncpg.Record | None:
    return await pool().fetchrow(
        "SELECT * FROM pacientes WHERE clinica_id = $1 AND telefone = $2", clinica_id, telefone
    )


async def find_profissional_by_nome(clinica_id, nome: str) -> asyncpg.Record | None:
    return await pool().fetchrow(
        "SELECT * FROM profissionais WHERE clinica_id = $1 AND nome ILIKE $2 LIMIT 1",
        clinica_id, f"%{nome}%",
    )


async def get_profissional(profissional_id) -> asyncpg.Record | None:
    return await pool().fetchrow("SELECT * FROM profissionais WHERE id = $1", profissional_id)


async def create_consulta(clinica_id, paciente_id, profissional_id, data_hora: datetime) -> asyncpg.Record:
    return await pool().fetchrow(
        """
        INSERT INTO consultas (clinica_id, paciente_id, profissional_id, data_hora)
        VALUES ($1, $2, $3, $4)
        RETURNING *
        """,
        clinica_id, paciente_id, profissional_id, data_hora,
    )


async def get_consultas_para_lembrete(inicio: datetime, fim: datetime) -> list[asyncpg.Record]:
    return await pool().fetch(
        """
        SELECT c.id, c.data_hora, cl.instancia_whatsapp, cl.id AS clinica_id,
               p.nome AS paciente_nome, p.telefone AS paciente_telefone,
               pr.nome AS profissional_nome
        FROM consultas c
        JOIN clinicas cl ON cl.id = c.clinica_id
        JOIN pacientes p ON p.id = c.paciente_id
        LEFT JOIN profissionais pr ON pr.id = c.profissional_id
        WHERE c.status = 'agendado' AND c.lembrete_enviado = false
          AND c.data_hora BETWEEN $1 AND $2
        """,
        inicio, fim,
    )


async def mark_lembrete_enviado(consulta_id) -> None:
    await pool().execute("UPDATE consultas SET lembrete_enviado = true WHERE id = $1", consulta_id)


async def get_consulta_pendente_confirmacao(clinica_id, telefone: str) -> asyncpg.Record | None:
    return await pool().fetchrow(
        """
        SELECT c.* FROM consultas c
        JOIN pacientes p ON p.id = c.paciente_id
        WHERE c.clinica_id = $1 AND p.telefone = $2
          AND c.status = 'agendado' AND c.lembrete_enviado = true
        ORDER BY c.data_hora ASC
        LIMIT 1
        """,
        clinica_id, telefone,
    )


async def update_consulta_status(consulta_id, status: str) -> asyncpg.Record:
    return await pool().fetchrow(
        "UPDATE consultas SET status = $2 WHERE id = $1 RETURNING *", consulta_id, status
    )


async def add_mensagem_contexto(clinica_id, conversa_id: str, remetente: str, conteudo: str) -> None:
    await pool().execute(
        "INSERT INTO mensagens_contexto (clinica_id, conversa_id, remetente, conteudo) VALUES ($1, $2, $3, $4)",
        clinica_id, conversa_id, remetente, conteudo,
    )


async def get_contexto(clinica_id, conversa_id: str, limite: int) -> list[asyncpg.Record]:
    rows = await pool().fetch(
        """
        SELECT remetente, conteudo, criado_em FROM mensagens_contexto
        WHERE clinica_id = $1 AND conversa_id = $2
        ORDER BY criado_em DESC
        LIMIT $3
        """,
        clinica_id, conversa_id, limite,
    )
    return list(reversed(rows))


async def claim_next_waitlist(clinica_id, profissional_id, horario_oferecido: datetime) -> asyncpg.Record | None:
    """Trava atomicamente o primeiro da fila (preferência pro profissional, senão qualquer um)
    e grava o horário que foi oferecido a ele, pra usar se ele aceitar depois."""
    return await pool().fetchrow(
        """
        UPDATE lista_espera SET status = 'contatado', horario_oferecido = $3
        WHERE id = (
          SELECT id FROM lista_espera
          WHERE clinica_id = $1 AND status = 'ativo'
            AND (profissional_preferido_id = $2 OR profissional_preferido_id IS NULL)
          ORDER BY (profissional_preferido_id = $2) DESC, criado_em ASC
          LIMIT 1
          FOR UPDATE SKIP LOCKED
        )
        RETURNING *
        """,
        clinica_id, profissional_id, horario_oferecido,
    )


async def get_waitlist_contatado_por_telefone(clinica_id, telefone: str) -> asyncpg.Record | None:
    return await pool().fetchrow(
        """
        SELECT le.* FROM lista_espera le
        JOIN pacientes p ON p.id = le.paciente_id
        WHERE le.clinica_id = $1 AND p.telefone = $2 AND le.status = 'contatado'
        ORDER BY le.criado_em ASC
        LIMIT 1
        """,
        clinica_id, telefone,
    )


async def convert_waitlist_to_consulta(lista_espera, clinica_id) -> asyncpg.Record:
    lista_espera_id = lista_espera["id"]
    paciente_id = lista_espera["paciente_id"]
    profissional_id = lista_espera["profissional_preferido_id"]
    data_hora = lista_espera["horario_oferecido"]
    async with pool().acquire() as conn:
        async with conn.transaction():
            consulta = await conn.fetchrow(
                """
                INSERT INTO consultas (clinica_id, paciente_id, profissional_id, data_hora)
                VALUES ($1, $2, $3, $4)
                RETURNING *
                """,
                clinica_id, paciente_id, profissional_id, data_hora,
            )
            await conn.execute(
                "UPDATE lista_espera SET status = 'convertido' WHERE id = $1", lista_espera_id
            )
            return consulta

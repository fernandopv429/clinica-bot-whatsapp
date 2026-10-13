-- Esquema do banco de dados. Idempotente: roda toda vez que a aplicação sobe (ver app/db.py).

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS clinicas (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nome                TEXT NOT NULL,
  instancia_whatsapp  TEXT NOT NULL UNIQUE,
  openai_api_key      TEXT NOT NULL,
  telefone_recepcao   TEXT,
  ativa               BOOLEAN NOT NULL DEFAULT true,
  criado_em           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pacientes (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  clinica_id  UUID NOT NULL REFERENCES clinicas(id) ON DELETE CASCADE,
  nome        TEXT NOT NULL,
  telefone    TEXT NOT NULL,
  criado_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (clinica_id, telefone)
);

CREATE TABLE IF NOT EXISTS profissionais (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  clinica_id    UUID NOT NULL REFERENCES clinicas(id) ON DELETE CASCADE,
  nome          TEXT NOT NULL,
  especialidade TEXT,
  criado_em     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS consultas (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  clinica_id        UUID NOT NULL REFERENCES clinicas(id) ON DELETE CASCADE,
  paciente_id       UUID NOT NULL REFERENCES pacientes(id) ON DELETE CASCADE,
  profissional_id   UUID REFERENCES profissionais(id) ON DELETE SET NULL,
  data_hora         TIMESTAMPTZ NOT NULL,
  status            TEXT NOT NULL DEFAULT 'agendado'
                      CHECK (status IN ('agendado','confirmado','cancelado','realizado')),
  lembrete_enviado  BOOLEAN NOT NULL DEFAULT false,
  criado_em         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_consultas_lembrete ON consultas (clinica_id, data_hora) WHERE status = 'agendado' AND lembrete_enviado = false;
CREATE INDEX IF NOT EXISTS idx_consultas_paciente ON consultas (paciente_id, data_hora DESC);

CREATE TABLE IF NOT EXISTS lista_espera (
  id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  clinica_id                  UUID NOT NULL REFERENCES clinicas(id) ON DELETE CASCADE,
  paciente_id                 UUID NOT NULL REFERENCES pacientes(id) ON DELETE CASCADE,
  profissional_preferido_id   UUID REFERENCES profissionais(id) ON DELETE SET NULL,
  preferencia_periodo         TEXT NOT NULL DEFAULT 'qualquer'
                                 CHECK (preferencia_periodo IN ('manha','tarde','qualquer')),
  status                      TEXT NOT NULL DEFAULT 'ativo'
                                 CHECK (status IN ('ativo','contatado','convertido','inativo')),
  horario_oferecido           TIMESTAMPTZ,
  criado_em                   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_lista_espera_fila ON lista_espera (clinica_id, profissional_preferido_id, criado_em) WHERE status = 'ativo';

-- Janela de contexto da conversa, usada só pelo monitor de IA para saber o que já foi dito
-- (não é um requisito do pedido original, mas é o jeito de implementar "agrupar as últimas mensagens").
CREATE TABLE IF NOT EXISTS mensagens_contexto (
  id           BIGSERIAL PRIMARY KEY,
  clinica_id   UUID NOT NULL REFERENCES clinicas(id) ON DELETE CASCADE,
  conversa_id  TEXT NOT NULL,
  remetente    TEXT NOT NULL CHECK (remetente IN ('atendente','paciente')),
  conteudo     TEXT NOT NULL,
  criado_em    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_mensagens_conversa ON mensagens_contexto (clinica_id, conversa_id, criado_em DESC);

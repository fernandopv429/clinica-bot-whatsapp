# Clínica Bot WhatsApp

Microsserviço de automação para clínicas médicas/odontológicas, integrado ao WhatsApp via
Evolution API. A secretária atende normalmente no chat; a IA fica em segundo plano só
monitorando a conversa para registrar a consulta no banco quando o agendamento é fechado.
Além disso, dispara lembretes de 24h e oferece vagas da lista de espera quando alguém cancela.

```
app/
  main.py           app FastAPI + ciclo de vida (conecta no banco, sobe o scheduler)
  webhook.py        recebe o webhook da Evolution API (messages.upsert)
  ai_monitor.py      Módulo 1: IA passiva que lê o histórico e registra a consulta (function calling)
  reply_handler.py  Módulo 2 (reativo): trata resposta "1"/"2" ao lembrete de 24h
  scheduler.py       Módulo 2 (ativo): cron que varre a agenda e dispara o lembrete
  waitlist.py        Módulo 3: oferece vaga liberada pro primeiro da lista de espera
  repo.py            acesso a dados (SQL direto via asyncpg, sem ORM)
  evolution.py        cliente HTTP da Evolution API
  db.py, config.py    conexão com o Postgres e variáveis de ambiente
schema.sql           schema do banco — aplicado automaticamente a cada start da aplicação
Dockerfile
```

## Arquitetura
- **Multi-tenant**: cada clínica tem sua própria instância da Evolution API e sua própria
  chave da OpenAI (cadastradas na tabela `clinicas`). O custo de IA fica com a clínica, não
  com quem opera o sistema.
- **IA passiva (Monitor)**: a cada mensagem trocada na conversa, o backend acumula o histórico
  recente (`mensagens_contexto`) e manda pra OpenAI com o system prompt de monitor. Só quando o
  modelo identifica um agendamento fechado ele aciona a função `registrar_consulta`
  (function calling) — aí sim o backend valida/cria o paciente e grava a consulta.
- **Lembrete de 24h**: um job em `APScheduler` roda a cada `REMINDER_INTERVAL_MINUTES` e varre
  consultas do dia seguinte ainda sem lembrete enviado.
- **Resposta ao lembrete**: se o paciente responder "1" (confirmar) ou "2" (cancelar/reagendar)
  numa consulta com lembrete pendente, o status é atualizado automaticamente. No cancelamento,
  a recepção é avisada (campo opcional `telefone_recepcao` da clínica) e a vaga é oferecida pro
  próximo da lista de espera.
- **Lista de espera**: a oferta de vaga trava o primeiro da fila atomicamente (`FOR UPDATE SKIP
  LOCKED`), então mesmo que várias vagas abram ao mesmo tempo não tem risco de oferecer a mesma
  vaga pra duas pessoas. Quando o paciente responde "SIM", a entrada é convertida numa consulta
  oficial.

## Banco de dados
`schema.sql` roda (idempotente, `CREATE TABLE IF NOT EXISTS`) toda vez que a aplicação sobe —
não precisa rodar migração manual. As tabelas são: `clinicas`, `pacientes`, `profissionais`,
`consultas`, `lista_espera` (todas conforme especificado) e `mensagens_contexto`, que guarda a
janela de histórico que a IA usa pra analisar a conversa (necessária pra implementar o
"agrupar as últimas mensagens", não fazia parte do desenho original das 5 tabelas).

## Variáveis de ambiente
| Variável | Obrigatória | O que faz |
|---|---|---|
| `DATABASE_URL` | **Sim** | String de conexão do PostgreSQL |
| `EVOLUTION_API_URL` | **Sim** | URL base da sua Evolution API |
| `EVOLUTION_API_KEY` | **Sim** | Chave global da Evolution API (usada para enviar mensagens em qualquer instância) |
| `REMINDER_INTERVAL_MINUTES` | Não | Intervalo do cron de lembrete. Padrão `30` |
| `CONTEXT_WINDOW_MESSAGES` | Não | Quantas mensagens recentes a IA recebe de contexto. Padrão `20` |
| `OPENAI_MODEL` | Não | Padrão `gpt-4o-mini` |
| `TZ` | Não | Fuso horário. Padrão `America/Sao_Paulo` |

A chave da OpenAI **não** é uma variável de ambiente — ela é cadastrada por clínica, na coluna
`openai_api_key` da tabela `clinicas` (cada clínica usa a própria conta).

## Deploy no Coolify
1. **Application** → aponte pro repositório.
2. **Build Pack**: Dockerfile.
3. **Ports Exposes**: `8000`.
4. **Environment Variables**: cadastre as obrigatórias da tabela acima.
5. Deploy. O healthcheck já está em `/healthz`.

## Cadastrando uma clínica
Não existe painel administrativo ainda — o cadastro é direto no banco:
```sql
INSERT INTO clinicas (nome, instancia_whatsapp, openai_api_key, telefone_recepcao)
VALUES ('Clínica Exemplo', 'nome-da-instancia-na-evolution', 'sk-...', '5511999999999');

INSERT INTO profissionais (clinica_id, nome, especialidade)
VALUES ('<id-da-clinica>', 'Dr. Fulano', 'Clínico geral');
```
O `instancia_whatsapp` precisa ser exatamente o nome da instância configurada na sua Evolution
API, e o webhook da instância precisa apontar para `https://seu-dominio/webhook/evolution`
(evento `messages.upsert`, modo HTTP).

## O que foi testado e o que não foi
**Testado, em ambiente local (Postgres descartável + Evolution API/OpenAI falsos):**
- Build da imagem e subida do container: schema aplicado automaticamente, `/healthz` OK.
- Webhook → fluxo completo de ponta a ponta: resposta "2" ao lembrete cancela a consulta,
  avisa a recepção e oferece a vaga pro próximo da lista de espera; resposta "SIM" converte a
  entrada da lista de espera numa consulta oficial.
- Job de lembrete de 24h rodado manualmente: encontra as consultas do dia seguinte sem
  lembrete e marca `lembrete_enviado = true`.
- Mensagem de negociação (sem ser resposta curta) cai no monitor de IA: fica registrada em
  `mensagens_contexto` e a chamada à OpenAI falha **graciosamente** com chave inválida (não
  derruba a aplicação — exatamente o comportamento esperado quando uma clínica configurar uma
  chave errada).

**Não testado:**
- Chamada real à OpenAI com function calling (preciso de uma chave de verdade pra validar se o
  modelo aciona `registrar_consulta` do jeito esperado, e ajustar o prompt se necessário).
- Payload real do webhook da sua Evolution API (o parser em `webhook.py` assume o formato
  comum de `messages.upsert` com `message.conversation` ou `message.extendedTextMessage.text` —
  se a sua versão vier diferente, ajusto).
- Envio real de mensagem pela Evolution API (testei só contra URL falsa — preciso da URL/chave
  reais pra confirmar o formato do `sendText`).
- Execução dentro do Coolify e conexão com o Postgres de produção.

## Limitações conhecidas
- O vínculo do profissional extraído pela IA é por nome (`ILIKE '%nome%'`) — se não achar, a
  consulta é salva sem profissional vinculado e um aviso fica no log. Não cria profissional
  novo automaticamente.
- Não há autenticação no endpoint `/webhook/evolution` — quem souber a URL pode postar payloads
  falsos. Se quiser, dá pra validar um header/segredo que a Evolution API manda no webhook.
- A IA é chamada a cada mensagem trocada na conversa (no limite do que o prompt pede: "monitore
  cada mensagem"). Isso tem custo pra clínica a cada mensagem — se o volume for alto, vale
  revisitar (ex: só analisar quando a atendente escrever, ou agrupar por um pequeno delay).

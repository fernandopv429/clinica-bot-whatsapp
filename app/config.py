import os

DATABASE_URL = os.environ["DATABASE_URL"]
EVOLUTION_API_URL = os.environ["EVOLUTION_API_URL"].rstrip("/")
EVOLUTION_API_KEY = os.environ["EVOLUTION_API_KEY"]

REMINDER_INTERVAL_MINUTES = int(os.environ.get("REMINDER_INTERVAL_MINUTES", "30"))
CONTEXT_WINDOW_MESSAGES = int(os.environ.get("CONTEXT_WINDOW_MESSAGES", "20"))
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
TZ_NAME = os.environ.get("TZ", "America/Sao_Paulo")

MONITOR_SYSTEM_PROMPT = (
    "Você é um assistente analítico invisível. Sua única função é monitorar o histórico de "
    "conversas entre a atendente da clínica e o paciente. Analise se a conversa resultou em um "
    "acordo de agendamento fechado (data e hora definidas e aceitas). Se houver um agendamento "
    "confirmado, você DEVE acionar a função de salvamento. Se a conversa ainda estiver em "
    "negociação ou for apenas tirada de dúvidas, não faça nada."
)

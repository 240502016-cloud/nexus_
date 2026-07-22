from app.config import settings
from app.services.ollama.client import DEFAULT_SYSTEM_PROMPT, OllamaError, ollama_client


def handle_command(context):
    """plugin.json'daki entry_point ('main:handle_command') tarafından çağrılır.

    backend/app/services/ollama/client.py'deki paylaşılan OllamaClient'ı kullanır - böylece
    bu komut ile /ai REST uç noktaları aynı bağlantı ayarlarını (base_url/api_key; hibrit
    mimaride uzak bir "AI işlem sunucusu"na işaret edebilir) paylaşır. Anthropic/OpenAI gibi
    ücretli bir API kullanmaz - internet bağlantısı veya API anahtarı gerekmez.
    """
    question = (context.args or "").strip()
    if not question:
        return "Kullanım: /sor <soru>"

    try:
        response = ollama_client.chat(
            settings.ollama_default_model,
            [
                {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
        )
    except OllamaError as exc:
        return f"AI asistan şu anda yanıt veremiyor: {exc}"

    return response.get("message", {}).get("content", "")

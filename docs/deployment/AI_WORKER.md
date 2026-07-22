# TASK-007 — AI Worker sistemi

## TASK-008 — token context, streaming ve iptal

Worker, Ollama'nın modelden bağımsız bir tokenizer'ını varsaymak yerine yaklaşık
`4 karakter ≈ 1 token` hesabıyla en yeni mesajları `AI_CONTEXT_TOKEN_BUDGET` içinde tutar.
Üretim tamamlandığında Ollama'nın gerçek `prompt_eval_count`/`eval_count` değerleri ayrıca
`ai_token_usage` tablosuna yazılır. Çıktı üst sınırı `AI_MAX_OUTPUT_TOKENS` ile belirlenir.

Üretim sırasında worker, çıktıyı `ai_jobs.output_text` alanına periyodik olarak kaydeder.
İstemci Bearer kimlik doğrulamasıyla aşağıdaki SSE endpoint'ine bağlanabilir (tarayıcıda
`EventSource` Bearer header gönderemediği için `fetch` + `ReadableStream` kullanılmalıdır):

```text
GET /api/ai/jobs/{job_id}/stream
POST /api/ai/jobs/{job_id}/cancel
```

SSE `token`, `status` ve terminal durumda `complete` olayları gönderir. Bağlantı koparsa
aynı endpoint'e yeniden bağlanmak güvenlidir; mevcut çıktı DB'den okunur. İptal isteği
cooperative'dir: queued job hemen `cancelled` olur, çalışan job bir sonraki çıktı flush'ında
durdurulur ve kısmi çıktı assistant mesajına dönüştürülmez.

Core AI sohbetlerinde model üretimi artık HTTP isteğinin içinde yapılmaz:

```text
POST /ai/conversations/{id}/messages
        │ kısa DB transaction
        ▼
ai_jobs (queued)
        │
        ▼
ai-worker ── Ollama/AI Gateway (blocking çağrı)
        │
        ▼
ai_messages + ai_token_usage, job=succeeded
```

Kanal içindeki `@bot sor ...` / `/sor ...` komutları da `ai_bot_jobs` üzerinden aynı worker'a
bırakılır. Worker cevabı botun Matrix hesabıyla gönderir; job ID'sinden türetilen Matrix transaction
ID'si timeout sonrası retry'larda duplicate event oluşmasını önler. Diğer plugin komutları mevcut
senkron dispatcher akışını kullanır.

## API davranışı

`POST /ai/conversations/{id}/messages` artık `201 MessageRead` yerine `202 AiJobRead` döndürür.
Yanıtta `id`, `status`, `user_message_id` bulunur. İstemci job durumunu şu endpoint ile izler:

```text
GET /api/ai/jobs/{job_id}
GET /api/ai/conversations/{conversation_id}/messages
```

İstemci retry'larında duplicate prompt oluşturmamak için aynı isteği `Idempotency-Key` header'ı
ile tekrar gönderebilirsiniz; aynı kullanıcı, conversation ve anahtar mevcut job kaydını döndürür.

Başarısız üretimde kullanıcı mesajı korunur, job `failed` olur ve `error` alanı kullanıcıya
gösterilebilir. Aynı prompt'u tekrar göndermek yerine yeni bir job oluşturulmalıdır.

## Worker dayanıklılığı

- İşler `ai_jobs` tablosunda kalıcıdır; process restart kuyruğu kaybetmez.
- Worker `SELECT ... FOR UPDATE SKIP LOCKED` ile bir işi lease eder.
- Ollama çağrısı DB transaction'ı dışında yapılır; API ve DB bağlantıları uzun süre tutulmaz.
- Worker ölürse lease süresi dolan `running` iş tekrar alınabilir.
- Gateway timeout/temporary unavailable hataları sınırlı exponential backoff ile yeniden denenir.
- Model/auth/config hataları doğrudan `failed` durumuna geçer; `error` 1000 karakterle sınırlıdır.
- Context, işin kendi `user_message_id` değerine kadar olan mesajlardan token bütçesine sığan
  en yeni bölümle oluşturulur; daha sonra kuyruğa giren prompt'lar önceki üretimin context'ine sızmaz.
- `AI_MAX_PENDING_JOBS_PER_USER` varsayılanı kullanıcı başına 20 bekleyen iştir.
- Worker, process tam Ollama yanıtını aldıktan hemen önce ölürse dış model çağrısı teknik olarak
  yeniden üretilebilir (Ollama tarafında exactly-once garantisi yoktur); DB/Matrix sonuç yazımı
  fencing ve sabit transaction ID ile duplicate etkisini sınırlar.

Compose'ta varsayılan tek `ai-worker` instance'ı aynı conversation içindeki işleri FIFO'ya yakın
sırada işler. Daha fazla worker replica'sı `SKIP LOCKED` ile farklı kullanıcıları paralelleştirebilir;
aynı conversation için sıralı üretim garantisi gerektiğinden bunu ayrıca test etmeden ölçeklemeyin.

## Operasyon

```powershell
docker compose logs -f --tail 200 ai-worker
docker compose ps ai-worker
```

Worker image'ı backend ile aynıdır; ancak Ollama HTTP çağrısı ayrı container process'inde yapılır.
API container'ı yeniden başlatılırken kuyruğa alınmış işler kaybolmaz. `ai_jobs` ve `ai_bot_jobs`
migration'ları `0002_ai_jobs`/`0003_ai_bot_jobs`/`0004_ai_stream_cancel` ile gelir ve `migrate`
servisi tarafından uygulanır.

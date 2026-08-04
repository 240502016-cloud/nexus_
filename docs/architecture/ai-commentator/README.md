# AI Commentator — ürün ve teknik tasarım

Durum: uygulama öncesi referans tasarım  
Hedef: Nexus içindeki tam üç kişilik özel oyun oturumlarına kısa, bağlama sadık ve yorucu olmayan
canlı yorum eklemek  
Uyum: mevcut React/TypeScript istemci, FastAPI/SQLAlchemy/Alembic backend, PostgreSQL 16, AI Gateway
ve Party Lore tasarımı

## Karar özeti

AI Commentator bir kanala rastgele şaka atan chatbot değildir. Yapılandırılmış oyun olaylarını alır,
çoğunu deterministik olarak sessizce eler, yalnız gerçekten yorum değeri olan olayı kısa bir cümleye
dönüştürür. Başarının ana metriği yorum sayısı değil, doğru anda söylenen yorumların oranıdır.

Modül `backend/app/commentator/` altında ortak bir backend alanı olmalıdır. Mevcut plugin sandbox'ı
PostgreSQL/Party Lore erişimine sahip değildir ve canlı session state için uygun değildir. Discord ve
gelecek oyun connector'ları ince istemciler olarak Event Ingestion API'ye bağlanır.

Mevcut repo içindeki AI Gateway bugün çoklu sağlayıcı orkestratörü değil, güvenli bir Ollama proxy'sidir.
Commentator gerçek model adına bağlanmayacaktır. Geçiş çözümünde `COMMENTATOR_LIVE_MODEL` ayarı,
hedef mimaride Gateway'deki mantıksal `commentary-live` profili kullanılır. Kullanıcı tarafından
planlanan LLM değişikliği bu nedenle event, veritabanı veya prompt API'sini değiştirmez.

Canlı kalite için model yayın kapısı vardır: JSON başarısı, hallucination/safety golden setleri ve
gerçek donanım p95 gecikmesi geçilmeden model production profiline atanmaz. Şu anki model işlevsel
prototipte kullanılabilir; ürün kalitesi varsayımı olarak kabul edilmez.

## 1. Ürün tanımı

### Tam amaç

Üç arkadaş oyun oynarken sistem:

1. Manuel veya yapılandırılmış bir event alır.
2. Event'in yeni, önemli, güvenilir, güvenli ve doğru zamanda olup olmadığını puanlar.
3. Uygunsa oyuncu izinlerini, seçili yorumcu kişiliğini, yakın yorum geçmişini ve en çok iki Party
   Lore kaydını kısa context'e koyar.
4. LLM'den tek, kısa, yapılandırılmış yorum ister.
5. Çıktıyı tekrar/güvenlik/olgusal sadakat kontrolünden geçirip metin ve isteğe bağlı TTS ile yollar.
6. Tepkiyi bir sonraki session ve profil ayarlarında kullanmak üzere kaydeder.

### Üç kişilik özel grup farkı

- Oyuncuların kim olduğu sabittir; kimlik ve izin belirsizliği kabul edilmez.
- İç şakalar değerlidir ama bir kişiyi sürekli hedef alma riski daha görünürdür.
- Public ürün için gereken tenant ölçeği, global moderasyon ve abuse marketplace yoktur.
- Üç kişide kötü bir yorum grubun bütün atmosferini etkileyebilir; bir “sessiz/rahatsızım” kontrolü
  çoğunluk oylamasından daha önemlidir.
- Az event ve az lore nedeniyle Redis/Kafka/vector DB gibi altyapılar faydadan çok yük getirir.

### Ana oyun döngüsü

```text
session başlat -> üç oyuncu/profil/intensity -> event akışı
    -> çoğu event sessizce elenir
    -> seçili event -> kısa yorum -> tepki/cooldown
    -> session bitir -> kısa recap -> ayarlar/lore adayları (ayrı onayla)
```

### Uzun dönemli değer

İlk gün değer, doğru anda yapılan birkaç özgün yorumdur. Haftalar içinde oyuncu tercihleri, işe
yarayan kişilik, fazla kullanılan cümle kalıpları ve onaylı Party Lore bağlantıları daha iyi seçilir.
Sistem arkadaşların “kişilik analizi”ni üretmez; açık tercih ve oyun içi kanıt kullanır. Recap içindeki
önemli olaylar Party Lore'a doğrudan yazılmaz, yalnız onaylanabilir aday olabilir.

Haftalar sonra hâlâ eğlenceli kalmasını sağlayanlar: session başına düşük yorum yoğunluğu, profil
değişimi, eski şakalara cooldown, hedef oyuncu adaleti, pozitif başarı yorumları ile failure şakalarının
dengesi ve “not funny/too harsh/repetitive” geri bildiriminin hemen etkili olmasıdır.

## 2. MVP kapsamı

### Must have

- Tam üç oyuncuyla session başlatma/bitirme ve session history.
- Altı built-in kişilik, LOW/NORMAL/HIGH intensity ve anlık silent mode.
- Manuel event formu ve sürümlü generic event ingestion API.
- Event normalization, idempotency, duplicate, trigger score ve global/player/category cooldown.
- AI Gateway üzerinden tek kısa JSON yorum; timeout/stale suppression.
- Text output; hedef oyuncu izni, harshness sınırı ve oyuncu adalet guard'ı.
- Feedback: funny, not funny, too harsh, repetitive, wrong context.
- LLM/event/lore uydurmasına karşı strict schema ve post-validation.
- Gateway/model kapalıyken session'ı bozmayan “yorum yok” fallback'i.

### Should have

- Session recap ve önemli event listesi.
- Party Lore retrieval/usage entegrasyonu; lore yokken normal çalışma.
- Matrix kanalına output ve frontend session paneli.
- Basit profil/oyuncu preference ekranı.
- Event stream ve trigger kararlarını gösteren geliştirici görünümü.
- Gateway kullanım/latency/model ölçümleri.

### Later

- Discord slash command/bot, gerçek oyun connector'ları.
- Speech-to-text event önerisi ve isteğe bağlı TTS.
- Session tone sınıflandırıcısı, reaction tabanlı otomatik feedback.
- Custom kişilik editörü, kontrollü A/B model karşılaştırması.
- Daha gelişmiş semantic phrase repetition tespiti.

### Açıkça kapsam dışı

- Her ekranı sürekli izleyen vision/screen scraping.
- Bütün sesli sohbeti kalıcı kaydetme veya pasif gözetim.
- Her oyuna tek sürümde native connector.
- Public yayın/stream moderasyonu ve binlerce kullanıcılı SaaS ölçeği.
- Oyuncuların psikolojik profilini LLM ile çıkarmak.
- Otonom Party Lore yazımı, gerçek çatışmaya hakemlik veya oyuncuyu provoke eden roast modu.
- MVP için Redis, Kafka, graph DB, ayrı Node backend ya da ayrı vector DB.

## 3. Kullanıcı akışları

### Session başlatma ve oyuncuları kaydetme

1. Sunucu üyesi Commentator panelini açar, oyun adını seçer.
2. Server üyelerinden tam üç Party Lore oyuncusu seçilir. Eksik preference kaydı güvenli varsayılanla
   (`harshness=1`, targeted=true, lore=true, TTS=true) yaratılır.
3. Kişilik, intensity, output kanalı ve TTS seçilir.
4. Backend üyelik, üç farklı player, profil ve kanal iznini doğrular; snapshot preferences ile session açar.
5. Panel “aktif, sessiz mod kapalı” durumunu gösterir.

Session sırasında oyuncu ayrılabilir; session kapanmaz ama `is_present=false` olur ve hedeflenmez. Dördüncü
oyuncu eklenmez; ürün kuralı tam üç kişiliktir.

### Kişilik seçme

Kartlarda ton, örnek, harshness ve lore sıklığı gösterilir. Effective harshness her zaman
`min(profile.harshness, üç oyuncunun maximum_harshness değeri)` olur. Profil değişimi bir sonraki event'te
etkilidir ve session history'ye yazılır.

### Manuel event ve yorum

1. Oyuncu kategori, ilgili oyuncu(lar) ve en fazla 240 karakterlik olgusal özet girer.
2. `POST .../events` hemen `202` döner; çift tıklama aynı event ID ile idempotenttir.
3. Trigger engine event'i elerse panelde yalnız geliştirici modunda sebep görünür.
4. Üretim seçilirse p95 hedefi 2,5 saniyedir; 4 saniyeyi aşan yorum stale sayılır ve gönderilmez.
5. Text kanala düşer; TTS açıksa aynı metin bağımsız adaptöre gider.

### Feedback

Her yorumun yanında beş küçük tepki vardır. `TOO_HARSH` aynı oyuncuya hedefli şakaları session boyunca
hemen yumuşatır; `REPETITIVE` phrase/profile-pattern cooldown ekler. Bir oyuncu “rahatsızım/sessiz”
kontrolünü seçerse session anında silent mode'a geçer; feedback için açıklama zorunlu değildir.

### Session bitirme ve recap

Owner/başlatan Bitir'e basar; yeni event kabulü kapanır, açık worker işi en fazla 4 saniye beklenir.
Recap istenirse en yüksek puanlı en fazla 6 event, en iyi 4 yorum ve feedback özeti güçlü/ucuz olmayan
`commentary-recap` profiline gönderilir. Recap 3–5 cümledir, yeni lore uyduramaz. Event'leri Lore adayı
yapmak ayrı bir kullanıcı seçimi ve Party Lore onayıdır.

## 4. Sistem mimarisi

| Bileşen | Sorumluluk ve I/O | Karar türü | Hata davranışı |
|---|---|---|---|
| Session Manager | Session/player/profile/intensity/silent state alır ve snapshot döndürür | Deterministik | Geçersiz üçlü veya çift aktif session 409 |
| Event Ingestion API | Auth, boyut, schema, idempotency; event kaydı | Deterministik | 4xx veya önceki sonucu döndürür |
| Event Normalizer | Connector payload → `NormalizedCommentatorEvent` | Deterministik; serbest metinde opsiyonel küçük model | Bilinmeyen alanı atar; belirsiz oyuncuyu reddeder |
| Trigger Engine | Skor, threshold, hard veto, event window | Deterministik | Hesaplanamazsa yorum yapmaz |
| Context Builder | Session, güvenli preference, lore, history, event'i token bütçesine sığdırır | Deterministik | Lore yoksa lore'suz devam |
| Party Lore Retriever | `COMMENTARY` izinli top-2 lore | Party Lore deterministik retrieval | Hata/timeout: boş liste |
| Repetition Guard | Event dedup, phrase/lore/pattern cooldown | Deterministik | Güvenli tarafta bastırır |
| Tone & Safety Filter | Upset/argument/blocked topic/harshness/target izni | Deterministik; gelecekte classifier yalnız sinyal | Riskte yorum yapmaz, silent önerebilir |
| LLM Gateway Client | Mantıksal profil, prompt version, kısa timeout ve usage | LLM | 3 s timeout; retry yok, event stale olur |
| Output Dispatcher | Matrix text; opsiyonel TTS | Deterministik adapter | Text hatası retry; TTS hatası text'i etkilemez |
| Feedback Collector | Upsert feedback, session guard/cooldown güncelleme | Deterministik | Idempotent; invalid actor 403 |
| TTS Adapter | Onaylı text → ses | Harici model olabilir | 2 s sonra vazgeç; oyun akışını bekletme |

### Çalışma akışı

```text
Connector/UI -> Ingestion -> PostgreSQL session_events (PENDING)
                                  |
                         Commentator worker
                                  |
                 normalize -> hard veto -> trigger score
                                  |
                 lore top-2 + history -> context
                                  |
                   AI Gateway commentary-live
                                  |
             schema -> safety -> repetition -> freshness
                                  |
                  Matrix text -> optional TTS
                                  |
                     usage + feedback + cooldown
```

Worker aynı `session_events` tablosundaki lease alanlarını kullanır; MVP'de Redis gerekmez. Bir backend
replica için in-process worker yeterli olsa da production crash recovery için mevcut `ai-worker`
pattern'ine benzeyen ayrı `commentator-worker` process'i önerilir.

## 5. Event modeli ve trigger kararı

TypeScript event sözleşmesi ve iki JSON örneği: [event-contract.ts](event-contract.ts).

### Kategori taban puanları

| Kategori | Base | Özel kural |
|---|---:|---|
| MILESTONE | .92 | Positive yorum önceliği |
| CLUTCH | .90 | 12 sn hard global dışında category cooldown aşabilir |
| BETRAYAL | .82 | Yalnız açıkça oyun içi; upset ise veto |
| REPEATED_MISTAKE | .80 | Kanıt/counter yoksa normal PLAYER_FAIL'e düşer |
| TEAMWORK | .77 | Takım yorumu, tek kişi hedefleme yok |
| ACCIDENTAL_SUCCESS | .74 | Niyet uydurma; event açıkça accidental demeli |
| MANUAL_NOTE | .70 | Force flag olmadan normal threshold |
| PLAYER_DEATH | .58 | Sıradan death seri hâlinde elenir |
| PLAYER_FAIL | .54 | Tekrarda novelty hızla düşer |
| SILENCE | .32 | Opt-in; en erken 180 sn ve session'da bir kez |
| ARGUMENT | .00 | Varsayılan safety veto; mizah üretme |

Base tek başına yorum kararı değildir, rarity özelliğinin başlangıç sinyalidir.

### Trigger formülü

```text
positive = 0.28*importance
         + 0.18*novelty
         + 0.14*category_value
         + 0.12*source_confidence
         + 0.10*lore_relevance
         + 0.08*pacing_opportunity
         + 0.05*emotional_fit
         + 0.05*manual_bonus

penalty  = 0.30*duplicate_risk
         + 0.20*recent_frequency
         + 0.18*target_saturation
         + 0.35*conflict_risk

trigger_score = clamp(positive - penalty, 0, 1)
```

Threshold: LOW `.76`, NORMAL `.64`, HIGH `.52`. Manual bonus yalnız kullanıcının bilerek gönderdiği
event'te 1'dir; safety veya cooldown'ı aşmaz. Source confidence `< .55`, silent mode, `ARGUMENT+TENSE/UPSET`,
bilinmeyen player, exact duplicate ve kapalı preference hard veto'dur; LLM çağrılmaz.

### Duplicate ve eşzamanlı event

- `(session_id, external_event_id)` unique'dir.
- Dedup key: category + sıralı actor/target + match/round + allowlist stable attribute'ların normalize
  edilmiş SHA-256 değeri.
- Aynı key, death/fail için 10 saniye; diğer telemetry için 5 saniye içinde duplicate'tir. İkinci event
  saklanabilir ama `SUPERSEDED` olur; önem/güven yüksek değeri birincinin trigger hesabına aktarılır.
- 750 ms içinde gelen event'ler tek window'da gruplanır. En yüksek skorlu event primary, en çok iki event
  destek context'idir; en fazla bir yorum üretilir.
- Aynı anda iki ayrı kritik milestone gelirse sırayla işlenir; ikinci, 12 saniyelik hard global cooldown
  nedeniyle birleşik takım yorumuna dönüşür veya bastırılır.

### Cooldown ve adalet

- Hard global: her intensity'de 12 saniye; normal global LOW 75, NORMAL 40, HIGH 18 saniye.
- Aynı hedef oyuncu: 90 saniye. Son 10 hedefli yorumun %40'ından fazlası bir oyuncuya aitse saturation
  cezası; üç oyuncu eşit event üretmediyse bu yalnız soft penalty'dir.
- Aynı kategori: 45 saniye; sıradan death/fail için 90 saniye.
- Aynı lore: Party Lore'un COMMENTARY cooldown'ı, varsayılan 7 gün.
- Aynı phrase: session boyunca exact; benzer 3-gram Jaccard `>= .72` için 30 dakika.
- Aynı personality punchline pattern: son 5 yorumda yeniden kullanılamaz.

## 6. Prompt mimarisi

İlk üretim system promptu ve post-validation hattı:
[production-prompt.md](production-prompt.md).

Prompt katmanları sırasıyla:

1. Sürüm kontrollü system safety/faithfulness kuralları.
2. Session: oyun, tone, intensity, zaman ve output limiti.
3. Üç güvenli player profile: görünen ad + açık humor/harshness izinleri.
4. En fazla 2 Party Lore öğesi; yalnız COMMENTARY için izinli.
5. Son 8 yorum + son 10 target sayacı.
6. Current primary event + en fazla 2 aynı-window destek event'i.
7. Strict JSON schema.

Input hedefi 250–450 token, output üst sınırı 60 token; yorum 240 karakter DB limiti olsa da profil
varsayılanları 120–190 karakterdir. Modelin `shouldComment` kararı trigger engine'in yerine geçmez;
yalnız safety/repetition/context veto hakkıdır.

## 7. Yorumcu kişilikleri

| Profil | Ton kuralları | Uzunluk | Harshness | Lore sıklığı | Örnek |
|---|---|---:|---:|---:|---|
| Dry Sarcastic | Düz, sakin, abartısız; ünlem/emoji yok | 140 char | 1 | %25 | “Plan kısa sürdü; düşüş kısmı daha kararlıydı.” |
| Sports Commentator | Enerjik play-by-play; başarıyı da över | 160 | 0 | %15 | “Tek can, iki rakip ve raund Aylin'in hanesinde!” |
| Documentary Narrator | Gözlemci doğa belgeseli dili; kişiyi değersizleştirmez | 180 | 1 | %25 | “Takım, nadir görülen eşzamanlı geri çekilme ritüelini sergiliyor.” |
| Chaotic Friend | Hızlı, absürt, beklenmedik; küfür ve gerçek sır yok | 120 | 2 | %20 | “Üç kişi, tek kapı, sıfır ortak karar: mükemmel.” |
| Calm Analyst | Nazik, net, hafif ironik; suçlama yok | 170 | 0 | %10 | “Pozisyon kayboldu ama zamanlama şaşırtıcı biçimde raundu kurtardı.” |
| Fantasy Narrator | Epik benzetme, oyun içi olayla sınırlı | 190 | 1 | %25 | “Son iksir saklandı; krallık düştü ama envanter güvende.” |

Yüzdeler hedef değil, uygun lore olduğunda maksimum kullanım olasılığıdır; Party Lore retrieval skoru ve
cooldown önce gelir. “Chaotic” safety'yi gevşetmez. Custom profil ilk sürümde yoktur; profil prompt
injection yüzeyi açar ve tone regression test yükünü büyütür.

## 8. Veri modeli

PostgreSQL referans DDL: [schema.sql](schema.sql).

| Tablo | Rol |
|---|---|
| `players` | `users` kaydının server içi ortak Party Lore/Commentator kimliği |
| `player_preferences` | Hedef, lore, harshness, style, blocked topic ve TTS tercihleri |
| `commentary_sessions` | Oyun, profil, intensity, tone, silent/status ve sayaçlar |
| `commentary_session_players` | Session üyeliği, preference snapshot ve hedef sayacı |
| `session_events` | Normalize event, trigger kararı, dedup ve worker lease |
| `generated_commentary` | Model/prompt/usage/latency, yapılandırılmış çıktı ve dispatch durumu |
| `commentary_feedback` | Oyuncu başına güncellenebilir tek feedback |
| `commentator_profiles` | Altı code-owned built-in profil ve ileride server custom profil |
| `cooldown_state` | Global/player/category/phrase/lore/pattern cooldown |
| `lore_references` | Context'e alınan ve gerçekten kullanılan lore bağlantıları |

`session_events.normalized_attributes` allowlist dışı connector verisi tutmaz. Transcript ham metni
MVP'de saklanmaz; yalnız oyuncunun onayladığı kısa event özeti alınır. `generated_commentary` kişisel
model analizi tutmaz. Session retention varsayılanı 90 gün; feedback ve aggregate metrik kalabilir,
ham event payload yoktur.

## 9. API tasarımı

TypeScript request/response türleri: [api-contract.ts](api-contract.ts).

| Method ve yol | Amaç | Sonuç |
|---|---|---|
| `POST /servers/{serverId}/commentary/sessions` | Session yarat | `201 CommentarySession` |
| `POST /commentary/sessions/{id}/players` | Kayıtlı üçlüye oyuncu ekle/yeniden kat | `200` |
| `DELETE /commentary/sessions/{id}/players/{playerId}` | Oyuncuyu absent işaretle | `204` |
| `POST /commentary/sessions/{id}/events` | Event gönder | `202 PostEventResponse` |
| `POST /commentary/sessions/{id}/generate` | Dev/internal manuel worker tetikleme | `202`; public UI normalde çağırmaz |
| `PATCH /commentary/sessions/{id}` | Profil/intensity/silent/TTS değiştir | `200` |
| `GET /commentary/sessions/{id}/history` | Cursor'lı event/yorum geçmişi | `200` |
| `POST /commentary/commentary/{id}/feedback` | Feedback upsert | `200` |
| `POST /commentary/sessions/{id}/end` | Event kabulünü kapat | `202` |
| `POST /commentary/sessions/{id}/recap` | Idempotent recap işi | `202 SessionRecap` |
| `GET /commentary/sessions/{id}/recap` | Recap durum/sonuç | `200` |
| `PUT /commentary/players/{id}/preferences` | Kendi tercihlerini güncelle | `200` |
| `GET /servers/{serverId}/commentary/profiles` | Built-in/server profilleri | `200` |

### Session oluşturma örneği

```json
{
  "serverId": 4,
  "gameKey": "generic-fps",
  "playerIds": [11, 12, 13],
  "commentatorProfileId": "a2012280-65ea-42d8-995b-ad6dd415f75c",
  "intensity": "NORMAL",
  "textToSpeechEnabled": false,
  "outputChannelId": 8
}
```

Event response bilinçli olarak yorum döndürmez; canlı generation async'dir:

```json
{
  "eventId": "580b99cf-dfba-4a85-80df-cf8d61d8bf04",
  "accepted": true,
  "state": "PENDING"
}
```

Output, mevcut Matrix channel dispatcher üzerinden gönderilir. Frontend yeni yorumları başlangıçta
2 saniyelik polling ile görebilir; mevcut gateway WebSocket/SSE altyapısı hazır olduğunda push'a geçilir.

## 10. Maliyet ve gecikme optimizasyonu

### LLM çağrılmayan durumlar

Silent mode, hard/global cooldown, duplicate, threshold altı, kapalı target preference, düşük source
confidence, gerçek gerilim, stale event ve dakikalık kota. Bunlar toplam event'lerin en az %80–90'ını
model çağrısından önce elemelidir.

MVP'de “ucuz modelle event filtreleme” yapılmaz; formül hem daha ucuz hem daha hızlı ve test edilebilirdir.
Yalnız serbest metin/Discord komutunu kategoriye normalize etmek gerektiğinde küçük model kullanılabilir;
belirsizlikte event reddedilir. Canlı cümle ve recap için kalite kapısını geçen güçlü profil kullanılır.

### Bütçeler ve hedefler

- Live context: 250–450 input, en fazla 60 output token.
- Recap: en fazla 1.200 input, 220 output token.
- Lore: en fazla 2 öğe/160 token; recent history: 8 satır/160 token.
- Event `202`: p95 `<150 ms`; text generation p50 `<1,2 s`, p95 `<2,5 s`; hard discard `4 s`.
- TTS: text'ten sonra p95 `<2 s`; hata text'i engellemez.
- Kota: LOW 12/saat, NORMAL 24/saat, HIGH 45/saat; hard üst sınır 4 model çağrısı/dakika/session.
- Recap session başına bir başarılı üretim; idempotent retry.

Kişilik/profile ve system prompt hash'i Gateway provider destekliyorsa prefix-cache'e uygundur. Event'e
özel yorum cache'lenip başka event'te kullanılmaz; bu generic ve yanlış şaka üretir. Aynı idempotency
key retry'sı önceki başarılı çıktıyı döndürebilir. Provider yoksa cached alakasız yorum veya kalitesiz
template yollamak yerine sessiz kalınır.

## 11. Edge case politikaları

| Durum | Karar |
|---|---|
| Yararlı context yok | Current event tek başına açıksa lore'suz yorum; değilse `INSUFFICIENT_CONTEXT` |
| İki event eşzamanlı | 750 ms window, tek primary ve en fazla bir yorum |
| Oyuncu gerçekten üzgün | “Rahatsızım” anında silent; UPSET/ARGUMENT safety veto; özür üretme zorunluluğu yok |
| Çok tekrarlı gameplay | Novelty düşer, kategori cooldown uzar; her ölüm yorumlanmaz |
| Model event uydurdu | Entity/number/lore allowlist doğrulama; dispatch suppression, canlı retry yok |
| LLM provider yok | Event kaydı/trigger metriği kalır; session devam eder; bir kez pasif durum göstergesi |
| TTS hatası | Text kalır, TTS circuit breaker 5 dk kapanır |
| Uzun sessizlik | Opt-in; 180 sn sonra session'da en çok bir gentle yorum; mikrofon dinleme gerektirmez |
| Kimse tepki vermiyor | Nötr sinyal; 5 yorum feedback'sizse intensity bir kademe düşürme önerisi, otomatik değil |
| Bir oyuncu fazla hedef | 90 sn cooldown, %40 fairness penalty; positive/team comment önceliği |
| Oyuncu ayrıldı | Event'te actor olabilir ama yeni hedefli yorum yapılmaz; recap'te olgusal kalır |
| Eski yorum geç geldi | 4 sn freshness sınırı; `STALE`, dispatch yok |
| Party Lore kapalı | Boş lore listesiyle normal çalışır; geçmiş uydurmaz |

## 12. Solo geliştirici uygulama planı

### Phase 0 — Prototype

- Görevler: event contract, trigger engine saf fonksiyon, 30 event golden set, altı profil promptu,
  CLI/mock stream ile Gateway çağrısı ve model benchmark.
- Bağımlılık: kullanılacak yeni model adayına erişim; repo AI Gateway çalışır durumda olmalı.
- Definition of done: JSON >= %99,5, hallucination/safety ihlali 0, p95 <= 2,5 s; 10 dakikalık mock
  streamde 5–10 anlamlı yorum.
- Risk: mevcut model kalite/gecikme kapısını geçmez.
- Henüz yapma: DB, UI, Discord, TTS, Party Lore.

### Phase 1 — MVP

- Görevler: modeller/Alembic, session/event/feedback API, DB-lease worker, trigger/context/repetition/safety,
  Matrix text dispatcher, frontend minimal panel, silent mode.
- Bağımlılık: Phase 0 prompt/model profili.
- Definition of done: üç oyunculu manuel session uçtan uca; duplicate/cooldown/fairness testleri; Gateway
  kapalıyken Core API ve session çalışır; stale yorum gönderilmez.
- Risk: mevcut sync Ollama client'ın canlı timeout davranışı.
- Henüz yapma: Redis, TTS, recap LLM, custom profil.

### Phase 2 — Discord integration

- Görevler: `/commentator start|event|silent|stop`, signed service credential, player mapping, rate limit.
- Bağımlılık: stabil ingestion API.
- Definition of done: Discord komutu aynı event contract'ını kullanır, duplicate retry yaratmaz, bot
  yalnız izinli server/channel'da çalışır.
- Risk: iki kimlik sisteminin yanlış eşleşmesi.
- Henüz yapma: bütün Discord mesajlarını dinleme.

### Phase 3 — Party Lore integration

- Görevler: COMMENTARY retrieval top-2, context packaging, lore allowlist validation, `lore_references`
  ve Party Lore usage kaydı.
- Bağımlılık: Party Lore retrieval/consent API.
- Definition of done: yasak/cooldown lore sızıntısı 0; lore servisi kapalıyken yorum devam; yalnız gerçekten
  kullanılan lore usage sayılır.
- Risk: lore callback'in tekrar/gizlilik sınırı.
- Henüz yapma: Commentator'ın otomatik lore yaratması.

### Phase 4 — Game connectors

- Görevler: önce tek oyun, connector SDK/fixture, category allowlist, match/round idempotency ve replay testi.
- Bağımlılık: gerçek oyunun güvenilir telemetry erişimi.
- Definition of done: 30 dakikalık kayıt replay'i deterministik trigger kararları üretir; disconnect/retry
  duplicate yaratmaz.
- Risk: oyun güncellemesi/event anlamı değişimi.
- Henüz yapma: evrensel connector veya screen vision.

### Phase 5 — Voice support

- Görevler: opt-in TTS adapter, queue/cancel, voice volume, circuit breaker; daha sonra açık push-to-talk
  transcript event önerisi.
- Bağımlılık: mevcut WebRTC voice ve oyuncu consent UI.
- Definition of done: TTS text'i geciktirmez, silent anında queue temizler, ses kaydı kalıcı tutulmaz.
- Risk: yorumun konuşmanın üstüne binmesi ve STT gizliliği.
- Henüz yapma: sürekli mikrofon kaydı, duygu/kimlik çıkarımı.

## 13. Depo yapısı

Repo zaten FastAPI backend'e sahip olduğu için ikinci bir Node backend eklemek gereksizdir. TypeScript
connector ve frontend sözleşmesinde kalır; ileride Discord bot Node.js/TypeScript olabilir.

```text
backend/app/commentator/
  models.py                 # SQLAlchemy
  schemas.py                # Pydantic event/API schema
  router.py                 # REST
  service.py                # session transaction sınırı
  normalizer.py             # connector -> generic event
  trigger_engine.py         # saf deterministik skor
  context_builder.py
  repetition_guard.py
  safety.py
  gateway_client.py         # commentary-live profile, 3s timeout
  dispatcher.py             # Matrix + TTS adapter interface
  worker.py                 # DB lease
  profiles.py               # built-in profile definitions

backend/tests/commentator/
  fixtures/events/
  golden/

frontend/src/components/commentator/
  CommentatorPanel.tsx
  SessionSetup.tsx
  CommentaryHistory.tsx
  FeedbackButtons.tsx

frontend/src/api/commentatorTypes.ts

integrations/discord-commentator/   # Phase 2, Node.js + TypeScript
  src/
  package.json

docs/architecture/ai-commentator/
```

Redis ancak birden fazla worker replica, yüzlerce eşzamanlı session veya PostgreSQL lease p95'i ölçülerek
sorun olursa eklenir. Üç kişilik sistemde PostgreSQL yeterlidir.

Gateway için hedef ekleme: concrete Ollama model alanı yerine authenticated internal istekte
`model_profile=commentary-live|commentary-recap`; routing, usage ve provider model adını response metadata'da
döndürme. Gateway yükseltilene kadar backend env ayarı concrete modeli seçer ve DB'ye kaydeder.

## 14. Test stratejisi

### Unit/integration

- Trigger feature/threshold sınırları, bütün intensity seviyeleri ve hard veto property testleri.
- Event schema, unknown field removal, player/server authorization, exact idempotency/dedup window.
- Cooldown zaman testi, simultaneous window, target fairness ve feedback guard etkisi.
- Worker lease expiry/recovery, event sırası, stale suppression ve dispatch idempotency.
- Gateway timeout/invalid JSON/provider down; TTS circuit breaker.
- PostgreSQL gerçek integration testinde session unique, FK ve concurrent event claim.

### Prompt ve golden set

- 150 event: 50 comment, 50 no-comment, 25 lore, 25 safety/adversarial.
- Her built-in profil için tone rubric ve uzunluk/harshness/emoji beklentileri.
- Event/lore dışı isim-sayı-geçmiş assertion'ı; uydurma hedef 0.
- Son 8 yorumla exact, paraphrase ve punchline repetition regression.
- Model/prompt değişiminde JSON success, safety, faithfulness, style, novelty ve latency diff raporu.
- Exact string beklemek yerine invariant + insan rubric; sabit 20 örnek tone snapshot'ı manuel onaylıdır.

### Mock event streamleri

- 10 dakikada 60 death/fail: en fazla intensity kotası kadar yorum.
- 750 ms içinde death+clutch+milestone: tek birleşik karar.
- Bir oyuncuya ardışık 8 event: fairness target dağılımı.
- Provider 2/5/10 saniye latency: 4 saniye sonrası dispatch 0.
- Session ortasında silent/UPSET/oyuncu ayrılması.

### Manuel playtest checklist

- Yorum oyun sırasında okunabilecek kadar kısa mı?
- Event olmadan ayrıntı ekledi mi?
- Üç oyuncudan biri “üzerime geliyor” hissediyor mu?
- Beş yorumdan sonra aynı yapı duyuluyor mu?
- LOW/NORMAL/HIGH farkı spam olmadan hissediliyor mu?
- Silent anında çalışıyor mu; TTS kuyruğu temizleniyor mu?
- Lore callback doğal mı ve izinli mi?
- Feedback bir sonraki yorumlarda gözle görülür biçimde etkili mi?

Yayın hedefleri: safety/hallucination kritik ihlal 0; schema >= %99,5; repetition test pass >= %95;
manuel playtest “uygun anda” >= %80; p95 live <= 2,5 s.

## 15. Nihai teslimler

### Önerilen MVP mimarisi

```text
Manual UI / future Discord / connector
              |
       FastAPI ingestion
              |
  PostgreSQL event + session state
              |
  commentator-worker (DB lease)
       | trigger/filter (no LLM for most events)
       | context + optional Party Lore top-2
       v
 AI Gateway logical profile -> selected stronger model
              |
 schema/safety/repetition/freshness
              |
 Matrix text -> optional TTS -> feedback/cooldown
```

### Kesin ilk 10 geliştirme görevi

1. Üç aday modelle `commentary-live-v1` golden benchmark'ını çalıştır ve production model profilini seç.
2. `backend/app/commentator/` paketini, Pydantic event schema'sını ve saf `trigger_engine.py`yi oluştur.
3. Session, player preference, profile ve session-player SQLAlchemy modelleri/Alembic migration'ı ekle.
4. Session create/patch/silent/end ve preference endpointlerini authorization ile yaz.
5. `session_events` ingestion, normalization, idempotency ve dedup transaction'ını ekle.
6. DB lease kullanan `commentator-worker`ı, 750 ms event window ve stale event politikasıyla yaz.
7. Context builder, Gateway 3 saniye client'ı, strict JSON validator ve post-safety/repetition guard'ı ekle.
8. Matrix text dispatcher, `generated_commentary`, cooldown ve idempotent feedback akışını tamamla.
9. Frontend Session Setup/History/Feedback/Silent panelini ekle ve üç hesapla uçtan uca test et.
10. Party Lore hazır olduğunda top-2 COMMENTARY retrieval + allowlist + gerçek usage kaydını feature flag ile bağla.

### İlk production system prompt

Tam sürüm [production-prompt.md](production-prompt.md) içindedir. Kritik invariant: model yalnız current
event ve izinli lore'dan konuşur; tek kısa JSON yorum verir; safety/repetition/context dışında trigger
kararını geçersiz kılmaz.

### Üç gerçekçi örnek session

#### Session A — Dry Sarcastic, NORMAL, manuel MVP

| Zaman | Event | Skor/karar | Sonuç |
|---|---|---|---|
| 00:30 | Sıradan PLAYER_DEATH, Mert | .43, threshold altı | Sessiz |
| 02:10 | Mert takımı beklemeden girip elendi | .71, generate | “Mert yine takımı beklemedi; plan en azından hızlı bitti.” |
| 02:24 | Aynı death connector retry | exact duplicate | Sessiz |
| 05:40 | Aylin tek canla clutch | .91, generate | “Tek can yetti; kalan ekipman dekor olarak katıldı.” |
| 05:45 | Aylin `FUNNY` | feedback | Profile pattern pozitif, target cooldown devam |
| 08:00 | Üç oyuncu aynı kapıya sıkıştı | .74, team | “Üç kişi, tek kapı ve şaşırtıcı derecede eşit sorumluluk.” |

#### Session B — Sports Commentator, HIGH, Party Lore açık

Party Lore top-2 içinde izinli “Köprü Faciası” vardır. Yeni event aynı oyuncunun yeni oyunda köprüden
düşmesidir; retrieval skoru .78, lore cooldown uygundur.

| Event | Karar | Sonuç |
|---|---|---|
| Köprü düşüşü | .83 + lore callback | “Köprü serisinin yeni bölümü geldi; Mert yine açılışı yaptı!” |
| 20 sn sonra ikinci düşüş | player/category cooldown | Sessiz |
| Takım milestone | .94 positive | “Üçlü savunma tamamlandı; bu kez köprü bile ayakta!” — lore cooldown nedeniyle lore id kullanılmaz, bu ifade doğrulanamıyorsa bastırılır |
| Feedback `REPETITIVE` | lore/profile cooldown | Köprü callback session boyunca kapanır |

Son satırdaki örnek bilerek validation sınırını gösterir: event köprünün ayakta kaldığını söylemiyorsa model
bu ayrıntıyı ekleyemez ve yorum dispatch edilmez.

#### Session C — Calm Analyst, LOW, gerilim

| Event | Session tone | Karar |
|---|---|---|
| İki oyuncu loot konusunda tartışıyor (`ARGUMENT`) | TENSE | Safety veto; LLM çağrısı yok |
| Bir oyuncu “rahatsızım” seçiyor | UPSET | Silent mode anında açık |
| Sonraki clutch | UPSET/silent | Event kaydolur, canlı yorum yok |
| Session recap | ENDED | “Oturum güçlü bir geri dönüşle bitti.” gibi yalnız doğrulanmış, nötr özet; tartışmada taraf yok |

### Ertelenecek özellikler

- Discord botu ve bütün oyun connector'ları MVP ile aynı anda.
- Sürekli STT, screen vision, OCR ve otomatik emotion detection.
- TTS ve ses klonlama; özellikle oyuncu sesi taklidi.
- Custom prompt/personality marketplace.
- Commentator'ın Party Lore'a otomatik yazması.
- Redis/Kafka/microservice ayrıştırması.
- Fine-tuning, reinforcement learning ve otomatik “mizah kişiliği” çıkarımı.
- Çok dilli aynı session, public stream modu ve seyirci etkileşimi.
- Semantic phrase model/embedding; 3-gram + feedback yetersiz ölçülene dek.
- Otomatik intensity değişimi; sistem yalnız öneri gösterir.

## Model değişimi için operasyon notu

Yeni LLM seçildiğinde event/API/DB değişmez. Yapılacaklar: Gateway'de `commentary-live` mantıksal profilini
yeni provider modele yönlendir, JSON mode ve timeout capability'sini tanımla, golden benchmark'ı çalıştır,
prompt/model sürümünü DB metriğinde ayır ve küçük canary session'dan sonra profili aktif et. Model adı
frontend'e veya Party Lore kayıtlarına yazılmaz.


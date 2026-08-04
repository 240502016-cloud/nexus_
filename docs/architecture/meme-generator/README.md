# Meme Generator — ürün ve teknik tasarım

Durum: uygulama öncesi referans tasarım  
Hedef: üç kişilik özel oyun grubunun doğrulanmış komik anlarını kısa, kişiselleştirilmiş ve tekrar
etmeyen meme artifact'lerine dönüştürmek  
Uyum: mevcut FastAPI/PostgreSQL backend, React/TypeScript istemci, AI Gateway, Party Lore ve AI Commentator

## Karar özeti

Meme Generator genel bir text-to-image aracı değildir. Kaynak event'in ne olduğunu, setup/payoff'u,
ilgili oyuncuyu, izinli lore'u ve yakın template/caption geçmişini kullanarak küçük bir küratörlü template
kütüphanesinden seçim yapar. LLM piksel üretmez; kısa caption adayları üretir. Render deterministik ve
sunucu tarafında Python Pillow ile yapılır.

İlk sürümde özgün AI görseli, video/FFmpeg, sürekli transcript, ekran izleme veya internetten template
scraping yoktur. On adet lisansı/kaynağı belli template, yapılandırılmış manuel event, üç caption önizlemesi,
PNG/JPEG render, web/Matrix teslimi ve altı feedback düğmesi yeterlidir. Çıktılar Discord'un önizleyebileceği
ölçü/formatta olur; Discord adapter v1.5'te aynı artifact API'sini kullanır.

Mevcut AI Gateway gerçek çoklu-model router değil, Ollama proxy'sidir. Modül concrete model adına değil
`meme-text` ve gerektiğinde `meme-review` mantıksal profillerine bağlanır. Planlanan daha güçlü model geçişi
event/template/veri sözleşmesini değiştirmez. Mevcut zayıf model kalite kapısını geçmedikçe yalnız geliştirme
profilinde kalır.

## 1. Ürün stratejisi

### Ana kullanım senaryoları

- Oyuncu “Emir on dakika eşya topladı, sonra ilk engelde düştü” olayını manuel gönderir ve üç caption
  önizlemesinden birini seçer.
- AI Commentator'ın zaten normalize ettiği yüksek puanlı event, kullanıcıya “meme yap” aksiyonu sunar.
- Highlight Generator'daki ekran görüntüsü/clip frame'i daha sonra caption overlay kaynağı olur.
- Session sonunda en yüksek puanlı, birbirinden farklı 3–5 artifact “meme pack” olarak listelenir.
- Başarılar yalnız alay konusu olmaz; fake achievement, haber ve istatistik kartlarıyla kutlanır.

### Neden üç kişide iyi çalışır

Üç oyuncuda context sabittir, isim/izin eşlemesi yapılabilir ve meme'nin hedefi belirsiz kalmaz. Grup içi
callback'ler public template'lerden daha değerlidir. Buna karşılık bir kişiyi üst üste hedeflemek veya bir
şakayı üç kez kullanmak hemen yorucu olur. Bu nedenle oyuncu adaleti, explicit humor boundary ve template/
phrase cooldown ürünün merkezindedir; “daha çok üretim” hedef değildir.

### Zamanla kişiselleşme

Sistem oyuncu hakkında gizli kişilik çıkarmaz. Açık preference, meme feedback'i, template/category başarısı,
target dağılımı ve Party Lore consent kullanır. Küçük grup için ML/ranking modeli gerekmez; Beta prior'lı
basit affinity puanları ve son kullanım cezaları açıklanabilir sonuç verir.

```text
template_affinity = (FUNNY + SAVE + 2) / (FUNNY + SAVE + FORCED + REPETITIVE + 4)
style_penalty = min(0.30, 0.10*FORCED_30D + 0.12*REPETITIVE_30D)
```

Bir kişinin `TOO_HARSH` feedback'i benzer target/category için anında session guard'ı ekler. Kalıcı harshness
ayarını sistem sessizce değiştirmez; oyuncuya ayar önerir ve onay ister.

### Tekrarı önleme

- Template başına varsayılan 7 gün; yüksek riskli “expectation/reality” için 14 gün cooldown.
- Aynı meme kategorisi aynı target için 14 gün içinde en fazla iki kez.
- Caption exact hash 90 gün; token 3-gram Jaccard `>= .72` ise 30 gün.
- Son session pack'te template, kategori ve target çeşitlendirmesi.
- `REPETITIVE` feedback'i template+caption-style cooldown'ını 30 güne çıkarır.
- Lore callback aynı lore için Party Lore MEME cooldown'ına, varsayılan 14 güne uyar.
- Aynı target son 10 meme'nin %40'ından fazlaysa soft fairness cezası; açık “save” bile safety'yi aşmaz.

### Party Lore ve Highlight bağlantısı

Party Lore yalnız event meme-worthy bulunduktan sonra, `usageType=MEME`, aynı server/player ve consent hard
filter'larıyla aranır. En fazla iki kayıt context'e girer, normal durumda sıfır veya biri kullanılır. Meme
çıktısındaki lore ID allowlist ile doğrulanır ve yalnız gerçekten kullanılan kayıt için usage yazılır.

Highlight Generator kaynak screenshot/clip/frame ve event provenance sağlar; Meme Generator highlight
olgusunu değiştirmez. `source_type=HIGHLIGHT` ve dış event ID ile bağlanır. Meme silmek highlight'ı, highlight
silmek meme caption snapshot'ını otomatik silmez; kaynak medya silindiyse yeni render yapılamaz. İki modülün
de Party Lore'a otomatik kalıcı olay yazma yetkisi yoktur.

## 2. MVP tanımı

### MVP

- `MemeEventV1` ile yapılandırılmış/manual event ve idempotent job.
- Deterministik meme-worthiness + safety/target/cooldown prefilter.
- Lisansı/kaynağı metadata'da bulunan 10 built-in template:
  4 iki-caption görsel, fake achievement, fake patch note, fake news, fake player stat ve 2 reaction card.
- LLM ile üç kısa Türkçe caption adayı; strict JSON ve kaynak/lore allowlist.
- Önizle, caption seç/düzelt, template değiştir ve server-side Pillow render.
- Kare `1200×1200` PNG/JPEG, web/Matrix teslimi; Discord-compatible dosya.
- Feedback: Komik, Zorlama, Fazla sert, Tekrarlı, Yanlış bağlam, Kaydet.
- Artifact metadata, private download, silme ve template/phrase usage history.
- Party Lore olmadığı/AI Gateway kapalı olduğu durumda açıklanabilir hata; uydurma/cached alakasız meme yok.

### v1.5

- Server-owned screenshot input ve screenshot overlay template'leri.
- Party Lore top-2 retrieval/usage ve lore callback cooldown.
- Discord slash command/delivery adapter.
- Session meme pack (en fazla 5 çeşitli artifact), AI Commentator “meme yap” butonu.
- Template/category affinity ve basit feedback dashboard.
- Landscape `1200×675` ve portrait/reaction `1080×1350` formatları.

### v2

- Highlight frame seçimi, clip meme/FFmpeg ve kısa animasyon.
- Opt-in transcript'ten event adayı; ham ses/transcript retention sınırı.
- Güçlü multimodal modelle screenshot anlayışı, ama event kanıtı/oyuncu eşlemesi backend'de kalır.
- Orijinal AI görseli için ayrı, onaylı ve maliyet limitli provider adapter.
- Kontrollü custom template editor ve template import lisans kontrolü.

### Henüz yapmaya değmez

- Kendi image modelini eğitmek/fine-tune etmek.
- İnternetten otomatik meme/template scraping ve telif belirsiz kütüphane.
- Yüz değiştirme, gerçek kişi fotomontajı veya oyuncu avatarından alaycı görsel üretme.
- Template marketplace, sosyal keşif, public feed ve viral paylaşım optimizasyonu.
- Her event için paralel beş model çağrısı, agent graph, Redis/Kafka veya ayrı render microservice.
- Sürekli ekran/ses kaydı ve otomatik emotion/personality çıkarımı.

## 3. Meme üretim pipeline'ı

| Adım | İşlem | Karar | Hata davranışı |
|---|---|---|---|
| 1 | Event al, auth/schema/idempotency | Deterministik | 4xx veya önceki job |
| 2 | Oyuncu, setup/payoff, facts ve screenshot'ı normalize et | Deterministik; serbest metinde opsiyonel LLM | Belirsiz oyuncu/fact ret |
| 3 | İzinli lore top-2 getir | Party Lore deterministik retrieval | Timeout: lore'suz devam |
| 4 | Meme-worthiness ve hard veto | Deterministik; borderline'da planner LLM | Eşik altı `NOT_WORTHY` |
| 5 | Meme kategorisi adayları | Kural eşlemesi + opsiyonel planner LLM | Güvenli generic kategori veya ret |
| 6 | Eligible template top-5, sonra top-3 | Deterministik ranking; LLM yalnız tie-break | Uygun template yoksa text card |
| 7 | Üç caption adayı | LLM `meme-text` | JSON/timeout: job retry, artifact yok |
| 8 | Dil, fact, policy, repetition, safety ve quality | Deterministik + yalnız risklide review LLM | Adayı reddet; tümü reddedilirse fail |
| 9 | Görsel render | Deterministik Pillow worker | Overflow/asset/font hatası fail |
| 10 | Asset+artifact metadata transaction | Deterministik | Byte yazıldı/DB olmadıysa orphan cleanup |
| 11 | Web/Matrix/Discord adapter | Deterministik | Artifact READY kalır; delivery retry |
| 12 | Feedback upsert ve ranking/cooldown | Deterministik | Idempotent; yorum üretimini bozmaz |

### Meme-worthiness formülü

```text
positive = 0.28*setup_payoff_clarity
         + 0.22*event_impact
         + 0.16*surprise
         + 0.12*specificity
         + 0.10*lore_relevance
         + 0.07*visual_potential
         + 0.05*manual_intent

penalty  = 0.25*sensitivity_or_conflict
         + 0.18*event_repetition
         + 0.15*target_saturation
         + 0.12*format_saturation

meme_score = clamp(positive - penalty, 0, 1)
```

Preview threshold `.62`; kullanıcının açık “meme yap” eyleminde `.55`, fakat safety/consent/cooldown hard
filter'ları değişmez. Confidence `<.65`, gerçek tartışma/UPSET, kapalı MEME izni, bilinmeyen oyuncu ve özel
hayat verisi hard ret. Borderline `.55–.70` olayda planner prompt kullanılabilir; güçlü açık event'te gereksiz
değerlendirme çağrısı yapılmaz.

### Template suitability

```text
score = 0.32*category_fit
      + 0.18*source_and_aspect_fit
      + 0.15*required_context_coverage
      + 0.12*feedback_affinity
      + 0.10*freshness
      + 0.08*predicted_text_fit
      + 0.05*asset_health
      - 0.22*recent_template_penalty
      - 0.15*target_format_saturation
```

Backend önce required context, asset status, max harshness ve cooldown ile hard filter uygular. LLM yalnız
bu eligible ID listesinden seçebilir. `score < .55` template render edilmez; uygun built-in text card varsa
ona düşülür, yoksa job `NO_TEMPLATE` olur.

## 4. Meme taksonomisi

| Tür | Ne zaman | Görsel | Caption kalıbı | Zorunlu event alanı | Tekrar riski |
|---|---|---|---|---|---|
| REPEATED_FAILURE | Aynı oyun içi hata kanıtlı tekrar | Seri/istatistik kartı | “Deneme N / aynı sonuç” | actor, attemptCount veya lore | Yüksek |
| OVERCONFIDENT_FAILURE | İddialı setup hemen tersine döner | Beklenti/gerçeklik | “Planı anlatırken / ilk engelde” | actor, setup, payoff | Yüksek |
| ACCIDENTAL_SUCCESS | Event açıkça kazara başarı der | Reaction/achievement | “Plan değildi / yine de çalıştı” | actor, payoff | Orta |
| BETRAYAL | Yalnız oyun içi ihanette | Fake news/wanted | “Takım arkadaşı / güncelleme sonrası” | actor, target, game context | Yüksek |
| USELESS_PREPARATION | Uzun hazırlık çok kısa sürede boşa gider | Beklenti/gerçeklik | “X dakika hazırlık / Y saniye macera” | actor, duration, payoff | Orta |
| BAD_NAVIGATION | Rota açıkça yanlış/başlangıca dönüş | Harita/stat kartı | “Mesafe / ilerleme: 0” | actor, route result | Yüksek |
| PANIC | Event panik eylemini açıkça tanımlar | Reaction card | “Tehlike / bütün tuşlar” | actor, observed action | Orta |
| CLUTCH | Düşük kaynakla kritik başarı | Achievement/hype | “Tek can / tam zamanında” | actor, stakes, payoff | Düşük |
| FAKE_EXPERT | Tavsiye ile sonuç açıkça çelişir | Tutorial/patch card | “Uzman görüşü / saha testi” | actor, advice summary, payoff | Yüksek |
| BLAMING_LAG | Oyuncunun doğrulanmış oyun içi sözü | Fake support ticket | “Sebep: lag / dosya durumu” | actor, exact claim | Yüksek |
| SILENT_DISASTER | Sessizlikle eşzamanlı açık başarısızlık | Documentary/reaction | “Mikrofon: sessiz / sonuç: yüksek” | actors, silence evidence, payoff | Orta |
| TEAM_WIDE_FAILURE | Üç oyuncu aynı olayda birlikte başarısız | Team poster/stat | “Takım çalışması / yanlış yönde” | three actors, shared payoff | Orta |
| GREED_PUNISHED | Fazla loot/ödül isteği tuzağa dönüşür | News/achievement | “Bir sandık daha / bütün envanter” | actor, greedy action, payoff | Orta |
| FRIENDLY_FIRE | Connector açıkça takım hasarı bildirir | Incident report | “Tehdit kaynağı / takım içi” | actor, target, verified damage | Orta |
| MISSED_OBVIOUS | Açık ipucu/nesne kanıtlı biçimde kaçırılır | Zoom/reaction | “Aranan şey / kadrajın ortası” | actor, missed object evidence | Yüksek |
| RESOURCE_HOARDER | Kaynak maç sonuna kadar kullanılmaz | Inventory/stat card | “Final envanteri / kullanım: 0” | actor, item/count, end state | Orta |
| PREMATURE_CELEBRATION | Kutlama bitişten önce gelir, sonuç tersine döner | News/timeline | “Zafer konuşması / raund devam ediyor” | actor, celebration, payoff | Orta |
| IMPOSSIBLE_COMEBACK | Düşük ihtimalli, kanıtlı geri dönüş | Achievement/news | “Kalan şans / sonuç” | actor/team, stakes, payoff | Düşük |
| AFK_TIMING | AFK dönüşü kritik anla çakışır | Attendance/stat | “Katılım süresi / final vuruşu” | actor, AFK timing, payoff | Orta |
| CURSED_PLAN | Açık plan birden çok üyeyi zincirleme etkiler | Patch note/diagram | “Plan v1.0 / bilinen sorunlar” | planner, plan, multi-step payoff | Yüksek |

“Fake expert” kişiyi kalıcı sahte/aptal olarak etiketlemez; yalnız verilen tavsiye ile aynı event sonucunun
çelişkisini işler. “Blaming lag” exact claim olmadan seçilemez. Betrayal gerçek hayata taşınamaz.

## 5. Template sistemi

TypeScript şeması, caption zone modeli ve geçerli JSON/nesne örneği:
[template-contract.ts](template-contract.ts).

Her template immutable `template_key+version` ile yayınlanır. Bir asset veya zone değişince version artar;
eski artifact `captions_snapshot`, `template_version` ve render version ile yeniden açıklanabilir. Built-in
template JSON'u code-owned'dır; public API doğrudan sistem promptu/zone JSON'u düzenlemez.

Caption zone koordinatları `0..1` normalize edilir. Backend yüklemede JSON Schema ile şunları doğrular:

- Zone canvas dışına taşmaz ve birbirini izinsiz örtmez.
- `maxChars 8..120`, `maxLines 1..4`, font `Noto Sans`, min/max font güvenli aralıktadır.
- Renk `#RRGGBB`, stroke 0..8; unknown font/renderer özelliği reddedilir.
- `requiredContext` event'te yoksa template eligibility'ye girmez.
- Görsel asset `ACTIVE`, beklenen boyut/mime ve aynı server veya built-in scope'tadır.

Curated kütüphanede internet meme yüzleri yerine platforma ait soyut oyun illüstrasyonları, UI kartları ve
lisansı açık asset'ler kullanılmalıdır. Lisans/kaynak `media_assets.metadata` içinde tutulur. Bu hem telif
belirsizliğini hem de template'in kısa sürede “eski internet meme'i” hissini azaltır.

## 6. Prompt engineering

Beş production-ready prompt:

1. Meme-worthiness + kategori seçimi
2. Eligible template seçimi
3. Lore-aware üç caption adayı
4. Caption ranking
5. Safety ve tone review

Tam metinler ve JSON çıktıları: [prompts.md](prompts.md).

Önerilen MVP çağrı sayısı event başına çoğunlukla **bir**: backend kesin worthiness/category/template top-3
üretir, `meme-caption-v1` caption yazar, deterministik rank/filter seçer. Planner yalnız borderline veya
kategori belirsizliğinde; LLM rank yalnız kullanıcı “daha iyi aday” istediğinde; review yalnız risk flag'inde
çağrılır. Tek job'da dört zorunlu çağrı yapılmaz.

LLM çıktısı chain-of-thought içermez/saklamaz; yalnız kısa reason code'lar tutulur. Caption ve lore ID'leri
render öncesi kaynak allowlist'ine göre tekrar doğrulanır.

## 7. Caption kalite kuralları

- Zone başına 48 karakter varsayılan; toplam en fazla 18 kelime. Fake card formatında başlık 36,
  alt açıklama 72 karakter olabilir.
- Şaka ilk bakışta anlaşılmalı; ayrı açıklama, footnote veya lore özeti olmamalı.
- “When you.../sen ... iken”, “POV”, hashtag ve generic “gamer moment” kalıbı mümkünse kullanılmaz.
- Oyuncu adı yalnız target izni açık ve isim görseli gerçekten daha anlaşılır kılıyorsa kullanılır.
- Event/lore dışında niyet, sayı, süre, alıntı, sebep veya geçmiş eklenmez.
- Oyun içi olay eleştirilebilir; gerçek kişi “beceriksiz/aptal/değersiz” diye etiketlenmez.
- Küfür MVP'de kapalıdır. Sonra explicit opt-in olsa bile nefret/tehdit/korunan özellik daima yasaktır.
- Recent phrase/punchline tekrar edilmez; lore callback anlatılmaz.
- Türkçe Unicode NFC saklanır; `ı/İ/ğ/ş/ç/ö/ü` ASCII'ye çevrilmez. Programatik uppercase gerekirse
  Türkçe locale-aware dönüşüm veya caption'ın modelden istenen case'i kullanılır.
- Caption template zone'a minimum fontta sığmıyorsa otomatik küçültme sınırında reddedilir; kırpma,
  taşma veya okunmaz 12px metin yoktur.
- Harshness: 0 kutlayıcı/nötr, 1 hafif takılma, 2 belirgin oyun içi roast, 3 yalnız açık opt-in; MVP
  effective cap 2'dir.

## 8. Görsel render mimarisi

### Seçim: Python Pillow

Nexus backend zaten Python/FastAPI'dir. Pillow, PNG/JPEG template üzerine deterministik text/image compositing,
font ölçümü, stroke, wrap ve thumbnail için yeterlidir. Sharp için ayrı Node runtime/service, Playwright için
Chromium, Canvas için native Node bağımlılığı eklemek üç kişilik MVP'de gereksiz operasyon yüküdür. SVG
template'leri ileride tasarım kolaylığı için input olabilir; MVP render kaynağı raster + zone JSON'dur.

Çalışabilir örnek: [renderer-example.py](renderer-example.py).

### Font ve layout

- Repo/Docker image içine lisansı ile `NotoSans-Regular.ttf`, `NotoSans-Bold.ttf`, `NotoSans-Black.ttf`.
- Font dosyası kullanıcı input'u değildir; template allowlist'i yalnız bu aileyi seçer.
- Renderer max fonttan min fonta 2px adımla iner, pixel-bbox ile satır sarar; maxLines/height aşılırsa fail.
- Çok uzun tek token karakter bazında güvenli kırılabilir; fakat aday kalite filtresi bunu normalde reddeder.
- Beyaz text + siyah stroke varsayılanı; kart template'lerinde erişilebilir kontrast oranı önceden test edilir.
- Mobile için ana caption en az 30px @1200 canvas; önizlemede 320px genişlikte okunabilirlik testi.

### Formatlar

- Kare: `1200×1200`, default text/template meme.
- Landscape: `1200×675`, Discord/Highlight screenshot (v1.5).
- Portrait: `1080×1350`, reaction/news card (v1.5).
- UI/text ağırlıklı artifact PNG; fotoğraf/screenshot JPEG quality 88. WebP opsiyonel API formatıdır ama
  Discord tesliminde PNG/JPEG tercih edilir.
- Çıktı hedefi `<4 MB`, hard limit `<8 MB`; render sonrası ölçülür, PNG büyükse kayıpsız optimize veya JPEG.

### Storage, auth ve cache

Mevcut `/attachments/{id}` indirme ucu server üyeliği bağlamı kontrol etmiyor ve artifact yaşam döngüsü
tutmuyor. Meme için `media_assets` tablosuna bağlı `/servers/{serverId}/meme-assets/{assetId}` private endpoint'i
oluşturulmalıdır. Byte'lar ayrı `/srv/meme-media/<hash-prefix>/<uuid>.<ext>` namespace/volume'unda yaşar;
storage key backend üretir, client path/URL veremez.

Üç kişi için CDN gerekmez. Immutable hash'li aktif asset `Cache-Control: private, max-age=86400`; silme status'u
endpoint'te her istekte kontrol edilir. Aynı template+captions+renderVersion+sourceHash için render cache key
üretilebilir. Silinen/izin değişen lore'u içeren meme yeni render cache'inden dönmez; mevcut artifact kullanıcı
silme politikasına tabidir.

Upload'ta MIME yalnız header'dan kabul edilmez: Pillow decode, magic/mime, pixel/dimension ve decompression-bomb
limitleri doğrulanır; EXIF orientation uygulanır, EXIF metadata output'a taşınmaz.

## 9. Veri modeli

PostgreSQL referans şeması: [schema.sql](schema.sql).

| Tablo | Amaç |
|---|---|
| `meme_templates` | Version'lı zone/limit/category/asset ve suitability/cooldown |
| `meme_generation_jobs` | Event snapshot, worker lease, score, model/prompt/usage ve idempotency |
| `generated_memes` | Seçilen candidate/template, output asset, caption snapshot ve delivery/delete state |
| `meme_feedback` | Oyuncu başına güncellenebilir feedback |
| `meme_caption_candidates` | Üç caption, target/lore/harshness/quality/safety/phrase hash |
| `meme_lore_links` | Retrieval skoru ve gerçekten kullanılan lore ID |
| `meme_template_usage` | Server/session/target bazlı format cooldown ve çeşitlilik |
| `media_assets` | Template, screenshot, preview ve rendered byte metadata |

Job'daki `input_event` kanonik event snapshot'ıdır; serbest connector payload değildir. Render artifact, prompt/model
değişse bile caption/template snapshot'ı ile tekrar açıklanır. Job/event retention 90 gün, saved meme kullanıcı
silene kadar; başarısız preview asset 24 saat, sahipsiz byte cleanup günlük çalışır.

`lore_entries` ve `players` Party Lore ortak alanından gelir. Party Lore migration henüz yoksa Meme migration'ın
lore bağlantısı Phase v1.5'te eklenir; MVP runtime'da sahte tablo yaratılmaz.

## 10. API tasarımı

Tam TypeScript contract: [api-contract.ts](api-contract.ts).

| Method ve yol | Amaç | Başarı |
|---|---|---|
| `POST /servers/{serverId}/memes/jobs` | Event'i meme job'a gönder | `202 MemeJobAccepted` |
| `GET /memes/jobs/{jobId}/candidates` | Worthiness ve üç preview adayı | `200`, pending ise `202` |
| `POST /memes/jobs/{jobId}/render` | Seçilen/override caption'ı render et | `201 GeneratedMeme` |
| `POST /memes/{memeId}/regenerate-caption` | Yeni caption candidate job | `202`, eski artifact değişmez |
| `POST /memes/jobs/{jobId}/change-template` | Eligible template değiştir/preview | `200 candidates` |
| `PUT /memes/{memeId}/feedback` | Feedback upsert | `200` |
| `GET /servers/{serverId}/sessions/{sessionId}/meme-pack` | Çeşitli saved/ready meme listesi | `200` |
| `POST /servers/{serverId}/sessions/{sessionId}/meme-pack` | Eksik adaylardan pack job | `202` |
| `GET /servers/{serverId}/meme-assets/{assetId}` | Auth'lu private asset | image response |
| `DELETE /memes/{memeId}` | Artifact/byte silme kuyruğu | `202` |

Job gönderme:

```json
{
  "event": {
    "schemaVersion": "1.0",
    "eventId": "fce32b68-29fc-4443-9a8b-56e9d2917807",
    "serverId": 4,
    "source": "MANUAL",
    "occurredAt": "2026-08-04T20:14:32Z",
    "momentType": "PREPARATION",
    "actorPlayerIds": ["player_2"],
    "targetPlayerIds": [],
    "game": {"gameKey": "survival-game"},
    "summary": "player_2 on dakika eşya topladıktan sonra ilk engelde düşüp hepsini kaybetti.",
    "setup": "On dakika boyunca eşya topladı.",
    "payoff": "İlk engelde düşüp bütün eşyaları kaybetti.",
    "importance": 0.82,
    "confidence": 1
  },
  "preferredFormats": ["EXPECTATION_REALITY", "PATCH_NOTES"],
  "desiredHarshness": 1
}
```

Preview yanıtı caption text + template ID döndürür. Low-resolution preview yalnız kullanıcı gerçekten görsel
önizleme isterse render edilir; üç candidate için baştan üç tam PNG üretmek CPU/storage israfıdır. Caption override
de aynı karakter/policy/safety kontrollerinden geçer; kullanıcı metni güvenilir değildir.

Regenerate mevcut artifact'i mutate etmez; yeni candidate/job lineage yaratır. Delete, asset endpoint'ini anında
404/410 yapar, Matrix/Discord'da önceden yüklenmiş dış kopyayı her zaman silemeyebileceğini UI açıklar.

## 11. Party Lore entegrasyonu

Lore retrieval request:

```text
module=MEME
query=event.summary + setup + payoff + category tags
participants=actor + target
maxItems=2
exclude=last 20 meme lore IDs
minimumScore=.72
```

Kurallar:

- Event score `.62` altında ise lore retrieval yapılmaz; lore zayıf olayı “komikmiş” gibi kurtarmaz.
- Yalnız `ACTIVE`, `MEME` izinli, target oyuncunun preference'ına uygun ve cooldown dışı kayıtlar.
- Participant overlap veya çok güçlü event semantic eşleşmesi gerekir; yalnız aynı oyun adı yetmez.
- `score >= .82` doğal callback adayı; `.72–.81` model görebilir ama kullanmak zorunda değildir.
- Promptta en fazla 2, çıktıda normalde 0–1 lore. İki lore ancak ikisi aynı running joke'un doğrudan parçalarıysa.
- Eski olayı açıklayan uzun caption yok; üç arkadaşın hemen anlayacağı alias/tek kısa çağrışım tercih edilir.
- Private recap-only, restricted, disputed, deleted veya player `allow_memes=false` lore prompta hiç girmez.
- Modelin döndürdüğü lore ID, input allowlist'inde değilse bütün candidate reddedilir.
- Meme render edildikten sonra `actually_used=true` lore için Party Lore usage kaydı; sadece retrieval usage değildir.
- Lore sonradan kısıtlanırsa yeni render/regenerate/delivery durur. Mevcut saved artifact için kullanıcıya silme seçeneği sunulur.

## 12. Feedback döngüsü

| Düğme | Anlık etki | Sonraki ranking etkisi |
|---|---|---|
| Komik | Pozitif kalite sinyali | Template/category/style affinity `+`; tek başına cooldown azaltmaz |
| Zorlama | Caption style+reason pattern'e eksi | Aynı pattern 30 gün `-.10`; event gerçeğini değiştirmez |
| Fazla sert | Aynı target/category session guard | Effective harshness o target için bir kademe düşer; kalıcı ayar önerilir |
| Tekrarlı | Phrase/template cooldown 30 gün | Template freshness ve style rank düşer |
| Yanlış bağlam | Artifact candidate başarısız sayılır | Prompt/model golden sete ekleme adayı; lore/template affinity düşer |
| Kaydet | Artifact saved/pin | Format için hafif pozitif; “daha sert yap” sinyali değildir |

Üç kişilik veri az olduğu için kişi başına model eğitilmez. Ağırlık güncellemeleri cap'li, geri alınabilir ve
ayar ekranında açıklanabilir olmalıdır. Feedback yalnız veren oyuncunun soft preference'ını etkiler; target'ın
`TOO_HARSH` kararı herkese uygulanan safety guard olur. Bir oyuncunun “komik” oyu başka oyuncunun boundary'sini
geçemez.

Feedback upsert'tir: oyuncu kararını değiştirince sayaçlar transaction içinde eski sinyali çıkarıp yenisini ekler.
Aggregate score gecelik materialize edilebilir; üç kişi için sorguda hesaplamak da yeterlidir.

## 13. Solo geliştirici planı

### Milestone 0 — Template ve renderer spike

- Kapsam: 3 lisanslı asset, zone JSON, Noto Sans ve Pillow render.
- Teknik işler: font paketleme, wrap/fit/stroke, PNG/JPEG output, hash/private asset PoC.
- Definition of done: 30 Türkçe caption 320px preview'de okunur; overflow sessiz kırpılmaz; output <4 MB.
- Test: pixel/perceptual golden, uzun `İ/ı/ğ/ş/ç/ö/ü`, tek uzun token, EXIF/dimension testleri.
- Ertele: DB, LLM, Discord, screenshot.

### Milestone 1 — Deterministik manuel MVP çekirdeği

- Kapsam: 10 template, manual event, worthiness/category/template rules, elle caption override ve render.
- Teknik işler: SQLAlchemy/Alembic, media storage, job/asset/render API, worker lease, authz/delete.
- Definition of done: üç hesap yalnız kendi server asset'ini görür; aynı idempotency tek job; 10 template render.
- Test: PostgreSQL integration, path traversal, cross-server IDOR, asset cleanup.
- Ertele: LLM caption, feedback learning, lore.

### Milestone 2 — AI caption ve önizleme

- Kapsam: caption prompt, üç candidate, schema/fact/policy/repetition validation.
- Teknik işler: `meme-text` Gateway profile, token/timeout, candidate/rank, regenerate/template change.
- Definition of done: 100-event golden sette invented fact 0, Türkçe/style pass >= %85, schema >= %99,5.
- Test: prompt injection, wrong player/number/lore, timeout/invalid JSON, snapshot rubric.
- Ertele: planner/review calls yalnız ölçülen gereksinimde.

### Milestone 3 — Feedback ve teslim

- Kapsam: altı feedback, Matrix/web delivery, Discord-compatible artifact ve private history.
- Teknik işler: feedback upsert, cooldown/affinity, target fairness, dispatcher retry, frontend buttons.
- Definition of done: feedback bir sonraki ranking/guard'da etkili; delivery retry duplicate mesaj yaratmaz.
- Test: concurrent feedback, repeated phrase/template, Matrix upload ve 8 MB sınırı.
- Ertele: Discord bot; artifact API hazır olur.

### Milestone 4 — Party Lore ve screenshot (v1.5)

- Kapsam: lore top-2, screenshot upload/import, overlay template ve AI Commentator action.
- Teknik işler: consent/cooldown/usage, safe asset import, crop/EXIF, provenance.
- Definition of done: forbidden lore leakage 0; lore servisi yokken normal; kötü/çok büyük görsel quarantine.
- Test: lore relevance, deleted lore, image bomb/corrupt MIME, source deletion.
- Ertele: multimodal screenshot understanding.

### Milestone 5 — Session pack ve Discord

- Kapsam: max 5 çeşitli meme, Discord slash command/delivery.
- Teknik işler: diversity selector, pack job, service credential/player mapping, delivery idempotency.
- Definition of done: pack aynı template'i tekrarlamaz ve target dağılımını dengeler; Discord preview doğru.
- Test: mock Discord errors/rate limit, duplicate command, 30-event session replay.
- Ertele: video/TTS/AI image.

## 14. Test stratejisi

- Caption snapshot: deterministic model fixture çıktısı + schema/zone/reason snapshot; model canlı exact string'e bağlanmaz.
- Image layout: her template/caption zone için PNG golden, perceptual hash veya SSIM toleransı; font/render version sabit.
- Türkçe overflow: bütün özel harfler, büyük `İ`, noktalama, 48/49 char boundary, uzun kelime ve iki satır.
- Template cooldown: saat kontrollü test, target/category saturation, save'in bypass etmemesi.
- Hallucination: event/lore dışı oyuncu, sayı, süre, niyet ve alıntı candidate'da reddedilir.
- Lore relevance: strong/weak participant overlap, max 2 context, allowlist, deleted/restricted/cooldown leakage 0.
- Safety: gerçek çatışma, korunan özellik, görünüş/sağlık/finans/özel hayat, profanity ve harshness permutations.
- Discord delivery: PNG/JPEG MIME, byte limit, retry-after, upload timeout, idempotent external message ID.
- Media security: spoof MIME, corrupt image, decompression bomb, EXIF, path traversal, cross-server IDOR, deleted asset.
- Job concurrency: çift render, regenerate-vs-delete, expired lease, orphan file cleanup.
- Repetition: exact hash, paraphrase 3-gram, same template/category/target, pack diversity.
- Feedback: upsert counter reversal, target TOO_HARSH priority ve unrelated player boundary.

Golden dataset en az 120 sentetik event: 40 worthy, 30 not-worthy, 20 lore, 15 safety, 15 repetition/template.
Yayın kapısı: critical safety/hallucination 0; schema >= %99,5; caption rubric >= %85; render golden %100;
MVP worker p95 candidate <5 s, render p95 <800 ms (1200×1200, gerçek production CPU).

Manuel playtest:

- Meme açıklamasız anlaşılıyor mu?
- Caption 320px telefonda okunuyor mu?
- Aynı template/punchline bir sessionda tekrar ediyor mu?
- Başarılar da en az failure kadar görünür mü?
- Hedef oyuncu rahat mı ve feedback hemen etkili mi?
- Lore callback doğal mı, yoksa eski olayı açıklamaya mı çalışıyor?
- “Template değiştir” caption'ı bozmadan ya da açıkça yeniden üreterek mi çalışıyor?
- Silinen artifact private endpoint ve history'den hemen kalkıyor mu?

## 15. Nihai teslimler

### Önerilen MVP mimarisi

```text
Manual event / Commentator action (later Highlight/Discord)
                    |
          FastAPI Meme API + authz
                    |
      PostgreSQL job/media/template metadata
                    |
       meme-worker (DB lease, no Redis)
          | deterministic worthiness/category
          | eligible template top-3
          | Party Lore top-2 optional
          v
        AI Gateway meme-text -> 3 captions
                    |
      schema/fact/safety/repetition/text-fit
                    |
       Pillow renderer + private media volume
                    |
       web/Matrix (Discord v1.5) + feedback
```

### İlk 10 uygulama görevi

1. `backend/app/memes/` paketini ve `MemeEventV1` Pydantic/TypeScript contract'ını oluştur.
2. Noto Sans fontları lisanslarıyla paketle; Pillow bağımlılığını Docker'a ekle ve üç-template renderer spike'ını geçir.
3. `media_assets` private storage/indirme, MIME/pixel/hash doğrulama ve async byte deletion akışını yaz.
4. `meme_templates` model/migration, JSON Schema validator ve 10 built-in template seed'ini ekle.
5. Job/candidate/generated/usage modellerini, DB lease worker ve idempotent event submit API'yi ekle.
6. Deterministik worthiness/category/template scoring, cooldown, target fairness ve safety hard filter'larını yaz.
7. `meme-caption-v1`i Gateway'deki `meme-text` profile bağla; strict JSON/fact/lore/phrase doğrulamasını ekle.
8. Candidate preview, render, regenerate, template change ve delete endpointlerini tamamla.
9. Frontend Meme panelini event formu, üç candidate, caption override, feedback ve history ile ekle.
10. Matrix teslimini ve uçtan uca üç-hesap testini geçir; ardından Party Lore ve Discord'u ayrı feature flag'lerle bağla.

### TypeScript template ve event şemaları

- [template-contract.ts](template-contract.ts)
- [event-contract.ts](event-contract.ts)

### PostgreSQL şeması ve API contract

- [schema.sql](schema.sql)
- [api-contract.ts](api-contract.ts)

### Rendering örneği

[renderer-example.py](renderer-example.py), güvenilir asset path, Noto Sans, pixel-aware wrap, minimum font,
stroke, EXIF normalization ve 1200×1200 PNG output gösterir. Örnek path auth/storage çözümlemesini bilerek dışarıda
bırakır; client path'i renderer'a ulaşamaz.

### Beş production prompt

[prompts.md](prompts.md): plan/category, template selection, lore-aware caption, ranking ve safety review.

### Yirmi gerçekçi oyun meme örneği

Tüm olaylar sentetiktir; gerçek oyuncular hakkında iddia değildir. Caption'lar template zone sınırına göre daha
da kısaltılabilir.

| # | Event | Kategori / format | Caption |
|---:|---|---|---|
| 1 | Emir 10 dk eşya topladı, ilk engelde hepsini kaybetti | USELESS_PREPARATION / expectation | “10 dakika hazırlık / 10 saniye macera” |
| 2 | Mert köprünün güvenli olduğunu söyleyip ilk düşen oldu | OVERCONFIDENT_FAILURE / iki panel | “Köprü raporu: güvenli / Test sonucu: Mert” |
| 3 | Aylin yanlışlıkla attığı bomba ile boss'u bitirdi | ACCIDENTAL_SUCCESS / achievement | “Planlanmamış Mükemmellik açıldı” |
| 4 | Deniz hidden-role oyununda takımı son tur sattı | BETRAYAL / fake news | “Takım anlaşması son turda güncellendi” |
| 5 | Mert yanlış rotayla grubu başlangıca döndürdü | BAD_NAVIGATION / stat | “Yolculuk: 12 dk / İlerleme: 0 m” |
| 6 | Aylin panikle bütün yetenekleri boş duvara kullandı | PANIC / reaction | “Tehlike görülünce / Bütün tuşlar göreve” |
| 7 | Deniz tek canla iki rakibi yenip raundu aldı | CLUTCH / achievement | “Tek Canlık Kamu Hizmeti” |
| 8 | Emir build dersi verip aynı build ile hemen elendi | FAKE_EXPERT / tutorial card | “Teori: kusursuz / Saha testi: kısa” |
| 9 | Mert elendikten sonra açıkça “lag” dedi | BLAMING_LAG / support ticket | “Destek talebi: LAG / Durum: geleneksel” |
| 10 | Üçlü sessizce aynı tuzağa yürüdü | SILENT_DISASTER / documentary | “İletişim: sessiz / Koordinasyon: eksiksiz” |
| 11 | Üç oyuncu aynı anda yanlış kapıyı seçti | TEAM_WIDE_FAILURE / team card | “Aynı yanlış karar / Tam takım uyumu” |
| 12 | Deniz bir sandık daha açınca bütün loot tuzağa düştü | GREED_PUNISHED / news | “Bir sandık daha denendi / Ekonomi kapandı” |
| 13 | Aylin'in doğrulanmış atışı takım arkadaşını düşürdü | FRIENDLY_FIRE / report | “Tehdit yönü: takım içi” |
| 14 | Emir aradığı düğmenin önünde üç dakika dolaştı | MISSED_OBVIOUS / reaction | “Aranan düğme / Kadrajın başrolü” |
| 15 | Mert maç sonunda sekiz iksirle hâlâ bekliyordu | RESOURCE_HOARDER / stat | “İksir kullanımı: 0 / Koleksiyon: 8” |
| 16 | Deniz raund bitmeden zafer emote'u yaptı ve elendi | PREMATURE_CELEBRATION / timeline | “Kutlama başladı / Raund devam etti” |
| 17 | Grup son 20 saniyede kayıp maçı çevirdi | IMPOSSIBLE_COMEBACK / news | “Maç bitti sanıldı / Üçlü itiraz etti” |
| 18 | Aylin AFK'den dönüp tek atışla final vuruşunu aldı | AFK_TIMING / attendance | “Katılım: son saniye / Katkı: final” |
| 19 | Emir'in planı üç oyuncuyu sırayla aynı çukura düşürdü | CURSED_PLAN / patch notes | “Plan v1.0 / Bilinen sorun: herkes” |
| 20 | Mert üçüncü sessionda yine son iksiri hiç kullanmadı | REPEATED_FAILURE / series card | “Bölüm 3 / İksir yine güvende” |

Örnek 9 yalnız exact claim event'te varsa geçerlidir; sistem ağın gerçekten iyi/kötü olduğuna dair bilgi uydurmaz.
Örnek 20 ancak Party Lore/ayrı event kanıtı tekrar sayısını doğruluyorsa kullanılabilir.

### Ertelenecek özellikler

- AI-generated original image, face swap, avatar roast ve görsel fine-tuning.
- Video/clip/animated GIF ve FFmpeg pipeline.
- Sürekli STT, screen capture, OCR ve otomatik highlight detection.
- Multimodal screenshot anlayışı; v1.5 yalnız kullanıcı seçtiği screenshot'a caption koyar.
- Custom template editor/import ve template marketplace.
- Public CDN/social feed/analytics ve viral scoring.
- Redis/Kafka/ayrı renderer servisi; ölçülen yük gerekmedikçe.
- Otomatik Party Lore yazımı ve onaysız private callback.
- Kişiye özel model/fine-tuning veya psikolojik humor profili.
- Dört-beş zorunlu LLM çağrılı agent pipeline; MVP çoğu eventte tek caption çağrısıdır.

## Model değişimi ve ölçüm notu

Yeni LLM için `meme-text` golden setinde strict JSON `>= %99,5`, invented fact/yanlış player/private lore `0`,
Türkçe doğallık ve template-fit insan puanı `>= %85`, üç aday üretimi p95 `<=4 saniye` hedeflenir. Model adı
frontend/template/lore'a yazılmaz; job metadata provider model ve prompt version saklar. Yeni profil küçük canary
ile açılır, eski profile dönüş event/DB migration gerektirmez.


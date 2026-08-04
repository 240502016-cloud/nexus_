# Highlight Generator — ürün ve teknik tasarım

Durum: uygulama öncesi referans tasarım  
Hedef: üç kişilik özel oyun grubunun işaretlediği veya güvenilir sinyallerle desteklenen anları kısa,
doğru zamanlanmış ve paylaşılabilir MP4 highlight'larına dönüştürmek  
Uyum: mevcut FastAPI/PostgreSQL/React platformu, AI Gateway, AI Commentator, Meme Generator ve Party Lore

## Karar özeti

Nexus MVP'de ekran kaydetmez. Oyuncu OBS Replay Buffer veya başka bir yerel kayıt aracıyla son 30–90 saniyeyi
kendi bilgisayarında kaydeder; hotkey OBS'ye aittir. Nexus MP4/MKV dosyasını, yaklaşık event marker'ını ve
metadata'yı alır. FFprobe dosyayı doğrular, backend deterministic bir başlangıç/bitiş önerir, LLM yalnız kısa
başlık/açıklama ve sınırlı trim düzeltmesi önerir, ayrı media worker FFmpeg ile final MP4/thumbnail üretir.

Bu yaklaşım tam video editörü, sürekli cloud recording, screen capture agent veya multimodal video modeli
gerektirmez. İlk kullanışlı ürün: yükle → marker koy → 8–45 saniyelik preview → trim düzelt → render → paylaş.

FFmpeg/FFprobe şu an hostta ve backend image'ında kurulu değildir. Genel `ai-worker` içine eklenmeyecektir.
CPU/disk/timeout profili farklı olduğu için pinned FFmpeg içeren, network'süz, concurrency=1 ayrı
`media-worker` container'ı ve PostgreSQL lease kuyruğu kullanılacaktır. Redis gerekmez.

Video byte'ları AI Gateway'e gönderilmez. MVP'de Gateway yalnız doğrulanmış event/transcript parçalarından
metadata üretir. Planlanan daha güçlü LLM geçişi `highlight-metadata` mantıksal model profili üzerinden yapılır;
veri, FFmpeg ve API sözleşmeleri model adına bağlanmaz.

## 1. Ürün tanımı

### Highlight sayılan şey

Bir an, en az bir güçlü kaynak niyeti/sinyali taşımalı ve kısa clip içinde anlaşılabilir setup/payoff'a sahip
olmalıdır: oyuncunun manuel marker'ı, önemli Commentator event'i, doğrulanmış oyun telemetry'si, birden fazla
oyuncunun belirgin tepkisi veya nadir/özgün bir sonuç. Yalnız sesin yükselmesi ya da birinin ölmesi highlight
değildir.

### Highlight türleri

| Tür | Tanım | Örnek karar |
|---|---|---|
| Skill highlight | Doğrulanmış beceri, clutch, stratejik başarı veya milestone | Başarıyı kutlayan kısa başlık; roast yok |
| Comedy highlight | Açık setup/payoff, beklenmedik sonuç veya ortak tepki | Tepkiyi de içeren daha geniş pre/post padding |
| Failure highlight | Belirli oyun içi hata ve güvenli grup bağlamı | Oyuncu izni/harshness kontrolü; kalıcı beceriksizlik etiketi yok |
| Lore-worthy highlight | Aylar sonra anlamlı olabilecek özgün/tekrarlı olay ve güçlü kanıt | Otomatik lore değil; kullanıcı onaylı Party Lore adayı + evidence |

`CHAOS`, birden fazla eşzamanlı olayın primary kategorisidir; ürün görünümünde comedy/failure ile birlikte
etiketlenebilir. Bir clip hem skill hem lore-worthy sinyali taşıyabilir ama tek primary category ile sıralanır.

### Üç kişilik grup değeri

- Oyuncu kimliği ve consent, server üyeliğiyle açıkça doğrulanabilir.
- Kısa session derlemeleri public esports ürünü kadar ağır altyapı istemez.
- Commentator, Meme ve Lore aynı event ID/provenance üzerinden birbirine bağlanabilir.
- Üç kişide ortak tepki çok anlamlıdır; buna karşılık yanlış speaker/target ataması güveni hızla bozar.
- Yerel kayıt, bütün oyun oturumunu merkezi sunucuya sürekli göndermediği için daha az ürkütücüdür.

### Zayıf clip bolluğunu önleme

- Otomatik detection kapalı başlar; kullanıcı marker'ı review adayı yaratır, otomatik render yapmaz.
- Automatic threshold `.62`; manuel marker `.45` ile preview listesine girebilir ama safety'yi aşmaz.
- Aynı recording'de 30 saniye içinde benzer marker'lar tek candidate window'da birleşir.
- Session başına otomatik en fazla 10 candidate; compilation en fazla 8 clip/90 saniye.
- Yalnız kullanıcı onayladığı candidate render edilir; upload başına onlarca türev dosya üretilmez.
- Recent highlight semantic/marker benzerliği uniqueness'i düşürür; aynı failure seri hâlinde kesilmez.
- `WRONG_MOMENT` ve `TOO_LONG` feedback'i sinyal/trim varsayımlarını düşürür; event gerçeğini değiştirmez.

## 2. MVP stratejisi

### En basit yararlı akış

1. Oyuncu OBS Replay Buffer'ı 60 saniyeye ayarlar ve oyun sırasında OBS hotkey'ine basar.
2. Kaydedilen MP4/MKV Nexus'a yüklenir. Kullanıcı event'in dosyanın sonundan yaklaşık kaç saniye önce
   olduğunu seçer veya timeline'da marker koyar.
3. Backend `duration`, stream, codec, hash ve limitleri FFprobe ile doğrular.
4. Kategoriye göre örneğin marker'dan 12 saniye önce/8 saniye sonra window önerilir.
5. LLM yalnız doğrulanmış marker/opsiyonel kısa nottan başlık, tek satır açıklama, tag ve meme/lore aday flag'i üretir.
6. Kullanıcı başlangıç/bitişi görür ve onaylar.
7. FFmpeg H.264/AAC, faststart MP4 ve thumbnail üretir; web/Matrix'te paylaşılır.

Discord `/highlight` komutu yerel OBS buffer'ını kaydedemez. Yalnız server zamanı üzerinde marker yaratır;
sonradan `capture_started_at/end_at` metadata'lı OBS dosyası yüklenirse marker offset'e çevrilir. Otomatik dosya
watcher/hotkey bridge sonraki sürümdür.

### MVP

- Streamed MP4/MKV upload, 1 GiB ve 15 dakika hard limit; private local disk.
- Manuel/OBS source, relative veya wall-clock marker, tam üç player mapping.
- FFprobe validation, SHA-256/idempotency ve cross-server authorization.
- Deterministik marker window/score, candidate review ve trim UI.
- Accurate re-encode, landscape 1080p-or-source-size MP4, audio normalization, thumbnail.
- AI Gateway ile kısa başlık/açıklama/category flag; LLM yoksa nötr metadata fallback.
- Web/Matrix private delivery, feedback, save/delete ve 14/90 günlük retention.
- Ayrı PostgreSQL-backed media worker; progress/cancel/retry.

### Sonraki sürüm

- OBS desktop folder watcher ve marker/hotkey correlation.
- AI Commentator marker'ları, Discord marker/upload adapter.
- STT, subtitle cleanup/burn-in ve separate OBS audio-track speaker mapping.
- Doğrulanmış transcript'ten tek kısa reaction text overlay; güvenli ASS katmanı title/subtitle ile ortaktır.
- Center/manual vertical 9:16 varyant.
- Party Lore candidate ve MemeEventV1 dönüşümü.
- Session compilation, max 5–8 clip.

### İleri sistem

- Güvenilir game telemetry connector'ları ve automatic candidate detection.
- Multimodal screenshot/frame/video anlayışı ve smart crop/object tracking.
- Laughter/reaction classifier ölçümlerle gerçekten faydalıysa.
- Resumable/chunked upload, object storage ve birden çok media worker host.
- Clip transitions, iki-pass compilation loudness ve kontrollü background music.

### Kapsam dışı

- Tam non-linear video editor, timeline katman sistemi ve Premiere alternatifi.
- Sürekli cloud screen/audio capture veya gizli kayıt.
- Yüz tanıma, voiceprint ile oyuncu kimliği, duygu/psikoloji çıkarımı.
- Public streaming moderation, otomatik viral scoring veya sosyal feed.
- MVP'de video üretici model, cinematic effect, face swap veya AI avatar.
- Orijinal kaydı onaysız Party Lore/Meme/Discord'a gönderme.

## 3. Ingestion mimarisi

### Upload MP4/MKV

API önce metadata/declared SHA ile `AWAITING_UPLOAD` recording açar. Client aynı-origin, süreli content URL'ye
tek streamed `PUT` yapar; backend body'yi RAM'e almadan `.part` dosyasına yazar, Content-Length/1 GiB limitini
uygular ve hash hesaplar. Complete çağrısında size/hash eşleşirse atomik rename + PROBE job olur. LAN'daki
30–90 saniyelik replay için yeterlidir; vNext resumable chunks.

Client MIME güvenilir değildir. FFprobe allowlist, süre, stream, çözünürlük ve codec doğrulamasından sonra
`READY` olur. Normal web attachment endpoint'i 25 MB limitli ve server-scoped media lifecycle taşımadığı için
recording upload'da kullanılmaz.

### OBS Replay Buffer

MVP'de OBS entegrasyonu yoktur; OBS file normal upload'dır, source type/profil metadata'sı eklenir. Server yerel
OBS klasör path'ini veya credential'ını saklamaz. Desktop helper sonraki sürümde folder watch ile yeni dosyayı
görüp source metadata, capture clock ve marker ID ile yükleyebilir.

OBS için MP4 yanında MKV kabul edilmesi pratiktir: yarım kalan kayıtta daha dayanıklıdır. Output her zaman MP4'tür.
Remux'u OBS yapabilir veya media worker decode/re-encode eder.

### Discord screen recording

Dosya önce Discord adapter tarafından indirilip aynı upload API'sine service credential ile aktarılır. Dış URL
FFmpeg'e verilmez; SSRF önlemek için downloader ayrı allowlist/size/timeout uygular. MVP'de kullanıcı dosyayı
web'den yükleyebilir, adapter sonra gelir.

### Manuel timestamp ve live marker

- Dosya biliniyorsa `offset_ms` otoritedir.
- Live command yalnız `occurred_at` taşır. Recording'in `capture_started_at` değeriyle offset hesaplanır.
- İkisi varsa fark `<=2 saniye` olmalı; aksi hâlde kullanıcı timeline'da düzeltir.
- Marker event ID idempotenttir; aynı Commentator/Discord retry duplicate yaratmaz.

### Audio transcript

Audio-only upload transcript ve aday metadata üretebilir ama video clip çıkaramaz. Video input'un audio'su
transcript için mono 16 kHz WAV'a geçici çıkarılır. STT/raw transcript otomatik highlight için sonraki sürümdür;
MVP marker notu LLM metadata için yeterlidir.

### Event marker ve gelecek telemetry

AI Commentator, Meme/Highlight ortak event ID'sini ve normalized category/priority/participants/occurredAt'i
gönderir. Game connector yalnız güvenilir timestamp+event severity sağlar; doğrudan FFmpeg argümanı veya lore
yazısı üretmez. Bütün kaynaklar [media-contract.ts](media-contract.ts) sözleşmesine normalize edilir.

## 4. Highlight scoring

### Sinyaller

- `manual_marker`: kullanıcının bilinçli işareti; 0/1.
- `commentator_priority`: Commentator deterministic event priority, 0..1.
- `game_event_severity`: connector'ın allowlist event severity'si.
- `reaction_intensity`: doğrulanmış transcript/energy/event reaction gücü; absolute ses değil session baseline.
- `multiple_players_reacting`: doğrulanmış farklı player sayısı / 3; mixed speaker'da kimliksiz tepki sayısı kullanılır.
- `laughter_confidence`: STT/audio classifier sinyali; tek başına highlight yaratmaz.
- `voice_volume_spike`: median/RMS baseline'a göre kısa yükseliş; bağırma/öfke olarak yorumlanmaz.
- `repeated_phrase`: aynı kısa sözün yakın window'da tekrarı; transcription confidence ile ağırlanır.
- `sudden_silence`: yüksek tepkinin ardından belirgin sessizlik; konuşmama tek başına sinyal değildir.
- `lore_similarity`: yalnız HIGHLIGHT/kanıt kullanımına izinli lore retrieval skoru.
- `uniqueness`: recent marker/event/clip'lere benzememe.
- `duration_suitability`: önerilen window 8–45 saniyeyse 1, sınıra yaklaştıkça azalır.

### Deterministik formül

```text
positive = 0.20*manual_marker
         + 0.12*commentator_priority
         + 0.12*game_event_severity
         + 0.10*reaction_intensity
         + 0.09*multiple_players_reacting
         + 0.08*laughter_confidence
         + 0.06*voice_volume_spike
         + 0.04*repeated_phrase
         + 0.04*sudden_silence
         + 0.06*lore_similarity
         + 0.06*uniqueness
         + 0.03*duration_suitability

penalty  = 0.20*confidence_penalty
         + 0.25*duplicate_penalty
         + 0.40*privacy_or_conflict_penalty
         + 0.15*invalid_duration_penalty
         + 0.15*overused_similar_clip_penalty

score = clamp(positive - penalty, 0, 1)
```

Automatic threshold `.62`. Manual marker hard safety geçiyorsa `.45` ile review'a alınabilir; kullanıcı niyeti
başka sinyal yokken düşük score'u gizlemez. MVP'de mevcut olmayan audio/telemetry sinyali `0`dır, uydurulmaz.
Manual candidate sıralamasında marker niyeti ayrıca tie-break'tir.

LLM'nin uygun olduğu yer: kategori/başlık/açıklama, transcript içinden açık setup/payoff sınıflandırma, en fazla
±5 saniye trim önerisi, lore/meme candidate önerisi ve compilation order. Uygun olmadığı yer: byte/codec probe,
gerçek timestamps, RMS/loudness, oyuncu kimliği, izin, duplicate, süre sınırı ve FFmpeg komutu.

## 5. Clip extraction

Tam pipeline, güvenlik kuralları ve örnek komutlar: [ffmpeg-pipeline.md](ffmpeg-pipeline.md).

Özet kararlar:

- Category padding: skill `-8/+5`, comedy/chaos `-12/+8`, failure `-10/+7`, lore `-12/+8` saniye.
- Window source duration'a clamp; hedef 8–45, hard max 60 saniye.
- Kullanıcıya sunulan bütün clip'ler keyframe bağımsız doğru başlangıç ve ortak codec için re-encode.
- H.264 `libx264`, AAC, `yuv420p`, `+faststart`; CRF 22 master, vertical CRF 23.
- Audio varsa one-pass loudnorm `I=-16/LRA=11/TP=-1.5`; compilation'da opsiyonel two-pass.
- Subtitle/intro title güvenli ASS+libass; raw text filter argümanına girmez.
- Landscape max 1920×1080/source size; vertical 1080×1920 center/manual crop.
- Thumbnail clip orta noktasında 640px JPEG; black-frame seçim iyileştirmesi sonra.
- Master CRF; delivery limitine göre ayrı bitrate varyantı. Servis upload limitleri kodda sabit değildir.
- Final output FFprobe + SHA doğrulandıktan sonra `.part` atomik rename edilir.

## 6. Transcript analizi

### Pipeline

1. FFmpeg video audio'sunu mono 16 kHz PCM WAV'a çıkarır; hash/recording ID ile geçici asset.
2. Speech-to-text adapter `tr` dili ve segment timestamps ile sonuç üretir.
3. Speaker labeling yalnız ayrı OBS audio track → player mapping varsa güvenilir kabul edilir.
4. Segment text + audio features; laughter/shout/repeated phrase/sudden silence yalnız confidence sinyalidir.
5. 10–30 saniyelik overlapping window'larda reaction/marker/game signals birleştirilir.
6. Deterministik threshold sonrası LLM category/title/description ve küçük trim önerisi yapar.
7. Backend segment timestamps'i recording duration'a, monotonic sıraya ve minimum süreye karşı doğrular.

### Üç arkadaşta diarization sınırı

Üç kişi olması diarization'ı otomatik güvenilir yapmaz. Discord/game audio miksinde aynı anda konuşma, benzer
mikrofon kalitesi, compression ve oyun sesi speaker cluster'larını bozar. Cluster “Speaker A” olabilir ama bunun
Mert olduğuna dair kanıt değildir. Voice embedding/voiceprint hassas biyometrik veri ve MVP dışıdır.

Tercih sırası:

1. OBS'de her mikrofon/Discord source ayrı audio track ve source ayarında explicit player mapping.
2. Mixed track'te `Speaker A/B/C/UNKNOWN`; UI oyuncuya isteğe bağlı mapping onayı verir.
3. Mapping onaysızsa transcript segment `player_id=null`; LLM target/lore participant tahmin edemez.

STT hataları, küfür/oyun özel adı ve Türkçe ekler için kaçınılmazdır. Subtitle cleanup yalnız noktalama/dolgu/
okunabilirlik düzeltir; bilinmeyen sözü yaratıcı biçimde tamamlamaz. Ham WAV başarılı transcript sonrası silinir;
raw transcript 30 gün, saved highlight subtitle snapshot'ı artifact'le birlikte kalabilir.

## 7. AI prompt tasarımı

Altı production-ready JSON prompt: [prompts.md](prompts.md).

- Worthiness + kategori + sınırlı trim offset
- Başlık + tek satır açıklama
- Subtitle cleanup
- Kullanıcı onaylı Party Lore aday önerisi
- MemeEventV1 aday dönüşümü
- Session compilation ordering

MVP'de çoğunlukla tek metadata çağrısı yeterlidir. Worthiness deterministic olduğundan açık manuel marker'da
ayrı worthiness LLM çağrısı gerekmeyebilir; metadata promptu kullanılır. Transcript, lore ve compilation promptları
ilgili faz gelmeden çalışmaz.

Model output hiçbir zaman raw FFmpeg parametresi olmaz. Timestamp, ID, player, lore, sayı ve alıntı input allowlist
ile doğrulanır. Video byte/frame MVP'de modele gönderilmez. Prompt/model değişimi job metadata'da sürümlenir.

## 8. Veri modeli

PostgreSQL referans şeması: [schema.sql](schema.sql).

| Tablo | Amaç |
|---|---|
| `recording_sources` | Player'a bağlı manuel/OBS/Discord/audio source, consent ve güvenli ayarlar |
| `recordings` | Upload/hash/probe/stream metadata, capture clock, storage ve retention |
| `event_markers` | Relative/wall-clock marker, source/priority/participants ve idempotency |
| `transcripts` | Provider/model/language/status/full text ve diarization mode |
| `transcript_segments` | Timestamp text, confirmed speaker mapping, confidence ve reaction flags |
| `highlight_candidates` | Window/anchor/score/category/title/description/signals ve integration flags |
| `rendered_highlights` | MP4/thumbnail metadata, variant, render params/version, delivery/save/delete |
| `highlight_feedback` | Oyuncu başına güncellenebilir trim/quality/save feedback |
| `highlight_lore_links` | Var olan lore reference/source-evidence bağlantısı |
| `processing_jobs` | Stage DAG, params hash, lease/heartbeat/retry/progress/error |

`players` ve `lore_entries` Party Lore ortak alanından gelir. Lore migration yoksa `highlight_lore_links` Phase 5'te
eklenir. `session_id` şimdilik ortak opaque UUID'dir; ileride tek `game_sessions` bounded context'i Commentator,
Meme ve Highlight için canonical session olur.

## 9. Job sistemi

### Redis gerekli mi?

Hayır. Bir server, üç oyuncu ve tek media worker için PostgreSQL `FOR UPDATE SKIP LOCKED`, lease ve heartbeat
yeterlidir; repo mevcut AI worker'ında bu pattern'i kullanıyor. Video job'ları ayrı `processing_jobs` tablosu/
worker process'inde olmalı. Redis ancak birden fazla worker host, yüzlerce job, DB polling baskısı veya priority/
pubsub ihtiyacı ölçülürse eklenir.

### Stage DAG

```text
UPLOAD -> PROBE -> [EXTRACT_AUDIO -> TRANSCRIBE] -> ANALYZE
                                      |
candidate approved -> TRIM -> [SUBTITLE] -> RENDER -> THUMBNAIL -> DELIVER
session candidates -------------------------------------------> compilation RENDER
```

Upload API'nin streaming state'idir; worker byte indirmez. PROBE başarılı olmadan başka stage yok. Subtitle
kapalıysa stage atlanır. TRIM+RENDER tek FFmpeg pass olabilir; stage'ler denetim/progress için mantıksal ayrıdır.

### Retry kuralları

| Stage | Max | Retry | Retry yapılmayan hata |
|---|---:|---|---|
| UPLOAD | client 3 | bağlantı kesilmesi; vNext resume | hash/size/limit uyuşmazlığı |
| PROBE | 2 | geçici I/O/process crash | bozuk/unsupported codec, limit |
| EXTRACT_AUDIO | 2 | worker crash/geçici disk | audio stream yok/bozuk |
| TRANSCRIBE | 3 | provider 429/5xx/timeout, exponential | invalid audio, auth/config |
| ANALYZE | 2 | provider geçici hata; schema invalid bir retry | privacy/insufficient input |
| TRIM/SUBTITLE/RENDER | 2 | worker crash/geçici disk | invalid timestamp/filter/font/input |
| THUMBNAIL | 2 | process crash | video stream yok |
| DELIVER | 5 | 429/5xx/timeout + Retry-After | 4xx permission/size policy |
| DELETE | 5 | file lock/geçici disk | storage key invariant ihlali alarmdır |

Idempotency key: `stage + input_sha256 + canonical_parameters_hash + tool/render/prompt_version`.
SUCCEEDED output aynı key'de reuse edilir. Her output `.part`, doğrula, atomik rename, sonra DB. Lease varsayılanı
PROBE 2 dk, render 15 dk, transcribe 30 dk; worker 10 saniyede heartbeat verir. Expired lease başka worker tarafından
claim edilir. Fencing kontrolü olmadan eski worker completion yazamaz.

Cancel, queued işi doğrudan CANCELLED; çalışan FFmpeg'e terminate, 10 saniye sonra kill gönderir. Orphan `.part`
dosyaları 24 saat sonra temizlenir. Worker concurrency başlangıçta 1; aynı volume'u mount eden backend yalnız
private download ve upload yapar, FFmpeg çalıştırmaz.

## 10. API tasarımı

TypeScript request/response contract: [api-contract.ts](api-contract.ts).

| Method ve yol | Amaç | Başarı |
|---|---|---|
| `POST /servers/{serverId}/highlight-recordings` | Upload metadata/init | `201 RecordingUploadTarget` |
| `PUT /highlight-recordings/{id}/content` | Süreli token ile streamed byte | `204` |
| `POST /highlight-recordings/{id}/complete` | Hash/size doğrula, PROBE kuyruğa | `202 ProcessingJob` |
| `POST /highlight-recordings/{id}/markers` | Relative/live marker | `201` veya idempotent `200` |
| `POST /highlight-recordings/{id}/analyze` | Marker/transcript candidate işleri | `202` |
| `GET /highlight-candidates/{id}` | Candidate/trim/transcript preview | `200` |
| `POST /highlight-candidates/{id}/render` | Seçilen trim/variant | `202 ProcessingJob` |
| `PATCH /highlight-candidates/{id}/trim` | Start/end değiştir | `200` yeni candidate version/snapshot |
| `POST /highlights/{id}/vertical` | Master'dan 9:16 varyant | `202` |
| `PUT /highlights/{id}/feedback` | Feedback upsert | `200` |
| `POST /servers/{serverId}/highlight-compilations` | Session clip listesi render | `202` |
| `GET /processing-jobs/{id}` | Progress/error/sonuç | `200` |
| `POST /processing-jobs/{id}/cancel` | Kuyruk/process iptal | `202` |
| `GET /servers/{serverId}/highlight-assets/{id}` | Auth'lu MP4/thumbnail, range destekli | media |
| `DELETE /highlight-recordings/{id}` | Original+türev/transcript sil | `202` |
| `DELETE /highlights/{id}` | Rendered artifact sil | `202` |

`PUT content` token recording/user/server/size/expiry'ye bağlıdır ve Authorization header gerektirir; arbitrary
storage path taşımaz. Byte upload p95 için reverse proxy request timeout/body limiti highlight path'e özel ayarlanır.
MVP tek PUT'tur; resume gereksinimi ölçülürse `Content-Range`/multipart session eklenir.

Asset GET, MP4 seek için `Range`/206 ve `Accept-Ranges: bytes` desteklemelidir. Server üyeliği ve status her istekte
kontrol edilir; hash tahmini IDOR izni vermez. Download URL kısa süreli application URL olabilir, public filesystem
path değildir.

Trim patch, önceki render'ı mutate etmez; aynı candidate üzerinde version/parameters hash değişir ve yeni render
job olur. Vertical, subtitle'sız master'dan türetilir; landscape burned subtitle'ı crop etmez.

## 11. Storage stratejisi

### MVP local disk

```text
/srv/highlight-media/
  originals/<server-id>/<prefix>/<recording-uuid>.input
  derived/<server-id>/<prefix>/<highlight-uuid>.mp4
  thumbnails/<server-id>/<prefix>/<highlight-uuid>.jpg
  transcripts/<server-id>/<prefix>/<transcript-uuid>.json
  work/<job-uuid>/*.part
```

İsimler UUID'dir; user filename yalnız metadata'da kalır. Path backend tarafından resolve edilip root içinde olduğu
doğrulanır. Symlink izlenmez. Ayrı persistent Docker volume kullanılır; `/tmp` büyük video için kullanılmaz.

### Limit ve quota

- Tek input 1 GiB, 15 dakika, 8K/240 FPS probe hard limit; ürün hedefi 30–90 saniye replay.
- Server toplam original+derived soft quota 20 GiB; UI kullanım/retention gösterir.
- Candidate hard max 60 saniye; compilation 8 clip/90 saniye; rendered master max configurable 500 MB.
- Adapter-specific delivery limit env/config ve provider response'tan gelir; sabit Discord limiti kodlanmaz.

### Retention

- AWAITING upload `.part`: 2 saat.
- Başarısız/intermediate work: 24 saat.
- Original: varsayılan 14 gün; başarılı render'dan sonra kullanıcı isterse 7 güne kısaltabilir.
- Raw extracted WAV: transcript sonrası hemen, en geç 24 saat.
- Raw transcript: 30 gün; saved subtitle snapshot artifact retention'ıyla.
- Rendered highlight: 90 gün; `SAVE` kullanıcı silene kadar.
- Thumbnail highlight ile aynı lifecycle.

Delete, API erişimini anında kapatır, queued/running job'ı iptal eder, sonra bytes ve transcript fiziksel silinir.
Matrix/Discord'a önceden yüklenen dış kopyanın silinmesi provider yeteneğine bağlıdır ve UI açıklar. Party Lore
evidence link'i silinen clip'i oynatamaz; lore kaydının metni ayrı consent/silme politikasına göre yönetilir.

SHA-256 server içinde duplicate upload'ı bulur. Doğrulanmış aynı file tekrar yüklenirse mevcut recording dönebilir;
farklı session marker'ları aynı recording'e eklenir. CDN/object storage üç kullanıcıda gerekmez. İkinci host veya
disk kapasitesi ihtiyacı oluşursa storage adapter S3-compatible object store'a geçer; DB storage key değişmez.

## 12. Entegrasyonlar

### AI Commentator

Commentator high-priority event'i `external_marker_id`, occurredAt, participants, category ve deterministic priority
ile gönderir. Highlight event'i kaydeder ama recording yoksa bekleyen live marker olarak session düzeyinde tutulması
gerekir; MVP'de recording seçildikten sonra marker eklenir, sonraki shared `game_sessions` fazı correlation'ı çözer.
Commentator text'i transcript kanıtı değildir ve clip'e zorla eklenmez.

### Meme Generator

Kullanıcı “Meme yap” dediğinde doğrulanmış highlight event/marker/transcript facts, source=`HIGHLIGHT` ile
`MemeEventV1`e çevrilir. Anchor thumbnail/frame server-owned screenshot asset olarak içe alınır. Meme Generator
yeniden worthiness/consent/template kontrolü yapar; highlight flag otomatik render izni değildir.

### Party Lore

Lore similarity scoring yalnız izinli existing lore ile callback/uniqueness sinyalidir. Yeni Party Lore entry için
highlight prompt yalnız candidate önerir; kullanıcı özet/katılımcı/kanıtı görüp onaylarsa Party Lore raw event/
candidate API çağrılır. Rendered highlight `SOURCE_EVIDENCE` link'i olur. Clip silinirse evidence unavailable işaretlenir;
lore uydurulmaz veya otomatik silinmez.

### Discord/Matrix

MVP web ve mevcut Matrix altyapısı. Discord bot marker yaratabilir, küçük output'u upload eder veya auth'lu kısa ömürlü
link yollar. Provider rate/size error için delivery retry ve gerekiyorsa ayrı küçültülmüş varyant. Aynı idempotency key
duplicate mesaj yaratmaz. Discord bot kullanıcının yerel OBS dosyasına erişemez.

### AI Gateway

Gateway'e video değil, sınırlı JSON facts ve en fazla ilgili transcript segmentleri gider. Logical profiles:
`highlight-metadata`, `highlight-compilation`, ileride `speech-to-text`. Mevcut Gateway yalnız chat/Ollama proxy olduğu
için STT ve gerçek profile routing önce Gateway capability olarak eklenmelidir. Provider model/prompt/token/latency
job metadata'da tutulur; model değişimi FFmpeg output sözleşmesini değiştirmez.

## 13. Solo geliştirici yol haritası

### Phase 0 — FFmpeg/storage spike

- Kapsam: pinned FFmpeg media-worker image, fixture probe/trim/thumbnail, volume ve subprocess güvenliği.
- Görevler: Dockerfile, network none, non-root, CPU/RAM; ffprobe parser; exact trim; `.part` rename.
- Definition of done: 10 codec/çözünürlük fixture'ı, 20 timestamp boundary, corrupt/timeout güvenli davranır.
- Risk: codec/HDR/font/libass image farkları.
- Ertele: API, LLM, transcript, vertical.

### Phase 1 — Manual marker MVP

- Kapsam: kısa MP4/MKV upload, tek marker, fixed category padding, candidate approve/render.
- Görevler: temel recording/marker/candidate/render/job modelleri, streamed upload, worker lease, private asset GET.
- Definition of done: üç kullanıcı aynı server'da upload→marker→MP4→thumbnail yapar; başka server okuyamaz.
- Test: IDOR, hash/idempotency, invalid duration, marker 0/end sınırları.
- Ertele: title LLM, transcript, compilation.

### Phase 2 — Upload ve trim deneyimi

- Kapsam: timeline preview, trim handles, progress/cancel, Matrix delivery, feedback/retention.
- Görevler: Range GET, low-res preview, exact re-render, loudnorm, title overlay, cleanup/quota UI.
- Definition of done: kullanıcı 8–45 sn clip'i ayarlar; stale render mutate olmaz; output mobile/web okunur.
- Test: keyframe olmayan marker, audio yok, portrait/4K, büyük upload, concurrent cancel/delete.
- Ertele: resumable chunks ölçülene kadar.

### Phase 3 — Transcript desteği

- Kapsam: audio extract, STT adapter, Turkish segments, subtitle preview/burn-in; speaker UNKNOWN/separate tracks.
- Görevler: transcript tabloları/jobs, Gateway STT capability, cleanup prompt, ASS renderer.
- Definition of done: Türkçe timestamps monotonic, wrong player mapping 0, subtitles taşmadan iki satır.
- Test: mixed speech, game noise, profanity policy, overlapping segments, STT/provider timeout.
- Ertele: voiceprint/automatic identity/laughter model.

### Phase 4 — Automatic candidate detection

- Kapsam: Commentator markers, reaction/audio/telemetry signals, threshold/dedup/session cap.
- Görevler: signal extractor, scoring, 30-sec merge, uniqueness, review queue.
- Definition of done: golden session replay top-3 recall >= %80, weak auto candidate oranı < %20, auto render 0.
- Test: no-signal, repeated deaths, loud game audio, simultaneous markers, conflict privacy veto.
- Ertele: multimodal raw video model.

### Phase 5 — Lore ve Meme entegrasyonu

- Kapsam: lore similarity/candidate confirmation/evidence, MemeEventV1+frame handoff.
- Görevler: consent/usage, source link, deletion propagation, explicit user actions.
- Definition of done: forbidden lore leakage 0; highlight tek tıkla preview Meme job'a gider; otomatik lore 0.
- Test: deleted/restricted lore, wrong participant, clip deletion, duplicate Party Lore candidate.
- Ertele: automatic cross-module publishing.

### Phase 6 — Compilation generation

- Kapsam: en fazla 8 clip/90 sn, diversity/order, normalization/concat, opsiyonel title card.
- Görevler: session selector, compilation prompt+validator, normalized intermediates, two-pass loudness opsiyonu.
- Definition of done: aynı template/oyuncu/category yığılmaz, izin dışı clip yok, bütün concat fixture'ları oynar.
- Test: farklı FPS/resolution/audio, missing audio, total duration, cancelled child job, duplicate order IDs.
- Ertele: crossfade/music/beat sync/full editor.

## 14. Test stratejisi

- FFmpeg command: argv snapshot (shell string değil), tool version fixture, expected codec/pixfmt/faststart/probe.
- Timestamp boundary: marker 0, son frame, pre/post clamp, exact non-keyframe, 1 ms/60 s sınırı, invalid end<=start.
- Corrupt video: truncated MP4, fake MIME, external protocol, decompression/resource bomb, zero stream/duration.
- Large file: declared/actual >1 GiB, disk quota, upload disconnect, `.part` cleanup, hash mismatch.
- Subtitle overflow: Türkçe `İ/ı/ğ/ş/ç/ö/ü`, 84/85 char, iki satır, long token, overlapping segments, ASS escaping.
- Turkish transcript: oyun terimi, ekler, noktalama, `[anlaşılmadı]`, profanity policy ve timestamp preservation.
- Duplicate jobs: upload complete retry, marker retry, same parameters reuse, render version değişiminde yeni output.
- Wrong clip selection: 60 sentetik marker/session golden set, expected window/category/top candidates.
- Job/lease: expired worker, heartbeat fencing, cancel/kill, transient retry, validation no-retry, orphan cleanup.
- Storage/auth: Range/206, cross-server IDOR, deleted status, path traversal/symlink, retention and external delivery caveat.
- Audio: no audio, mono/stereo, separate tracks, loudness clipping, mixed speaker identity null.
- Integration: Commentator wall-clock correlation, Meme event allowlist, Party Lore explicit confirm, Matrix/Discord idempotency.

FFmpeg integration testleri synthetic ve küçük fixture üretir; telifli gerçek oyun videosu repoya konmaz. CI hızlı
unit/probe fixture'larını çalıştırır; 4K/long/transcription benchmark nightly/manual olabilir. FFmpeg image digest ve
font sürümü sabitlenir; golden thumbnail/frame farkı perceptual hash toleransıyla ölçülür.

Yayın hedefleri:

- Corrupt/unsupported input'ın worker crash ettirmesi: 0.
- Cross-server media erişimi: 0.
- Marker window dışı yanlış clip: golden sette 0 kritik; top-3 automatic recall >= %80 Phase 4.
- Subtitle timestamp/player uydurması: 0.
- 60 sn 1080p render p95: production CPU'da gerçek-time'ın <=2 katı hedef; ölçülmeden garanti edilmez.
- Başarılı output probe/playback: %100 fixture.

## 15. Nihai teslimler

### MVP mimarisi

```text
OBS/local recorder -- hotkey saves 30–90s file
          |
Frontend/Desktop -> streamed Highlight Upload API
          |                 |
          |           PostgreSQL metadata/jobs
          |                 |
      private media volume <- media-worker (FFprobe/FFmpeg, concurrency 1)
                                    |
                         marker + deterministic scoring
                                    |
                    AI Gateway highlight-metadata (JSON only)
                                    |
                         candidate trim approval
                                    |
                  H.264/AAC MP4 + thumbnail -> web/Matrix
                                    |
                 explicit Meme / Party Lore / compilation actions
```

### İlk 10 uygulama görevi

1. Pinned FFmpeg/FFprobe ve Noto Sans/libass içeren network'süz `media-worker` Docker image'ını oluştur.
2. `backend/app/highlights/` paketini, storage root resolver'ı ve subprocess argv/timeout güvenlik katmanını yaz.
3. Recording/source modelleri + Alembic migration ve 1 GiB streamed init/content/complete upload akışını ekle.
4. FFprobe JSON parser/allowlist'i, SHA-256 doğrulama, duration/codec/dimension status ve invalid cleanup'ı yaz.
5. Event marker/candidate modellerini ve category padding + deterministic score/dedup fonksiyonlarını ekle.
6. PostgreSQL `processing_jobs` claim/lease/heartbeat/fencing/cancel worker altyapısını kur.
7. Accurate landscape trim, optional audio loudnorm, output probe/hash/atomic publish ve thumbnail stage'lerini ekle.
8. Candidate preview/trim/render/progress/private Range asset/delete API'lerini ve authorization testlerini tamamla.
9. Frontend upload, marker timeline, trim handles, preview, progress, feedback/save/delete panelini ekle.
10. `highlight-metadata` promptunu Gateway'e bağla, Matrix teslimini ve üç gerçek hesapla uçtan uca testi geçir.

### FFmpeg pipeline

[ffmpeg-pipeline.md](ffmpeg-pipeline.md): probe, exact re-encode trim, title/subtitle ASS, audio extraction/normalization,
vertical crop, thumbnail, compilation concat, size adaptation ve process güvenliği.

### TypeScript şemaları ve API

- [media-contract.ts](media-contract.ts)
- [api-contract.ts](api-contract.ts)

### Database ve promptlar

- [schema.sql](schema.sql)
- [prompts.md](prompts.md)

### Job queue tasarımı

PostgreSQL `SKIP LOCKED` + stage row + params hash + lease/heartbeat/fencing. Tek media worker, concurrency=1;
Redis yok. Stage retry tablosu Bölüm 9'dadır. API upload byte'ını stream eder, worker probe/render yapar, AI Gateway
yalnız metadata/transcript JSON'u işler.

### Üç uçtan uca örnek

#### Örnek A — OBS comedy failure

1. Emir OBS hotkey ile 75 sn MKV replay kaydeder, Nexus'a yükler; hash/probe READY, duration `75.000`.
2. Timeline'da `62.000` ms marker ve “10 dk hazırlıktan sonra ilk engelde düştü” notu koyar.
3. Manual + setup/payoff + uniqueness score `.71`; COMEDY/FAILURE candidate window `50.000–70.000`.
4. Metadata: “Planın 4 Saniyelik Ömrü”; açıklama yalnız marker olgusunu kullanır.
5. Emir start'ı `48.500`e çeker; backend clamp/validate, FFmpeg 21.5 sn MP4+thumbnail üretir.
6. Kullanıcı kaydeder, Matrix'e yollar. “Meme yap” explicit aksiyonu source=HIGHLIGHT MemeEvent job açar.
7. “Party Lore adayı” seçilirse highlight evidence ile confirm queue; otomatik lore yazılmaz.

#### Örnek B — Commentator skill marker ve vertical

1. Aylin'in tek canla kazandığı event, Commentator'dan occurredAt/priority `.92` ile gelir.
2. Sonradan capture clock metadata'lı 90 sn MP4 yüklenir; wall clock marker offset `68.400` ms olur.
3. Skill + game severity + commentator + uniqueness skoru `.82`; window `60.400–73.400`.
4. “Tek Canlık Savunma” metadata'sı, lore kullanmadan üretilir; başarı target roast değildir.
5. Landscape master oluşur. Aylin manual crop preview ile 9:16 varyant ister; subtitle'sız master'dan render edilir.
6. Discord adapter limiti master'a yetmezse ayrı delivery variant üretir; master saklanır.

#### Örnek C — Transcript, yanlış speaker'dan kaçınma ve compilation

1. Üç arkadaşın Discord/game sesi tek mixed track'tedir. STT üç tepki segmenti bulur ama speaker mapping `UNKNOWN`.
2. Sistem çoklu tepki/laughter sinyali kullanabilir; hiçbir segmenti oyuncuya atamaz, targeted lore/meme oluşturmaz.
3. Kullanıcı marker'ı onaylar ve başlığı “Üçlü Kaos” olarak düzeltir; subtitle speaker etiketi göstermez.
4. Session sonunda bu clip, bir skill ve bir comedy clip compilation'a adaydır; restricted dördüncü clip hard filter'da çıkar.
5. Compilation model yalnız üç eligible ID sırası önerir; backend toplam 58 sn ve diversity'yi doğrular.
6. Normalized clip'ler concat edilir, tek thumbnail üretilir; mixed speaker bilgisi Lore'a aktarılmaz.

### Ertelenecek özellikler

- Sürekli kayıt/screen capture, Nexus'un kendi replay buffer implementation'ı.
- Resumable upload/object storage/CDN; tek PUT/LAN ölçülene dek.
- Automatic speaker identity, voiceprint, face recognition ve emotion inference.
- Laughter modelini varsayılan karar verici yapmak.
- Raw videoyu multimodal modele göndermek ve full-session video analysis.
- Smart vertical crop/object tracking, cinematic transition, music/beat sync.
- Full video editor, katmanlı timeline ve frame-level UI.
- Otomatik Party Lore/Meme/Discord yayınlama.
- Redis/Kafka veya birden fazla worker host; ölçülen ihtiyaç gelene dek.
- AI-generated intro/video effect ve public/social highlight feed.

## Model ve deployment notu

Yeni LLM `highlight-metadata` golden setinde strict JSON `>=%99,5`, invented event/player/number/quote `0`, Türkçe
başlık rubric `>=%85` ve p95 metadata yanıtı `<=4 saniye` eşiğini geçmelidir. STT ayrı capability/benchmark'tır;
chat modelin güçlü olması transcript çözebildiği anlamına gelmez.

Media worker image'ı backend'den ayrıdır: FFmpeg paket boyutu ve codec surface Core API'ye eklenmez. Compose'a
`highlight_media` volume, storage-init chown, `media-worker` service ve gerekirse upload path proxy timeout ayarı
eklenir. Production gerçek CPU/disk benchmark'ı yapılmadan concurrency veya süre garantisi yükseltilmez.

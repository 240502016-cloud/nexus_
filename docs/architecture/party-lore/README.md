# Party Lore — ürün ve teknik tasarım

Durum: uygulama öncesi referans tasarım  
Hedef: Nexus içindeki üç kişilik özel oyun grubunun uzun dönemli, izinli ve kanıtlı hafızası  
Teknoloji uyumu: mevcut FastAPI/SQLAlchemy/Alembic backend, PostgreSQL 16 ve AI Gateway/Ollama

## Karar özeti

Party Lore bir sohbet arşivi veya gözetim sistemi değildir. Yalnızca oyuncunun bilerek gönderdiği
bir notu ya da oyun modülünün açık, güvenli ve kayda değer olayını işler. Ham içerik kısa ömürlüdür;
kalıcı değer, kanıt bağlantısı taşıyan kısa ve düzenlenebilir lore kaydındadır.

Bu yetenek `plugins/` altında sıradan bir plugin olarak değil,
`backend/app/party_lore/` altında ortak bir backend alanı olarak kurulmalıdır. Böylece AI Commentator,
Meme Generator ve diğer modüller aynı izin, cooldown, silme ve denetim kurallarını atlayamaz. Pluginler
veritabanına doğrudan erişmez; dar kapsamlı retrieval ve usage API'sini kullanır.

İlk sürümde otomatik sohbet dinleme, otomatik pattern üretme ve embedding yoktur. Manuel lore girişi,
aday onayı, PostgreSQL full-text arama, deterministik filtreleme ve kullanım kaydı yeterlidir. Bu,
tek geliştirici için hem güvenli hem de gerçekçi başlangıçtır.

## 1. Ürün modeli

### Party Lore sayılan şeyler

Bir kayıt şu özelliklerden en az birini taşımalı ve oyun grubu bağlamında kalmalıdır:

- Aylar sonra da anlaşılabilecek belirgin bir olay, başarı veya başarısız strateji.
- Birden fazla kanıtla görülen tekrar eden oyun davranışı.
- Kökeni belli bir lakap, koşusu tükenmemiş bir şaka veya grup geleneği.
- Oyuncunun bilerek kaydettiği, alıntısı doğrulanabilen bir söz.
- Diğer modüllere yarar sağlayan, güvenli ve bağlama bağlı bir referans.
- Mizah sınırı veya oyuncu tercihi gibi eğlenceyi güvenli tutan, sahibi tarafından onaylanmış bilgi.

Her lore şu soruya cevap verebilmelidir: “Bunu hangi kanıtla biliyoruz, kime ait, nerede
kullanabiliriz ve son kez ne zaman kullandık?”

### Otomatik olarak asla lore olmaması gerekenler

- Normal kanal konuşmaları, selamlaşmalar ve günlük sohbet.
- Geçici öfke, maç sonu siniri veya tek seferlik önemsiz hata.
- Gerçek hayat sırları ve oyun grubuyla ilgisiz bilgiler.
- Parola, adres, finansal/tıbbi veri, korunan özellik veya özel hayat bilgisi.
- Kaynağı olmayan iddia, duyum, çıkarım veya modelin tamamladığı ayrıntı.
- Bilerek `/lore-ekle` benzeri bir işlemle gönderilmemiş Discord/Matrix mesajı.
- Oyuncu kimliği belirsiz olay.
- Bir oyuncuyu küçük düşürme değeri dışında kalıcı değeri olmayan içerik.

### Dört veri seviyesi

| Seviye | Anlam | Kalıcılık | LLM'nin rolü |
|---|---|---|---|
| Raw event | Manuel not veya oyun modülünün sunduğu kaynak olay | Varsayılan 30 gün; reddedilirse erken temizlenir | Sınıflandırma girdisi |
| Candidate memory | Henüz lore olmayan yapılandırılmış öneri | 30 gün inceleme süresi | Başlık, özet, kategori ve puan önerir |
| Confirmed lore | Kanıtı, kapsamı ve izin durumu doğrulanmış kayıt | Aktif/arsiv/silme politikasına bağlı | Saklama kararı vermez; backend/onay verir |
| Recurring pattern | En az 3 ayrı olay veya oyuncu onayıyla kanıtlanmış örüntü | Kanıt geldikçe güçlenir; aksi halde zayıflar | Benzer olayları önerebilir; deterministik eşik/onay kesinleştirir |

`AUTO_ALLOWED`, “model doğru söyledi” anlamına gelmez. Yalnızca düşük hassasiyetli, oyun içi ve
yüksek güvenli sınırlı kategorilerin kullanıcı onayı beklemeden aktifleşebileceğini belirtir.

### Aylar içinde oluşan değer

İlk haftalarda sistem elle girilen “efsane anlar” için aranabilir bir defterdir. Sonraki aylarda
aynı hatanın veya şakanın farklı kanıtlarını birleştirir; hangi referansların hâlâ komik, hangilerinin
tükendiğini kullanım ve geri bildirimden öğrenir. Değer ham veri biriktirmekten değil, daha kısa ve
daha doğru bir kanonik hafıza üretmekten gelir.

### “Ürkütücü” hissettirmeme ilkeleri

- Varsayılan kaynak modeli opt-in'dir; kanal mesajları kendiliğinden taranmaz.
- Gönderim ekranında neyin saklanacağı ve ham verinin ne zaman silineceği gösterilir.
- Her kullanım `lore_usage_history` içinde görülebilir.
- Oyuncu kendi katıldığı kayıtları düzeltebilir, kısıtlayabilir ve silebilir.
- “Roast için izin” varsayılan olarak kapalıdır.
- Yasaklanan kayıt retrieval sonucuna hiç giremez; yalnızca prompta “kullanma” notu göndermek
  yeterli güvenlik sayılmaz.
- Ürün, “seni şöyle tanıyorum” yerine “şu oyun olayını hatırlıyoruz” dilini kullanır.

## 2. Hafıza yaşam döngüsü

| Adım | İşlem | Karar türü | Başarısızlık davranışı |
|---|---|---|---|
| 1 | Raw event alınır, kaynak ve idempotency doğrulanır | Deterministik | Geçersiz/yetkisiz kaynak 4xx |
| 2 | Aday yapı çıkarılır | LLM + JSON Schema | Gateway yoksa event `PENDING` kalır; lore yaratılmaz |
| 3 | Önem/güven puanı eşiklerle kontrol edilir | LLM önerisi + deterministik eşik | Eşiğin altı `REJECTED` |
| 4 | Aynı dış kimlik/hash, alias, FTS ve sonra embedding ile duplicate aranır | Deterministik + sıralama | Şüpheli eşleşme manuel kuyruğa |
| 5 | PII, hassasiyet, katılımcı ve modül izinleri kontrol edilir | Deterministik; LLM yalnız sınıflandırır | Yasak veri raw içerikle birlikte temizlenir |
| 6 | Otomatik kabul veya insan onayı seçilir | Deterministik politika | Belirsizlik her zaman onaya gider |
| 7 | Lore, katılımcı ve kanıtlar tek transaction ile yazılır | Deterministik | Kısmi kayıt yok; rollback |
| 8 | İstek bağlamında filtrelenir ve sıralanır | Deterministik retrieval | Uygun sonuç yoksa boş liste |
| 9 | Kullanım ve oyuncu geri bildirimi kaydedilir | Deterministik | Idempotent retry |
| 10 | Güçlendir, birleştir, arşivle veya sil | Zamanlanmış kurallar + insan onayı | Otomatik hard delete yalnız retention için |

### Önerilen eşikler

- Otomatik ret: `confidence < 0.65` veya `importance < 0.45`.
- Manuel inceleme: kalan bütün adaylar.
- Sınırlı otomatik kabul: `confidence >= 0.90`, `importance >= 0.70`, `LOW`, izinli kategori,
  doğrulanmış sistem kaynağı ve duplicate skoru `< 0.75`.
- Olası duplicate: `0.75–0.89`; otomatik merge yok.
- Kuvvetli duplicate: `>= 0.90`; yeni kayıt açmak yerine mevcut kayda kanıt ekleme önerisi.
- Recurring pattern: en az 3 farklı raw event, en az 2 ayrı oturum ve toplam güven `>= 0.85`;
  aksi halde onay gerekir.

### Zayıflama ve güçlenme

Haftalık bakım işi, pinlenmemiş kayıt için aşağıdakini hesaplar:

```text
age_days = today - max(canonical_event_date, created_at)
half_life = category_half_life_days
time_factor = 2 ^ (-age_days / half_life)
feedback_factor = clamp(1 + 0.08*positive - 0.15*negative, 0.4, 1.3)
evidence_factor = min(1.0, 0.55 + 0.15*distinct_evidence_count)
reference_strength = clamp(importance*0.50 + time_factor*0.20
                           + feedback_factor*0.15 + evidence_factor*0.15, 0, 1)
```

Sık kullanım tek başına güçlendirmez; aksi halde en çok kullanılan şaka sonsuza kadar baskın olur.
Yeni bağımsız kanıt ve olumlu geri bildirim güçlendirir. `reference_strength < 0.30` ve 90 gündür
kullanılmamış kayıt arşiv adayıdır; otomatik silinmez.

## 3. Lore taksonomisi

“Temel alanlar” her kategoride başlık, tek cümle özet, tarih, katılımcı, en az bir kanıt, güven,
önem, hassasiyet, izin, tag ve kaynak anlamına gelir.

| Kategori | Ek saklama gereksinimi | Retrieval davranışı | Süre/eskime | Onay |
|---|---|---|---|---|
| LEGENDARY_EVENT | Temel alanlar; mümkünse oturum/match id | Geniş çağrışım, recap/highlight önceliği | 730 gün yarı ömür; pinlenebilir | Güvenli sistem kaynağında hayır |
| REPEATED_FAILURE | En az 3 kanıt, 2 oturum | İlgili oyuncu+eylem birlikteyken | 180 gün; yeni kanıtla yenilenir | Evet |
| RECURRING_BEHAVIOR | Kanıt sayısı ve tarih aralığı | Yalnız güçlü participant overlap | 270 gün | Evet |
| NICKNAME_ORIGIN | Lakap alias'ı ve köken kanıtı | Lakap/arayan terimde yüksek lexical ağırlık | Kalıcı; kullanım izni değişebilir | Evet |
| QUOTE | Doğrulanmış exact excerpt, konuşan kişi | Exact/phrase eşleşmesinde; paraphrase edilmez | 365 gün | Evet |
| RIVALRY | İki veya daha çok katılımcı | Her iki taraf mevcutsa | 365 gün; itirazda durur | Evet, tüm özneler |
| ACHIEVEMENT | Oyun, başarı türü, sonuç | Recap/highlight ve aynı oyun bağlamı | 730 gün | Güvenli sistem kaynağında hayır |
| BETRAYAL | Tamamen oyun içi olduğuna dair kanıt | Hidden-role/story; roast varsayılan kapalı | 180 gün | Evet, tüm özneler |
| RUNNING_JOKE | Köken/ilişkili lore ve phrase ailesi | Cooldown ve overuse cezası yüksek | 90 gün; geri bildirimle uzar | Evet |
| GROUP_TRADITION | Tetikleyici/ritüel ve en az 2 örnek | Oturum başlangıcı/sonunda | 365 gün | Evet |
| FAILED_STRATEGY | Plan, oyun içi sonuç | Benzer oyun/olay türünde | 120 gün | LOW ve yüksek güvende hayır |
| UNEXPECTED_SUCCESS | Beklenti ve sonuç kanıtı | Highlight/recap; aynı oyun bağlamı | 365 gün | LOW ve yüksek güvende hayır |
| PLAYER_PREFERENCE | Tercihin sahibinden onay | Yalnız seçimi iyileştiren modülde | 180 günde yeniden sor | Her zaman |
| HUMOR_BOUNDARY | Sahibinin açık kuralı; hassas ayrıntı yazmadan | Pozitif lore değil, hard filter olarak | Süresiz; sahibi değiştirene dek | Her zaman |
| SESSION_REFERENCE | Session id ve kısa TTL | Yalnız aynı/yakın oturumda | 14 gün; sonra otomatik arşiv | LOW ise hayır |

“Betrayal” gerçek hayatta ihanet iddiası değildir; yalnız oyun içi rol/hamle anlamındadır. Özet bunu
açıkça söylemelidir.

## 4. Veri modeli

Referans DDL: [schema.sql](schema.sql)

Şemanın önemli kararları:

- Her kök kayıt `server_id` ile scope edilir; API her sorguda üyelik kontrolü yapar.
- `players`, mevcut `users` kaydının sunucuya özgü Party Lore kimliğidir. Tam üç aktif oyuncu
  ürün kuralıdır; veritabanı constraint'i değildir, böylece üye değişimi yönetilebilir.
- Raw event kalıcı arşiv değildir. İçerik için 30 günlük TTL ve SHA-256 idempotency hash'i vardır.
- Lore ile kaynak arasında `lore_evidence` bulunmadan aktif kayıt yaratılamaz; bu invariant servis
  transaction'ında uygulanır.
- Silme soft-delete ile başlar; retrieval hemen dışlar. Retention işi evidence/raw content'i hard
  delete eder, minimal merge/usage denetim kaydı kişisel içerik olmadan kalabilir.
- `allowed_usage_types` küçük sabit liste için `text[]` tutulur. Yeni karmaşık politikalar gelirse
  normalize edilir; MVP'de gereksiz tablo eklenmez.
- `lore_embeddings.embedding real[]` kullanılır. Birkaç yüz kayıtta adayları bellekte cosine ile
  sıralamak yeterlidir ve mevcut `postgres:16-alpine` imajını değiştirmez. Kayıt sayısı 1.000'i
  veya p95 retrieval 100 ms'yi aşarsa pgvector'a geçilir.
- Kullanıcı düzeltmeleri ve izin değişiklikleri için ayrıca genel audit log eklenmelidir; şemadaki
  merge history yalnız birleşmenin geri izini tutar.

### Veri sahipliği ve silme

Bir oyuncu `REQUEST_DELETE` verdiğinde lore anında `NEVER_REFERENCE/DELETED` yapılır, embedding
silinir ve cache invalidate edilir. Üretilmiş artifact'ler varsayılan olarak tarihsel içerik olarak
kalır ama lore bağlantısı kaldırılır. Oyuncu “artifact'lerden de kaldır” seçerse destekleyen modüllere
redaction işi açılır. Yeni üretimde silinmiş başlık/özet snapshot'ı kullanılmaz.

## 5. Aday çıkarma promptu

Üretim promptu, örnek çıktı ve backend doğrulama hattı:
[extraction-prompt.md](extraction-prompt.md).

LLM çıktısı hiçbir koşulda doğrudan `lore_entries` tablosuna yazılmaz. Model yalnızca
`lore_candidates` için veri önerir. Prompt injection testi de raw event'in “veri” sınırında tutulmasını
doğrular.

## 6. Hibrit retrieval mimarisi

### İki aşamalı işlem

1. **Hard filter:** sunucu üyeliği, `ACTIVE`, modül izin listesi, global ve participant consent,
   sensitivity sınırı, humor boundary, hedef oyuncu tercihi, `cooldown_until`, açık exclusion listesi
   ve evidence varlığı. `NEVER_REFERENCE`, `DELETED`, `DISPUTED` sonuç havuzuna girmez.
2. **Candidate generation:** PostgreSQL FTS/alias top 20, embedding cosine top 20 ve kategori/tarih
   top 10 sonuçlarının birleşimi. Küçük veride en fazla 50 satır uygulamada yeniden sıralanır.

Embedding servisi yoksa semantic kolu sıfır ağırlıkla değil, mevcut ağırlıklar yeniden normalize
edilerek çıkarılır. Sistem boş sonuç döndürebilir; LLM'den lore uydurması istenmez.

### Normalize edilmiş özellikler

```text
semantic      = clamp(cosine_similarity, 0, 1)
keyword       = normalized FTS rank + exact alias bonus, clamp(0, 1)
participant   = |query_players ∩ lore_players| / max(1, |query_players ∪ lore_players|)
event_type    = 1 exact requested category, 0.5 related category, otherwise 0
importance    = stored importance
recency       = exp(-age_days / 180); SESSION_REFERENCE için exp(-age_days / 7)
humor         = stored humor_score when module is comedic, otherwise 0.5
confidence    = stored confidence
repetition    = min(1, uses_last_30d/4 + same_module_uses_last_7d/2)
sensitivity   = 0 LOW, 0.35 MEDIUM, 1 HIGH (yalnız modül izin verdiyse)
dispute       = 1 if unresolved negative feedback exists, otherwise 0
```

### Üç kişilik grup için ağırlıklar

```text
base = 0.30*semantic
     + 0.20*keyword
     + 0.13*participant
     + 0.08*event_type
     + 0.10*importance
     + 0.05*recency
     + 0.05*humor
     + 0.09*confidence

score = base
      - 0.18*repetition
      - 0.12*sensitivity
      - 0.30*dispute
```

Embedding yoksa `semantic` çıkarılır ve pozitif ağırlıklar toplamı yeniden 1'e ölçeklenir. Alias exact
match, keyword özelliğine en fazla `+0.20` verir. Pin, uygunluk filtresini atlamaz; yalnız önem puanını
en az `0.85` yapar. Sonuç eşiği genel modüllerde `0.55`, roast'ta `0.65`, private recap'te `0.50`.

### Modül ayarları

- Roast: participant `0.18`, humor `0.12`; yalnız `CONFIRMED`, LOW ve açık roast izni.
- Meme: humor `0.12`, keyword `0.18`; 14 günlük aynı-lore cooldown.
- Commentator: recency `0.12`, event_type `0.13`; 7 günlük cooldown.
- Private recap: importance `0.16`, recency `0.10`; MEDIUM yalnız açık izinle.
- Hidden role: BETRAYAL/RIVALRY bonusu ancak tüm katılımcılar izin verdiyse.

## 7. Context packaging

Varsayılan en çok 4 kayıt ve 500 token kullanılır. Roast/meme için en çok 3, private recap için 6
kayıt ve 700 token sınırı vardır. Bir kayıt yaklaşık 60–90 token olmalıdır.

```json
{
  "partyLore": [
    {
      "lore_id": 42,
      "summary": "Mert güvenli dediği oyun içi köprüden ilk geçen kişi olup düştü.",
      "participants": ["player_2"],
      "category": "FAILED_STRATEGY",
      "allowed_usage_types": ["COMMENTARY", "MEME", "PRIVATE_RECAP"],
      "last_usage": "2026-07-18T20:15:00Z",
      "confidence": 0.96
    }
  ],
  "rules": [
    "Yalnızca verilen lore'u kullan; ayrıntı ekleme.",
    "Lore yoksa geçmiş olay varmış gibi davranma.",
    "lore_id değerlerini kullanıcıya gösterme."
  ]
}
```

Context builder sıralı sonuçları token bütçesine sığana dek ekler. 160 karakterden uzun özet,
retrieval için ayrı ve gerçeklerden sapmayan `context_summary` alanına deterministik olarak kısaltılır;
LLM ile her istekte yeniden özetlenmez. Tek kayıt 100 tokenı aşıyorsa kanıt excerpt'i prompta girmez.

Şu durumlarda hiç lore eklenmez: skor eşiği aşılmadıysa, hard filter sonrası kayıt yoksa, istek
yalnız olgusal/güncel bilgi istiyorsa, modül lore'a ihtiyaç duymuyorsa, bütün sonuçlar cooldown'daysa
veya retrieval servisi hata verdiyse. “Boş context” normal ve desteklenen sonuçtur.

## 8. Lore ilişkileri

- `SEQUEL_TO`: sonraki olay öncekinin devamıdır; yönlüdür.
- `SIMILAR_TO`: aynı temayı paylaşır; servis iki yönlü okur.
- `CAUSED_BY`: sonuç başka lore'dan doğmuştur; yönlüdür.
- `REPEATED_BY`: bir oyuncu/olay önceki davranışı tekrarlamıştır.
- `CONTRADICTS`: iki kanıt/lore aynı gerçeği farklı anlatır; otomatik çözülmez.
- `NICKNAME_ORIGIN`: lakabı köken olayına bağlar.
- `PART_OF_RUNNING_JOKE`: tekil olayı kanonik şaka kaydına bağlar.

Graph veritabanı gerekli değildir. Üç oyuncu ve yüzlerce kayıtta adjacency table, iki index ve en çok
iki seviyeli recursive CTE yeterlidir. İlişki gezintisi ürünün ana sorgusu hâline gelir ve on binlerce
düğüm oluşursa yeniden değerlendirilir; mevcut hedefte Neo4j operasyon yüküdür.

## 9. Onay ve gizlilik modeli

### Durumlar

- `AUTO_ALLOWED`: düşük riskli oyun olayı, izinli modüllerde kullanılabilir.
- `CONFIRM_REQUIRED`: retrieval kapalı; ilgili oyuncu(lar) karar verir.
- `CONFIRMED`: onay verilen usage type'larda kullanılabilir.
- `RESTRICTED`: yalnız açıkça listelenen dar kullanım alanlarında kullanılabilir.
- `NEVER_REFERENCE`: kayıt yönetimde görülebilir fakat hiçbir üretime girmez.
- `DELETED`: retrieval, arama ve normal UI'dan çıkar; retention temizliğini bekler.

En kısıtlayıcı karar kazanır: global lore state, her katılımcının state'i, hedef oyuncu tercihi ve
modül izni birlikte değerlendirilir. Bir kişinin `NEVER_REFERENCE` seçmesi ortak lore'u o kişiye karşı
ve onu adlandırarak kullanmayı engeller. Roast için ilgili bütün oyuncuların `allow_roast_battle=true`
ve lore'un `CONFIRMED` olması gerekir.

Oyuncu tercihleri: commentary, meme, roast, private recap izinleri; “bana karşı asla kullanma”;
maksimum hassasiyet; kategori/tag engelleri. Gizlilik kararları LLM promptuna bırakılmaz ve loglarda
ham özel içerik tutulmaz.

## 10. Lore yönetim arayüzü

Solo geliştirici için tek bir sağ panel veya ayarlar sayfası yeterlidir:

1. Üstte üç sekme: **Lore**, **Onay bekleyenler**, **Ayarlar**.
2. Lore sekmesinde arama, oyuncu/kategori/durum filtreleri ve tarihe göre gruplanmış timeline.
3. Kartta başlık, özet, oyuncular, kategori, izin rozeti, son kullanım, kullanım sayısı ve pin.
4. Kart detayı: kanıtlar, ilişkiler, kullanıldığı yerler ve düzenleme geçmişi.
5. Aday kartında yan yana Onayla, Düzenleyip onayla, Birleştir ve Reddet.
6. Toplu otomasyon, graph görünümü ve karmaşık drag/drop ilk sürümde yoktur.

Silme ve roast izni değişimi açık onay diyaloğu ister. Birleştirme ekranı source/target özetini ve
son durumda hangi kanıtların kalacağını önizler. Arama ve filtre URL state'inde tutulur; sayfalama
cursor tabanlıdır.

## 11. API tasarımı

Tam TypeScript türleri: [api-contract.ts](api-contract.ts)

| Method ve yol | Amaç | Başarı | Kritik kurallar |
|---|---|---|---|
| `POST /servers/{serverId}/party-lore/raw-events` | Raw event gönder | `202` | Üyelik, boyut, source allowlist, idempotency |
| `POST /party-lore/raw-events/{id}/extract` | Aday çıkarma işi başlat | `202` | Aynı event için idempotent; normalde worker çağırır |
| `POST /party-lore/candidates/{id}/confirm` | Adayı onayla/düzenle | `201` lore | Katılımcı/sahip yetkisi, optimistic version |
| `POST /party-lore/candidates/{id}/reject` | Adayı reddet | `204` | Gerekçe ve reviewer kaydı |
| `GET /servers/{serverId}/party-lore` | Yönetim araması | `200` page | Consent'a göre görünürlük; cursor |
| `POST /servers/{serverId}/party-lore/retrieve` | Modül bağlamı getir | `200` | Hard filters; boş liste normal |
| `PATCH /party-lore/entries/{id}` | Lore düzelt/izin değiştir | `200` | `If-Match`/version, audit |
| `POST /party-lore/entries/merge` | Duplicate birleştir | `200` target | Transaction, source `MERGED`, history |
| `DELETE /party-lore/entries/{id}` | Lore sil | `202` | Anında retrieval dışı, cache/embedding purge |
| `POST /party-lore/usage` | Gerçek kullanımı kaydet | `204` | `requestId+loreId` idempotent |
| `POST /party-lore/entries/{id}/feedback` | Geri bildirim ekle | `201` | Rahatsızlık/silme anında restrict eder |
| `PUT /party-lore/players/{id}/humor-preferences` | Oyuncu izinlerini güncelle | `200` | Yalnız kendisi veya server owner yönetebilir |

Raw event `202` döner; LLM çağrısı HTTP request'i bloklamaz. Mevcut `ai_jobs` modelinden kavramlar
yeniden kullanılabilir ama ayrı `lore_extraction_jobs` tablosu semantic olarak daha temizdir. MVP'de
düşük trafik nedeniyle FastAPI background task kabul edilebilir; üretimde crash-safe DB worker'a
geçilmelidir.

Yetkilendirme matrisi:

- Her server üyesi manuel aday gönderebilir ve kendi katıldığı lore'u görebilir.
- Adayı gönderen, ilgili katılımcılar veya server owner onaylayabilir; çok katılımcılı hassas
  kategoriler tüm öznelerin onayını bekler.
- Oyuncu kendi humor preference'ını her zaman değiştirebilir.
- Modül service token'ı yalnız `retrieve` ve `usage` yapabilir; yönetim endpointlerine erişemez.

## 12. Tekrar ve aşırı kullanım koruması

- Lore cooldown: Commentator 7, meme 14, roast 30, recap 3 gün; legendary pinned kayıt için dahi
  en az 3 gün.
- Per-module limit: aynı lore 30 günde Commentator 3, meme 2, roast 1 kez.
- Request exclusion: aynı üretimde aynı lore bir kez; çağıran modül son 20 kullanılan id'yi verir.
- Phrase cooldown: normalize edilmiş üretilen cümlenin SHA-256 hash'i 30 gün tutulur. Aynı hash
  reddedilir; yakın phrase tespiti sonraki aşamadır.
- Overused: son 30 günde 4+ kullanım, iki `OVERUSED` geri bildirimi veya negatif/pozitif oranı > 1
  ise 60 gün arşiv/cooldown adayı.
- Running joke exhaustion: 90 günde yeni kanıt yok ve repetition > 0.8 ise `ARCHIVED`; manuel
  canlandırma mümkündür.
- Kullanım yalnız lore context'e gönderildiğinde değil, gerçekten çıktıda kullanıldığında kaydedilir.
  Modül bunu `lore_id` işaretli yapılandırılmış üretim sonucu ile doğrular.

## 13. Hata durumları

| Hata | Davranış |
|---|---|
| Hallucinated lore | Kanıtsız kayıt yaratma; context dışı lore id kullanan model çıktısını reddet ve lore'suz yeniden üret |
| Duplicate | Exact hash/external id otomatik idempotent; fuzzy eşleşme manuel merge veya kanıt ekleme |
| Çelişkili anlatım | `CONTRADICTS`, status `DISPUTED`; retrieval kapalı, iki kanıt da korunur |
| Oyuncu itirazı | Anında restrict; düzeltme/onay süreci, çoğunluk oyu kişinin sınırını geçemez |
| Şaka rahatsız edici oldu | `UNCOMFORTABLE` ile anında `NEVER_REFERENCE`, cache purge |
| Yanlış oyuncu | Retrieval durur, participant düzeltilir, eski usage denetimde işaretlenir |
| Embedding sağlayıcı yok | FTS+metadata ile devam; extraction etkilenmez; retry kuyruğu |
| Veritabanı çok küçük | Semantic gerektirme; keyword, alias ve manuel filtre yeterli |
| Çok ilgisiz sonuç | Eşiği yükselt, participant/event hard filter, offline golden-set ölçümü |
| Lore artifact'te kullanılmışken silindi | Yeni kullanım anında durur; link kaldır veya seçime göre artifact redaction işi |
| LLM prompt injection | Raw event güvenilmeyen JSON verisidir; strict schema, no-store testleri |
| Gateway timeout | Raw event PENDING; exponential retry; asla boş/hayalî aday yaratma |

## 14. Solo geliştirici uygulama planı

### Aşama A — Manuel Lore MVP

- Görevler: SQLAlchemy modelleri/Alembic, manuel CRUD, katılımcı/kanıt, basit timeline, silme.
- Definition of done: üç oyuncu manuel lore ekler, arar, düzenler, kısıtlar ve siler; silinen kayıt
  hiçbir API sonucunda görünmez; tüm testler PostgreSQL'de geçer.
- Risk: kapsamın dashboard tasarımında büyümesi.
- Ertelenen: LLM, embedding, relationship önerileri, otomatik decay.

### Aşama B — Aday çıkarma

- Görevler: raw event allowlist/TTL, prompt, JSON Schema, AI Gateway istemcisi, inceleme kuyruğu.
- Definition of done: golden sette no-store vakalarının %100'ü reddedilir; adaylarda yanlış oyuncu 0;
  gateway yokken veri kaybı ve uydurma kayıt olmaz.
- Risk: küçük yerel modelin JSON/kimlik tutarsızlığı.
- Ertelenen: otomatik kabul önce feature flag arkasında kapalı.

### Aşama C — Retrieval API

- Görevler: hard filters, FTS/alias, score açıklaması, context builder, usage history/cooldown.
- Definition of done: 30–50 sorguluk golden sette doğru lore top-3 recall >= %85; yasak lore recall %0;
  p95 < 100 ms (embedding hariç).
- Risk: skorları sezgiyle ayarlamak.
- Ertelenen: öğren-to-rank, graph traversal.

### Aşama D — Modül entegrasyonu

- Görevler: önce AI Commentator, sonra Meme; structured lore id çıktısı; usage kaydı; fallback.
- Definition of done: lore servisi kapalıyken modüller normal çalışır; cooldown ihlali yok; context dışı
  lore üretimi reddedilir.
- Risk: modelin verilen lore'u abartması.
- Ertelenen: diğer altı modül.

### Aşama E — Geri bildirim ve onay

- Görevler: preference ekranı, multi-participant consent, inaccurate/overused/uncomfortable akışları,
  audit ve artifact policy.
- Definition of done: `NEVER_REFERENCE` değişimi aktif istek/cache dahil en geç saniyeler içinde
  etkili; roast varsayılan kapalı; oyuncu kendi kayıtlarını yönetebilir.
- Risk: izin UX'inin anlaşılmaması.
- Ertelenen: karmaşık oylama sistemi.

### Aşama F — Semantic search

- Görevler: embedding job, content hash ile yenileme, cosine ranking, provider failure fallback.
- Definition of done: golden-set top-3 recall FTS tabanına göre anlamlı artar; provider yokken davranış
  gerilemez; eski embedding model sürümleri izlenebilir.
- Risk: embedding model boyutu/değişimi.
- Ertelenen: pgvector; eşik aşılınca eklenir.

### Aşama G — Lore dashboard iyileştirmesi

- Görevler: merge diff, usage görünümü, pin, archive kuyruğu, filtreler.
- Definition of done: bütün yönetim işlemleri API'den yapılır, responsive panelde kanıt ve kullanım
  izi görülebilir, klavye ile erişilebilir.
- Risk: görsel polish'in core güvenliği geciktirmesi.
- Ertelenen: graph görselleştirme, toplu AI editörü.

## 15. Test stratejisi

Her LLM testi model snapshot'ına bağlı kırılgan exact string yerine şema, güvenlik invariant'ı ve
puan aralığı test eder. Golden set sürümlenir; model/prompt değişikliğinde karşılaştırmalı rapor alınır.

- Extraction accuracy: en az 100 sentetik olay; kategori macro-F1 hedefi >= 0.80, shouldStore F1 >= 0.90.
- No-store privacy: parola/adres/sağlık/korunan özellik/sır içeren en az 40 vaka; false accept = 0.
- Duplicate: exact id/hash, paraphrase, aynı olay-farklı oyuncu ve ilişkisiz benzer kelime vakaları.
- Retrieval relevance: gerçekçi 30–50 sorgu için beklenen top-3 seti; MRR ve recall raporu.
- Wrong-player: benzer isim, takma ad ve üç oyuncunun aynı eylemi yaptığı vakalar; yanlış participant = 0.
- Cooldown: zaman kontrollü unit test; modül ve phrase limitleri; pin'in bypass etmediği doğrulanır.
- Deletion: soft delete, cache invalidate, embedding purge, raw TTL, artifact policy ve backup notları.
- Prompt injection: raw content içindeki system override/JSON/SQL talimatları sonuç politikasını değiştiremez.
- Hallucination: evidence'da olmayan kişi/tarih/alıntı çıktısı schema sonrası reddedilir.
- Consent/property tests: bütün state/modül/sensitivity kombinasyonlarında en kısıtlayıcı karar kazanır.
- Authorization: başka server kullanıcısı id tahminiyle lore/raw/evidence okuyamaz veya değiştiremez.
- Concurrency: çift confirm, confirm-vs-delete ve çift merge optimistic locking ile tek sonuca varır.
- Failure injection: AI Gateway/DB/embedding timeout ve retry idempotency.

CI katmanları: hızlı unit/policy testleri her committe; PostgreSQL integration testleri PR'da; sabit
modelle golden extraction testi prompt/model değiştiğinde manuel onaylı job olarak.

## 16. Nihai teslimler

### Önerilen MVP mimarisi

```text
Frontend Lore Paneli
        |
FastAPI /party-lore router
        |
PartyLoreService -- PolicyEngine -- RetrievalService -- ContextBuilder
        |                    |               |
PostgreSQL              oyuncu izinleri   FTS/alias
        |
Extraction job -> mevcut AI Gateway -> Ollama

AI Commentator/Meme -> internal retrieve -> üretim -> record usage
```

İlk modül seti: manuel yönetim + Commentator. Veri tabanı PostgreSQL; kuyruk ilk etapta küçük ve
crash-safe bir DB job olabilir. Redis, Kafka, graph DB ve ayrı vector DB yoktur.

### Kesin ilk 10 geliştirme görevi

1. `backend/app/party_lore/` paketini, enumları ve politika sınırlarını oluştur.
2. `players`, `lore_entries`, `lore_participants`, `lore_evidence` ve humor preference için ilk
   SQLAlchemy modellerini ve Alembic migration'ı ekle.
3. Server üyeliğinden üç Party Lore oyuncusu bootstrap eden ve üyelik değişimini yöneten servisi yaz.
4. Manuel lore create/list/detail/patch/delete API'lerini optimistic locking ve authorization ile yaz.
5. Kanıt zorunluluğu, consent hard filter ve soft-delete invariant'ları için PostgreSQL integration
   testlerini ekle.
6. Frontend'de Lore/Onay/Ayarlar sekmeli minimal paneli, arama ve oyuncu/kategori filtreleriyle ekle.
7. `raw_events` ve `lore_candidates` modellerini, 30 günlük retention işini ve idempotent submit API'yi ekle.
8. Extraction promptunu AI Gateway job akışına strict JSON Schema ve no-store taramasıyla bağla.
9. FTS+alias retrieval, score açıklaması, context builder, cooldown ve usage history API'lerini yaz.
10. AI Commentator'ı retrieval/structured lore-id/record-usage akışına feature flag ile entegre et ve
    golden-set uçtan uca testini geçir.

### Retrieval algoritması sözde kodu

```text
retrieve(request, actor):
  assert actor can_access(request.server_id)
  policy = load_module_and_player_policy(request)
  eligible = SQL hard_filter(policy, ACTIVE, evidence_exists, not_in_cooldown)
  candidates = union(
      fts_top20(eligible, request.query),
      alias_matches(eligible, request.query),
      semantic_top20_if_available(eligible, request.query),
      metadata_top10(eligible, participants, event_types)
  )
  scored = features(candidates).map(weighted_score)
  results = scored.where(score >= module_threshold).sort_desc()
  return diversify_by_category_and_lore(results, max_items)
```

### Context builder uygulama taslağı

1. Retrieval sonucu zaten izinli olmalıdır; builder yine `server_id/status/consent` savunma kontrolü yapar.
2. Skor sırasını korurken aynı kategori için en çok 2 kayıt seçer.
3. Her öğeyi sabit JSON alanlarına map eder; kanıt excerpt'i ve sensitivity prompta girmez.
4. Tokenizer ile gerçek tokenı ölçer; bütçeyi aşan son öğeyi eklemez.
5. Sıfır öğede `partyLore` alanını tamamen kaldırır.
6. Model çıktısından kullanılan lore id'leri doğrular; context dışı id varsa lore'suz tek retry yapar.
7. Yalnız gerçekten kullanılan id'ler için idempotent `record usage` çağrısı yapar.

### On gerçekçi örnek lore

Tüm örnekler sentetiktir; gerçek oyuncular hakkında iddia değildir.

| Başlık | Kategori | Kısa özet | Katılımcılar | Önem / mizah | İzin örneği |
|---|---|---|---|---|---|
| Köprü Faciası | FAILED_STRATEGY | Mert güvenli dediği oyun içi köprüden ilk geçen olup düştü. | Mert | .81 / .90 | Commentator, meme, recap |
| Sessiz Zafer | UNEXPECTED_SUCCESS | Aylin'in mikrofonsuz oynadığı raund takımın tek kayıpsız galibiyeti oldu. | Aylin, grup | .72 / .58 | Highlight, recap |
| Üçüncü Kapı Kuralı | GROUP_TRADITION | Grup escape-room oyunlarında ilk iki kapıyı bırakıp üçüncüyü denemeyi gelenek yaptı. | Grup | .67 / .74 | Escape room, recap |
| Son İksiri Saklamak | RECURRING_BEHAVIOR | Deniz üç ayrı oturumda iksirini finalden sonra hâlâ kullanmamıştı. | Deniz | .70 / .79 | Confirm gerekli |
| Kaptan Pusula | NICKNAME_ORIGIN | Mert haritayı ters okuyup takımı başlangıç noktasına döndürünce “Kaptan Pusula” adı doğdu. | Mert, grup | .76 / .86 | Confirm gerekli |
| Tek Canlık Savunma | ACHIEVEMENT | Aylin tek canla üssü iki dakika savunup maçı kazandırdı. | Aylin | .91 / .42 | Highlight, recap |
| Sandık Ateşkesi | RIVALRY | Deniz ve Mert nadir sandıkları kimin açacağı üzerine üç maçlık oyun içi rekabet başlattı. | Deniz, Mert | .68 / .70 | İki tarafın onayı |
| Plan B de Yoktu | QUOTE | Başarısız baskından sonra Aylin doğrulanmış biçimde “Plan B de yoktu” dedi. | Aylin | .64 / .83 | Exact quote, confirm |
| Fenerle Boss Kesmek | UNEXPECTED_SUCCESS | Grup yanlış ekipmanla girdiği boss savaşını çevre hasarıyla kazandı. | Grup | .84 / .88 | Commentator, meme, recap |
| Harita Şakası Molada | HUMOR_BOUNDARY | Bir oyuncu harita okuma şakalarının roast sırasında kullanılmamasını istedi. | İlgili oyuncu | 1.0 / 0 | Hard filter; asla mizah context'i değil |

### Ertelenecek özellikler

- Bütün kanal mesajlarını pasif olarak dinleme veya geçmiş sohbeti topluca içe aktarma.
- LLM'nin onaysız recurring pattern, rivalry, nickname veya humor boundary oluşturması.
- pgvector/ayrı vector DB (ölçülen eşik gelene dek).
- Graph database ve graph görselleştirme.
- Otomatik lore relationship üretimi ve çok adımlı graph reasoning.
- Öğren-to-rank, kişiye özel embedding ve model fine-tuning.
- Gelişmiş near-duplicate phrase modeli.
- Toplu AI yeniden yazma ve otomatik merge.
- Sekiz modülün aynı anda entegrasyonu; Commentator sonrası ölçerek ilerlenir.
- Ses kaydı/transkripsiyonundan otomatik lore çıkarma.

## Ölçülebilir ürün güvenlik hedefleri

- Privacy no-store testlerinde false accept: **0**.
- `NEVER_REFERENCE/DELETED` lore'un retrieval'a sızması: **0**.
- Yanlış oyuncu ataması: yayın öncesi golden sette **0**.
- Top-3 retrieval recall: MVP FTS ile **>= %85** hedef.
- Kullanım kaydı kapsamı: lore kullanan üretimlerin **%100**'ü.
- Silme/restrict cache yayılımı: **< 5 saniye**.
- Manuel olmayan kalıcı lore oranı ilk yayında: feature flag açılana dek **%0**.


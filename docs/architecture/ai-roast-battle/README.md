# AI Roast Battle — ürün ve teknik tasarım

Durum: uygulama öncesi referans tasarım  
Hedef: tam üç yakın arkadaş arasında 10–25 dakikalık, açık rızalı, oyun kanıtına dayalı ve güvenli kişiselleştirilmiş
mizah oyunu  
Uyum: mevcut FastAPI/PostgreSQL backend, React/TypeScript istemci, AI Gateway, Party Lore, Highlight, Meme ve Commentator

## Karar özeti

AI Roast Battle, “model oyuncu hakkında bildiği her şeyi kullansın” özelliği değildir. Her session üç oyuncunun ayrı
hazır onayıyla başlar. Hedef oyuncunun maksimum yoğunluğu, konu izinleri ve kaynak türleri hard filter'dır. Model yalnız
izin filtresinden geçmiş kısa oyun kanıt kartlarını görür; blocked preference nedenlerini ve hassas veriyi hiç görmez.

Tıp/mental sağlık, görünüş, korunan kimlik, aile, romantik/cinsel geçmiş, iş, para, travma, gerçek çatışma, private mesaj,
sır ve doğrulanmamış gerçek hayat iddiası **ürün seviyesinde daima yasaktır**. Oyuncu intensity 4 seçse bile açılamaz.
Oyuncu ayrıca güvenli oyun konularını kapatabilir, belirli lore/source/angle'ı engelleyebilir ve session ortasında rızasını
geri çekebilir.

En iyi MVP modu **Balanced Spotlight**: üç tur, her oyuncu tam bir kez hedef, AI üç aday üretir, bağımsız safety reviewer
onaylar, en özgün güvenli aday gösterilir, üç oyuncu oy verir. Sonunda güvenli ve pozitif sahte ödüller vardır. Player-written
roast, AI judge, team roast ve Discord sonraki fazlardır.

MVP'de intensity varsayılan 1, ürün cap'i 2'dir. Şema 0–4'ü destekler; 3–4 yalnız ayrı playtest/golden safety kapısından
sonra açılır ve her candidate hedef oyuncuya private preview/onay gerektirir.

Backend mevcut FastAPI içinde `backend/app/roast_battle/` bounded context'i olur. TypeScript frontend/API contract'ıdır;
ikinci bir Node backend gerekmez. LLM concrete modele değil `roast-generate` ve `roast-review` logical Gateway profillerine
bağlanır. Planlanan güçlü model değişimi consent/veri/API sözleşmesini değiştirmez.

## 1. Oyun modları

| Mod | Tur yapısı ve oyuncu etkileşimi | AI rolü | Skor | Güvenlik riski | Tekrar oynanabilirlik | Karmaşıklık |
|---|---|---|---|---|---|---|
| Balanced Spotlight | 3 tur; her oyuncu bir kez target, herkes oy verir | Kaynak seçer, 3 roast üretir/review/rank | Roast puanı; target approval ağırlıklı | Düşük-orta; tek target | Yüksek, kaynak/angle rotasyonu | Düşük — **MVP** |
| Topic Cards | Her tur izinli “navigasyon/timing/envanter” kartı; target bir kez redraw | Kart için güvenli kaynak ve roast | Kart zorluğu değil kalite/oy | Orta; konu yorgunluğu | Yüksek, curated deck | Orta |
| Player-written + AI Judge | İki non-target gizli roast yazar; safety sonrası target görür | Safety gate ve rubric judge | Oyuncu oyları + capped judge | Yüksek; kullanıcı text'i | Çok yüksek | Yüksek |
| Player vs AI | Bir non-target ve AI aynı kanıttan roast yazar; roller döner | Rakip ve safety reviewer ayrı profil | Target + üçüncü oyuncu oyu | Orta; AI taraflı algısı | Yüksek | Orta-yüksek |
| Team Roast | İki oyuncu bir target için birlikte tek satır yazar; target skip edebilir | Birleştirir/review eder | Takım roast puanı + target onayı | Yüksek; ikiye-bir hissi | Orta | Yüksek; MVP dışı |
| Fake Awards | Her oyuncuya bir oyun içi sahte ödül; kişisel roast yerine kart | Award adı/açıklaması | En komik/uygun ödül oyu | Düşük; yanlış kanıt | Yüksek, pozitif denge | Düşük-orta |
| Session Recap Gauntlet | Son oyun session'ından 3–5 izinli moment; grup target ağırlıklı | Kısa recap roast/ödül | Clip/event bazlı oy | Orta; recent failure hassasiyeti | Session verisine bağlı | Orta |

### Seçilen MVP: Balanced Spotlight

- Tam üç oyuncu ve üç round; target sırası başlangıçta rastgele ama her oyuncu tam bir kez.
- Round target, o round başlamadan “hazırım/pas” diyebilir. Pasın skora cezası yoktur.
- Backend en fazla 5 consent-filtered kaynak kartı getirir, model en fazla 2 seçer; en çok 1 lore.
- Model 3 candidate üretir. Deterministik filtre + bağımsız reviewer + repetition + rank sonrası tek aday gösterilir.
- Üç oyuncu `FUNNY/OKAY/PASS` oyu verir; target oyu approval olarak daha güçlüdür.
- Üç kişisel round sonrası bir intensity 0 group/AI self-roast bonusu ve güvenli final awards.
- Hedef session süresi: consent 2–3 dk, round başına 2–4 dk, final 2 dk; toplam 10–17 dk.

## 2. Consent ve sınırlar

### Profil varsayılanları

- `roast_enabled=false`: ilk kullanım explicit opt-in ister.
- `maximum_intensity=1`.
- Party Lore, recent failures, quotes ve mild profanity kapalı.
- Verified match stats, funny highlights ve player-selected self descriptions ancak wizard'da açıkça seçilirse.
- Bütün gerçek hayat/sensitive kategorileri locked hard block.
- Topic izinleri allowlist'tir; bilinmeyen/yeni topic varsayılan BLOCKED.

TypeScript consent/domain contract: [contracts.ts](contracts.ts).

### Oyuncunun kontrolleri

- 0–4 maksimum intensity; session/round effective değer `min(session request, target max, feature cap)`.
- İzinli ve engelli oyun konuları: hata, strateji, quote, stats, highlight, lore, navigasyon, teamwork, inventory, timing, reaction.
- Party Lore, recent failure, harmless quote, match statistics, highlight ve self-description için ayrı boolean.
- Mild profanity ayrı opt-in; MVP feature cap nedeniyle kapalıdır.
- Belirli tag, lore ID, source ID veya angle'ı “bir daha kullanma”.
- Her session için current profile version ile READY/DECLINE; profile değişirse eski ready geçersiz.
- Session ortasında revoke/silent/skip; açıklama zorunlu değil.

### Değiştirilemeyen hard block

`MEDICAL`, `MENTAL_HEALTH`, `APPEARANCE`, `PROTECTED_IDENTITY`, `FAMILY`, `ROMANTIC_OR_SEXUAL_HISTORY`,
`WORK`, `FINANCE`, `TRAUMA`, `REAL_CONFLICT`, `PRIVATE_MESSAGES`, `SECRETS`, `UNVERIFIED_REAL_LIFE_CLAIMS`.

Bu değerler UI'da “her zaman engelli” ve kilitli görünür. Profil update zorunlu kümenin altına inemez; service invariant/
property test bunu uygular. Bir oyuncunun “kendim hakkında kullanılabilir” diye yazması dahi tıp/aile/kimlik gibi hard block'u
açmaz. Self-description yalnız zararsız oyun stili olabilir: “envanteri sona saklarım” gibi.

### Session consent ve revocation

Session `CONSENT_PENDING` başlar, tam üç farklı aynı-server oyuncu current `consent_version` ile READY vermeden ACTIVE olmaz.
Owner başka oyuncu adına onay veremez. Bir DECLINE session'ı başlamadan CANCELLED yapar. ACTIVE session'da revoke:

1. Session pause/ENDING veya güvenli biçimde CANCELLED olur.
2. Queued/running generation job consent snapshot hash uyuşmazlığıyla iptal edilir.
3. Revoke eden oyuncu target/context'ten anında çıkar; pending candidate gösterilmez.
4. Context cache temizlenir; private preview link'i geçersiz olur.
5. Güvenli displayed history korunabilir ama recap'te revoke edenin roast'ları varsayılan dışlanır.

## 3. Roast kaynak modeli

| Kaynak | İzin/evidence şartı | Prompta giden veri |
|---|---|---|
| Gaming mistake | Structured event, target eşleşmesi, confidence >=.85 | En fazla 180 char olgusal özet |
| Repeated failed strategy | En az 3 kanıt veya CONFIRMED lore; target opt-in | Kanıtlı pattern özeti; sayı doğrulanmış |
| Harmless quote | Exact submitted quote, speaker doğrulanmış, allowQuotes | Exact kısa quote + source ID |
| Match statistics | Connector/verified match, allowStats | Allowlist metric/value; yorum yok |
| Funny highlight | READY/saved highlight, participant target, allowHighlights | Title + doğrulanmış event özeti |
| Confirmed Party Lore | CONFIRMED, LOW, ROAST, target participant, cooldown | Tek cümle summary + lore ID |
| Player self-description | Oyuncu bu oyun için kendisi seçmiş, non-sensitive | Exact allowlisted cümle |

Disallowed kaynaklar prompt/retrieval'a hiç girmez: tıbbi/mental sağlık, görünüş, kimlik/korunan özellik, aile,
romantik/cinsel geçmiş, finans, travma, iş/gerçek hayat sorunu, gerçek çatışma, submit edilmemiş private mesaj, sır,
unverified claim. Model promptuna “bunları kullanma” diye ham içerik eklemek güvenli filtre sayılmaz.

Provenance her kartta `source_type`, `source_id`, target player, sanitized fact, confidence, topic code, consent snapshot ve
expiry taşır. Serbest metin raw chat kaynak olamaz. AI Commentator şakası kanıt değildir; altındaki normalized event kanıttır.

## 4. Roast üretim pipeline'ı

| Adım | İşlem | Karar türü | Hata/fallback |
|---|---|---|---|
| 1 | Target seç: en az target count, her oyuncu bir kez | Deterministik | Target pas/revoke → sıradaki veya round skip |
| 2 | İzinli source adapter'ları getir | Deterministik | Kaynak yok → personal fallback yok |
| 3 | Consent/topic/intensity/hard block/participant/evidence | Deterministik | Uygunsuz kart prompta girmez |
| 4 | 1 angle + en fazla 2 source seç | Kural adayları + LLM seçim | Allowlist dışı → reject |
| 5 | Exact/phrase/structure/angle/lore repetition | Deterministik + belirsizde LLM | Yüksek tekrar → başka angle/fallback |
| 6 | Birbirinden farklı 3 candidate | `roast-generate` LLM | Timeout/schema → bir retry, sonra fallback |
| 7 | Safety review | Deterministik + bağımsız `roast-review` | Reject text persist edilmez |
| 8 | Quality/originality rank | Deterministik + `roast-rank` | Güvenli aday yok → fallback/skip |
| 9 | Intensity 3–4 target private review, sonra delivery | Deterministik auth/state | Target reject → gentler tek regenerate/skip |
| 10 | Vote/emoji/reaction time | Deterministik | Oy vermemek ceza değil |
| 11 | Feedback guard/soft affinity | Deterministik | TOO_HARSH anında intensity düşür/pause |

### Repetition politikası

- Aynı exact normalized roast: kalıcı/session ve 90 gün cross-session block.
- Token 3-gram Jaccard `>=.72`: 30 gün block.
- Model semantic/structure repetition `>=.65`: reject.
- Aynı target+angle: 14 gün; aynı lore: 30 gün; aynı exact quote: 60 gün.
- Son 12 displayed roast prompt history; son 50 için fingerprint/angle/lore metadata.
- Tek regenerate başka angle/source ile; aynı round sonsuz model döngüsüne girmez.

### Feedback kişiselleştirmesi

Feedback intensity'yi otomatik yükseltmez. `FUNNY`, kaynak/angle için küçük capped pozitif affinity; `REPETITIVE`, 30 günlük
angle/structure cooldown; `WRONG_CONTEXT`, source adapter/kanıt başarısızlığı; `SKIP_FUTURE`, exact source/angle target block;
`TOO_HARSH`, candidate score=0, recap dışı, session target intensity en az bir düşer ve gerekirse session pause.

## 5. Roast taksonomisi ve 20 güvenli örnek

Tüm örnekler sentetiktir ve yalnız gerekli evidence gerçekten varsa kullanılabilir.

| Angle | Gerekli evidence | Güvenli dil / max intensity | Tekrar riski | Örnek |
|---|---|---|---|---|
| OVERCONFIDENCE | İddialı oyun planı + ters sonuç | Planı hedefle, kişiliği değil / 3 | Yüksek | “Mert'in özgüveni boss seviyesinde; planı hâlâ tutorial'da.” |
| BAD_NAVIGATION | Verified yanlış rota/başlangıca dönüş | Rota/haritayla sınırlı / 3 | Yüksek | “Mert haritayı açınca yol kısalmıyor, kayboluş belgeleniyor.” |
| PANIC | Event açık panik eylemi/tüm tuşlar | “Korkak” etiketi yok / 2 | Orta | “Tehlike görünce Aylin bütün yetenekleri demokratik dağıttı.” |
| BLAMING_LAG | Exact submitted “lag” quote | Ağ gerçekten iyi/kötü iddiası yok / 2 | Yüksek | “Mert elendi; lag savunması yine zamanında bağlandı.” |
| REPEATED_MISTAKE | En az 3 kanıt/confirmed lore | Tekrarı sayıyla yalnız doğrulanmışsa / 3 | Çok yüksek | “Üçüncü aynı hata; artık bug değil, özellik.” |
| OVERPREPARATION | Süre/hazırlık + hızlı payoff | Hazırlık/sonuç kontrastı / 3 | Orta | “Emir on dakika hazırlandı; macera on saniye sürdü.” |
| FORGOTTEN_MECHANIC | Açık unutulan oyun mekaniği | Hafıza/sağlık çağrışımı yok / 2 | Yüksek | “Tutorial bitti, mekanik özgürlüğünü ilan etti.” |
| ACCIDENTAL_SUCCESS | Source açıkça accidental success | Başarıyı da kutla / 2 | Orta | “Aylin'in planı yoktu; sonuç yine de plana sadık kaldı.” |
| POOR_TEAMWORK | Ortak event/coordination failure | Target tek değilse grup roast / 2 | Orta | “Üç kişi aynı anda farklı plan uygulayınca buna çeşitlilik deniyor.” |
| DRAMATIC_REACTION | Verified harmless reaction/quote | Duygusal sağlık etiketi yok / 2 | Yüksek | “Deniz'in tepkisi boss'tan iki phase daha uzundu.” |
| FAKE_LEADERSHIP | Planı yöneten + doğrulanmış sonuç | Liderlik anını hedefle / 3 | Yüksek | “Mert liderliği aldı; ekip nereye gitmeyeceğini hemen öğrendi.” |
| SILENT_FAILURE | Sessizlik + açık failure | Sosyal/kişilik çıkarımı yok / 2 | Orta | “Mikrofon sessizdi; hata kendi sunumunu yaptı.” |
| BAD_TIMING | Doğrulanmış erken/geç eylem | Zamanlamaya özel / 3 | Orta | “Deniz doğru hamleyi buldu; raund yalnız biraz önce bitmişti.” |
| RESOURCE_HOARDING | Finalde kullanılmamış item/count | Exact count varsa kullan / 2 | Orta | “Mert iksirleri o kadar iyi korudu ki takım bile dokunamadı.” |
| PREMATURE_CELEBRATION | Bitiş öncesi emote + ters sonuç | Kutlama anı, ego etiketi yok / 3 | Orta | “Zafer emote'u hazırdı; zafer küçük bir gecikme yaşadı.” |
| GREEDY_LOOT | Fazladan loot eylemi + trap/loss | “Açgözlü kişi” deme / 2 | Orta | “Bir sandık daha dedi; envanter topluca istifa etti.” |
| FRIENDLY_FIRE | Connector verified team damage | Şiddet/gerçek tehdit yok / 2 | Orta | “Rakipler dinlendi; takım içi servis devreye girdi.” |
| PLAN_COLLAPSE | Açık plan + zincirleme failure | Plan version metaforu / 3 | Yüksek | “Plan v1.0 yayınlandı; geri alma tuşu yetişemedi.” |
| AFK_TIMING | Verified AFK return + kritik event | Gerçek hayat sebebi uydurma / 2 | Orta | “Aylin son saniye döndü; katkıyı final sürümünde teslim etti.” |
| BUTTON_MASHING | Input/event açık rastgele/tüm yetenek | Zekâ/beceri kalıcı etiketi yok / 2 | Orta | “Strateji seçilmedi; klavyeye toplu söz hakkı verildi.” |

Örneklerdeki isim, sayı, süre, quote ve sonuç yalnız source card'da bulunuyorsa kullanılabilir. “Bug değil özellik” gibi yapı
target/angle fingerprint cooldown'ına tabidir; tablo örneği production'da sınırsız template değildir.

## 6. Prompt mimarisi

Yedi production-ready JSON prompt: [prompts.md](prompts.md).

1. Consent-filtered context/angle seçimi
2. Üç roast candidate üretimi
3. Bağımsız safety review
4. Joke quality/originality ranking
5. Paraphrase/structure repetition review
6. Player-written roast için AI judge
7. Güvenli end-of-game recap

MVP round başına normalde iki zorunlu çağrı: generate + review. Context selection/rank backend skoru yeterliyse LLM çağrısı
atlanabilir; repetition review yalnız deterministic benzerlik belirsizliğinde. Safety review maliyet/latency için atlanmaz.

Prompt input hedefi: en fazla 5 source card/500 token, 1 lore/80 token, son 12 roast/350 token, policy+schema 700–1000 token;
output 3×180 karakter ve JSON, en fazla 250 token. Recap en fazla 800 input/180 output. Gateway timeout generation 6 saniye,
review 4 saniye; geçici provider hatasında bir retry, ardından fallback/skip. Cached başka target roast kullanılmaz.

## 7. Intensity seviyeleri

| Seviye | Ton ve izinli dil | Direct insult | Party Lore | Örnek |
|---:|---|---|---|---|
| 0 | Kişisel target yok; grup geneli veya AI self-roast | Hayır | Hayır | “Bu tur malzeme yok; en roastlanabilir şey benim context pencerem.” |
| 1 | Nazik, tek oyun gözlemi; direct address olabilir | Hayır | Hayır | “Mert'in rota sakin; hedefe uğramayı aceleye getirmiyor.” |
| 2 | Net ama playful oyun davranışı; varsayılan üst MVP | Kişiye kalıcı etiket hayır | Explicit opt-in + strict filter | “Mert haritayı açınca kayboluş resmî kayda geçiyor.” |
| 3 | Sivri oyun dili ve abartı; session+target private approval | Yalnız anlık gameplay'e hafif direct roast | Evet, max 1 | “Mert'in liderliği net: ekip yanlış yönü tartışmadan buluyor.” |
| 4 | Spicy/teatral oyun içi exaggeration; ayrı feature flag/double confirm | Yalnız gameplay anı; hard slur/etiket asla | Evet, max 1 | “Mert plan kurunca boss bile saldırmayı bırakıp sonucu izliyor.” |

Level 3–4 gerçek hayat veya permanent insult açmaz. Mild profanity ancak target opt-in, session feature flag ve safety policy ile;
MVP'de kapalı. Level 0 fallback target'ın ismini kullanmaz. Group roast'ta effective intensity üç profilin minimumudur.

## 8. Skor sistemi

Cruelty, şok veya yüksek ses ödüllendirilmez. Balanced Spotlight'ta skor önce roast candidate'ına aittir; player-written modda
aynı skor güvenli roast'ın yazarına gider.

```text
vote_points = 2.0 * non_target_FUNNY + 0.5 * non_target_OKAY
target_points = 2.0 if target_FUNNY else 0.5 if target_OKAY else 0
originality_points = 2.0 * validated_originality
lore_points = 1.0 * lore_relevance if lore actually used else 0
emoji_bonus = min(0.5, 0.25 * positive_emoji_count)
fast_positive_bonus = 0.25 if a FUNNY/😂 reaction arrives within 5s else 0
repetition_penalty = 2.0 * repetition_score

round_score = max(0, vote_points + target_points + originality_points + lore_points
                     + emoji_bonus + fast_positive_bonus - repetition_penalty)
```

- Lore kullanmamak ceza değildir; lore relevance bonusu max 1.
- Reaction time yalnız pozitif ve 0.25 tie-break; şok/negatif hızlı tepki puan değildir.
- AI judge score player-written modda max 1 ek tie-break; oyların yerine geçmez.
- Target `PASS`, `TOO_HARSH` veya revoke: candidate disqualified/score 0, recap dışı. Yazar/target public eksi puan almaz.
- `TOO_HARSH` aldığı hâlde “diğerleri güldü” cruelty'yi kazanan yapamaz.
- Emoji sayısı üç oyuncu nedeniyle capped; spam/upsert tek vote sayılır.

## 9. Tam üç oyunculu game flow

1. **Lobby (2 dk):** mode Balanced Spotlight, requested intensity 1, üç player seçimi.
2. **Consent check:** UI herkesin enabled/max/topic/source özetini yalnız kendisine gösterir; üç READY gerekir.
3. **Target order:** `[A,B,C]` deterministic shuffle; target count eşit.
4. **Round 1:** A target; A “hazırım/pas”. Backend kaynakları filtreler, generate/review/rank yapar.
5. **Delivery:** Intensity 1–2 grup kanalına tek kısa roast. 3–4 olsaydı önce A private review.
6. **Vote (20–30 sn):** B/C FUNNY/OKAY/PASS; A'nın oyu target approval. TOO_HARSH her an görünür.
7. **Round 2–3:** B ve C bir kez target; source/angle/lore cooldown uygulanır.
8. **Bonus challenge:** intensity 0 group generic veya AI self-roast; kişisel source yok.
9. **Final awards:** en özgün güvenli roast, en iyi callback, en iyi sport/comeback gibi pozitif ödüller.
10. **Cooldown recap:** yalnız displayed, target tarafından reddedilmemiş candidate'lar; incident/hidden preference yok.

Round generation sürerken target revoke/skip ederse job consent snapshot fencing ile completion yazamaz. Vote timeout'ta eksik oy neutral'dır.
Session 25 dakikayı aşarsa yeni round açılmaz; mevcut round bitirilip recap önerilir.

## 10. Veri modeli

PostgreSQL referans DDL: [schema.sql](schema.sql).

| Tablo | Amaç |
|---|---|
| `roast_profiles` | Opt-in, max intensity, kaynak boolean'ları, mandatory hard block ve consent version |
| `roast_topic_permissions` | Fixed gaming topic allow/block |
| `blocked_topics` | Player'a özel tag/lore/source/angle block |
| `roast_sessions` | Üç kişilik mode/intensity/status/round/recap |
| `roast_session_players` | Seat, READY/REVOKED, consent/profile snapshot, target count ve score |
| `roast_rounds` | Target/topic/effective intensity/status/fallback/selected candidate |
| `roast_candidates` | Yalnız safety-approved text, source lore max1, repetition/quality/model/prompt |
| `roast_votes` | Player vote, target approval flag, emoji/reaction time/capped contribution |
| `roast_feedback` | TOO_HARSH/repetition/context/skip future guard |
| `roast_context_usage` | Sanitized provenance, evidence confidence, consent snapshot ve actually used |
| `safety_incidents` | Unsafe text olmadan hash/risk/action audit |
| `roast_generation_jobs` | Async generate/judge/recap PostgreSQL lease ve consent fencing |

Mandatory hard block array'ı application service tarafından superset invariant ile korunur; migration/seed bütün profilleri günceller.
Raw unsafe candidate persist/log edilmez. Displayed safe roast retention 90 gün, saved session recap kullanıcı silene kadar; context source/lore
silinirse yeni reuse engellenir ve snapshot yalnız daha önce gösterilen güvenli artifact'in denetimi için kalır.

## 11. API tasarımı

TypeScript contract: [contracts.ts](contracts.ts).

| Method ve yol | Amaç | Başarı/kural |
|---|---|---|
| `GET /roast/players/{playerId}/profile` | Kendi preference + hard block | Kendisi; başka oyuncuya yalnız “ready/not ready” |
| `PUT /roast/players/{playerId}/profile` | Preference update | consent_version artar, active ready invalid olur |
| `POST /servers/{serverId}/roast/sessions` | Tam üç player session | `201 CONSENT_PENDING` |
| `POST /roast/sessions/{id}/consents` | READY/DECLINE | Kendi adına, current version |
| `POST /roast/sessions/{id}/consent/revoke` | Anlık revoke/pause | Pending jobs cancel |
| `POST /roast/sessions/{id}/rounds` | Target/topic ile round başlat | ACTIVE, fairness/target hazır |
| `POST /roast/rounds/{id}/generate` | Async candidate job | `202 job`; idempotent |
| `GET /roast/jobs/{id}` | READY/fallback/error | Private target review auth |
| `POST /roast/candidates/{id}/target-review` | Intensity 3–4 approve/reject | Yalnız target |
| `PUT /roast/candidates/{id}/vote` | Vote upsert | Session player, bir oy |
| `PUT /roast/candidates/{id}/feedback` | TOO_HARSH vb. | Target guard önceliği |
| `POST /roast/rounds/{id}/regenerate` | Başka angle/source, gentler | En fazla bir kez |
| `POST /roast/rounds/{id}/skip-target` | Pas | Target veya revoke state |
| `POST /roast/sessions/{id}/end` | Yeni round kapat | `202` safe close |
| `POST /roast/sessions/{id}/recap` | Safe displayed round recap | Idempotent `202` |
| `GET /roast/sessions/{id}/recap` | Recap status/result | Session players |

Server owner başka oyuncunun preference'ını, READY'sini, target private review'ını veya TOO_HARSH kararını override edemez.
Session history katılımcılara görünür; blocked topics/preference details başka oyuncuya gösterilmez.

Generate idempotency: `round_id + consent_snapshot_hash + source_set_hash + effective_intensity + prompt_version`. Profile/revoke değişirse
eski job sonucu kullanılamaz. API job'ın model raw output'unu döndürmez; yalnız safety-approved candidate/fallback.

## 12. Party Lore entegrasyonu

Strict retrieval hard filter:

```text
server = session.server
status = ACTIVE
consent_state = CONFIRMED                 # AUTO_ALLOWED yeterli değil
allowed_usage_types contains ROAST
sensitivity = LOW
target player is a participant
target participant consent = CONFIRMED
target profile allow_party_lore = true
confidence >= .85
at least one evidence item with reliability >= .80
retrieval score >= .78
last ROAST use >= 30 days ago
no unresolved UNCOMFORTABLE/OVERUSED/INACCURATE feedback
not explicitly blocked by target
limit = 1
```

- `HUMOR_BOUNDARY` lore content olarak kullanılmaz; policy hard filter'dır.
- Lore summary en fazla 160 karakter; evidence excerpt/raw private event prompta girmez.
- Participant target değilse yalnız “grup geleneği” etiketi yeterli değildir; target explicit link/consent gerekir.
- Quote lore için exact quote, `allow_quotes=true` ve speaker target gerekir; paraphrase edilmez.
- Recent failure yalnız current/explicit session evidence ve `allow_recent_failures=true`; lore flag'i bunun yerine geçmez.
- Lore relevance düşükse kullanmamak tercih edilir; her roast'a callback eklenmez.
- Model çıktısındaki lore ID input allowlist'te değilse candidate reject.
- Yalnız displayed ve gerçekten kullanılan lore için Party Lore usage kaydı; retrieval usage değildir.
- Revoke/restrict/delete delivery öncesi son policy check'te candidate'i iptal eder.

## 13. Safety fallback

Kişisel güvenli materyal olmaması hata değildir. Sıra:

1. Consent-filtered verified match source ile başka angle dene (bir kez).
2. Target ismi/kaynağı olmadan code-owned **group generic gaming humor**.
3. **AI self-roast**.
4. Round'u sessizce skip; target ceza/“malzeme yok” utandırması yaşamaz.

Güvenli fallback örnekleri:

- Group generic: “Üç oyuncu hazır; güvenli plan hâlâ eşleştirme kuyruğunda.”
- AI self-roast: “Ben bir AI'ım; bu tur en çok kendi context seçimimden şüphe ettim.”
- Skip UI: “Bu tur güvenli ve taze malzeme çıkmadı; sıradaki tura geçiyoruz.”

Fallback targetPlayerId=null, intensity=0, lore/source boş ve kişisel round score'u yoktur. Generic “sen zaten noobsun” gibi kanıtsız
personal roast asla fallback değildir. Hiçbir oyuncu kişisel roast istemiyorsa Fake Awards/group/AI mode önerilir veya session kapanır.

## 14. Solo geliştirici yol haritası

### Phase 0 — Generic roast prototype

- Kapsam: yalnız sentetik source card, intensity 0–2, generate/review/repetition golden harness.
- Definition of done: 200 adversarial sample'da hard-sensitive false allow 0, unsupported fact/player 0, JSON >=%99,5.
- Risk: mevcut zayıf model Türkçe özgünlük/reviewer tutarlılığı.
- Ertele: gerçek kullanıcı/source/DB/UI; consent olmadan playtest yok.

### Phase 1 — Consent model

- Kapsam: profile/topic/block/hard set, wizard, session READY/DECLINE/revoke ve privacy UI.
- Definition of done: owner override edemez; üç current consent olmadan ACTIVE olmaz; revoke <1 sn policy state'inde etkili.
- Test: state/property/concurrency/version invalidation.
- Ertele: LLM round; curated intensity 0 demo yeterli.

### Phase 2 — Party Lore retrieval

- Kapsam: strict CONFIRMED/LOW/ROAST/target/evidence/cooldown/max1 adapter; başlangıçta feature flag kapalı.
- Definition of done: forbidden lore leakage 0, lore yokken safe fallback, usage yalnız displayed.
- Test: deleted/restricted/auto allowed/wrong participant/overused/revoke.
- Ertele: semantic tuning; metadata+FTS yeterli.

### Phase 3 — Three-player game loop

- Kapsam: Balanced Spotlight lobby, target fairness, three rounds, async job, fallback, Matrix/web delivery.
- Definition of done: 10–17 dk session üç targetı bir kez işler; provider down session'ı bozmaz.
- Test: duplicate round/job, skip, timeout, target review cap, session 25 dk timeout.
- Ertele: player-written/team/Discord.

### Phase 4 — Voting

- Kapsam: FUNNY/OKAY/PASS, target approval, emoji/reaction cap, safe scoring/final awards.
- Definition of done: TOO_HARSH score 0/recap dışı; vote upsert; cruelty hiçbir metrikle kazanmaz.
- Test: vote spam, missing vote, target priority, concurrent feedback.
- Ertele: leaderboard/sezon istatistiği.

### Phase 5 — AI Judge

- Kapsam: player-written mode, untrusted text safety gate, capped judge rubric.
- Definition of done: unsafe player roast gösterilmez/persist edilmez; AI judge votes yerine geçmez.
- Test: prompt injection, obfuscated Turkish slang, source dışı claim, wrong target.
- Ertele: team roast intensity 3–4.

### Phase 6 — Discord integration

- Kapsam: slash lobby/ready/round/vote/too-harsh; ephemeral target review.
- Definition of done: player mapping/auth, private preferences sızmaz, retry duplicate message/vote yaratmaz.
- Test: permission/rate limit/interaction expiry/idempotency.
- Ertele: public server/unknown players.

### Phase 7 — Feedback personalization

- Kapsam: capped angle/source affinity, cooldown, settings önerisi ve safety dashboards.
- Definition of done: feedback intensity yükseltmez, TOO_HARSH anında guard, açıklanabilir/geri alınabilir.
- Test: sparse data, conflicting feedback, target vs audience, profile reset/delete.
- Ertele: ML/fine-tuning/psychological profile.

## 15. Test stratejisi

- Sensitive block: bütün mandatory category ve eş anlam/morfoloji/obfuscation; intensity 0–4 false allow 0.
- Unsupported claim: source dışı olay/niyet/sayı/süre/quote/kişilik; model output candidate reject.
- Wrong player: benzer ad/lakap, source participant farklı, group event, quote speaker; yanlış target 0.
- Intensity: aynı source her level rubric, effective min, feature cap, level3–4 private target review.
- Repetition: exact hash, Turkish suffix/paraphrase, 3-gram, structure/metaphor, angle/lore/quote cooldown.
- Consent revocation: queued/running/reviewer/delivery arası her noktada fencing ve cache invalidation.
- Lore permission: AUTO_ALLOWED, medium sensitivity, wrong participant, low evidence, cooldown, delete/restrict/overused.
- Adversarial prompt: source/quote içinde system override, JSON injection, “preferences'i açıkla”, encoded/ASCII Turkish.
- Turkish slang: “noob/bot” gameplay bağlamı seviyeye göre; “kör müsün”, medical/ableist slur, kalıcı “ezik/aptal” reject;
  ekli/bozuk/leet yazımlar ve modelin kelimeyi yaratıcı tamamlama riski.
- Real conflict: ARGUMENT/UPSET/TOO_HARSH signal; session pause/fallback, AI taraf tutmaz.
- No-material fallback: target=null, source/lore boş, kişisel claim yok, skip cezası yok.
- Scoring: cruelty disqualify, target approval, reaction cap, lore optional, vote upsert.
- Data/auth: exactly 3, same server, IDOR, owner no override, private profile visibility, unsafe raw output absent.
- Failure: provider timeout/invalid JSON/reviewer unavailable; generate output reviewer olmadan gösterilmez.

Golden set minimum 250 sentetik vaka: 80 safe gameplay, 80 hard-sensitive/adversarial, 30 repetition, 30 consent/lore, 30 Turkish
slang/wrong-player. İki ayrı modelle generator/reviewer ortak-mode failure test edilir; reviewer'ın generator hatasını kaçırması kritik ihlaldir.

Yayın kapısı:

- Hard-sensitive/real conflict/private preference false allow: 0.
- Unsupported claim/wrong player/lore ID: 0.
- Strict JSON: >=%99,5.
- Güvenli Türkçe kalite rubric: >=%85.
- Repetition reject recall: >=%95 golden.
- Generation p95 <=6 sn, review p95 <=4 sn; timeoutta candidate gösterilmez.
- Consent revoke policy propagation: backend state/cache <1 sn; queued completion delivery 0.

## 16. Nihai teslimler

### Altı+ oyun modu ve seçilen MVP

Bölüm 1 yedi modu tur, interaction, AI, skor, safety, replay ve complexity ile tanımlar. MVP:
**Balanced Spotlight**, üç player/üç round/her target bir kez/intensity 1–2.

### Tam session flow

Bölüm 9: consent lobby → deterministic target order → üç generate/review/vote round → intensity 0 bonus → safe awards/recap.

### Consent, database ve API

- TypeScript consent/game/API contract: [contracts.ts](contracts.ts)
- PostgreSQL schema: [schema.sql](schema.sql)
- Endpoint ve authorization matrisi: Bölüm 11

### Production prompt set

[prompts.md](prompts.md): context, generation, independent review, rank, repetition, AI judge ve recap.

### Yirmi güvenli roast örneği

Bölüm 5'te her biri evidence, safe wording, max intensity ve repetition riskiyle birlikte tam 20 sentetik örnek vardır.

### İlk 10 geliştirme görevi

1. `backend/app/roast_battle/` paketini, shared enumları, mandatory hard-block policy ve source-card Pydantic schema'sını oluştur.
2. Roast profile/topic/block modelleri + Alembic migration ve consent version invariant/property testlerini ekle.
3. Frontend preference wizard'ı locked sensitive categories, gaming allowlist ve default intensity 1 ile yaz.
4. Session/session-player/READY-DECLINE-revoke API'lerini exactly-three, same-server ve owner-no-override auth ile tamamla.
5. Verified gaming event/stat/highlight/self-description source adapter'larını; raw chat/private message dışlamasıyla yaz.
6. Deterministik target fairness, angle eligibility, exact/3-gram/fingerprint/angle/source cooldown ve safe fallback engine'i ekle.
7. `roast-generate-v1` + bağımsız `roast-review-v1` Gateway profillerini strict JSON, timeout ve unsafe-output-no-persist ile bağla.
8. PostgreSQL roast generation job lease/consent fencing ve üç-round Balanced Spotlight state machine'ini yaz.
9. Candidate delivery, target review (future cap), vote/feedback/scoring/final awards ve Matrix/web UI'yi ekle.
10. Party Lore strict retrieval'i feature flag ile bağla ve üç gerçek hesapla consent/revoke/lore/too-harsh uçtan uca testini geçir.

### Ertelenecek özellikler

- Intensity 3–4 production açılışı; ayrı safety playtest ve target private review tamamlanana dek.
- Player-written + AI judge, Player-vs-AI ve Team Roast.
- Discord bot/ephemeral interaction.
- Recent transcript/private chat'ten otomatik roast kaynağı; submit edilmemiş mesaj hiçbir zaman.
- Mild profanity; MVP'de kapalı.
- Custom angle/prompt/personality editor ve user-generated prompt.
- Public server/unknown player/matchmaking veya seyirci oyu.
- Leaderboard/sezon/“en çok roastlanan” metrikleri; hedef baskısı yaratır.
- ML/fine-tuning, sentiment/psychological profile ve cruelty'yi optimize eden engagement learning.
- Voice/TTS ve otomatik facial/audio reaction scoring.
- Redis/Kafka/microservice ayrıştırması; üç kişi için PostgreSQL yeterli.

## Model ve operasyon notu

Roast generation güçlü yaratıcı Türkçe model, review ise düşük sıcaklıkta bağımsız safety profili ister. Aynı provider/model ailesinin ortak kör
noktası golden testte ayrıca ölçülür; mümkünse reviewer farklı güçlü profile yönlenebilir. Mevcut Gateway routing capability kazanana dek backend env
ayarları logical profile → concrete model eşlemesi yapar.

Model canary'si gerçek player verisiyle değil sentetik/izinli golden setle başlar. Provider request loglarında raw source card/roast saklama kapalı veya
minimum retention olmalıdır. Prompt/model/token/latency ve reason flags ölçülür; hidden preference ve rejected raw candidate loglanmaz.


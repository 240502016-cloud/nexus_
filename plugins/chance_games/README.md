# Şans Ustası

Ücretsiz harici servis veya ücretli API kullanmadan çalışan, sunucu temasıyla uyumlu oyun botu
pluginidir. Rastgele seçimler Python `secrets` modülüyle sunucu tarafında yapılır.

## Kurulum

1. **Botlar → Platform pluginleri** bölümünden `chance_games` pluginini kur.
2. `sans-ustasi` gibi bir bot oluştururken **Bota özel plugin** alanında `chance_games` seç.
3. Mevcut bir bot kullanılacaksa bot kartındaki **chance_games bağla** düğmesine bas.
4. Sohbette `/şans` yazarak rehberi aç.

Bir sunucuda bu plugin aynı anda yalnız bir bota bağlanabilir. Böylece aynı komuta birden fazla
botun cevap vermesi engellenir.

## Komutlar

### Taş · Kağıt · Makas

- `/takama @kullanıcı`: 2 dakika geçerli davet gönderir.
- `/kabul <davet-kodu>` veya `/kabul takama @kullanıcı`: daveti kabul eder.
- `/reddet <davet-kodu>`: gelen daveti reddeder.
- `/iptal <davet-kodu>`: gönderilen daveti iptal eder.
- `/taş`, `/kağıt`, `/makas`: kabulden sonra hamleyi kilitler.

İlk hamle Matrix'e ve gateway'e hiç yazılmaz. Yalnız “hamle kilitlendi” bilgisi yayınlanır;
iki oyuncu da tamamladıktan sonra hamleler ve kazanan tek sonuç kartında açıklanır. Başlayan oyun
5 dakika içinde tamamlanmazsa süre aşımına uğrar.

ASCII klavyeler için `/tas` ve `/kagit` eşdeğerdir.

### Yazı · Tura

- `/yazıtura`: tek kişilik güvenli rastgele atış yapar.
- `/yazıtura @kullanıcı`: davet gönderir. Davet sahibi Yazı, rakibi Tura olur; kabul anında atış
  yapılıp kazanan açıklanır.

ASCII klavyeler için `/yazitura` ve `/yazi-tura` eşdeğerdir.

### Çarkıfelek

Her kullanıcının her metin kanalında ayrı bir çarkı vardır ve seçenekler PostgreSQL'de kalıcıdır.

- `/ekleçark elma` veya `ekleçark: elma`: seçenek ekler.
- `/ekleçark elma | 3`: ağırlığı 3 olan seçenek ekler.
- `/çarkliste`: seçenekleri ve ağırlıkları gösterir.
- `/çıkarçark <sıra|ad>`: seçenek çıkarır.
- `/temizleçark`: kullanıcının o kanaldaki çarkını temizler.
- `/çark`: en az iki seçenek varsa çevirir.

Bir çark en fazla 50 seçenek ve toplam 500 ağırlık kabul eder. Aynı isimli seçenekler tekrarlanmaz.

## Güvenlik ve durum

- Plugin sandbox yalnız komutu doğrulanabilir bir zarfla Core API'ye iletir; DB kimlik bilgisi almaz.
- Yetki, sunucu üyeliği, davetin gerçek hedefi ve bot-plugin bağı Core tarafında doğrulanır.
- Davet, gizli hamle ve çark durumu yeniden başlatmalarda kaybolmaz.
- Rastgele sonuç için üçüncü taraf servis, reklam, ücretli API veya kullanıcı ödemesi yoktur.

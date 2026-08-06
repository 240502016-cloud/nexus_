# Yerel insan testi

Bu ortam, production sunucusuna aktarim veya Git push yapmadan dokuz oyun modulunu gercek arayuzden test etmek icindir. PostgreSQL ve Matrix `nexus-local` adli ayri Docker Compose projesinde ve ayri volume'lerde calisir. Guncel backend, AI worker, AI Gateway ve React/Vite arayuzu hostta calisir; boylece working tree'deki kod image olusturmadan dogrudan test edilir. Mevcut production veritabanina baglanmaz.

## Baslatma

1. Docker Desktop'i ve AI metinleri de test edilecekse Ollama'yi baslatin.
2. Proje kokundeki `Yerel-Test-Baslat.cmd` dosyasina cift tiklayin.
3. Otomatik testler gectikten ve konteynerler hazir olduktan sonra `http://localhost:5173` acilir.
4. Ilk kullaniciyi kaydedin, bir sunucu ve kanal olusturun. Sol menudeki deneyim bolumlerinden modulleri acin.

Ilk calistirmada izole PostgreSQL ve Matrix volume'leri hazirlanir. `.env.local` ilk baslatmada rastgele anahtarlarla uretilir ve Git tarafindan yok sayilir. Highlight video render testi icin hostta `ffmpeg` ve `ffprobe` gerekir; bu makinede `Gyan.FFmpeg.Essentials` kullanilir.

## AI Gateway ve Ollama

Yerel AI Gateway hostta `http://localhost:18090` adresinde calisir ve varsayilan olarak host makinedeki `http://127.0.0.1:11434` Ollama servisine baglanir. Oyun mekanikleri Ollama olmadan da calisir; anlatim, yorum, meme metni, roast ve benzeri AI ciktilari icin Ollama'da `.env.local` icindeki modelin kurulu olmasi gerekir (varsayilan `qwen2.5:7b`).

Ollama baska bir adresteyse `.env.local` icindeki `LOCAL_OLLAMA_BASE_URL` degerini degistirin ve ortami yeniden baslatin.

## Kontrol ve durdurma

```powershell
.\scripts\local-test-status.ps1
.\scripts\local-test-status.ps1 -Logs
```

`Yerel-Test-Durdur.cmd` konteynerleri durdurur ve yerel test verilerini korur. Bu akista volume silme komutu yoktur.

## Yerel adresler

| Servis | Adres |
|---|---|
| Web arayuzu | `http://localhost:5173` |
| Backend saglik | `http://localhost:18100/health` |
| Matrix | `http://localhost:18008` |
| PostgreSQL | `127.0.0.1:55432` |
| AI Gateway | `http://localhost:18090` |

AI Gateway endpoint'leri `.env.local` icindeki `AI_GATEWAY_API_KEY` Bearer anahtarini ister.

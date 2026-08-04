# FFmpeg/FFprobe pipeline

FFmpeg komutları yalnız dedicated `media-worker` container'ında çalışır. Backend container'a FFmpeg
eklenmez. Image içinde sürüm pinlenir ve startup'ta `ffmpeg -version`/`ffprobe -version` kaydedilir.
Worker network'süz, non-root, read-only root filesystem, ayrı writable work dizini, tek concurrency,
CPU/RAM/PID limitleri ve process timeout ile çalışır.

Kod `subprocess.run([...], shell=False)` veya `Popen([...], shell=False)` kullanır. Aşağıdaki komutlar
okunabilirlik için shell biçimindedir; production kodu string birleştirip shell'e göndermez. Dosya yolları
yalnız UUID storage key'lerinden gelir; başlık/subtitle text'i command argümanına değil güvenli ASS/text
dosyasına yazılır.

## 1. Probe

```bash
ffprobe -v error \
  -protocol_whitelist file,pipe \
  -show_entries format=format_name,duration,size,bit_rate \
  -show_entries stream=index,codec_type,codec_name,width,height,avg_frame_rate,duration,channels,sample_rate \
  -of json \
  /media/originals/4/2f/2f4e7c2d-61d7-4df8-a216-d8672ad216f9.input
```

Probe en fazla 30 saniye çalışır. JSON schema ile doğrulanır. MVP allowlist:

- Container: MP4/MOV veya Matroska/WebM.
- Video: H.264, H.265/HEVC, VP9, AV1 (decode desteği image build testinde doğrulanır).
- Audio: AAC, Opus, Vorbis, MP3, PCM.
- Süre: en fazla 15 dakika; boyut: en fazla 1 GiB; çözünürlük: en fazla 7680×4320; FPS: en fazla 240.

Audio-only dosya transcript aşamasına gidebilir ama video highlight render etmez. Probe sonucu client MIME
değerinin yerine geçer. Bozuk, sıfır süreli, dış protokol isteyen veya limit aşan input `INVALID` olur.

## 2. Zaman seçimi

```text
anchor_ms = validated marker offset
pre_ms = category default: SKILL 8000, COMEDY 12000, FAILURE 10000, CHAOS 12000, LORE 12000
post_ms = category default: SKILL 5000, COMEDY 8000, FAILURE 7000, CHAOS 8000, LORE 8000
start_ms = clamp(anchor_ms - pre_ms + model_start_adjustment, 0, duration_ms)
end_ms = clamp(anchor_ms + post_ms + model_end_adjustment, start_ms + 1000, duration_ms)
```

LLM offset önerisi yalnız `[-5000,+5000]` ms aralığında küçük düzeltmedir. Backend doğrulanmış marker/
transcript segment sınırlarına snap eder. Otomatik clip hedefi 8–45 saniye, hard maximum 60 saniye.
Kullanıcı UI'da wave/timeline ile değiştirebilir; her değişiklik duration ve source sınırında doğrulanır.

## 3. Doğru trim ve normalizasyon

Stream-copy yalnız hızlı debug için düşünülebilir; non-keyframe başlangıcı yanlış gösterebilir. Bütün kullanıcıya
sunulan clip'ler tam başlangıç ve ortak output codec için re-encode edilir:

```bash
ffmpeg -nostdin -v error -y \
  -ss 18.200 -i /media/originals/4/2f/recording.input \
  -t 24.000 \
  -map 0:v:0 -map 0:a:0? -sn -dn \
  -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,setsar=1" \
  -c:v libx264 -preset medium -crf 22 -pix_fmt yuv420p \
  -c:a aac -b:a 160k -ar 48000 \
  -af "loudnorm=I=-16:LRA=11:TP=-1.5" \
  -movflags +faststart \
  /media/work/job-uuid/clip.part.mp4
```

Input'ta audio yoksa worker `-map 0:a:0?`, `-c:a` ve `-af` argümanlarını probe sonucuna göre tamamen
çıkarır. 1080p'den küçük video varsayılan olarak büyütülmez; filter boyutu probe'a göre hesaplanır.
FPS korunur fakat output maksimum 60 FPS'e düşürülür. HDR/color metadata MVP'de SDR'a normalize edilmeden
doğru işlenemiyorsa input `UNSUPPORTED_HDR` ile kullanıcıya bildirilir; soluk renkli clip üretilmez.

FFmpeg `-progress pipe:1 -nostats` ile ilerleme verir. Worker heartbeat/progress günceller; 60 saniyelik clip
için 10 dakikalık hard process timeout, cancel'da SIGTERM ve 10 saniye sonra SIGKILL uygulanır.

## 4. Subtitle ve intro title

STT segmentleri önce güvenli ASS dosyasına dönüştürülür. Aynı ASS dosyasında `Title` style ile ilk iki
saniyelik intro overlay, `Reaction` style ile doğrulanmış tek kısa tepki ve `Subtitle` style ile konuşma
satırları bulunabilir. Reaction text en fazla 120 karakterdir ve transcript/event allowlist kontrolünden geçer.
Subtitle kuralları:

- En fazla iki satır, satır başına yaklaşık 42 karakter.
- Segment en az 500 ms, en fazla 6 saniye; çakışmalar deterministic olarak birleştirilir.
- 1080p'de alt güvenli bölgede Noto Sans Bold 52px, outline 3px; vertical'da 58px ve daha yüksek konum.
- ASS control karakterleri ve `{}` ters slash'ları escape edilir; kullanıcı style/tag ekleyemez.

```bash
ffmpeg -nostdin -v error -y \
  -ss 18.200 -i /media/originals/4/2f/recording.input \
  -t 24.000 \
  -map 0:v:0 -map 0:a:0? -sn -dn \
  -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,setsar=1,subtitles=/media/work/job-uuid/captions.ass:fontsdir=/opt/nexus/fonts" \
  -c:v libx264 -preset medium -crf 22 -pix_fmt yuv420p \
  -c:a aac -b:a 160k -ar 48000 \
  -movflags +faststart \
  /media/work/job-uuid/subtitled.part.mp4
```

Filter path'leri UUID-only work klasöründedir. Production kodu FFmpeg filter expression'ını allowlist parçalarla
oluşturur; arbitrary path/text filtreye eklenmez.

## 5. Audio extraction ve normalization

STT için:

```bash
ffmpeg -nostdin -v error -y \
  -i /media/originals/4/2f/recording.input \
  -map 0:a:0 -vn -ac 1 -ar 16000 -c:a pcm_s16le \
  /media/work/job-uuid/speech.part.wav
```

OBS ayrı oyuncu mikrofonlarını ayrı track'lerde kaydetmişse her track ayrı WAV çıkarılır ve source ayarıyla
player'a bağlanır. Karışık Discord/game audio tek track ise speaker kimliği tahmin edilmez.

Tek clip için one-pass `loudnorm` yeterlidir. Compilation'da daha tutarlı ses için ilk pass JSON ölçümü,
ikinci pass `measured_I/LRA/TP/thresh` değerleriyle uygulanabilir. Orijinal dosya değiştirilmez.

## 6. Vertical varyant

MVP center crop veya kullanıcının `cropCenterX/Y` değeridir. Otomatik yüz/oyun objesi tracking yoktur.

```bash
ffmpeg -nostdin -v error -y \
  -i /media/derived/source-highlight.mp4 \
  -vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920:(iw-1080)*0.50:(ih-1920)*0.50,setsar=1" \
  -c:v libx264 -preset medium -crf 23 -pix_fmt yuv420p \
  -c:a aac -b:a 128k -movflags +faststart \
  /media/work/job-uuid/vertical.part.mp4
```

`cropCenterX/Y` 0..1'den güvenli crop x/y ifadesine backend tarafından çevrilir ve source sınırına clamp edilir.
UI render öncesi crop preview gösterir. Subtitle varsa vertical ASS yeniden düzenlenir; landscape burned text'i
crop etmek yerine subtitle'sız master'dan yeni varyant üretilir.

## 7. Thumbnail

```bash
ffmpeg -nostdin -v error -y \
  -ss 12.000 -i /media/derived/highlight.mp4 \
  -frames:v 1 -vf "scale=640:-2" -q:v 3 \
  /media/work/job-uuid/thumbnail.part.jpg
```

Frame zamanı clip orta noktasıdır; tamamen siyah frame için üç sabit adayın luma metriği karşılaştırılabilir.
AI thumbnail seçimi MVP'de yoktur.

## 8. Compilation

Önce seçili clip'ler aynı 1920×1080/H.264/AAC/48k formatına normalize edilir. LLM yalnız allowlist clip ID
sırası önerebilir; backend toplam süre, kategori/oyuncu çeşitliliği ve max 8 clip/90 saniye kuralını uygular.
Trusted work klasöründe relative UUID adlarıyla concat listesi üretilir:

```text
file '01.mp4'
file '02.mp4'
file '03.mp4'
```

```bash
ffmpeg -nostdin -v error -y \
  -f concat -safe 1 -i /media/work/job-uuid/concat.txt \
  -c copy -movflags +faststart \
  /media/work/job-uuid/compilation.part.mp4
```

Crossfade, müzik, otomatik beat sync ve karmaşık transition MVP dışıdır. Title card gerekiyorsa aynı formatta
2 saniyelik tek bir code-owned card clip'i başa eklenir.

## 9. Boyut limiti ve publish

Master render CRF tabanlıdır. Web/Matrix/Discord adapter'ın upload limiti config ile gelir; değişebilen servis
limitleri kodda sabitlenmez. Artifact limitten büyükse delivery varyantı için hedef bitrate hesaplanır:

```text
video_bps = floor((delivery_limit_bytes * 8 / duration_seconds - audio_bps) * 0.94)
```

`video_bps < 500 kbps` olursa kaliteyi görünmez biçimde ezmek yerine süre/çözünürlük düşürme önerisi verilir.
Delivery varyantı iki-pass encode edilebilir; master artifact korunur. Başarılı output önce `ffprobe` ile duration,
codec, dimensions ve stream doğrulamasından geçer, SHA-256 hesaplanır, `.part` atomik olarak final key'e rename
edilir, ardından DB transaction tamamlanır.

OFFICES = ["SENTINEL", "ARCHIVIST", "ENVOY"]
# AI'ın doldurduğu koltuğun konsey içindeki adı.
AI_PLAYER_NAME = "Vekil"
MANDATES = ["SEAL", "REVEAL", "REDIRECT"]
OBJECTIVES = ["SAFE_THREE", "SUPPORTED_THREE", "VARIED_VOTES", "REPUTATION_THREE"]

SCENARIOS = [
    {
        "key": "WHISPER_ARCHIVE",
        "title": "Fısıltı Arşivi",
        "brief": "Kendi kendine çoğalan bir kayıt parçası şehir ağına ulaşmak üzere.",
        "public_clue": "Doğrulanmamış kaydı doğrudan yaymak geri döndürülemez sonuç doğurabilir.",
        "options": [
            {"id": "A", "disposition": "SEAL", "title": "Kasayı mühürle"},
            {"id": "B", "disposition": "REVEAL", "title": "Kontrollü doğrulama yayınla"},
            {"id": "C", "disposition": "REDIRECT", "title": "Kaydı dış düğüme yönlendir"},
        ],
        "safe": "B", "severity": 1,
        "clues": {"SENTINEL": "A ve C seçenekleri kaynağın çoğalmasını durdurmuyor.", "ARCHIVIST": "B seçeneği kayıt zincirini doğrulanabilir tutuyor.", "ENVOY": "B seçeneğinin kontrollü yayını dış paniği sınırlıyor."},
    },
    {
        "key": "GLASS_EMISSARY",
        "title": "Cam Elçi",
        "brief": "Kimliği belirsiz bir elçi, mühürlü bir anlaşmayı teslim etti.",
        "public_clue": "Anlaşma açılmadan önce taşıyıcının etkisizleştirilmesi gerekiyor.",
        "options": [
            {"id": "A", "disposition": "SEAL", "title": "Elçiyi güvenli bölmede mühürle"},
            {"id": "B", "disposition": "REVEAL", "title": "Anlaşmayı halka aç"},
            {"id": "C", "disposition": "REDIRECT", "title": "Elçiyi komşu şehre gönder"},
        ],
        "safe": "A", "severity": 1,
        "clues": {"SENTINEL": "Taşıyıcı hareket ettikçe anlaşmanın etkisi güçleniyor.", "ARCHIVIST": "Belgenin kaynağı henüz doğrulanmadı.", "ENVOY": "Elçiyi başka hedefe göndermek krizi yalnız taşır."},
    },
    {
        "key": "TIDAL_SIGNAL",
        "title": "Gelgit Sinyali",
        "brief": "Derinliklerden gelen sinyal kıyı savunmasını yanlış hedefe kilitliyor.",
        "public_clue": "Sinyalin geldiği kanal, kaynağın bulunduğu kanal değil.",
        "options": [
            {"id": "A", "disposition": "SEAL", "title": "Tüm antenleri kapat"},
            {"id": "B", "disposition": "REVEAL", "title": "Ham sinyali yayınla"},
            {"id": "C", "disposition": "REDIRECT", "title": "Savunmayı doğrulanmış kaynağa yönlendir"},
        ],
        "safe": "C", "severity": 2,
        "clues": {"SENTINEL": "Tehdit mevcut savunma hattının dışında.", "ARCHIVIST": "C rotası iki bağımsız kayıtla doğrulandı.", "ENVOY": "A seçeneği kıyıyı savunmasız bırakır; B ise paniği büyütür."},
    },
    {
        "key": "EMBER_WITNESS",
        "title": "Köz Tanığı",
        "brief": "Bir tanık, sönmüş portalın yeniden açıldığını iddia ediyor.",
        "public_clue": "Tanığın ifadesi doğru, ancak yayın anı kritik.",
        "options": [
            {"id": "A", "disposition": "SEAL", "title": "Tanığı sustur"},
            {"id": "B", "disposition": "REVEAL", "title": "Kanıtla birlikte açıklama yap"},
            {"id": "C", "disposition": "REDIRECT", "title": "Tanığı başka konseye gönder"},
        ],
        "safe": "B", "severity": 1,
        "clues": {"SENTINEL": "Kanıt kontrollü salındığında portal güvenliği bozulmuyor.", "ARCHIVIST": "Tanığın kaydı özgün ve zinciri tam.", "ENVOY": "Kanıtlı ortak açıklama, söylenti yayılımını kesiyor."},
    },
]


def public_scenario(index: int) -> dict:
    scenario = SCENARIOS[index]
    return {key: scenario[key] for key in ["key", "title", "brief", "public_clue", "options"]}

from __future__ import annotations


# İki içerik seti vardır ve koltuk sayısı hangisinin kullanılacağını belirler:
#   nadir3-v1  üç konsol — üç insan ya da iki insan + AI üçüncü konsol
#   nadir2-v1  iki konsol — AI'sız iki kişilik oda, bulmacalar iki role göre yazıldı
# Her sette bulmaca grafiğinin şekli aynıdır (giriş → paralel → geçit → meta → final),
# böylece oda mantığı tek koddan yürür.

ROLES = ["ENGINEER", "ANALYST", "NAVIGATOR"]

PUZZLES = {
    "E0": {"title": "Üç Işık", "kind": "ENTRY", "dependencies": [], "answer_type": "EXACT_CODE", "answer_format": "3 rakam", "solution": "317", "owner_role": "ANY", "grant": None, "required": True, "hints": ["Üç konsoldaki ışık değerlerini koltuk sırasıyla birleştirin.", "Mühendis ilk, Analist orta, Navigatör son rakamı taşıyor.", "Cevap üç özel rakamın doğrudan yan yana yazılmasıdır."]},
    "P1": {"title": "Güç Rotası", "kind": "PARALLEL", "dependencies": ["E0"], "answer_type": "NORMALIZED_TEXT", "answer_format": "Düğüm yolu: A-C-F", "solution": "A-C-F", "owner_role": "ENGINEER", "grant": "charged_fuse", "required": True, "hints": ["Topoloji, tehlike ve hedef bilgisini aynı rota üzerinde birleştirin.", "Tehlikeli düğümleri eleyip F'ye giden yolu seçin.", "Güvenli rota A düğümünde başlar ve F'de biter; arada tek düğüm vardır."]},
    "P2": {"title": "Kayıt Kronolojisi", "kind": "PARALLEL", "dependencies": ["E0"], "answer_type": "ORDERED_SEQUENCE", "answer_format": "Virgülle dört kayıt adı", "solution": "DELTA,BETA,ALFA,GAMA", "owner_role": "ANALYST", "grant": "archive_strip_47", "required": True, "hints": ["Kayıtları zaman damgalarına göre eskiden yeniye sıralayın.", "DELTA ilk, GAMA son kayıttır.", "Ortadaki iki kayıt BETA ve ardından ALFA'dır."]},
    "P3": {"title": "Yıldız Overlay", "kind": "PARALLEL", "dependencies": ["E0"], "answer_type": "EXACT_CODE", "answer_format": "Harf+rakam koordinatı", "solution": "K4", "owner_role": "NAVIGATOR", "grant": "nav_vector", "required": True, "hints": ["Üç konsol katmanının ortak koordinatını arayın.", "K sütunu iki katmanda, 4 satırı diğer ikisinde görünür.", "Kesişim K sütunu ile 4 satırındadır."]},
    "G1": {"title": "Yetkilendirme", "kind": "GATE", "dependencies": ["P1", "P2"], "answer_type": "EXACT_CODE", "answer_format": "3 rakam", "solution": "471", "owner_role": "ENGINEER", "grant": "authorization_key", "required": True, "hints": ["Güç rotasının düğüm sayısını ve arşiv şeridindeki sayıları birlikte okuyun.", "Arşiv şeridi 47 ile başlıyor; rota tek güvenli sonuca gidiyor.", "47 değerinin arkasına rotadaki güvenli çıkış sayısını ekleyin."]},
    "G2": {"title": "Soğutma Dengesi", "kind": "GATE", "dependencies": ["P1", "P3"], "answer_type": "ORDERED_SEQUENCE", "answer_format": "SOL-SAG-SOL", "solution": "SOL-SAG-SOL", "owner_role": "ANALYST", "grant": "coolant_seal", "required": True, "hints": ["Vektör yönlerini güç hattındaki güvenli valflerle eşleştirin.", "Üç valf vardır; orta valf sağa çevrilir.", "Dıştaki iki valf sola, ortadaki sağa çevrilir."]},
    "O1": {"title": "Kaptan Dolabı", "kind": "OPTIONAL", "dependencies": ["P2"], "answer_type": "NORMALIZED_TEXT", "answer_format": "5 harfli istasyon çağrı adı", "solution": "NADIR", "owner_role": "NAVIGATOR", "grant": "captain_log", "required": False, "hints": ["Kronoloji kayıtlarının baş harflerini istasyon adıyla karşılaştırın.", "Çağrı adı istasyonun kendi adının ilk bölümüdür.", "Beş harfli çağrı adı N ile başlar ve R ile biter."]},
    "M1": {"title": "Üç Konsol Senkronu", "kind": "META", "dependencies": ["G1", "G2", "P3"], "answer_type": "SIMULTANEOUS_INPUT", "answer_format": "Her oyuncu kendi konsol kodunu girer", "solution": {"ENGINEER": "ION", "ANALYST": "47", "NAVIGATOR": "K4"}, "owner_role": "ALL", "grant": "flight_key", "required": True, "hints": ["Her rol yalnız kendi özel konsol değerini göndermeli.", "Mühendis güç sözcüğünü, Analist şerit numarasını, Navigatör koordinatı girer.", "Değerler sırasıyla bir sözcük, iki rakam ve harf+rakam biçimindedir."]},
    "F1": {"title": "Tahliye Dizisi", "kind": "FINAL", "dependencies": ["M1", "G1", "G2"], "answer_type": "ORDERED_SEQUENCE", "answer_format": "ANAHTAR-MUHUR-UCUS", "solution": "ANAHTAR-MUHUR-UCUS", "owner_role": "ANY", "grant": None, "required": True, "hints": ["Üç kritik item'i kullanım sırasına koyun.", "Önce yetkilendirme yapılır, uçuş anahtarı en son kullanılır.", "Yetki anahtarı, soğutma mührü ve uçuş anahtarı sırasını yazın."]},
}

PRIVATE_CLUES = {
    "ENGINEER": {"E0": "İlk ışık değeri 3.", "P1": "Topoloji: A, B ve C'ye; C de F'ye bağlı.", "P2": "DELTA kaydı tümünden daha eski.", "P3": "Güç katmanı K2, K4 ve M4 hücrelerini işaretliyor.", "G1": "Güvenli rotanın tek bir çıkışı var.", "G2": "Güç hattında dış iki valf aynı yönde olmalı.", "M1": "Konsol kodun: ION", "F1": "Yetki anahtarı ilk kullanılmalı."},
    "ANALYST": {"E0": "Orta ışık değeri 1.", "P1": "B düğümü karantina riski taşıyor.", "P2": "Zamanlar: DELTA 01:10, BETA 02:40, ALFA 03:15, GAMA 05:00.", "P3": "Arşiv katmanı J4, K4 ve K5 hücrelerini işaretliyor.", "G1": "Arşiv şeridinde 47 damgası bulunuyor.", "G2": "Orta valf sağa çevrilmeli.", "M1": "Konsol kodun: 47", "F1": "Soğutma mührü yetkilendirmeden sonra takılmalı."},
    "NAVIGATOR": {"E0": "Son ışık değeri 7.", "P1": "Hedef düğüm F; güvenli varış için C üzerinden gidilmeli.", "P2": "BETA, ALFA'dan önce; GAMA hepsinden sonra.", "P3": "Navigasyon katmanı K3, K4 ve L4 hücrelerini işaretliyor.", "G1": "Kod, şerit damgası ve çıkış sayısının birleşimi.", "G2": "Vektör dizisi başlangıç yönüne geri dönüyor.", "O1": "İstasyon çağrı adı NADİR-3'ün beş harfli köküdür.", "M1": "Konsol kodun: K4", "F1": "Uçuş anahtarı dizinin son adımıdır."},
}


# --- İki konsollu set -------------------------------------------------------
# Analist konsolu yoktur; taşıdığı bilgi iki role bölünmüştür. Her zorunlu
# bulmaca hâlâ iki konsolun birlikte okunmasını gerektirir — tek başına
# çözülebilen tek düğüm isteğe bağlı O1'dir.

ROLES_TWO = ["ENGINEER", "NAVIGATOR"]

PUZZLES_TWO = {
    "E0": {"title": "İki Işık", "kind": "ENTRY", "dependencies": [], "answer_type": "EXACT_CODE", "answer_format": "2 rakam", "solution": "37", "owner_role": "ANY", "grant": None, "required": True, "hints": ["İki konsoldaki ışık değerlerini koltuk sırasıyla birleştirin.", "Mühendis ilk, Navigatör son rakamı taşıyor.", "Cevap iki özel rakamın doğrudan yan yana yazılmasıdır."]},
    "P1": {"title": "Güç Rotası", "kind": "PARALLEL", "dependencies": ["E0"], "answer_type": "NORMALIZED_TEXT", "answer_format": "Düğüm yolu: A-C-F", "solution": "A-C-F", "owner_role": "ENGINEER", "grant": "charged_fuse", "required": True, "hints": ["Topolojiyi tehlike ve hedef bilgisiyle birleştirin.", "Karantinalı düğümü eleyip F'ye giden yolu seçin.", "Güvenli rota A düğümünde başlar ve F'de biter; arada tek düğüm vardır."]},
    "P2": {"title": "Yıldız Overlay", "kind": "PARALLEL", "dependencies": ["E0"], "answer_type": "EXACT_CODE", "answer_format": "Harf+rakam koordinatı", "solution": "K4", "owner_role": "NAVIGATOR", "grant": "nav_vector", "required": True, "hints": ["İki konsol katmanının ortak koordinatını arayın.", "Her iki katmanda da görünen tek hücre aranıyor.", "Kesişim K sütunu ile 4 satırındadır."]},
    "G1": {"title": "Yetkilendirme", "kind": "GATE", "dependencies": ["P1", "P2"], "answer_type": "EXACT_CODE", "answer_format": "3 rakam", "solution": "471", "owner_role": "ENGINEER", "grant": "authorization_key", "required": True, "hints": ["Arşiv şeridindeki damgayı güvenli rotanın çıkış sayısıyla birleştirin.", "Şerit damgası 47; rota tek güvenli sonuca gidiyor.", "47 değerinin arkasına rotadaki güvenli çıkış sayısını ekleyin."]},
    "G2": {"title": "Soğutma Dengesi", "kind": "GATE", "dependencies": ["P1", "P2"], "answer_type": "ORDERED_SEQUENCE", "answer_format": "SOL-SAG-SOL", "solution": "SOL-SAG-SOL", "owner_role": "NAVIGATOR", "grant": "coolant_seal", "required": True, "hints": ["Vektör yönlerini güç hattındaki güvenli valflerle eşleştirin.", "Üç valf vardır; orta valf sağa çevrilir.", "Dıştaki iki valf sola, ortadaki sağa çevrilir."]},
    "O1": {"title": "Kaptan Dolabı", "kind": "OPTIONAL", "dependencies": ["P2"], "answer_type": "NORMALIZED_TEXT", "answer_format": "5 harfli istasyon çağrı adı", "solution": "NADIR", "owner_role": "NAVIGATOR", "grant": "captain_log", "required": False, "hints": ["İstasyonun tam adıyla çağrı adını karşılaştırın.", "Çağrı adı istasyonun kendi adının ilk bölümüdür.", "Beş harfli çağrı adı N ile başlar ve R ile biter."]},
    "M1": {"title": "İki Konsol Senkronu", "kind": "META", "dependencies": ["G1", "G2"], "answer_type": "SIMULTANEOUS_INPUT", "answer_format": "Her oyuncu kendi konsol kodunu girer", "solution": {"ENGINEER": "ION", "NAVIGATOR": "K4"}, "owner_role": "ALL", "grant": "flight_key", "required": True, "hints": ["Her rol yalnız kendi özel konsol değerini göndermeli.", "Mühendis güç sözcüğünü, Navigatör koordinatı girer.", "Değerler sırasıyla bir sözcük ve harf+rakam biçimindedir."]},
    "F1": {"title": "Tahliye Dizisi", "kind": "FINAL", "dependencies": ["M1", "G1", "G2"], "answer_type": "ORDERED_SEQUENCE", "answer_format": "ANAHTAR-MUHUR-UCUS", "solution": "ANAHTAR-MUHUR-UCUS", "owner_role": "ANY", "grant": None, "required": True, "hints": ["Üç kritik item'i kullanım sırasına koyun.", "Önce yetkilendirme yapılır, uçuş anahtarı en son kullanılır.", "Yetki anahtarı, soğutma mührü ve uçuş anahtarı sırasını yazın."]},
}

PRIVATE_CLUES_TWO = {
    "ENGINEER": {"E0": "İlk ışık değeri 3.", "P1": "Topoloji: A, B ve C'ye; C de F'ye bağlı.", "P2": "Güç katmanı K2, K4 ve M4 hücrelerini işaretliyor.", "G1": "Güvenli rotanın tek bir çıkışı var.", "G2": "Güç hattında dış iki valf aynı yönde ve sola çevrili olmalı.", "M1": "Konsol kodun: ION", "F1": "Yetki anahtarı ilk kullanılmalı."},
    "NAVIGATOR": {"E0": "Son ışık değeri 7.", "P1": "B düğümü karantina riski taşıyor; hedef düğüm F.", "P2": "Navigasyon katmanı K3, K4 ve L4 hücrelerini işaretliyor.", "G1": "Arşiv şeridinde 47 damgası bulunuyor.", "G2": "Orta valf sağa çevrilmeli.", "O1": "İstasyon çağrı adı NADİR-3'ün beş harfli köküdür.", "M1": "Konsol kodun: K4", "F1": "Uçuş anahtarı dizinin son adımıdır."},
}


CONTENT_SETS = {
    "nadir3-v1": {"roles": ROLES, "puzzles": PUZZLES, "clues": PRIVATE_CLUES},
    "nadir2-v1": {"roles": ROLES_TWO, "puzzles": PUZZLES_TWO, "clues": PRIVATE_CLUES_TWO},
}


def rules_version_for(seat_count: int) -> str:
    """Koltuk sayısına göre kullanılacak içerik seti. AI dolu koltuk da koltuktur."""
    return "nadir2-v1" if seat_count == 2 else "nadir3-v1"


def content_for(rules_version: str) -> dict:
    return CONTENT_SETS[rules_version]


def validate_graph(puzzles: dict, roles: list[str]) -> None:
    for node_id, puzzle in puzzles.items():
        for dependency in puzzle["dependencies"]:
            if dependency not in puzzles: raise ValueError(f"missing dependency {dependency}")
            if puzzle["required"] and not puzzles[dependency]["required"]: raise ValueError(f"required node {node_id} depends on optional {dependency}")
        if puzzle["owner_role"] not in {"ANY", "ALL", *roles}: raise ValueError(f"node {node_id} belongs to an unknown role")
        if puzzle["answer_type"] == "SIMULTANEOUS_INPUT" and set(puzzle["solution"]) != set(roles):
            raise ValueError(f"node {node_id} needs one code per role")
    visiting: set[str] = set(); visited: set[str] = set()
    def visit(node_id: str) -> None:
        if node_id in visiting: raise ValueError("puzzle graph has a cycle")
        if node_id in visited: return
        visiting.add(node_id)
        for dependency in puzzles[node_id]["dependencies"]: visit(dependency)
        visiting.remove(node_id); visited.add(node_id)
    for required_id, puzzle in puzzles.items():
        if puzzle["required"]: visit(required_id)
    if "F1" not in visited: raise ValueError("final is unreachable")


for _version, _set in CONTENT_SETS.items():
    validate_graph(_set["puzzles"], _set["roles"])

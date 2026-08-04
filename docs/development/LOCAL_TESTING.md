# Yerel Otomatik Testler

Bu akış kaynak kodunu uzak Git deposuna göndermez ve herhangi bir commit oluşturmaz.

İlk çalıştırma:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test-local.ps1 -Install
```

Sonraki çalıştırmalar:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test-local.ps1
```

Komut sırasıyla backend testlerini, Alembic migration zincirini, FastAPI rota kaydını, AI Gateway
testlerini ve frontend TypeScript kontrolünü çalıştırır. Python bağımlılıkları depo kökündeki Git
tarafından yok sayılan `.venv` dizisinde tutulur.

İnsan kabul testleri tüm oyun modülleri tamamlandıktan sonra ayrıca yürütülecektir. Bu komut,
geliştirme boyunca tekrarlanabilir regresyon kontrolü sağlamak içindir.

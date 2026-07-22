from __future__ import annotations

import asyncio

_main_loop: asyncio.AbstractEventLoop | None = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop


def get_main_loop() -> asyncio.AbstractEventLoop:
    """Uvicorn'un çalıştırdığı ana asyncio event loop'u.

    Plugin handler'ları senkron bir threadpool thread'inde çalışır (FastAPI'nin sync `def`
    endpoint davranışı); aiortc gibi async işler gerektiren plugin'ler bu loop'a
    `asyncio.run_coroutine_threadsafe` ile iş verir. `app/main.py`'nin startup event'inde set edilir.
    """
    if _main_loop is None:
        raise RuntimeError("Ana event loop henüz ayarlanmadı (uygulama startup'ı tamamlanmamış olabilir)")
    return _main_loop

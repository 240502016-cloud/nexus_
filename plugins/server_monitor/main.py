import os
import platform
import shutil


def handle_command(context):
    """plugin.json'daki entry_point ('main:handle_command') tarafından çağrılır.

    `context` bir app.plugins_engine.context.PluginContext'tir; bu plugin şu an
    içeriğini kullanmıyor, ama Plugin API sözleşmesi gereği parametre olarak alınır.
    """
    total, used, _free = shutil.disk_usage("/")
    gb = 2**30

    return (
        f"Platform: {platform.system()} {platform.release()}\n"
        f"CPU çekirdek sayısı: {os.cpu_count()}\n"
        f"Disk: {used // gb}GB kullanılan / {total // gb}GB toplam"
    )

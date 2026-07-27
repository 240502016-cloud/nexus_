import unittest
from unittest.mock import patch

from app.config import settings
from app.plugins_engine.loader import PluginRegistry
from app.plugins_engine.manifest import PluginManifest


def manifest(name: str) -> PluginManifest:
    return PluginManifest(
        name=name,
        version="1.0",
        entry_point="main:handle_command",
        commands=["test"],
    )


class PluginLoaderTests(unittest.TestCase):
    def test_trusted_core_plugins_stay_local_in_production_sandbox_mode(self):
        local_handler = lambda _context: "local"
        for name in ("ai_assistant", "moderation", "music"):
            registry = PluginRegistry()
            with (
                patch.object(settings, "plugin_execution_mode", "sandbox"),
                patch("app.plugins_engine.loader.load_handler", return_value=local_handler) as local,
                patch("app.plugins_engine.loader._sandbox_handler") as sandbox,
            ):
                registry.load(manifest(name))
            local.assert_called_once()
            sandbox.assert_not_called()
            self.assertIs(registry.get_handler("test").handler, local_handler)

    def test_other_plugins_remain_isolated_in_sandbox_mode(self):
        registry = PluginRegistry()
        sandbox_handler = lambda _context: "sandbox"
        with (
            patch.object(settings, "plugin_execution_mode", "sandbox"),
            patch("app.plugins_engine.loader.load_handler") as local,
            patch("app.plugins_engine.loader._sandbox_handler", return_value=sandbox_handler) as sandbox,
        ):
            registry.load(manifest("third_party"))
        local.assert_not_called()
        sandbox.assert_called_once()
        self.assertIs(registry.get_handler("test").handler, sandbox_handler)


if __name__ == "__main__":
    unittest.main()

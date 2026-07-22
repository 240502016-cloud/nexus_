"""One-shot plugin runner; the parent sandbox process kills it on timeout."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from app.plugins_engine.context import PluginContext


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: runner MODULE_PATH FUNCTION", file=sys.stderr)
        return 2
    module_path = Path(sys.argv[1]).resolve()
    function_name = sys.argv[2]
    spec = importlib.util.spec_from_file_location("nexus_sandbox_plugin", module_path)
    if spec is None or spec.loader is None:
        print("plugin module yüklenemedi", file=sys.stderr)
        return 2
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    handler = getattr(module, function_name, None)
    if not callable(handler):
        print("plugin handler bulunamadı", file=sys.stderr)
        return 2
    context = PluginContext(**json.load(sys.stdin))
    output = handler(context)
    if hasattr(output, "job_id"):
        # Queue-backed AI jobs need the Core process and are intentionally not allowed
        # to smuggle arbitrary objects across the sandbox boundary.
        output = str(output)
    print(json.dumps({"output": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

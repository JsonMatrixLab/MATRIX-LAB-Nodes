"""Load the hyphenated checkout as one valid, named Python package."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
from unittest import mock


TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
PACKAGE_NAME = "matrix_lab_nodes"

# One legacy compatibility module imports ``test_distribution`` by its bare
# unittest-discover name. Expose only the tests directory; the repository root
# stays off sys.path so pytest cannot collect its ``__init__.py`` as a package.
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))


def _host_import_stubs() -> dict[str, types.ModuleType]:
    def unavailable(*_args, **_kwargs):
        raise AssertionError("runtime-only ComfyUI API called during offline collection")

    class SocketType:
        Input = staticmethod(lambda socket_id, **options: types.SimpleNamespace(id=socket_id, **options))
        Output = staticmethod(lambda socket_id="output", **options: types.SimpleNamespace(id=socket_id, **options))

    io = types.SimpleNamespace(
        ComfyNode=object,
        Schema=lambda **values: types.SimpleNamespace(**values),
        Video=SocketType,
        String=SocketType,
        NodeOutput=lambda *values, **_options: values,
        FolderType=types.SimpleNamespace(output="output"),
    )
    latest = types.ModuleType("comfy_api.latest")
    latest.InputImpl = types.SimpleNamespace(VideoFromFile=unavailable)
    latest.io = io
    latest.ui = types.SimpleNamespace(PreviewVideo=unavailable, SavedResult=unavailable)
    comfy_api = types.ModuleType("comfy_api")
    comfy_api.latest = latest
    folder_paths = types.ModuleType("folder_paths")
    folder_paths.get_output_directory = unavailable
    folder_paths.get_save_image_path = unavailable
    runtime_bootstrap = types.ModuleType(f"{PACKAGE_NAME}._core.runtime_bootstrap")
    runtime_bootstrap.bootstrap_runtime = lambda: None
    return {
        "folder_paths": folder_paths,
        "comfy_api": comfy_api,
        "comfy_api.latest": latest,
        f"{PACKAGE_NAME}._core.runtime_bootstrap": runtime_bootstrap,
    }


if PACKAGE_NAME not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        PACKAGE_NAME,
        ROOT / "__init__.py",
        submodule_search_locations=[str(ROOT)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {ROOT} as {PACKAGE_NAME}")
    package = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE_NAME] = package
    try:
        with mock.patch.dict(sys.modules, _host_import_stubs()):
            spec.loader.exec_module(package)
    except BaseException:
        sys.modules.pop(PACKAGE_NAME, None)
        raise

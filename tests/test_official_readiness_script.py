import importlib.util
from pathlib import Path
from urllib.error import HTTPError


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_script_module():
    path = PROJECT_ROOT / "scripts/check_official_close_readiness.py"
    spec = importlib.util.spec_from_file_location(
        "check_official_close_readiness",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_http_error_becomes_non_ready_source_status(monkeypatch):
    module = _load_script_module()

    def forbidden(url):
        raise HTTPError(url, 403, "forbidden", {}, None)

    monkeypatch.setattr(module, "fetch_official_source", forbidden)
    close, status, blocker = module._load_official_close(
        "https://www.tpex.org.tw/openapi/v1/example",
        "00719B",
    )

    assert close is None
    assert status == {
        "available": False,
        "error": "HTTP 403",
        "url": "https://www.tpex.org.tw/openapi/v1/example",
    }
    assert blocker == "00719B official source unavailable (HTTP 403)"

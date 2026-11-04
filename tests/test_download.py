"""The downloader against a local imitation of the OCP Data Registry."""

import copy
import gzip
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from procontrol.config import Config
from procontrol.download import DownloadError, download

GOOD = gzip.compress((json.dumps({"ocid": "ocds-abcdef-1", "id": "1"}) + "\n").encode())
STATE = {"flaky": 0}


class Registry(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence
        pass

    def do_GET(self):
        p = self.path
        if p.startswith("/en/publications.json"):
            body = json.dumps([{"id": 135, "title": "OECE", "country": "Peru",
                                "date_from": "2015-01-01", "date_to": "2026-10-01"}]).encode()
            return self._send(200, body, "application/json")
        if "name=2024.jsonl.gz" in p:  # redirect to the downloads server, like the registry
            self.send_response(302)
            self.send_header("Location", "/downloads/2024.jsonl.gz")
            return self.end_headers()
        if p == "/downloads/2024.jsonl.gz":
            return self._send(200, GOOD, "application/gzip")
        if "name=2023.jsonl.gz" in p:  # fails once, then works
            STATE["flaky"] += 1
            if STATE["flaky"] == 1:
                return self._send(503, b"busy", "text/plain")
            return self._send(200, GOOD, "application/gzip")
        if "name=2022.jsonl.gz" in p:  # not gzip: an HTML error page
            return self._send(200, b"<html>maintenance</html>", "text/html")
        return self._send(404, b"File not found", "text/plain")

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture()
def registry():
    srv = HTTPServer(("127.0.0.1", 0), Registry)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def cfg_for(base, tmp_path, pub=135):
    cfg = copy.deepcopy(Config.load())
    reg = cfg.settings["registry"]
    reg["base_url"] = base + "/en/publication/{publication_id}/download?name={name}"
    reg["publications_api"] = base + "/en/publications.json"
    reg["publications"]["oece"]["publication_id"] = pub
    reg["backoff_seconds"] = 0
    reg["retries"] = 3
    cfg.settings["paths"]["raw_dir"] = str(tmp_path / "raw")
    return cfg


def test_downloads_follows_redirect_skips_missing_year_and_logs(registry, tmp_path, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    paths, record = download(cfg_for(registry, tmp_path), "oece", [2024, 2025])
    assert [p.name for p in paths] == ["2024.jsonl.gz"]
    status = {f["year"]: f["status"] for f in record["files"]}
    assert status == {2024: "descargado", 2025: "no existe"}
    assert record["files"][0]["sha256"] and record["publication"]["title"] == "OECE"
    assert (tmp_path / "raw" / "oece" / "registro_descargas.json").exists()


def test_retries_after_server_error(registry, tmp_path, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    STATE["flaky"] = 0
    paths, record = download(cfg_for(registry, tmp_path), "oece", [2023])
    assert len(paths) == 1 and record["files"][0]["attempts"] == 2


def test_rejects_non_gzip_payload(registry, tmp_path, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    with pytest.raises(DownloadError, match="no es un archivo comprimido"):
        download(cfg_for(registry, tmp_path), "oece", [2022])


def test_unknown_publication_is_a_clear_error(registry, tmp_path, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    with pytest.raises(DownloadError, match="no aparece en el registro"):
        download(cfg_for(registry, tmp_path, pub=999), "oece", [2024])


def test_no_year_available_is_a_clear_error(registry, tmp_path, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    with pytest.raises(DownloadError, match="No se descargó ningún año"):
        download(cfg_for(registry, tmp_path), "oece", [2019])

from __future__ import annotations

import os
from pathlib import Path

import pytest

from repolens.graph import (
    GraphExportError,
    GraphStoreError,
    build_graph_store,
    export_graph_artifacts,
)
from repolens.scanner import scan_repository


def test_graph_store_rebuild_leaves_existing_database_when_replace_fails(tmp_path, monkeypatch):
    (tmp_path / ".repolens").mkdir()
    (tmp_path / "app.py").write_text("print('ok')\n", encoding="utf-8")
    scan = scan_repository(tmp_path)
    build_graph_store(tmp_path, scan)
    graph_store = tmp_path / ".repolens" / "graph.sqlite"
    original_store = graph_store.read_bytes()
    real_replace = os.replace

    def fail_graph_store_replace(source, target):
        if Path(target).name == "graph.sqlite":
            raise OSError("simulated replace failure")
        real_replace(source, target)

    monkeypatch.setattr("repolens.graph.os.replace", fail_graph_store_replace)

    with pytest.raises(GraphStoreError, match="graph_store_rebuild_failed"):
        build_graph_store(tmp_path, scan)

    assert graph_store.read_bytes() == original_store


def test_graph_export_leaves_existing_artifact_when_replace_fails(tmp_path, monkeypatch):
    (tmp_path / ".repolens").mkdir()
    (tmp_path / "app.py").write_text("print('ok')\n", encoding="utf-8")
    scan = scan_repository(tmp_path)
    build_graph_store(tmp_path, scan)
    export_graph_artifacts(tmp_path)
    graph_export = tmp_path / ".repolens" / "graph.json"
    original_export = graph_export.read_text(encoding="utf-8")
    real_replace = os.replace

    def fail_graph_json_replace(source, target):
        if Path(target).name == "graph.json":
            raise OSError("simulated replace failure")
        real_replace(source, target)

    monkeypatch.setattr("repolens.graph.os.replace", fail_graph_json_replace)

    with pytest.raises(GraphExportError, match="graph_export_write_failed"):
        export_graph_artifacts(tmp_path)

    assert graph_export.read_text(encoding="utf-8") == original_export

from __future__ import annotations

from textwrap import dedent

from repolens.javascript_index import extract_javascript_index
from repolens.scanner import scan_repository


def test_javascript_index_supports_scanner_approved_source_extensions(tmp_path):
    for extension in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts"):
        _write_text(tmp_path / f"src/module{extension}", 'import dep from "pkg";\n')

    scan = scan_repository(tmp_path)
    javascript_index = extract_javascript_index(tmp_path, scan.files)

    assert {module.path for module in javascript_index.modules} == {
        "src/module.cjs",
        "src/module.cts",
        "src/module.js",
        "src/module.jsx",
        "src/module.mjs",
        "src/module.mts",
        "src/module.ts",
        "src/module.tsx",
    }
    assert {module.parser_status for module in javascript_index.modules} == {"parsed"}
    assert len(javascript_index.imports) == 8


def test_javascript_index_extracts_imports_and_classifies_packages(tmp_path):
    _write_text(
        tmp_path / "src" / "app.ts",
        dedent(
            """
            import React from "react";
            import { map } from "lodash/fp";
            import * as path from "node:path";
            import "zone.js";
            const fs = require("fs");
            const scoped = require("@scope/pkg/sub/path");
            const local = require("./local");
            const dynamic = import("kleur/colors");
            // import ignored from "comment-only";
            const text = "require('not-real')";
            """
        ).lstrip(),
    )

    scan = scan_repository(tmp_path)
    javascript_index = extract_javascript_index(tmp_path, scan.files)

    imports = {(item.kind, item.specifier): item for item in javascript_index.imports}
    assert imports[("default_import", "react")].root_name == "react"
    assert imports[("named_import", "lodash/fp")].root_name == "lodash"
    assert imports[("namespace_import", "node:path")].classification == "node_builtin"
    assert imports[("namespace_import", "node:path")].root_name == "path"
    assert imports[("side_effect_import", "zone.js")].root_name == "zone.js"
    assert imports[("require", "fs")].classification == "node_builtin"
    assert imports[("require", "@scope/pkg/sub/path")].root_name == "@scope/pkg"
    assert imports[("require", "./local")].classification == "local_unresolved"
    assert imports[("require", "./local")].root_name is None
    assert imports[("dynamic_import", "kleur/colors")].root_name == "kleur"

    packages = {(package.classification, package.name) for package in javascript_index.packages}
    assert packages == {
        ("node_builtin", "fs"),
        ("node_builtin", "path"),
        ("third_party", "@scope/pkg"),
        ("third_party", "kleur"),
        ("third_party", "lodash"),
        ("third_party", "react"),
        ("third_party", "zone.js"),
    }
    assert "comment-only" not in {item.specifier for item in javascript_index.imports}
    assert "not-real" not in {item.specifier for item in javascript_index.imports}


def _write_text(path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

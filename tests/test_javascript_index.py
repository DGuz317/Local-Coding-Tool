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


def test_javascript_index_resolves_relative_imports_with_extension_and_index_probing(tmp_path):
    _write_text(tmp_path / "src" / "lib" / "format.ts", "export const format = () => 'ok';\n")
    _write_text(tmp_path / "src" / "ui" / "index.tsx", "export const Ui = () => null;\n")
    _write_text(tmp_path / "src" / "exact.js", "module.exports = {};\n")
    _write_text(
        tmp_path / "src" / "app" / "main.ts",
        dedent(
            """
            import { format } from "../lib/format";
            import { Ui } from "../ui";
            const exact = require("../exact.js");
            const dynamic = import("../lib/format");
            """
        ).lstrip(),
    )

    scan = scan_repository(tmp_path)
    javascript_index = extract_javascript_index(tmp_path, scan.files)

    imports = {(item.kind, item.specifier): item for item in javascript_index.imports}
    assert imports[("named_import", "../lib/format")].classification == "local_resolved"
    assert imports[("named_import", "../lib/format")].root_name is None
    assert imports[("named_import", "../lib/format")].resolved_path == "src/lib/format.ts"
    assert imports[("named_import", "../lib/format")].resolution_status == "resolved_relative"
    assert imports[("named_import", "../ui")].resolved_path == "src/ui/index.tsx"
    assert imports[("require", "../exact.js")].resolved_path == "src/exact.js"
    assert imports[("dynamic_import", "../lib/format")].resolved_path == "src/lib/format.ts"


def test_javascript_index_leaves_ambiguous_and_unresolved_relative_imports_unresolved(tmp_path):
    _write_text(tmp_path / "src" / "lib" / "ambiguous.ts", "export const value = 1;\n")
    _write_text(tmp_path / "src" / "lib" / "ambiguous.tsx", "export const value = 1;\n")
    _write_text(
        tmp_path / "src" / "app" / "main.ts",
        dedent(
            """
            import ambiguous from "../lib/ambiguous";
            import missing from "../lib/missing";
            import absolute from "/src/lib/ambiguous";
            import packageName from "next/image";
            """
        ).lstrip(),
    )

    scan = scan_repository(tmp_path)
    javascript_index = extract_javascript_index(tmp_path, scan.files)

    imports = {item.specifier: item for item in javascript_index.imports}
    assert imports["../lib/ambiguous"].classification == "local_unresolved"
    assert imports["../lib/ambiguous"].resolved_path is None
    assert imports["../lib/ambiguous"].resolution_status == "unresolved_ambiguous_relative"
    assert imports["../lib/missing"].classification == "local_unresolved"
    assert imports["../lib/missing"].resolution_status == "unresolved_missing_relative"
    assert imports["/src/lib/ambiguous"].classification == "local_unresolved"
    assert imports["/src/lib/ambiguous"].resolution_status == "unresolved_unsupported_absolute"
    assert imports["next/image"].classification == "third_party"


def test_javascript_index_extracts_symbols_exports_and_commonjs_assignments(tmp_path):
    _write_text(
        tmp_path / "src" / "app.tsx",
        dedent(
            """
            export function exportedFunction() {
              return "ok";
            }

            function helper() {
              return "helper";
            }

            export const makeThing = (value: string) => value;
            export const version = "1.0.0";
            const localArrow = async (value: string) => value;

            export class Widget {}
            class Internal {}

            export interface WidgetProps { label: string }
            interface LocalShape { id: string }

            export type WidgetKind = "primary" | "secondary";
            type LocalAlias = string;

            export default Widget;
            export { helper, Internal as PublicInternal };

            module.exports = Widget;
            exports.helper = helper;

            function outer() {
              function nested() {}
              const nestedArrow = () => null;
              class Nested {}
            }
            """
        ).lstrip(),
    )

    scan = scan_repository(tmp_path)
    javascript_index = extract_javascript_index(tmp_path, scan.files)

    symbols = {(item.kind, item.name): item for item in javascript_index.symbols}
    assert set(symbols) == {
        ("arrow_function", "localArrow"),
        ("arrow_function", "makeThing"),
        ("class", "Internal"),
        ("class", "Widget"),
        ("function", "exportedFunction"),
        ("function", "helper"),
        ("function", "outer"),
        ("interface", "LocalShape"),
        ("interface", "WidgetProps"),
        ("type_alias", "LocalAlias"),
        ("type_alias", "WidgetKind"),
    }
    assert all(item.line == item.start_line == item.end_line for item in symbols.values())
    assert ("function", "nested") not in symbols
    assert ("arrow_function", "nestedArrow") not in symbols
    assert ("class", "Nested") not in symbols

    exports = {
        (item.kind, item.exported_name, item.local_name) for item in javascript_index.exports
    }
    assert exports == {
        ("class_export", "Widget", "Widget"),
        ("const_export", "makeThing", "makeThing"),
        ("const_export", "version", "version"),
        ("default_export", "default", "Widget"),
        ("function_export", "exportedFunction", "exportedFunction"),
        ("named_export", "PublicInternal", "Internal"),
        ("named_export", "helper", "helper"),
    }

    commonjs_assignments = {
        (item.kind, item.exported_name, item.assigned_name)
        for item in javascript_index.commonjs_assignments
    }
    assert commonjs_assignments == {
        ("exports_property", "helper", "helper"),
        ("module_exports", "module.exports", "Widget"),
    }


def test_javascript_index_resolves_simple_typescript_path_aliases(tmp_path):
    _write_text(
        tmp_path / "tsconfig.json",
        dedent(
            """
            {
              // TypeScript config JSON commonly permits comments.
              "compilerOptions": {
                "baseUrl": ".",
                "paths": {
                  "@/*": ["src/*"],
                  "@app/*": ["src/app/*"],
                },
              },
            }
            """
        ).lstrip(),
    )
    _write_text(tmp_path / "src" / "shared" / "format.ts", "export const format = () => 'ok';\n")
    _write_text(tmp_path / "src" / "app" / "entry.tsx", "export const Entry = () => null;\n")
    _write_text(
        tmp_path / "src" / "main.ts",
        dedent(
            """
            import { format } from "@/shared/format";
            import { Entry } from "@app/entry";
            import React from "react";
            """
        ).lstrip(),
    )

    scan = scan_repository(tmp_path)
    javascript_index = extract_javascript_index(tmp_path, scan.files)

    imports = {item.specifier: item for item in javascript_index.imports}
    assert imports["@/shared/format"].classification == "local_resolved"
    assert imports["@/shared/format"].root_name is None
    assert imports["@/shared/format"].resolved_path == "src/shared/format.ts"
    assert imports["@/shared/format"].resolution_status == "resolved_alias"
    assert imports["@app/entry"].resolved_path == "src/app/entry.tsx"
    assert imports["react"].classification == "third_party"

    packages = {(package.classification, package.name) for package in javascript_index.packages}
    assert packages == {("third_party", "react")}


def test_javascript_index_leaves_complex_aliases_unresolved_without_packages(tmp_path):
    _write_text(
        tmp_path / "tsconfig.json",
        dedent(
            """
            {
              "compilerOptions": {
                "paths": {
                  "@ambiguous/*": ["src/*", "lib/*"],
                  "@missing/*": ["src/missing/*"]
                }
              }
            }
            """
        ).lstrip(),
    )
    _write_text(tmp_path / "src" / "app.ts", 'import thing from "@ambiguous/thing";\n')
    _write_text(tmp_path / "src" / "other.ts", 'import missing from "@missing/thing";\n')

    scan = scan_repository(tmp_path)
    javascript_index = extract_javascript_index(tmp_path, scan.files)

    imports = {item.specifier: item for item in javascript_index.imports}
    assert imports["@ambiguous/thing"].classification == "local_unresolved"
    assert imports["@ambiguous/thing"].root_name is None
    assert imports["@ambiguous/thing"].resolved_path is None
    assert imports["@ambiguous/thing"].resolution_status == "unresolved_complex_alias"
    assert imports["@missing/thing"].classification == "local_unresolved"
    assert imports["@missing/thing"].resolved_path is None
    assert imports["@missing/thing"].resolution_status == "unresolved_missing_alias"
    assert javascript_index.packages == ()


def test_javascript_fact_ids_do_not_use_line_numbers_as_primary_identity(tmp_path):
    _write_text(
        tmp_path / "src" / "module.ts",
        "function stable() {}\nexport { stable };\nexports.stable = stable;\n",
    )
    first_index = extract_javascript_index(tmp_path, scan_repository(tmp_path).files)

    _write_text(
        tmp_path / "src" / "module.ts",
        "\n\nfunction stable() {}\nexport { stable };\nexports.stable = stable;\n",
    )
    second_index = extract_javascript_index(tmp_path, scan_repository(tmp_path).files)

    assert {item.id for item in second_index.symbols} == {item.id for item in first_index.symbols}
    assert {item.id for item in second_index.exports} == {item.id for item in first_index.exports}
    assert {item.id for item in second_index.commonjs_assignments} == {
        item.id for item in first_index.commonjs_assignments
    }
    assert first_index.symbols[0].line == 1
    assert second_index.symbols[0].line == 3


def _write_text(path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

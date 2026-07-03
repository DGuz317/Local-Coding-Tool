from __future__ import annotations

from dataclasses import fields
from textwrap import dedent
from types import SimpleNamespace

from repolens.javascript_index import (
    EXPERIMENTAL_JAVASCRIPT_FACT_POLICY,
    JAVASCRIPT_EXTRACTOR_VERSION,
    PROMOTED_JAVASCRIPT_FACT_FIELDS,
    PROMOTED_JAVASCRIPT_FACT_SCHEMA_VERSION,
    JavaScriptCallChainFact,
    JavaScriptCommonJSAssignmentFact,
    JavaScriptExportFact,
    JavaScriptImportFact,
    JavaScriptModuleFact,
    JavaScriptPackageFact,
    JavaScriptParserProvenance,
    JavaScriptSymbolFact,
    TreeSitterJavaScriptSupport,
    extract_javascript_index,
    extract_javascript_index_with_tree_sitter,
)
from repolens.scanner import scan_repository


def test_promoted_javascript_fact_contract_allows_only_source_free_fields():
    assert PROMOTED_JAVASCRIPT_FACT_SCHEMA_VERSION in JAVASCRIPT_EXTRACTOR_VERSION
    assert "Canonical Graph Hash" in EXPERIMENTAL_JAVASCRIPT_FACT_POLICY
    assert "source snippets" in EXPERIMENTAL_JAVASCRIPT_FACT_POLICY

    assert PROMOTED_JAVASCRIPT_FACT_FIELDS == {
        "modules": tuple(field.name for field in fields(JavaScriptModuleFact)),
        "imports": tuple(field.name for field in fields(JavaScriptImportFact)),
        "packages": tuple(field.name for field in fields(JavaScriptPackageFact)),
        "symbols": tuple(field.name for field in fields(JavaScriptSymbolFact)),
        "exports": tuple(field.name for field in fields(JavaScriptExportFact)),
        "commonjs_assignments": tuple(
            field.name for field in fields(JavaScriptCommonJSAssignmentFact)
        ),
        "call_chains": tuple(field.name for field in fields(JavaScriptCallChainFact)),
    }

    forbidden_terms = {
        "absolute",
        "body",
        "comment",
        "expression",
        "signature",
        "snippet",
        "source",
    }
    for allowed_fields in PROMOTED_JAVASCRIPT_FACT_FIELDS.values():
        for field_name in allowed_fields:
            assert not any(term in field_name for term in forbidden_terms)


def test_javascript_index_extracts_source_free_call_chain_facts(tmp_path):
    _write_text(
        tmp_path / "src" / "query.ts",
        dedent(
            """
            export function loadUsers() {
              return db.select().from().where();
            }

            const ignored = "client.get().post()";
            const single = client.get();
            const built = new Builder().step().finish();
            """
        ).lstrip(),
    )

    javascript_index = extract_javascript_index(tmp_path, scan_repository(tmp_path).files)

    chains = {
        (chain.start_line, chain.receiver_shape): chain for chain in javascript_index.call_chains
    }
    assert set(chains) == {(2, "identifier"), (7, "new_expression")}
    assert chains[(2, "identifier")].method_names == ("select", "from", "where")
    assert chains[(2, "identifier")].end_line == 2
    assert chains[(2, "identifier")].enclosing_symbol_id is not None
    assert chains[(2, "identifier")].parser_evidence_labels == (
        "line_local_member_call_sequence",
        "source_free_shape",
    )
    assert chains[(7, "new_expression")].method_names == ("step", "finish")

    serialized = repr(javascript_index.call_chains)
    assert "db.select" not in serialized
    assert "client.get" not in serialized
    assert "new Builder" not in serialized


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
    assert imports[("named_import", "../lib/format")].outcome_class == "resolved_edge"
    assert imports[("named_import", "../lib/format")].evidence_labels == (
        "javascript_import_specifier",
    )
    assert imports[("named_import", "../lib/format")].candidate_paths == ()
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
    assert imports["../lib/ambiguous"].outcome_class == "relationship_candidate"
    assert imports["../lib/ambiguous"].candidate_paths == (
        "src/lib/ambiguous.ts",
        "src/lib/ambiguous.tsx",
    )
    assert imports["../lib/missing"].classification == "local_unresolved"
    assert imports["../lib/missing"].resolution_status == "unresolved_missing_relative"
    assert imports["/src/lib/ambiguous"].classification == "local_unresolved"
    assert imports["/src/lib/ambiguous"].resolution_status == "unresolved_unsupported_absolute"
    assert imports["/src/lib/ambiguous"].outcome_class == "unsupported"
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
            export { value as ReExportedValue } from "./value";

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
    assert symbols[("function", "exportedFunction")].start_line == 1
    assert symbols[("function", "exportedFunction")].end_line == 3
    assert symbols[("function", "helper")].start_line == 5
    assert symbols[("function", "helper")].end_line == 7
    assert symbols[("function", "outer")].start_line == 29
    assert symbols[("function", "outer")].end_line == 33
    assert symbols[("arrow_function", "makeThing")].start_line == 9
    assert symbols[("arrow_function", "makeThing")].end_line == 9
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
        ("named_export", "ReExportedValue", "value"),
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
    assert imports["@/shared/format"].evidence_labels == (
        "javascript_import_specifier",
        "typescript_path_alias",
    )
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
    assert imports["@ambiguous/thing"].outcome_class == "unsupported"
    assert imports["@missing/thing"].classification == "local_unresolved"
    assert imports["@missing/thing"].resolved_path is None
    assert imports["@missing/thing"].resolution_status == "unresolved_missing_alias"
    assert javascript_index.packages == ()


def test_javascript_index_scopes_typescript_path_aliases_to_config_subtree(tmp_path):
    _write_text(
        tmp_path / "packages" / "app" / "tsconfig.json",
        '{"compilerOptions":{"baseUrl":".","paths":{"@app/*":["src/*"]}}}\n',
    )
    _write_text(tmp_path / "packages" / "app" / "src" / "feature.ts", "export const feature = 1;\n")
    _write_text(
        tmp_path / "packages" / "app" / "src" / "main.ts",
        'import { feature } from "@app/feature";\n',
    )
    _write_text(
        tmp_path / "packages" / "other" / "src" / "main.ts",
        'import { feature } from "@app/feature";\n',
    )

    javascript_index = extract_javascript_index(tmp_path, scan_repository(tmp_path).files)

    imports = {(item.path, item.specifier): item for item in javascript_index.imports}
    in_scope = imports[("packages/app/src/main.ts", "@app/feature")]
    out_of_scope = imports[("packages/other/src/main.ts", "@app/feature")]
    assert in_scope.classification == "local_resolved"
    assert in_scope.resolved_path == "packages/app/src/feature.ts"
    assert in_scope.resolution_status == "resolved_alias"
    assert out_of_scope.classification == "local_unresolved"
    assert out_of_scope.resolved_path is None
    assert out_of_scope.resolution_status == "unresolved_out_of_scope_alias"


def test_javascript_index_resolves_exact_path_aliases_and_base_url_imports(tmp_path):
    _write_text(
        tmp_path / "app" / "tsconfig.json",
        dedent(
            """
            {
              "compilerOptions": {
                "baseUrl": "src",
                "paths": {
                  "@settings": ["config/settings.ts"]
                }
              }
            }
            """
        ).lstrip(),
    )
    _write_text(
        tmp_path / "app" / "src" / "config" / "settings.ts", "export const settings = {};\n"
    )
    _write_text(tmp_path / "app" / "src" / "shared" / "format.ts", "export const format = '';\n")
    _write_text(
        tmp_path / "app" / "src" / "main.ts",
        dedent(
            """
            import { settings } from "@settings";
            import { format } from "shared/format";
            import React from "react";
            """
        ).lstrip(),
    )

    javascript_index = extract_javascript_index(tmp_path, scan_repository(tmp_path).files)

    imports = {item.specifier: item for item in javascript_index.imports}
    assert imports["@settings"].resolved_path == "app/src/config/settings.ts"
    assert imports["@settings"].resolution_status == "resolved_alias"
    assert imports["shared/format"].resolved_path == "app/src/shared/format.ts"
    assert imports["shared/format"].resolution_status == "resolved_base_url"
    assert imports["shared/format"].evidence_labels == (
        "javascript_import_specifier",
        "typescript_base_url",
    )
    assert imports["react"].classification == "third_party"
    assert imports["react"].resolution_status == "external"


def test_javascript_index_marks_ambiguous_scoped_alias_matches_unresolved(tmp_path):
    _write_text(
        tmp_path / "tsconfig.json",
        '{"compilerOptions":{"paths":{"@/*":["src/*"]}}}\n',
    )
    _write_text(
        tmp_path / "packages" / "app" / "tsconfig.json",
        '{"compilerOptions":{"paths":{"@/*":["src/*"]}}}\n',
    )
    _write_text(tmp_path / "src" / "shared" / "format.ts", "export const format = 1;\n")
    _write_text(
        tmp_path / "packages" / "app" / "src" / "shared" / "format.ts",
        "export const format = 2;\n",
    )
    _write_text(
        tmp_path / "packages" / "app" / "src" / "main.ts",
        'import { format } from "@/shared/format";\n',
    )

    javascript_index = extract_javascript_index(tmp_path, scan_repository(tmp_path).files)

    import_fact = javascript_index.imports[0]
    assert import_fact.classification == "local_unresolved"
    assert import_fact.resolved_path is None
    assert import_fact.resolution_status == "unresolved_ambiguous_alias"
    assert import_fact.outcome_class == "relationship_candidate"
    assert import_fact.candidate_paths == (
        "packages/app/src/shared/format.ts",
        "src/shared/format.ts",
    )


def test_javascript_index_represents_deterministic_re_export_imports(tmp_path):
    _write_text(tmp_path / "src" / "value.ts", "export const value = 1;\n")
    _write_text(tmp_path / "src" / "index.ts", 'export { value } from "./value";\n')

    javascript_index = extract_javascript_index(tmp_path, scan_repository(tmp_path).files)

    imports = {(item.kind, item.specifier): item for item in javascript_index.imports}
    assert imports[("re_export", "./value")].resolved_path == "src/value.ts"
    assert imports[("re_export", "./value")].resolution_status == "resolved_relative"
    assert imports[("re_export", "./value")].outcome_class == "resolved_edge"


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


def test_tree_sitter_javascript_index_reports_parse_failure_without_facts(tmp_path):
    _write_text(tmp_path / "src" / "broken.ts", 'import dep from "pkg";\n')

    javascript_index = extract_javascript_index_with_tree_sitter(
        tmp_path,
        scan_repository(tmp_path).files,
        _fake_tree_sitter_support(has_error=True),
    )

    assert [(module.path, module.parser_status) for module in javascript_index.modules] == [
        ("src/broken.ts", "parse_error")
    ]
    assert javascript_index.imports == ()
    assert javascript_index.symbols == ()


def test_tree_sitter_javascript_index_is_deterministic_and_scanner_bounded(tmp_path):
    _write_text(tmp_path / "src" / "b.ts", 'import b from "b";\n')
    _write_text(tmp_path / "src" / "a.ts", 'import a from "a";\n')
    _write_text(tmp_path / "notes.txt", 'import ignored from "not-js";\n')

    first_index = extract_javascript_index_with_tree_sitter(
        tmp_path,
        tuple(reversed(scan_repository(tmp_path).files)),
        _fake_tree_sitter_support(),
    )
    second_index = extract_javascript_index_with_tree_sitter(
        tmp_path,
        scan_repository(tmp_path).files,
        _fake_tree_sitter_support(),
    )

    assert [module.path for module in first_index.modules] == ["src/a.ts", "src/b.ts"]
    assert [item.specifier for item in first_index.imports] == ["a", "b"]
    assert first_index == second_index


def _write_text(path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _fake_tree_sitter_support(*, has_error: bool = False) -> TreeSitterJavaScriptSupport:
    class FakeParser:
        def __init__(self, language):
            self.language = language

        def parse(self, source: bytes):
            return SimpleNamespace(root_node=SimpleNamespace(has_error=has_error))

    return TreeSitterJavaScriptSupport(
        parser_class=FakeParser,
        language_class=object,
        javascript_language="javascript",
        typescript_language="typescript",
        tsx_language="tsx",
        provenance=JavaScriptParserProvenance(
            backend_name="tree_sitter_js_ts",
            parser_package_version="parser-test",
            javascript_grammar_version="grammar-js-test",
            typescript_grammar_version="grammar-ts-test",
            promoted_fact_schema_version="javascript-promoted-facts-v1",
        ),
    )

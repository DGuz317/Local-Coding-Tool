from __future__ import annotations

from textwrap import dedent

from repolens.python_index import extract_python_index
from repolens.scanner import scan_repository


def test_python_index_extracts_symbols_imports_comments_docstrings_and_calls(tmp_path):
    _write_text(tmp_path / "pyproject.toml", '[project]\nname = "acme"\n')
    _write_text(tmp_path / "src" / "acme" / "__init__.py", "")
    _write_text(
        tmp_path / "src" / "acme" / "service.py",
        dedent(
            '''
            """Service module. Extra module details."""

            import os
            import requests as http
            from collections import defaultdict
            from acme import models
            from .helpers import helper as imported_helper
            from vendor_lib import client

            # TODO: wire real implementation
            @registry.register
            class Child(Base, mixins.Logging):
                """Child handles work. Extra class details."""

                # RISK: class-level mutation
                @classmethod
                def build(cls):
                    """Build a child. Extra method details."""
                    return helper()

                @audit.logged
                async def refresh(self):
                    """Refresh state. Extra async method details."""
                    await async_worker()

            @decorated
            def helper():
                """Help now. Extra function details."""
                return Child()

            async def async_worker():
                """Work async. Extra async details."""
                helper()

            def caller():
                # SECURITY: preserve permission checks
                helper()
                Child()
                os.getcwd()
            '''
        ).lstrip(),
    )

    scan = scan_repository(tmp_path)
    python_index = extract_python_index(tmp_path, scan.files)

    modules = {module.path: module for module in python_index.modules}
    assert modules["src/acme/service.py"].module_name == "acme.service"
    assert modules["src/acme/service.py"].parser_status == "parsed"
    assert modules["src/acme/service.py"].docstring_summary == "Service module."

    symbols = {symbol.qualified_name: symbol for symbol in python_index.symbols}
    assert symbols["Child"].kind == "class"
    assert symbols["Child"].decorators == ("registry.register",)
    assert symbols["Child"].bases == ("Base", "mixins.Logging")
    assert symbols["Child"].docstring_summary == "Child handles work."
    assert symbols["Child.build"].kind == "method"
    assert symbols["Child.build"].decorators == ("classmethod",)
    assert symbols["Child.build"].docstring_summary == "Build a child."
    assert symbols["Child.refresh"].kind == "async_method"
    assert symbols["Child.refresh"].decorators == ("audit.logged",)
    assert symbols["helper"].kind == "function"
    assert symbols["helper"].decorators == ("decorated",)
    assert symbols["helper"].docstring_summary == "Help now."
    assert symbols["async_worker"].kind == "async_function"

    imports = {(item.kind, item.module, item.imported_name): item for item in python_index.imports}
    assert imports[("import", "os", None)].classification == "stdlib"
    assert imports[("from", "collections", "defaultdict")].classification == "stdlib"
    assert imports[("import", "requests", None)].classification == "third_party"
    assert imports[("from", "vendor_lib", "client")].classification == "third_party"
    assert imports[("from", "acme", "models")].classification == "local"
    assert imports[("from", "helpers", "helper")].classification == "local"

    packages = {(package.classification, package.name) for package in python_index.packages}
    assert ("local", "acme") in packages
    assert ("stdlib", "os") in packages
    assert ("third_party", "requests") in packages

    comments = {(comment.tag, comment.text): comment for comment in python_index.tagged_comments}
    assert ("TODO", "wire real implementation") in comments
    assert ("RISK", "class-level mutation") in comments
    assert ("SECURITY", "preserve permission checks") in comments
    assert (
        comments[("SECURITY", "preserve permission checks")].attached_node_id
        == symbols["caller"].id
    )

    call_pairs = {
        (call.caller_id, call.callee_id, call.callee_name, call.confidence)
        for call in python_index.calls
    }
    assert (symbols["caller"].id, symbols["helper"].id, "helper", "high") in call_pairs
    assert (symbols["caller"].id, symbols["Child"].id, "Child", "high") in call_pairs
    assert (symbols["helper"].id, symbols["Child"].id, "Child", "high") in call_pairs
    assert all(call.callee_name != "getcwd" for call in python_index.calls)


def test_python_index_records_syntax_errors_nonfatally_without_stale_symbols(tmp_path):
    _write_text(tmp_path / "good.py", "def ok():\n    return 1\n")
    _write_text(tmp_path / "bad.py", "# FIXME: repair syntax\ndef broken(:\n    pass\n")

    scan = scan_repository(tmp_path)
    python_index = extract_python_index(tmp_path, scan.files)

    statuses = python_index.parser_status_by_path
    assert statuses == {"bad.py": "parse_error", "good.py": "parsed"}
    assert [(error.path, error.message) for error in python_index.parse_errors] == [
        ("bad.py", "invalid syntax")
    ]
    assert {symbol.path for symbol in python_index.symbols} == {"good.py"}
    assert {comment.tag for comment in python_index.tagged_comments} == {"FIXME"}


def _write_text(path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

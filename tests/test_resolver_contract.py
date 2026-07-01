from __future__ import annotations

from repolens.resolver_contract import (
    RESOLVER_CONFIDENCE_LABELS,
    RESOLVER_EVIDENCE_LABELS,
    RESOLVER_OUTCOME_CLASSES,
)


def test_resolver_taxonomy_contract_uses_stable_public_labels() -> None:
    assert RESOLVER_EVIDENCE_LABELS == (
        "javascript_import_specifier",
        "package_manifest_dependency",
        "package_manifest_identity",
        "package_entrypoint_metadata",
        "workspace_declaration",
    )
    assert RESOLVER_OUTCOME_CLASSES == (
        "resolved_edge",
        "relationship_candidate",
        "unresolved",
        "unsupported",
    )
    assert RESOLVER_CONFIDENCE_LABELS == ("low", "medium", "high")

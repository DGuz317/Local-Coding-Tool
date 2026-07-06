"""Stable resolver evidence labels and outcome classes for public graph output."""

from __future__ import annotations

from typing import Literal

ResolverEvidenceLabel = Literal[
    "javascript_import_specifier",
    "package_manifest_dependency",
    "package_manifest_identity",
    "package_entrypoint_metadata",
    "workspace_declaration",
    "typescript_path_alias",
    "typescript_base_url",
]
ResolverOutcomeClass = Literal[
    "resolved_edge",
    "relationship_candidate",
    "unresolved",
    "unsupported",
]

RESOLVER_EVIDENCE_LABELS: tuple[ResolverEvidenceLabel, ...] = (
    "javascript_import_specifier",
    "package_manifest_dependency",
    "package_manifest_identity",
    "package_entrypoint_metadata",
    "workspace_declaration",
    "typescript_path_alias",
    "typescript_base_url",
)
RESOLVER_OUTCOME_CLASSES: tuple[ResolverOutcomeClass, ...] = (
    "resolved_edge",
    "relationship_candidate",
    "unresolved",
    "unsupported",
)
RESOLVER_CONFIDENCE_LABELS = ("low", "medium", "high")

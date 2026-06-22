"""Deterministic fixture generation and update benchmark helpers."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from repolens.indexer import IndexResult, UpdateResult, index_repository, update_repository


class RepoLensBenchmarkError(RuntimeError):
    """Raised when benchmark fixture generation cannot proceed safely."""


@dataclass(frozen=True)
class UpdateBenchmarkResult:
    """Relative selective update benchmark result."""

    fixture_path: str
    file_count: int
    changed_file_count: int
    selective_update_seconds: float
    full_rebuild_seconds: float
    update: UpdateResult
    rebuild: IndexResult

    def to_cli_data(self) -> dict[str, object]:
        speedup_factor = (
            self.full_rebuild_seconds / self.selective_update_seconds
            if self.selective_update_seconds > 0
            else None
        )
        return {
            "changed_file_count": self.changed_file_count,
            "file_count": self.file_count,
            "fixture_path": self.fixture_path,
            "full_rebuild_seconds": self.full_rebuild_seconds,
            "relative_speedup": {
                "basis": "full_rebuild_seconds / selective_update_seconds",
                "fixed_wall_clock_claim": False,
                "factor": speedup_factor,
                "interpretation": "Higher than 1.0 means the measured update was faster.",
            },
            "selective_update": self.update.to_cli_data().get("selective_update", {}),
            "selective_update_seconds": self.selective_update_seconds,
        }


def generate_update_benchmark_fixture(root: Path | str, *, file_count: int) -> Path:
    """Generate a deterministic local fixture repository for update benchmarking."""
    if file_count < 1:
        raise RepoLensBenchmarkError("file_count_must_be_positive")

    fixture_root = Path(root).resolve()
    if fixture_root.exists():
        if not fixture_root.is_dir():
            raise RepoLensBenchmarkError("fixture_path_not_directory")
        if any(fixture_root.iterdir()):
            raise RepoLensBenchmarkError("fixture_path_not_empty")
    else:
        fixture_root.mkdir(parents=True)

    _write_text(
        fixture_root / "pyproject.toml",
        '[project]\nname = "repolens-update-benchmark-fixture"\nversion = "0.0.0"\n',
    )
    _write_text(fixture_root / "README.md", "# RepoLens Update Benchmark Fixture\n")
    _write_text(fixture_root / "src" / "benchpkg" / "__init__.py", "")

    for index in range(file_count):
        import_line = "from benchpkg.module_0000 import value_0000\n" if index else ""
        body = f"{import_line}\ndef value_{index:04d}():\n    return {index}\n"
        _write_text(fixture_root / "src" / "benchpkg" / f"module_{index:04d}.py", body)

    return fixture_root


def run_update_benchmark(
    *,
    fixture_path: Path | str | None = None,
    file_count: int = 200,
    changed_file_count: int = 1,
) -> UpdateBenchmarkResult:
    """Generate a fixture, compare update with full rebuild, and return relative evidence."""
    if changed_file_count < 1:
        raise RepoLensBenchmarkError("changed_file_count_must_be_positive")
    if changed_file_count > file_count:
        raise RepoLensBenchmarkError("changed_file_count_exceeds_file_count")

    if fixture_path is None:
        with tempfile.TemporaryDirectory(prefix="repolens-update-benchmark-") as temp_dir:
            return _run_update_benchmark_in_path(
                Path(temp_dir) / "fixture",
                file_count=file_count,
                changed_file_count=changed_file_count,
            )

    return _run_update_benchmark_in_path(
        Path(fixture_path),
        file_count=file_count,
        changed_file_count=changed_file_count,
    )


def _run_update_benchmark_in_path(
    fixture_path: Path,
    *,
    file_count: int,
    changed_file_count: int,
) -> UpdateBenchmarkResult:
    fixture_root = generate_update_benchmark_fixture(fixture_path, file_count=file_count)
    index_repository(fixture_root)

    for index in range(changed_file_count):
        _write_text(
            fixture_root / "src" / "benchpkg" / f"module_{index:04d}.py",
            f"\ndef value_{index:04d}():\n    return {index + 10_000}\n",
        )

    update_started = perf_counter()
    update = update_repository(fixture_root)
    selective_update_seconds = perf_counter() - update_started

    rebuild_started = perf_counter()
    rebuild = index_repository(fixture_root)
    full_rebuild_seconds = perf_counter() - rebuild_started

    return UpdateBenchmarkResult(
        fixture_path=str(fixture_root),
        file_count=file_count,
        changed_file_count=changed_file_count,
        selective_update_seconds=selective_update_seconds,
        full_rebuild_seconds=full_rebuild_seconds,
        update=update,
        rebuild=rebuild,
    )


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

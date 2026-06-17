"""Shallow repository configuration extraction for RepoLens graph facts."""

from __future__ import annotations

import ast
import configparser
import hashlib
import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from repolens.scanner import ScannedFile

CONFIG_EXTRACTOR_VERSION = "issue-8-config-command-package-entrypoints-v1"

CONFIG_EXTENSIONS = frozenset({".json", ".toml", ".yaml", ".yml"})
JAVASCRIPT_MANIFEST_NAMES = frozenset({"package.json"})
PYTHON_REQUIREMENTS_PATTERN = re.compile(
    r"(?:^|-)requirements(?:[-_.].*)?\.txt$|^requirements\.txt$"
)
GITHUB_WORKFLOW_PREFIX = ".github/workflows/"
TASKFILE_NAMES = frozenset({"taskfile.yml", "taskfile.yaml"})
MAKEFILE_NAMES = frozenset({"gnumakefile", "makefile"})
DOCKERFILE_NAMES = frozenset({"dockerfile"})
PRE_COMMIT_CONFIG_NAMES = frozenset({".pre-commit-config.yaml", ".pre-commit-config.yml"})
PYTHON_SOURCE_SUFFIXES = frozenset({".py"})
JAVASCRIPT_SOURCE_SUFFIXES = frozenset(
    {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts"}
)

SAFE_SCALAR_METADATA_KEYS = frozenset(
    {
        "build-backend",
        "description",
        "license",
        "name",
        "packageManager",
        "private",
        "requires-python",
        "type",
        "version",
    }
)
SECRET_KEY_TOKENS = (
    "api_key",
    "apikey",
    "auth",
    "credential",
    "password",
    "passwd",
    "private_key",
    "secret",
    "token",
)
COMMAND_SECRET_OPTIONS = (
    "api-key",
    "apikey",
    "auth",
    "otp",
    "password",
    "passwd",
    "secret",
    "token",
)
LOCKFILE_BY_NAME = {
    "bun.lock": ("bun", "lock", "javascript"),
    "bun.lockb": ("bun", "binary", "javascript"),
    "npm-shrinkwrap.json": ("npm", "json", "javascript"),
    "package-lock.json": ("npm", "json", "javascript"),
    "pdm.lock": ("pdm", "toml", "python"),
    "pipfile.lock": ("pipenv", "json", "python"),
    "pnpm-lock.yaml": ("pnpm", "yaml", "javascript"),
    "poetry.lock": ("poetry", "toml", "python"),
    "uv.lock": ("uv", "toml", "python"),
    "yarn.lock": ("yarn", "lock", "javascript"),
}


@dataclass(frozen=True)
class ConfigFileFact:
    """A scanner-approved repository config file parsed shallowly or detected."""

    path: str
    node_id: str
    config_kind: str
    format: str
    parser_status: str
    top_level_keys: tuple[str, ...]
    metadata: dict[str, object]


@dataclass(frozen=True)
class ConfigPackageManagerFact:
    """A package manager inferred from shallow manifest or lockfile evidence."""

    id: str
    name: str
    ecosystem: str
    source_path: str
    evidence_kind: str


@dataclass(frozen=True)
class ConfigPackageFact:
    """A local package or external dependency declared by config files."""

    id: str
    name: str
    ecosystem: str
    classification: str
    source_path: str
    dependency_type: str
    version_constraint: str | None


@dataclass(frozen=True)
class ConfigPackageRootFact:
    """A local package root detected from strong packaging evidence."""

    id: str
    name: str
    ecosystem: str
    path: str
    source_path: str


@dataclass(frozen=True)
class ConfigLockfileFact:
    """A lockfile detected by filename without deep dependency graph parsing."""

    id: str
    path: str
    manager: str
    format: str
    ecosystem: str


@dataclass(frozen=True)
class ConfigCommandFact:
    """A candidate command discovered from config and explicitly not executed."""

    id: str
    path: str
    source: str
    name: str
    command: str
    purpose: str
    not_run: bool
    auto_run_recommended: bool


@dataclass(frozen=True)
class ConfigEntrypointFact:
    """A likely repository entrypoint backed by shallow static evidence."""

    id: str
    path: str
    kind: str
    name: str
    target: str
    evidence: str
    line: int | None


@dataclass(frozen=True)
class ConfigParseErrorFact:
    """A nonfatal config parse/read error fact for one scanner-approved file."""

    id: str
    path: str
    message: str


@dataclass(frozen=True)
class ConfigIndex:
    """All shallow config facts extracted for one scan result."""

    config_files: tuple[ConfigFileFact, ...]
    package_managers: tuple[ConfigPackageManagerFact, ...]
    packages: tuple[ConfigPackageFact, ...]
    package_roots: tuple[ConfigPackageRootFact, ...]
    lockfiles: tuple[ConfigLockfileFact, ...]
    commands: tuple[ConfigCommandFact, ...]
    entrypoints: tuple[ConfigEntrypointFact, ...]
    parse_errors: tuple[ConfigParseErrorFact, ...]

    @property
    def parser_status_by_path(self) -> dict[str, str]:
        return {config.path: config.parser_status for config in self.config_files}


def extract_config_index(root: Path, files: tuple[ScannedFile, ...]) -> ConfigIndex:
    """Extract deterministic shallow config facts from scanner-approved files only."""
    sorted_files = tuple(sorted(files, key=lambda item: item.path))
    file_paths = frozenset(file.path for file in sorted_files)
    config_files: dict[str, ConfigFileFact] = {}
    package_managers: dict[str, ConfigPackageManagerFact] = {}
    packages: dict[str, ConfigPackageFact] = {}
    package_roots: dict[str, ConfigPackageRootFact] = {}
    lockfiles: dict[str, ConfigLockfileFact] = {}
    commands: dict[str, ConfigCommandFact] = {}
    entrypoints: dict[str, ConfigEntrypointFact] = {}
    parse_errors: dict[str, ConfigParseErrorFact] = {}

    def add_config_file(fact: ConfigFileFact) -> None:
        config_files[fact.path] = fact

    def add_parse_error(path: str, message: str) -> None:
        fact = ConfigParseErrorFact(
            id=config_parse_error_node_id(path),
            path=path,
            message=message,
        )
        parse_errors[fact.id] = fact

    def add_package_manager(
        name: str,
        ecosystem: str,
        source_path: str,
        evidence_kind: str,
    ) -> None:
        fact = ConfigPackageManagerFact(
            id=config_package_manager_node_id(name, ecosystem, source_path, evidence_kind),
            name=name,
            ecosystem=ecosystem,
            source_path=source_path,
            evidence_kind=evidence_kind,
        )
        package_managers[fact.id] = fact

    def add_package(
        name: str,
        ecosystem: str,
        classification: str,
        source_path: str,
        dependency_type: str,
        version_constraint: str | None,
    ) -> None:
        normalized_name = name.strip()
        if not normalized_name:
            return
        fact = ConfigPackageFact(
            id=config_package_node_id(
                normalized_name,
                ecosystem,
                classification,
                source_path,
                dependency_type,
            ),
            name=normalized_name,
            ecosystem=ecosystem,
            classification=classification,
            source_path=source_path,
            dependency_type=dependency_type,
            version_constraint=version_constraint,
        )
        packages[fact.id] = fact

    def add_package_root(name: str, ecosystem: str, path: str, source_path: str) -> None:
        fact = ConfigPackageRootFact(
            id=config_package_root_node_id(name, ecosystem, path),
            name=name,
            ecosystem=ecosystem,
            path=path,
            source_path=source_path,
        )
        package_roots[fact.id] = fact

    def add_lockfile(path: str, manager: str, file_format: str, ecosystem: str) -> None:
        fact = ConfigLockfileFact(
            id=config_lockfile_node_id(path),
            path=path,
            manager=manager,
            format=file_format,
            ecosystem=ecosystem,
        )
        lockfiles[fact.id] = fact
        add_package_manager(manager, ecosystem, path, "lockfile")

    def add_command(source_path: str, source: str, name: str, command: str) -> None:
        sanitized = _sanitize_command(command)
        fact = ConfigCommandFact(
            id=config_command_node_id(source_path, source, name),
            path=source_path,
            source=source,
            name=name,
            command=sanitized,
            purpose=_classify_command_purpose(name, sanitized),
            not_run=True,
            auto_run_recommended=False,
        )
        commands[fact.id] = fact

    def add_entrypoint(
        source_path: str,
        kind: str,
        name: str,
        target: str,
        evidence: str,
        line: int | None = None,
    ) -> None:
        sanitized_target = _sanitize_command(target) if kind == "package_script" else target
        fact = ConfigEntrypointFact(
            id=config_entrypoint_node_id(source_path, kind, name, sanitized_target),
            path=source_path,
            kind=kind,
            name=name,
            target=sanitized_target,
            evidence=evidence,
            line=line,
        )
        entrypoints[fact.id] = fact

    for scanned_file in sorted_files:
        path = scanned_file.path
        lockfile = _lockfile_info(path)
        if lockfile is not None:
            manager, file_format, ecosystem = lockfile
            add_config_file(
                ConfigFileFact(
                    path=path,
                    node_id=config_file_node_id(path),
                    config_kind="lockfile",
                    format=file_format,
                    parser_status="detected",
                    top_level_keys=(),
                    metadata={"manager": manager},
                )
            )
            add_lockfile(path, manager, file_format, ecosystem)
            continue

        config_kind = _config_kind(path)
        if config_kind is not None:
            try:
                source = _read_scanner_approved_text(root, path)
            except OSError as exc:
                add_config_file(
                    ConfigFileFact(
                        path=path,
                        node_id=config_file_node_id(path),
                        config_kind=config_kind,
                        format=_config_format(path, config_kind),
                        parser_status="parse_error",
                        top_level_keys=(),
                        metadata={},
                    )
                )
                add_parse_error(path, f"read_error: {exc.__class__.__name__}")
                continue

            parsed = _parse_config_file(path, config_kind, source)
            add_config_file(
                ConfigFileFact(
                    path=path,
                    node_id=config_file_node_id(path),
                    config_kind=config_kind,
                    format=parsed.format,
                    parser_status=parsed.status,
                    top_level_keys=parsed.top_level_keys,
                    metadata=parsed.metadata,
                )
            )
            if parsed.status == "parse_error":
                add_parse_error(path, parsed.error_message or "parse_error")
                continue

            if path == "pyproject.toml" and isinstance(parsed.value, dict):
                _extract_pyproject_facts(
                    parsed.value,
                    path,
                    file_paths,
                    add_package_manager,
                    add_package,
                    add_package_root,
                    add_entrypoint,
                )
            elif PurePosixPath(path).name == "setup.cfg" and isinstance(
                parsed.value, configparser.ConfigParser
            ):
                _extract_setup_cfg_facts(
                    parsed.value,
                    path,
                    file_paths,
                    add_package_manager,
                    add_package,
                    add_package_root,
                    add_entrypoint,
                )
            elif PurePosixPath(path).name == "setup.py" and isinstance(parsed.value, ast.AST):
                _extract_setup_py_facts(
                    parsed.value,
                    path,
                    file_paths,
                    add_package_manager,
                    add_package,
                    add_package_root,
                    add_entrypoint,
                )
            elif _is_requirements_file(path):
                _extract_requirements_facts(source, path, add_package_manager, add_package)
            elif PurePosixPath(path).name == "package.json" and isinstance(parsed.value, dict):
                _extract_package_json_facts(
                    parsed.value,
                    path,
                    add_package_manager,
                    add_package,
                    add_package_root,
                    add_command,
                    add_entrypoint,
                )
            elif config_kind == "dockerfile":
                _extract_dockerfile_facts(source, path, add_entrypoint)
            elif config_kind == "makefile":
                _extract_makefile_facts(source, path, add_command)
            elif config_kind == "github_actions":
                _extract_github_actions_facts(source, path, add_command)
            elif config_kind == "pre_commit":
                add_command(path, "pre_commit", "pre-commit", "pre-commit run --all-files")
            elif config_kind == "taskfile":
                _extract_taskfile_facts(source, path, add_command)

        _extract_source_entrypoints(
            root,
            path,
            add_entrypoint,
        )

    return ConfigIndex(
        config_files=tuple(sorted(config_files.values(), key=lambda fact: fact.path)),
        package_managers=tuple(
            sorted(
                package_managers.values(),
                key=lambda fact: (fact.ecosystem, fact.name, fact.source_path, fact.evidence_kind),
            )
        ),
        packages=tuple(
            sorted(
                packages.values(),
                key=lambda fact: (
                    fact.ecosystem,
                    fact.classification,
                    fact.name,
                    fact.source_path,
                    fact.dependency_type,
                ),
            )
        ),
        package_roots=tuple(
            sorted(package_roots.values(), key=lambda fact: (fact.ecosystem, fact.path, fact.name))
        ),
        lockfiles=tuple(sorted(lockfiles.values(), key=lambda fact: fact.path)),
        commands=tuple(
            sorted(commands.values(), key=lambda fact: (fact.path, fact.source, fact.name))
        ),
        entrypoints=tuple(
            sorted(entrypoints.values(), key=lambda fact: (fact.path, fact.kind, fact.name))
        ),
        parse_errors=tuple(sorted(parse_errors.values(), key=lambda fact: fact.path)),
    )


@dataclass(frozen=True)
class _ParsedConfig:
    format: str
    status: str
    top_level_keys: tuple[str, ...]
    metadata: dict[str, object]
    value: object | None
    error_message: str | None = None


def config_file_node_id(path: str) -> str:
    return f"config_file:{path}"


def config_package_manager_node_id(
    name: str,
    ecosystem: str,
    source_path: str,
    evidence_kind: str,
) -> str:
    return f"config_package_manager:{ecosystem}:{name}:{_stable_suffix(source_path, evidence_kind)}"


def config_package_node_id(
    name: str,
    ecosystem: str,
    classification: str,
    source_path: str,
    dependency_type: str,
) -> str:
    return (
        f"config_package:{ecosystem}:{classification}:{name}:"
        f"{_stable_suffix(source_path, dependency_type)}"
    )


def config_package_root_node_id(name: str, ecosystem: str, path: str) -> str:
    return f"config_package_root:{ecosystem}:{name}:{path}"


def config_lockfile_node_id(path: str) -> str:
    return f"config_lockfile:{path}"


def config_command_node_id(path: str, source: str, name: str) -> str:
    return f"config_command:{path}:{source}:{name}"


def config_entrypoint_node_id(path: str, kind: str, name: str, target: str) -> str:
    return f"config_entrypoint:{path}:{kind}:{name}:{_stable_suffix(target)}"


def config_parse_error_node_id(path: str) -> str:
    return f"config_parse_error:{path}"


def _config_kind(path: str) -> str | None:
    pure_path = PurePosixPath(path)
    name = pure_path.name
    lower_name = name.lower()
    lower_path = path.lower()
    suffix = pure_path.suffix.lower()

    if name == "pyproject.toml":
        return "python_package"
    if lower_name in {"setup.cfg", "setup.py"} or _is_requirements_file(path):
        return "python_package"
    if lower_name in JAVASCRIPT_MANIFEST_NAMES:
        return "package_manifest"
    if lower_name in DOCKERFILE_NAMES or lower_name.startswith("dockerfile."):
        return "dockerfile"
    if lower_name in MAKEFILE_NAMES or lower_name.endswith(".mk"):
        return "makefile"
    if lower_name in PRE_COMMIT_CONFIG_NAMES:
        return "pre_commit"
    if lower_name in TASKFILE_NAMES:
        return "taskfile"
    if lower_path.startswith(GITHUB_WORKFLOW_PREFIX) and suffix in {".yaml", ".yml"}:
        return "github_actions"
    if suffix in CONFIG_EXTENSIONS:
        return "generic_config"
    return None


def _config_format(path: str, config_kind: str) -> str:
    suffix = PurePosixPath(path).suffix.lower()
    lower_name = PurePosixPath(path).name.lower()
    if config_kind == "dockerfile":
        return "dockerfile"
    if config_kind == "makefile":
        return "makefile"
    if _is_requirements_file(path):
        return "requirements"
    if lower_name == "setup.cfg":
        return "ini"
    if lower_name == "setup.py":
        return "python"
    if suffix == ".json":
        return "json"
    if suffix == ".toml":
        return "toml"
    if suffix in {".yaml", ".yml"}:
        return "yaml"
    return suffix.lstrip(".") or config_kind


def _parse_config_file(path: str, config_kind: str, source: str) -> _ParsedConfig:
    file_format = _config_format(path, config_kind)
    if file_format == "json":
        return _parse_json_config(source)
    if file_format == "toml":
        return _parse_toml_config(source)
    if file_format == "yaml":
        return _parse_yaml_config(source)
    if file_format == "ini":
        return _parse_ini_config(source)
    if file_format == "python":
        return _parse_setup_py_config(source)
    if file_format == "requirements":
        return _parse_requirements_config(source)
    if file_format == "dockerfile":
        return _parse_instruction_file(source, "dockerfile")
    if file_format == "makefile":
        return _parse_makefile_config(source)
    return _ParsedConfig(
        format=file_format,
        status="parsed",
        top_level_keys=(),
        metadata={},
        value=None,
    )


def _parse_json_config(source: str) -> _ParsedConfig:
    try:
        value = json.loads(_strip_json_trailing_commas(_strip_json_comments(source)))
    except json.JSONDecodeError:
        return _parse_error("json", "invalid_json")
    return _parsed_mapping("json", value)


def _parse_toml_config(source: str) -> _ParsedConfig:
    try:
        value = tomllib.loads(source)
    except tomllib.TOMLDecodeError:
        return _parse_error("toml", "invalid_toml")
    return _parsed_mapping("toml", value)


def _parse_yaml_config(source: str) -> _ParsedConfig:
    try:
        top_level = _yaml_top_level(source)
    except ValueError as exc:
        return _parse_error("yaml", str(exc))
    return _ParsedConfig(
        format="yaml",
        status="parsed",
        top_level_keys=tuple(sorted(top_level)),
        metadata={"top_level_types": dict(sorted(top_level.items()))},
        value=top_level,
    )


def _parse_ini_config(source: str) -> _ParsedConfig:
    parser = configparser.ConfigParser()
    try:
        parser.read_string(source)
    except configparser.Error:
        return _parse_error("ini", "invalid_ini")
    sections = tuple(sorted(parser.sections()))
    return _ParsedConfig(
        format="ini",
        status="parsed",
        top_level_keys=sections,
        metadata={"top_level_types": {section: "mapping" for section in sections}},
        value=parser,
    )


def _parse_setup_py_config(source: str) -> _ParsedConfig:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return _parse_error("python", "invalid_python")
    setup_keys = _setup_py_keyword_keys(tree)
    return _ParsedConfig(
        format="python",
        status="parsed",
        top_level_keys=setup_keys,
        metadata={"top_level_types": {key: "setup_keyword" for key in setup_keys}},
        value=tree,
    )


def _parse_requirements_config(source: str) -> _ParsedConfig:
    requirements = tuple(_requirement_name(line) for line in source.splitlines())
    names = tuple(sorted(name for name in requirements if name is not None))
    return _ParsedConfig(
        format="requirements",
        status="parsed",
        top_level_keys=(),
        metadata={"dependency_count": len(names)},
        value=names,
    )


def _parse_instruction_file(source: str, file_format: str) -> _ParsedConfig:
    instructions: list[str] = []
    for raw_line in source.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        instruction = stripped.split(maxsplit=1)[0].upper()
        if instruction:
            instructions.append(instruction)
    top_level_keys = tuple(sorted(set(instructions)))
    return _ParsedConfig(
        format=file_format,
        status="parsed",
        top_level_keys=top_level_keys,
        metadata={"instructions": top_level_keys},
        value=None,
    )


def _parse_makefile_config(source: str) -> _ParsedConfig:
    targets = tuple(sorted(_makefile_targets(source)))
    return _ParsedConfig(
        format="makefile",
        status="parsed",
        top_level_keys=targets,
        metadata={"targets": targets},
        value=None,
    )


def _parse_error(file_format: str, message: str) -> _ParsedConfig:
    return _ParsedConfig(
        format=file_format,
        status="parse_error",
        top_level_keys=(),
        metadata={},
        value=None,
        error_message=message,
    )


def _parsed_mapping(file_format: str, value: object) -> _ParsedConfig:
    if not isinstance(value, dict):
        return _ParsedConfig(
            format=file_format,
            status="parsed",
            top_level_keys=(),
            metadata={"top_level_type": _value_type(value)},
            value=value,
        )
    top_level_keys = tuple(sorted(str(key) for key in value))
    return _ParsedConfig(
        format=file_format,
        status="parsed",
        top_level_keys=top_level_keys,
        metadata=_metadata_from_mapping(value),
        value=value,
    )


def _extract_pyproject_facts(
    data: dict[str, Any],
    path: str,
    file_paths: frozenset[str],
    add_package_manager,
    add_package,
    add_package_root,
    add_entrypoint,
) -> None:
    add_package_manager("pip", "python", path, "pyproject")
    if "uv.lock" in file_paths:
        add_package_manager("uv", "python", "uv.lock", "lockfile")
    if (
        "poetry.lock" in file_paths
        or isinstance(data.get("tool"), dict)
        and "poetry" in data["tool"]
    ):
        add_package_manager("poetry", "python", path, "pyproject")

    build_system = data.get("build-system")
    if isinstance(build_system, dict):
        for requirement in _string_sequence(build_system.get("requires")):
            name = _requirement_name(requirement)
            if name is not None:
                add_package(name, "python", "external", path, "build-system.requires", requirement)

    project = data.get("project")
    if not isinstance(project, dict):
        poetry_project = _poetry_project(data)
        if poetry_project is not None:
            _extract_poetry_project_facts(
                poetry_project,
                path,
                file_paths,
                add_package,
                add_package_root,
                add_entrypoint,
            )
        return

    name = _string_value(project.get("name"))
    version = _string_value(project.get("version"))
    if name is not None:
        add_package(name, "python", "local", path, "project", version)
        for package_root in _python_package_roots(name, file_paths):
            add_package_root(name, "python", package_root, path)

    for dependency in _string_sequence(project.get("dependencies")):
        package_name = _requirement_name(dependency)
        if package_name is not None:
            add_package(
                package_name, "python", "external", path, "project.dependencies", dependency
            )

    optional = project.get("optional-dependencies")
    if isinstance(optional, dict):
        for group, dependencies in sorted(optional.items()):
            for dependency in _string_sequence(dependencies):
                package_name = _requirement_name(dependency)
                if package_name is not None:
                    add_package(
                        package_name,
                        "python",
                        "external",
                        path,
                        f"project.optional-dependencies.{group}",
                        dependency,
                    )

    for script_name, target in _string_mapping(project.get("scripts")).items():
        add_entrypoint(path, "python_console_script", script_name, target, "project.scripts")
    for script_name, target in _string_mapping(project.get("gui-scripts")).items():
        add_entrypoint(path, "python_gui_script", script_name, target, "project.gui-scripts")
    entry_points = project.get("entry-points")
    if isinstance(entry_points, dict):
        for group, entries in sorted(entry_points.items()):
            for script_name, target in _string_mapping(entries).items():
                add_entrypoint(path, f"python_entry_point:{group}", script_name, target, group)


def _extract_poetry_project_facts(
    poetry_project: dict[str, Any],
    path: str,
    file_paths: frozenset[str],
    add_package,
    add_package_root,
    add_entrypoint,
) -> None:
    name = _string_value(poetry_project.get("name"))
    version = _string_value(poetry_project.get("version"))
    if name is not None:
        add_package(name, "python", "local", path, "tool.poetry", version)
        for package_root in _python_package_roots(name, file_paths):
            add_package_root(name, "python", package_root, path)
    dependencies = poetry_project.get("dependencies")
    if isinstance(dependencies, dict):
        for dependency_name, version_constraint in sorted(dependencies.items()):
            if str(dependency_name).lower() == "python":
                continue
            add_package(
                str(dependency_name),
                "python",
                "external",
                path,
                "tool.poetry.dependencies",
                _version_constraint(version_constraint),
            )
    for script_name, target in _string_mapping(poetry_project.get("scripts")).items():
        add_entrypoint(path, "python_console_script", script_name, target, "tool.poetry.scripts")


def _extract_setup_cfg_facts(
    parser: configparser.ConfigParser,
    path: str,
    file_paths: frozenset[str],
    add_package_manager,
    add_package,
    add_package_root,
    add_entrypoint,
) -> None:
    add_package_manager("setuptools", "python", path, "setup.cfg")
    name = parser.get("metadata", "name", fallback=None)
    if name:
        add_package(name, "python", "local", path, "metadata", None)
        for package_root in _python_package_roots(name, file_paths):
            add_package_root(name, "python", package_root, path)
    install_requires = parser.get("options", "install_requires", fallback="")
    for requirement in install_requires.splitlines():
        package_name = _requirement_name(requirement)
        if package_name is not None:
            add_package(package_name, "python", "external", path, "install_requires", requirement)
    if parser.has_section("options.entry_points"):
        for option, value in parser.items("options.entry_points"):
            for line in value.splitlines():
                name_and_target = _entry_point_line(line)
                if name_and_target is not None:
                    script_name, target = name_and_target
                    add_entrypoint(
                        path, f"python_entry_point:{option}", script_name, target, option
                    )


def _extract_setup_py_facts(
    tree: ast.AST,
    path: str,
    file_paths: frozenset[str],
    add_package_manager,
    add_package,
    add_package_root,
    add_entrypoint,
) -> None:
    add_package_manager("setuptools", "python", path, "setup.py")
    setup_call = _setup_py_call(tree)
    if setup_call is None:
        return
    keywords = {keyword.arg: keyword.value for keyword in setup_call.keywords if keyword.arg}
    name = _ast_string(keywords.get("name"))
    if name is not None:
        add_package(name, "python", "local", path, "setup", None)
        for package_root in _python_package_roots(name, file_paths):
            add_package_root(name, "python", package_root, path)
    for requirement in _ast_string_sequence(keywords.get("install_requires")):
        package_name = _requirement_name(requirement)
        if package_name is not None:
            add_package(package_name, "python", "external", path, "install_requires", requirement)
    for script_name, target in _setup_py_entry_points(keywords.get("entry_points")):
        add_entrypoint(path, "python_console_script", script_name, target, "setup.entry_points")


def _extract_requirements_facts(source: str, path: str, add_package_manager, add_package) -> None:
    add_package_manager("pip", "python", path, "requirements")
    for raw_line in source.splitlines():
        package_name = _requirement_name(raw_line)
        if package_name is not None:
            add_package(package_name, "python", "external", path, "requirements", raw_line.strip())


def _extract_package_json_facts(
    data: dict[str, Any],
    path: str,
    add_package_manager,
    add_package,
    add_package_root,
    add_command,
    add_entrypoint,
) -> None:
    package_manager = _string_value(data.get("packageManager"))
    if package_manager is not None:
        add_package_manager(package_manager.split("@", 1)[0], "javascript", path, "packageManager")
    else:
        add_package_manager("npm", "javascript", path, "package.json")

    package_name = _string_value(data.get("name"))
    version = _string_value(data.get("version"))
    package_root = _file_directory(path)
    if package_name is not None:
        add_package(package_name, "javascript", "local", path, "package", version)
        add_package_root(package_name, "javascript", package_root, path)

    for dependency_type in (
        "dependencies",
        "devDependencies",
        "peerDependencies",
        "optionalDependencies",
    ):
        dependencies = data.get(dependency_type)
        if not isinstance(dependencies, dict):
            continue
        for dependency_name, version_constraint in sorted(dependencies.items()):
            add_package(
                str(dependency_name),
                "javascript",
                "external",
                path,
                dependency_type,
                _version_constraint(version_constraint),
            )

    for script_name, command in _string_mapping(data.get("scripts")).items():
        add_command(path, "package_script", script_name, command)
        if script_name in {"dev", "preview", "serve", "start"}:
            add_entrypoint(path, "package_script", script_name, command, "package.scripts")

    bin_field = data.get("bin")
    if isinstance(bin_field, str):
        add_entrypoint(path, "package_bin", package_name or "bin", bin_field, "package.bin")
    elif isinstance(bin_field, dict):
        for bin_name, target in _string_mapping(bin_field).items():
            add_entrypoint(path, "package_bin", bin_name, target, "package.bin")

    for field in ("main", "module", "browser"):
        main_target = _string_value(data.get(field))
        if main_target is not None:
            add_entrypoint(path, "package_main", field, main_target, f"package.{field}")
    exports = data.get("exports")
    if isinstance(exports, str):
        add_entrypoint(path, "package_export", "exports", exports, "package.exports")


def _extract_dockerfile_facts(source: str, path: str, add_entrypoint) -> None:
    for line_number, raw_line in enumerate(source.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        instruction, _, rest = stripped.partition(" ")
        upper_instruction = instruction.upper()
        if upper_instruction == "CMD":
            add_entrypoint(path, "docker_cmd", "CMD", rest.strip(), "Dockerfile CMD", line_number)
        elif upper_instruction == "ENTRYPOINT":
            add_entrypoint(
                path,
                "docker_entrypoint",
                "ENTRYPOINT",
                rest.strip(),
                "Dockerfile ENTRYPOINT",
                line_number,
            )


def _extract_makefile_facts(source: str, path: str, add_command) -> None:
    for target in _makefile_targets(source):
        add_command(path, "make_target", target, f"make {target}")


def _extract_github_actions_facts(source: str, path: str, add_command) -> None:
    workflow_name = PurePosixPath(path).stem
    run_index = 0
    for command in _github_actions_run_commands(source):
        run_index += 1
        add_command(path, "github_actions", f"{workflow_name}:{run_index}", command)


def _extract_taskfile_facts(source: str, path: str, add_command) -> None:
    for task_name in _taskfile_tasks(source):
        add_command(path, "taskfile", task_name, f"task {task_name}")


def _extract_source_entrypoints(root: Path, path: str, add_entrypoint) -> None:
    suffix = PurePosixPath(path).suffix.lower()
    if suffix not in PYTHON_SOURCE_SUFFIXES | JAVASCRIPT_SOURCE_SUFFIXES and "/" not in path:
        pass
    try:
        source = _read_scanner_approved_text(root, path)
    except OSError:
        return
    lines = source.splitlines()
    if lines and lines[0].startswith("#!") and _is_entrypoint_shebang(lines[0]):
        add_entrypoint(path, "shebang", path, path, _sanitize_command(lines[0][2:].strip()), 1)
    if suffix in PYTHON_SOURCE_SUFFIXES:
        for line_number, line in enumerate(lines, start=1):
            if _is_python_main_guard(line):
                add_entrypoint(
                    path,
                    "python_main_guard",
                    path,
                    path,
                    "if __name__ == '__main__'",
                    line_number,
                )
            if "FastAPI(" in line:
                add_entrypoint(
                    path, "python_framework_app", "FastAPI", path, "FastAPI()", line_number
                )
            elif "Flask(" in line:
                add_entrypoint(path, "python_framework_app", "Flask", path, "Flask()", line_number)
    elif suffix in JAVASCRIPT_SOURCE_SUFFIXES:
        for line_number, line in enumerate(lines, start=1):
            if ".listen(" in line:
                add_entrypoint(
                    path,
                    "javascript_server",
                    path,
                    path,
                    "listen()",
                    line_number,
                )


def _read_scanner_approved_text(root: Path, path: str) -> str:
    resolved_root = root.resolve(strict=True)
    source_path = resolved_root / PurePosixPath(path)
    source_path.resolve(strict=False).relative_to(resolved_root)
    return source_path.read_text(encoding="utf-8", errors="replace")


def _lockfile_info(path: str) -> tuple[str, str, str] | None:
    return LOCKFILE_BY_NAME.get(PurePosixPath(path).name.lower())


def _is_requirements_file(path: str) -> bool:
    return PYTHON_REQUIREMENTS_PATTERN.match(PurePosixPath(path).name.lower()) is not None


def _metadata_from_mapping(value: dict[Any, Any]) -> dict[str, object]:
    top_level_types = {
        str(key): "redacted" if _is_secret_key(str(key)) else _value_type(child)
        for key, child in value.items()
    }
    metadata: dict[str, object] = {"top_level_types": dict(sorted(top_level_types.items()))}
    for key in sorted(SAFE_SCALAR_METADATA_KEYS):
        if key not in value or _is_secret_key(key):
            continue
        scalar = _safe_scalar(value[key])
        if scalar is not None:
            normalized_key = "package_manager" if key == "packageManager" else key.replace("-", "_")
            metadata[normalized_key] = scalar
    return metadata


def _yaml_top_level(source: str) -> dict[str, str]:
    lines = source.splitlines()
    result: dict[str, str] = {}
    for index, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if _contains_yaml_tag(stripped):
            raise ValueError("unsupported_yaml_tag")
        if _indent(raw_line) != 0:
            continue
        match = re.match(r"(?P<key>[A-Za-z0-9_.-]+)\s*:\s*(?P<value>.*)$", stripped)
        if match is None:
            raise ValueError("invalid_yaml")
        key = match.group("key")
        value = match.group("value").strip()
        if _is_secret_key(key):
            result[key] = "redacted"
        elif value:
            result[key] = (
                "sequence"
                if value.startswith("[")
                else "mapping"
                if value.startswith("{")
                else "scalar"
            )
        else:
            result[key] = _yaml_nested_type(lines, index)
    return result


def _contains_yaml_tag(stripped_line: str) -> bool:
    return re.search(r"(^|[:\s\[{,])-?\s*![A-Za-z]", stripped_line) is not None


def _yaml_nested_type(lines: list[str], index: int) -> str:
    for child_line in lines[index + 1 :]:
        stripped = child_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if _indent(child_line) == 0:
            return "mapping"
        return "sequence" if stripped.startswith("-") else "mapping"
    return "mapping"


def _makefile_targets(source: str) -> tuple[str, ...]:
    targets: list[str] = []
    for raw_line in source.splitlines():
        if not raw_line or raw_line.startswith("\t") or raw_line.lstrip().startswith("#"):
            continue
        line = raw_line.strip()
        if ":" not in line or "=" in line.split(":", 1)[0]:
            continue
        target_part = line.split(":", 1)[0].strip()
        if not target_part or target_part.startswith(".") or "%" in target_part:
            continue
        for target in target_part.split():
            if re.match(r"^[A-Za-z0-9_.-]+$", target):
                targets.append(target)
    return tuple(sorted(set(targets)))


def _github_actions_run_commands(source: str) -> tuple[str, ...]:
    commands: list[str] = []
    lines = source.splitlines()
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()
        match = re.match(r"-?\s*run\s*:\s*(?P<value>.*)$", stripped)
        if match is None:
            index += 1
            continue
        value = match.group("value").strip()
        if value in {"|", ">"}:
            block_command = _first_yaml_block_line(lines, index)
            if block_command is not None:
                commands.append(block_command)
        elif value:
            commands.append(value.strip("\"'"))
        index += 1
    return tuple(commands)


def _first_yaml_block_line(lines: list[str], index: int) -> str | None:
    parent_indent = _indent(lines[index])
    for child_line in lines[index + 1 :]:
        stripped = child_line.strip()
        if not stripped:
            continue
        if _indent(child_line) <= parent_indent:
            return None
        return stripped
    return None


def _taskfile_tasks(source: str) -> tuple[str, ...]:
    tasks: list[str] = []
    lines = source.splitlines()
    in_tasks = False
    tasks_indent = 0
    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        current_indent = _indent(raw_line)
        if not in_tasks:
            if re.match(r"tasks\s*:\s*$", stripped):
                in_tasks = True
                tasks_indent = current_indent
            continue
        if current_indent <= tasks_indent:
            in_tasks = False
            continue
        if current_indent == tasks_indent + 2:
            match = re.match(r"(?P<name>[A-Za-z0-9_.-]+)\s*:\s*(?:$|\{)", stripped)
            if match is not None:
                tasks.append(match.group("name"))
    return tuple(sorted(set(tasks)))


def _python_package_roots(name: str, file_paths: frozenset[str]) -> tuple[str, ...]:
    module_name = name.replace("-", "_").replace(".", "/")
    candidates = (f"src/{module_name}", module_name)
    roots = []
    for candidate in candidates:
        if f"{candidate}/__init__.py" in file_paths or f"{candidate}/__main__.py" in file_paths:
            roots.append(candidate)
    return tuple(roots)


def _setup_py_call(tree: ast.AST) -> ast.Call | None:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "setup":
            return node
        if isinstance(func, ast.Attribute) and func.attr == "setup":
            return node
    return None


def _setup_py_keyword_keys(tree: ast.AST) -> tuple[str, ...]:
    setup_call = _setup_py_call(tree)
    if setup_call is None:
        return ()
    return tuple(sorted(keyword.arg for keyword in setup_call.keywords if keyword.arg))


def _setup_py_entry_points(node: ast.AST | None) -> tuple[tuple[str, str], ...]:
    value = ast.literal_eval(node) if node is not None else None
    entry_points: list[tuple[str, str]] = []
    if isinstance(value, dict):
        console_scripts = value.get("console_scripts")
        for line in _string_sequence(console_scripts):
            parsed = _entry_point_line(line)
            if parsed is not None:
                entry_points.append(parsed)
    return tuple(entry_points)


def _entry_point_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or "=" not in stripped:
        return None
    name, target = stripped.split("=", 1)
    name = name.strip()
    target = target.strip()
    if not name or not target:
        return None
    return name, target


def _poetry_project(data: dict[str, Any]) -> dict[str, Any] | None:
    tool = data.get("tool")
    if not isinstance(tool, dict):
        return None
    poetry = tool.get("poetry")
    return poetry if isinstance(poetry, dict) else None


def _requirement_name(raw_requirement: str) -> str | None:
    requirement = raw_requirement.strip()
    if not requirement or requirement.startswith("#") or requirement.startswith("-"):
        return None
    requirement = requirement.split("#", 1)[0].strip()
    if not requirement or requirement.startswith((".", "/", "git+", "http://", "https://")):
        return None
    match = re.match(r"(?P<name>[A-Za-z0-9_.-]+)(?:\[[^\]]+\])?", requirement)
    if match is None:
        return None
    return match.group("name")


def _version_constraint(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        version = value.get("version")
        return version if isinstance(version, str) else None
    return None


def _string_mapping(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): child for key, child in sorted(value.items()) if isinstance(child, str)}


def _string_sequence(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(item for item in value if isinstance(item, str))
    return ()


def _string_value(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _safe_scalar(value: object) -> object | None:
    if isinstance(value, str):
        return value[:120]
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    return None


def _value_type(value: object) -> str:
    if isinstance(value, dict):
        return "mapping"
    if isinstance(value, list):
        return "sequence"
    if value is None:
        return "null"
    return "scalar"


def _is_secret_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(token in normalized for token in SECRET_KEY_TOKENS)


def _sanitize_command(command: str) -> str:
    sanitized = command.strip()
    sanitized = re.sub(
        r"(?i)\b([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|AUTH|PRIVATE_KEY)[A-Z0-9_]*)=([^\s]+)",
        r"\1=<redacted>",
        sanitized,
    )
    option_pattern = "|".join(re.escape(option) for option in COMMAND_SECRET_OPTIONS)
    sanitized = re.sub(
        rf"(?i)(--(?:{option_pattern})(?:=|\s+))([^\s]+)",
        lambda match: f"{match.group(1)}<redacted>",
        sanitized,
    )
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    if len(sanitized) > 240:
        return f"{sanitized[:237]}..."
    return sanitized


def _classify_command_purpose(name: str, command: str) -> str:
    haystack = f"{name} {command}".lower()
    if any(token in haystack for token in ("deploy", "publish", "release", "upload")):
        return "deploy"
    if any(token in haystack for token in ("typecheck", "type-check", "mypy", "pyright", "tsc")):
        return "typecheck"
    if any(token in haystack for token in ("lint", "ruff check", "eslint", "pre-commit")):
        return "lint"
    if any(token in haystack for token in ("format", "prettier", "ruff format")):
        return "format"
    if any(token in haystack for token in ("test", "pytest", "vitest", "jest", "unittest")):
        return "test"
    if "build" in haystack:
        return "build"
    if "install" in haystack:
        return "install"
    if any(token in haystack for token in ("start", "serve", "dev")):
        return "run"
    return "unknown"


def _is_python_main_guard(line: str) -> bool:
    return bool(
        re.search(
            r"if\s+__name__\s*==\s*(['\"])__main__\1\s*:",
            line,
        )
    )


def _is_entrypoint_shebang(line: str) -> bool:
    lowered = line.lower()
    return any(token in lowered for token in ("bash", "bun", "deno", "node", "python", "sh"))


def _ast_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _ast_string_sequence(node: ast.AST | None) -> tuple[str, ...]:
    if node is None:
        return ()
    try:
        value = ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return ()
    return _string_sequence(value)


def _strip_json_comments(source: str) -> str:
    result: list[str] = []
    index = 0
    in_string = False
    quote = ""
    escaped = False
    while index < len(source):
        char = source[index]
        next_char = source[index + 1] if index + 1 < len(source) else ""
        if in_string:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                in_string = False
            index += 1
            continue
        if char in {'"', "'"}:
            in_string = True
            quote = char
            result.append(char)
            index += 1
            continue
        if char == "/" and next_char == "/":
            while index < len(source) and source[index] not in "\r\n":
                index += 1
            continue
        if char == "/" and next_char == "*":
            index += 2
            while index + 1 < len(source) and not (
                source[index] == "*" and source[index + 1] == "/"
            ):
                index += 1
            index += 2
            continue
        result.append(char)
        index += 1
    return "".join(result)


def _strip_json_trailing_commas(source: str) -> str:
    return re.sub(r",\s*([}\]])", r"\1", source)


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _file_directory(path: str) -> str:
    parent = PurePosixPath(path).parent.as_posix()
    return "." if parent == "." else parent


def _stable_suffix(*parts: str) -> str:
    value = "\0".join(parts)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]

"""Project metadata extraction per file type.

Scans known config files (pyproject.toml, Cargo.toml, package.json, go.mod, pom.xml,
Gemfile, etc.) and returns a structured JSON dict suitable for attaching to chunks.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def extract_file_metadata(file_path: str, project_root: str | None = None) -> dict[str, Any]:
    """Extract structured metadata from a file's nearest project-config ancestor.

    Walks *up* from *file_path* looking for known config files, then parses
    the first one found.  Returns a dict with at minimum ``{"type": None}``
    when nothing is found.
    """
    path = Path(file_path).resolve()
    if project_root:
        root = Path(project_root).resolve()
    else:
        root = path.root

    for parent in [path] + list(path.parents):
        try:
            parent.relative_to(root)
        except ValueError:
            break

        for config_name, parser_fn in _PARSERS.items():
            candidate = parent / config_name
            if candidate.is_file():
                try:
                    result = _PARSERS[config_name](candidate)
                    if result is not None:
                        return result
                except Exception:
                    pass

    return {"type": None}


# ── Per-file-type parsers ─────────────────────────────────────────────────────

_PARSERS: dict[str, Any] = {}


def _register(config_name: str):
    """Decorator that registers a parser function for *config_name*."""
    def wrapper(fn):
        _PARSERS[config_name] = fn
        return fn
    return wrapper


@_register("pyproject.toml")
def _parse_pyproject(path: Path) -> dict[str, Any] | None:
    """Parse ``pyproject.toml`` (PEP 621 / Poetry)."""
    try:
        import tomllib  # Python ≥ 3.11
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            return None

    with path.open("rb") as fh:
        data = tomllib.load(fh)

    out: dict[str, Any] = {"type": "python"}
    project = data.get("project", data.get("tool", {}).get("poetry", {}))
    out["name"] = project.get("name", path.parent.name)
    out["version"] = project.get("version", "")
    out["dependencies"] = _sorted_deps(
        project.get("dependencies", [])
    )
    if "tool" in data and "poetry" in data["tool"]:
        dev = data["tool"]["poetry"].get("group", {}).get("dev", {}).get("dependencies", {})
        if dev:
            out["dev_dependencies"] = _sorted_deps(dev)
    return out


def _sorted_deps(raw: list | dict) -> list[str]:
    """Normalise dependencies to a sorted list of package-name strings."""
    if isinstance(raw, dict):
        return sorted(raw.keys())
    if isinstance(raw, list):
        specs: list[str] = []
        for item in raw:
            if isinstance(item, str):
                # Strip version specifiers like ">=1.0"
                m = re.match(r"^([a-zA-Z0-9_.-]+)", item)
                if m:
                    specs.append(m.group(1))
        return sorted(specs)
    return []


@_register("Cargo.toml")
def _parse_cargo(path: Path) -> dict[str, Any] | None:
    """Parse ``Cargo.toml``."""
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            return None

    with path.open("rb") as fh:
        data = tomllib.load(fh)

    pkg = data.get("package", {})
    deps = data.get("dependencies", {})
    build_deps = data.get("build-dependencies", {})
    dev_deps = data.get("dev-dependencies", {})

    out: dict[str, Any] = {"type": "rust"}
    out["name"] = pkg.get("name", path.parent.name)
    out["version"] = pkg.get("version", "")
    out["dependencies"] = sorted(deps.keys()) if isinstance(deps, dict) else []
    if build_deps:
        out["build_dependencies"] = sorted(build_deps.keys())
    if dev_deps:
        out["dev_dependencies"] = sorted(dev_deps.keys())
    return out


@_register("package.json")
def _parse_package_json(path: Path) -> dict[str, Any] | None:
    """Parse ``package.json``."""
    try:
        with path.open() as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None

    out: dict[str, Any] = {"type": "javascript"}
    out["name"] = data.get("name", path.parent.name)
    out["version"] = data.get("version", "")
    deps: dict[str, str] = data.get("dependencies", {})
    out["dependencies"] = sorted(deps.keys())
    dev = data.get("devDependencies", {})
    if dev:
        out["dev_dependencies"] = sorted(dev.keys())
    return out


@_register("go.mod")
def _parse_go_mod(path: Path) -> dict[str, Any] | None:
    """Parse ``go.mod`` (Go module)."""
    try:
        text = path.read_text()
    except OSError:
        return None

    out: dict[str, Any] = {"type": "go"}
    match = re.search(r"^module\s+(\S+)", text, re.MULTILINE)
    out["name"] = match.group(1) if match else path.parent.name
    m = re.search(r"^go\s+(\S+)", text, re.MULTILINE)
    out["go_version"] = m.group(1) if m else ""
    # Collect require() blocks
    deps: list[str] = []
    in_require = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("require (") or stripped == "require (":
            in_require = True
            continue
        if in_require and stripped == ")":
            in_require = False
            continue
        if in_require:
            # e.g. "github.com/foo/bar v1.0.0"
            parts = stripped.split()
            if parts:
                deps.append(parts[0])
    if deps:
        out["dependencies"] = sorted(deps)
    return out


@_register("pom.xml")
def _parse_pom_xml(path: Path) -> dict[str, Any] | None:
    """Parse minimal ``pom.xml`` (Maven)."""
    try:
        text = path.read_text()
    except OSError:
        return None

    out: dict[str, Any] = {"type": "java"}
    m_name = re.search(r"<artifactId>\s*(\S+?)\s*</artifactId>", text)
    out["name"] = m_name.group(1) if m_name else path.parent.name
    m_ver = re.search(r"<version>\s*(\S+?)\s*</version>", text)
    out["version"] = m_ver.group(1) if m_ver else ""
    # Extract dependency groupId:artifactId
    deps: list[str] = []
    for m in re.finditer(
        r"<dependency>\s*<groupId>(.+?)</groupId>\s*<artifactId>(.+?)</artifactId>\s*(?:<version>(.+?)</version>)?",
        text,
        re.DOTALL,
    ):
        deps.append(f"{m.group(1)}:{m.group(2)}")
    if deps:
        out["dependencies"] = sorted(deps)
    return out


@_register("Gemfile")
def _parse_gemfile(path: Path) -> dict[str, Any] | None:
    """Parse ``Gemfile``."""
    try:
        text = path.read_text()
    except OSError:
        return None

    deps: list[str] = []
    for m in re.finditer(r"^\s*gem\s+['\"](.+?)['\"]", text, re.MULTILINE):
        deps.append(m.group(1))
    out: dict[str, Any] = {"type": "ruby", "name": path.parent.name}
    if deps:
        out["dependencies"] = sorted(deps)
    return out


@_register("CMakeLists.txt")
def _parse_cmake(path: Path) -> dict[str, Any] | None:
    """Parse minimal ``CMakeLists.txt`` for project name."""
    try:
        text = path.read_text()
    except OSError:
        return None

    out: dict[str, Any] = {"type": "cpp"}
    m = re.search(r"project\s*\(\s*(\S+)", text)
    out["name"] = m.group(1) if m else path.parent.name
    return out

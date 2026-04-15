#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


COMMON_GENERATED_DIR_NAMES = {
    ".cache",
    ".dart_tool",
    ".git",
    ".gradle",
    ".hg",
    ".mypy_cache",
    ".next",
    ".nox",
    ".nuxt",
    ".output",
    ".parcel-cache",
    ".pnpm-store",
    ".pytest_cache",
    ".ruff_cache",
    ".serverless",
    ".svelte-kit",
    ".svn",
    ".temp",
    ".terraform",
    ".tmp",
    ".tox",
    ".turbo",
    ".venv",
    ".vercel",
    "__pycache__",
    "build",
    "coverage",
    "debug",
    "dist",
    "node_modules",
    "out",
    "release",
    "target",
    "temp",
    "tmp",
    "venv",
}

GENERATED_PREFIXES = (".cache", ".temp", ".tmp")
GENERATED_SUFFIXES = ("-cache", "_cache", ".cache", ".egg-info")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Copy a filtered repo tree, the full files from a commit snapshot, "
            "or both to the clipboard."
        )
    )
    parser.add_argument(
        "mode",
        choices=("tree", "commit-files", "bundle"),
        help="What to export.",
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="Repo path or a subdirectory inside the repo. Defaults to the current directory.",
    )
    parser.add_argument(
        "--commit",
        default="HEAD",
        help="Commit to snapshot for commit-files or bundle. Defaults to HEAD.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Additional directory names to exclude from the tree.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print output instead of copying it to the clipboard.",
    )
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="Print detected runtime information before producing output.",
    )
    return parser.parse_args()


def configure_stdio() -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="replace")

    reconfigure_err = getattr(sys.stderr, "reconfigure", None)
    if callable(reconfigure_err):
        reconfigure_err(encoding="utf-8", errors="replace")


def run_command(
    command: list[str],
    *,
    cwd: Path | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        input=input_text,
        text=True,
        capture_output=True,
        check=True,
    )


def detect_shell() -> str:
    shell = os.environ.get("SHELL")
    if shell:
        return shell
    comspec = os.environ.get("COMSPEC") or os.environ.get("ComSpec")
    if comspec:
        return comspec
    if os.environ.get("PSModulePath"):
        return "powershell"
    return "unknown"


def detect_platform() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    if os.environ.get("WSL_DISTRO_NAME"):
        return "wsl"
    return "linux"


def clipboard_candidates() -> list[tuple[str, list[str]]]:
    platform_name = detect_platform()
    if platform_name == "windows":
        return [
            (
                "powershell",
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "[Console]::InputEncoding = [System.Text.Encoding]::UTF8; "
                    "Set-Clipboard -Value ([Console]::In.ReadToEnd())",
                ],
            ),
            (
                "pwsh",
                [
                    "pwsh",
                    "-NoProfile",
                    "-Command",
                    "[Console]::InputEncoding = [System.Text.Encoding]::UTF8; "
                    "Set-Clipboard -Value ([Console]::In.ReadToEnd())",
                ],
            ),
            ("clip", ["clip"]),
        ]
    if platform_name == "macos":
        return [("pbcopy", ["pbcopy"])]

    candidates = [
        ("wl-copy", ["wl-copy"]),
        ("xclip", ["xclip", "-selection", "clipboard"]),
        ("xsel", ["xsel", "--clipboard", "--input"]),
    ]
    if shutil.which("clip.exe"):
        candidates.append(("clip.exe", ["clip.exe"]))
    return candidates


def resolve_repo(path_str: str, *, require_git: bool) -> Path:
    start = Path(path_str).expanduser().resolve()
    if not start.exists():
        raise SystemExit(f"Path does not exist: {start}")

    working_dir = start if start.is_dir() else start.parent
    try:
        result = run_command(["git", "rev-parse", "--show-toplevel"], cwd=working_dir)
        return Path(result.stdout.strip()).resolve()
    except subprocess.CalledProcessError:
        if require_git:
            raise SystemExit(f"Not inside a git repository: {start}") from None
        return working_dir


def resolve_commit(repo_root: Path, commit: str) -> str:
    try:
        result = run_command(["git", "rev-parse", "--verify", commit], cwd=repo_root)
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip() or f"Invalid commit: {commit}"
        raise SystemExit(message) from None
    return result.stdout.strip()


def is_git_repository(path: Path) -> bool:
    try:
        run_command(["git", "rev-parse", "--is-inside-work-tree"], cwd=path)
        return True
    except subprocess.CalledProcessError:
        return False


def git_ignored_directories(repo_root: Path) -> set[str]:
    if not is_git_repository(repo_root):
        return set()

    try:
        result = run_command(
            ["git", "ls-files", "--others", "-i", "--exclude-standard", "--directory"],
            cwd=repo_root,
        )
    except subprocess.CalledProcessError:
        return set()

    ignored_dirs: set[str] = set()
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip().rstrip("/")
        if line:
            ignored_dirs.add(line.replace("\\", "/"))
    return ignored_dirs


def unique_paths(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            ordered.append(path)
    return ordered


def looks_generated_dir(name: str) -> bool:
    lowered = name.lower()
    if lowered in COMMON_GENERATED_DIR_NAMES:
        return True
    if lowered.startswith(GENERATED_PREFIXES):
        return True
    if lowered.endswith(GENERATED_SUFFIXES):
        return True
    return False


def is_under_ignored_path(relative_path: str, ignored_dirs: set[str]) -> bool:
    parts = [part for part in relative_path.split("/") if part]
    for index in range(1, len(parts) + 1):
        candidate = "/".join(parts[:index])
        if candidate in ignored_dirs:
            return True
    return False


def should_exclude_directory(
    directory: Path,
    root: Path,
    explicit_excludes: set[str],
    ignored_dirs: set[str],
) -> bool:
    lowered_name = directory.name.lower()
    if lowered_name in explicit_excludes:
        return True
    if looks_generated_dir(lowered_name):
        return True

    relative_path = directory.relative_to(root).as_posix()
    if is_under_ignored_path(relative_path, ignored_dirs):
        return True

    return False


def build_tree_lines(root: Path, excludes: set[str], ignored_dirs: set[str]) -> list[str]:
    lines = [root.name]

    def walk(directory: Path, prefix: str = "") -> None:
        try:
            children = [
                child
                for child in directory.iterdir()
                if not (
                    child.is_dir()
                    and should_exclude_directory(child, root, excludes, ignored_dirs)
                )
            ]
        except PermissionError:
            lines.append(f"{prefix}└── [permission denied]")
            return

        children.sort(key=lambda item: (not item.is_dir(), item.name.lower()))

        for index, child in enumerate(children):
            is_last = index == len(children) - 1
            branch = "└── " if is_last else "├── "
            lines.append(f"{prefix}{branch}{child.name}")
            if child.is_dir():
                child_prefix = f"{prefix}    " if is_last else f"{prefix}│   "
                walk(child, child_prefix)

    walk(root)
    return lines


def build_tree_output(root: Path, excludes: set[str]) -> str:
    ignored_dirs = git_ignored_directories(root)
    return "\n".join(build_tree_lines(root, excludes, ignored_dirs)).rstrip() + "\n"


def commit_file_paths(repo_root: Path, commit: str) -> list[str]:
    result = run_command(
        ["git", "show", "--name-only", "--pretty=format:", commit],
        cwd=repo_root,
    )
    paths = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return unique_paths(paths)


def file_exists_in_commit(repo_root: Path, commit: str, path: str) -> bool:
    check = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}:{path}"],
        cwd=str(repo_root),
        text=True,
        capture_output=True,
    )
    return check.returncode == 0


def build_commit_output(repo_root: Path, commit: str) -> str:
    resolved_commit = resolve_commit(repo_root, commit)
    paths = commit_file_paths(repo_root, resolved_commit)
    sections = [
        f"Repo: {repo_root}",
        f"Commit: {resolved_commit}",
        "",
    ]

    for path in paths:
        sections.append(f"===== FILE: {path} =====")
        if file_exists_in_commit(repo_root, resolved_commit, path):
            file_result = run_command(["git", "show", f"{resolved_commit}:{path}"], cwd=repo_root)
            sections.append(file_result.stdout.rstrip("\n"))
        else:
            sections.append("[File is not present in this commit snapshot.]")
        sections.append("")

    return "\n".join(sections).rstrip() + "\n"


def build_bundle_output(root: Path, excludes: set[str], commit: str) -> str:
    tree_output = build_tree_output(root, excludes).rstrip()
    commit_output = build_commit_output(root, commit).rstrip()
    return (
        "===== REPO TREE =====\n"
        f"{tree_output}\n\n"
        "===== COMMIT FILES =====\n"
        f"{commit_output}\n"
    )


def diagnose(root: Path, excludes: set[str], commit: str) -> str:
    available_backends = [name for name, command in clipboard_candidates() if shutil.which(command[0])]
    ignored_dirs = git_ignored_directories(root)
    return "\n".join(
        [
            f"repo_root={root}",
            f"platform={detect_platform()}",
            f"shell={detect_shell()}",
            f"commit={commit}",
            f"excludes={','.join(sorted(excludes))}",
            f"git_ignored_directories={len(ignored_dirs)}",
            f"clipboard_backends={','.join(available_backends) if available_backends else 'none'}",
            "",
        ]
    )


def copy_to_clipboard(text: str) -> str:
    failures: list[str] = []
    for name, command in clipboard_candidates():
        if shutil.which(command[0]) is None:
            continue
        try:
            subprocess.run(
                command,
                input=text.encode("utf-8"),
                capture_output=True,
                check=True,
            )
            return name
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode("utf-8", errors="replace").strip()
            stdout = exc.stdout.decode("utf-8", errors="replace").strip()
            details = stderr or stdout or "unknown error"
            failures.append(f"{name}: {details}")

    try:
        import tkinter

        root = tkinter.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update_idletasks()
        root.update()
        root.destroy()
        return "tkinter"
    except Exception as exc:
        failures.append(f"tkinter: {exc}")

    message = "Unable to find a working clipboard backend."
    if failures:
        message = f"{message} Tried: {'; '.join(failures)}"
    raise SystemExit(message)


def main() -> int:
    configure_stdio()
    args = parse_args()
    require_git = args.mode in {"commit-files", "bundle"}
    repo_root = resolve_repo(args.repo, require_git=require_git)
    excludes = {name.lower() for name in args.exclude}

    output_parts: list[str] = []
    if args.diagnose:
        output_parts.append(diagnose(repo_root, excludes, args.commit).rstrip())

    if args.mode == "tree":
        output_parts.append(build_tree_output(repo_root, excludes).rstrip())
    elif args.mode == "commit-files":
        output_parts.append(build_commit_output(repo_root, args.commit).rstrip())
    else:
        output_parts.append(build_bundle_output(repo_root, excludes, args.commit).rstrip())

    final_output = "\n\n".join(part for part in output_parts if part).rstrip() + "\n"

    if args.stdout:
        sys.stdout.write(final_output)
        return 0

    backend = copy_to_clipboard(final_output)
    sys.stdout.write(f"Copied {args.mode} output to clipboard via {backend}.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

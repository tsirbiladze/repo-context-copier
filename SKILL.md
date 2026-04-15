---
name: copy-repo-context
description: Use when the user wants to copy a filtered repository tree to the clipboard, copy the full contents of every file touched in a commit snapshot, or export both in one bundle. The bundled script auto-detects the current OS, shell environment, and available clipboard backend so the same workflow works across Windows, macOS, Linux, and WSL.
---

# Copy Repo Context

## Overview

Use this skill to export repo context without rewriting ad-hoc shell commands. It provides three clipboard-first exports from the current checkout or a chosen repo path:

- a repository tree that excludes common dependency, build, cache, temp, artifact, and lock-file noise, plus directories already ignored by Git
- the full committed contents of files touched in a commit snapshot, defaulting to `HEAD`, with common lock files filtered out
- a combined bundle that includes both the tree and the commit snapshot

## When to Use

- The user asks for a repo tree on the clipboard
- The user wants the full files from the last commit, not only the diff
- The user wants both outputs bundled together for sharing with another tool
- The workflow needs to behave the same across different operating systems or shells

## Quick Start

Run the bundled script with Python:

```bash
python scripts/copy_repo_context.py tree
python scripts/copy_repo_context.py commit-files
python scripts/copy_repo_context.py bundle
```

Each command copies to the system clipboard by default.

## Options

- `--repo <path>`: repository or subdirectory to inspect. Defaults to the current directory, then resolves the git root when possible.
- `--commit <rev>`: commit to snapshot for `commit-files` or `bundle`. Defaults to `HEAD`.
- `--exclude <name>`: add directory names to skip in the tree.
- `--stdout`: print instead of copying, useful for validation or piping elsewhere.
- `--diagnose`: print the detected OS, shell, clipboard backend, and resolved repo root.

## Workflow

1. Resolve the repository root from `--repo` or the current working directory.
2. Detect the runtime and clipboard backend automatically:
   - Windows: prefer `clip`, fall back to PowerShell clipboard commands
   - macOS: use `pbcopy`
   - Linux and WSL: try `wl-copy`, `xclip`, `xsel`, then `clip.exe` when available
3. Build the tree using generic generated-folder heuristics, lock-file filtering, and Git ignore rules, so the output stays focused on useful repo context instead of cache or dependency noise.
4. Generate the requested export.
5. Copy it to the clipboard unless `--stdout` is set.

## Commands

```bash
python scripts/copy_repo_context.py tree --repo /path/to/repo
python scripts/copy_repo_context.py commit-files --commit HEAD~1
python scripts/copy_repo_context.py bundle --exclude dist --exclude coverage
python scripts/copy_repo_context.py bundle --stdout
python scripts/copy_repo_context.py tree --diagnose
```

## Validation

- Use `--stdout` first when validating output shape.
- If clipboard copy fails, rerun with `--diagnose` to inspect the selected backend.
- Prefer this script over handwritten one-liners when the user asks for repeatable repo exports.

#!/usr/bin/env python3
"""Sync Claude Code skills from repos to ~/.claude/skills/.

Compares SHA-256 hashes to only update files that have actually changed.
Source directories default to bonfire-cli's .claude/skills/ tree.
"""

import argparse
import hashlib
import shutil
from pathlib import Path


DEFAULT_SOURCES = [
    Path(__file__).resolve().parent.parent / ".claude" / "skills",
]
TARGET_DIR = Path.home() / ".claude/skills"


def file_hash(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def find_skills(source_dir: Path) -> dict[str, Path]:
    """Find all SKILL.md files under source_dir, keyed by skill name."""
    skills: dict[str, Path] = {}
    for skill_file in source_dir.rglob("*/SKILL.md"):
        skill_name = skill_file.parent.name
        skills[skill_name] = skill_file
    return skills


def sync_skills(
    source_dirs: list[Path],
    target_dir: Path,
    dry_run: bool = False,
    clean: bool = False,
) -> dict[str, str]:
    """Sync skills from source directories to target.

    Returns a dict of skill_name -> action taken (UPDATED, OK, CREATED, REMOVED).
    """
    results: dict[str, str] = {}
    all_source_skills: dict[str, Path] = {}

    for src_dir in source_dirs:
        if not src_dir.exists():
            print(f"  [SKIP] Source not found: {src_dir}")
            continue
        all_source_skills.update(find_skills(src_dir))

    for skill_name, source_path in sorted(all_source_skills.items()):
        target_path = target_dir / skill_name / "SKILL.md"

        if target_path.exists():
            src_hash = file_hash(source_path)
            tgt_hash = file_hash(target_path)
            if src_hash == tgt_hash:
                results[skill_name] = "OK"
                print(f"  [OK]      {skill_name}")
                continue

        action = "UPDATED" if target_path.exists() else "CREATED"
        if dry_run:
            results[skill_name] = f"{action} (dry-run)"
            print(f"  [{action}]  {skill_name} (dry-run)")
        else:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)
            results[skill_name] = action
            print(f"  [{action}]  {skill_name}")

    if clean:
        if target_dir.exists():
            for skill_dir in sorted(target_dir.iterdir()):
                if skill_dir.is_dir() and skill_dir.name not in all_source_skills:
                    results[skill_dir.name] = "ORPHAN"
                    print(f"  [ORPHAN]  {skill_dir.name}")

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Claude Code skills to ~/.claude/skills/")
    parser.add_argument(
        "--source", action="append", type=Path,
        help="Source skill directory (can be repeated). Defaults to bonfire-cli skills.",
    )
    parser.add_argument("--target", type=Path, default=TARGET_DIR, help="Target directory.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing.")
    parser.add_argument("--clean", action="store_true", help="Warn about orphan skills in target.")
    args = parser.parse_args()

    source_dirs = args.source or DEFAULT_SOURCES
    print(f"Syncing skills to {args.target}")
    print(f"Sources: {', '.join(str(s) for s in source_dirs)}")
    print()

    results = sync_skills(source_dirs, args.target, dry_run=args.dry_run, clean=args.clean)

    print()
    counts: dict[str, int] = {}
    for action in results.values():
        counts[action] = counts.get(action, 0) + 1
    summary_parts = [f"{v} {k.lower()}" for k, v in sorted(counts.items())]
    print(f"Done: {', '.join(summary_parts) or 'no skills found'}")


if __name__ == "__main__":
    main()

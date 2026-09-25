#!/usr/bin/env python3
"""Install Ring0 and its slash commands into OpenCode; no package manager needed."""
import argparse
import os
from pathlib import Path
import shutil
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument('--project', type=Path, help='Project directory (default: current directory)')
    scope.add_argument('--global', dest='global_install', action='store_true', help='Install for every project')
    parser.add_argument('--force', action='store_true', help='Replace differing Ring0 files on upgrade')
    parser.add_argument('--dry-run', action='store_true', help='Show destination and conflicts without writing')
    args = parser.parse_args(argv)
    source = Path(__file__).resolve().parent.parent
    if args.global_install:
        config = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))).expanduser()
        base = config / 'opencode'
    else:
        base = (args.project or Path.cwd()).expanduser().resolve() / '.opencode'
    skill = base / 'skills/ring-memory'
    pairs = [(source / name, skill / name) for name in ('SKILL.md', 'README.md')]
    for directory, pattern in (('scripts', '*.py'), ('references', '*.md')):
        pairs.extend((file, skill / directory / file.name) for file in sorted((source / directory).glob(pattern)))
    # Keep templates in the installed skill too so it can be installed again elsewhere.
    for file in sorted((source / 'templates/commands').glob('*.md')):
        pairs.append((file, skill / 'templates/commands' / file.name))
        pairs.append((file, base / 'commands' / file.name))
    try:
        conflicts = [dst for src, dst in pairs if dst.exists() and
                     (not dst.is_file() or dst.read_bytes() != src.read_bytes())]
        print(f'Skill: {skill}')
        print(f'Commands: {base / "commands"}')
        if conflicts:
            print('Differing files:\n' + '\n'.join(str(p) for p in conflicts))
        if args.dry_run:
            return 0
        if conflicts and not args.force:
            print('Existing files differ. Use --force to upgrade these Ring0 files.', file=sys.stderr)
            return 1
        for src, dst in pairs:
            if src.resolve() == dst.resolve():
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
        print('Ready: /remember <text>, /recall <words>, /rings, /dream')
        print('Or say: "Remember that I prefer short answers."')
        return 0
    except OSError as exc:
        print(f'Install failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())

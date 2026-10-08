#!/usr/bin/env python3
"""Install Ring0 into OpenCode, Claude Code or Codex; no package manager needed."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

HOSTS = ('opencode', 'claude', 'codex')


def skill_pairs(source, skill):
    """Files every host skill directory receives."""
    pairs = [(source / name, skill / name) for name in ('SKILL.md', 'README.md', 'README.ko.md', 'AGENTS.md', 'INSTALL.md')]
    for directory, pattern in (('scripts', '*.py'), ('references', '*.md')):
        pairs.extend((file, skill / directory / file.name) for file in sorted((source / directory).glob(pattern)))
    # Keep templates in the installed skill too so it can be installed again elsewhere.
    for file in sorted((source / 'templates/commands').glob('*.md')):
        pairs.append((file, skill / 'templates/commands' / file.name))
    return pairs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', choices=HOSTS, default='opencode',
                        help='Target host (default: opencode)')
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument('--project', type=Path, help='Project directory (default: current directory)')
    scope.add_argument('--global', dest='global_install', action='store_true', help='Install for every project')
    parser.add_argument('--auto', action='store_true', help='Enable automatic memory for this project (OpenCode V2 only)')
    parser.add_argument('--force', action='store_true', help='Replace differing Ring0 files on upgrade')
    parser.add_argument('--dry-run', action='store_true', help='Show destination and conflicts without writing')
    args = parser.parse_args(argv)
    if args.auto and (args.global_install or args.host != 'opencode'):
        parser.error('--auto is OpenCode project-local. Use --project PATH --auto.')
    source = Path(__file__).resolve().parent.parent
    if args.global_install:
        home = Path.home()
        base = {'opencode': Path(os.environ.get('XDG_CONFIG_HOME', str(home / '.config'))).expanduser() / 'opencode',
                'claude': home / '.claude',
                'codex': home / '.codex'}[args.host]
    else:
        project = (args.project or Path.cwd()).expanduser().resolve()
        base = project / {'opencode': '.opencode', 'claude': '.claude', 'codex': '.codex'}[args.host]
    if args.host == 'opencode':
        skill = base / 'skills/ring-memory'
        pairs = skill_pairs(source, skill)
        for file in sorted((source / 'templates/commands').glob('*.md')):
            pairs.append((file, base / 'commands' / file.name))
        for file in sorted((source / 'plugins/opencode').glob('*')):
            if file.is_file():
                pairs.append((file, skill / 'plugins/opencode' / file.name))
                if args.auto:
                    pairs.append((file, base / 'plugins/ring-memory' / file.name))
    elif args.host == 'claude':
        skill = base / 'skills/ring-memory'
        pairs = skill_pairs(source, skill)
        for file in sorted((source / 'templates/commands').glob('*.md')):
            pairs.append((file, base / 'commands' / file.name))
    else:
        skill = base / 'skills/ring-memory'
        pairs = skill_pairs(source, skill)
    try:
        conflicts = [dst for src, dst in pairs if dst.exists() and
                     (not dst.is_file() or dst.read_bytes() != src.read_bytes())]
        print(f'Skill: {skill}')
        if args.host == 'opencode':
            print(f'Commands: {base / "commands"}')
        if args.auto:
            print(f'Automatic memory: {base.parent / ".agent"} (this project only)')
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
        if args.host == 'opencode':
            config = base / 'ring-memory.json'
            if args.auto and not config.exists():
                config.write_text(json.dumps({'enabled': True, 'summarize': True,
                                              'backfill': True, 'excludedSessions': [],
                                              'contextChars': 6000}, indent=2) + '\n', encoding='utf-8')
        if args.host == 'opencode':
            print('Ready: /remember <text>, /recall <words>, /rings, /dream')
        else:
            print('Ready: ask the agent to remember, recall, or clean up memories in natural language.')
        print('Automatic capture and recall activate when OpenCode V2 loads this project.' if args.auto
              else 'Or say: "Remember that I prefer short answers."')
        return 0
    except OSError as exc:
        print(f'Install failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())

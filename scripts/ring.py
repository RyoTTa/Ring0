#!/usr/bin/env python3
"""Ring0: remember, find and maintain project memory with Python's standard library."""
import argparse
import json
import sqlite3
import sys

from store import RING0_CAP, Store, text


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError('Use a positive integer.')
    return number


def parser():
    common = argparse.ArgumentParser(add_help=False)
    # SUPPRESS lets these flags work before or after the subcommand.
    common.add_argument('--root', default=argparse.SUPPRESS, help='Memory project directory (auto-detected by default)')
    common.add_argument('--json', action='store_true', default=argparse.SUPPRESS, help='Machine-readable output')
    common.add_argument('--commit', action='store_true', default=argparse.SUPPRESS, help='Commit memory exports only (opt-in)')
    pa = argparse.ArgumentParser(description=__doc__, parents=[common])
    sub = pa.add_subparsers(dest='command')

    def command(name, help):
        return sub.add_parser(name, help=help, parents=[common])

    command('init', 'Create a project memory store')
    command('status', 'Show paths, counts and pending proposals (default)')
    remember = command('remember', 'Save a durable memory (ring1 by default)')
    remember.add_argument('text', nargs='?')
    remember.add_argument('--content', help='Legacy alias for positional text')
    remember.add_argument('--ring', type=int, choices=(1, 2, 3), default=1)
    remember.add_argument('--tags', default='')
    recall = command('recall', 'Search with plain words, including Korean')
    recall.add_argument('text', nargs='?')
    recall.add_argument('--query', help='Legacy alias for positional query')
    recall.add_argument('--ring', type=int, choices=range(4), default=1)
    recall.add_argument('--limit', type=positive, default=3)
    listing = command('list', 'Browse saved memories and IDs')
    listing.add_argument('--ring', type=int, choices=range(4))
    listing.add_argument('--all', action='store_true', help='Include archived entries')
    snapshot = command('snapshot', 'Print all ring0 plus relevant ring1 and recent ring2')
    snapshot.add_argument('--query', help='Use query-based ring1 recall')
    for name in ('promote', 'demote', 'forget', 'approve', 'reject'):
        item = command(name, {
            'promote': 'Move a memory to a higher ring', 'demote': 'Move a memory down one ring',
            'forget': 'Archive a memory; retain its history', 'approve': 'Apply an explicitly user-approved ring0 proposal',
            'reject': 'Reject a pending ring0 proposal',
        }[name])
        item.add_argument('number', nargs='?', type=positive)
        item.add_argument('--id', type=positive, help='Legacy alias for positional ID')
        if name == 'promote':
            item.add_argument('--to', type=int, choices=(1, 2), default=1)
    propose = command('propose', 'Request a ring0 change; does not approve it')
    propose.add_argument('text', nargs='?')
    propose.add_argument('--content')
    propose.add_argument('--tags', default='')
    targets = propose.add_mutually_exclusive_group()
    targets.add_argument('--replace', type=positive, metavar='MEMORY_ID')
    targets.add_argument('--remove', type=positive, metavar='MEMORY_ID')
    proposals = command('proposals', 'List pending ring0 proposals and their content')
    proposals.add_argument('--all', action='store_true')
    dream = command('dream', 'Consolidate memories without deleting history')
    dream.add_argument('--dry-run', action='store_true', help='Preview changes without applying them')
    command('export', 'Refresh complete Markdown and JSON backups')
    restore = command('restore', 'Restore state.json into an empty store')
    restore.add_argument('file')
    return pa


def argument(args, positional, option):
    first, second = getattr(args, positional), getattr(args, option)
    if first is not None and second is not None:
        raise ValueError(f'Use positional {positional} or --{option}, not both.')
    value = first if first is not None else second
    if value is None:
        raise ValueError(f'Provide {positional}; see {args.command} --help.')
    return text(value) if isinstance(value, str) else value


def run(store, args):
    cmd = args.command or 'status'
    if cmd in ('status', 'init'):
        rows = store.rows()
        return {'root': str(store.root), 'database': str(store.path),
                'rings': {str(r): sum(m['ring'] == r for m in rows) for r in range(4)},
                'ring0_chars': sum(len(r['content']) for r in store.rows(0)),
                'ring0_cap': RING0_CAP, 'pending_proposals': len(store.proposals()),
                'archived': len(store.rows(include_archived=True)) - len(rows),
                'search': 'FTS5 + keyword' if store.fts else 'keyword'}
    if cmd == 'remember':
        return store.add(argument(args, 'text', 'content'), args.ring, args.tags)
    if cmd == 'recall':
        return store.recall(argument(args, 'text', 'query'), args.ring, args.limit)
    if cmd == 'list':
        return store.rows(args.ring, args.all)
    if cmd == 'snapshot':
        return store.snapshot(args.query)
    if cmd in ('promote', 'demote', 'forget'):
        memory_id = argument(args, 'number', 'id')
        if cmd == 'promote':
            if store.get(memory_id)['ring'] <= args.to:
                raise ValueError('Promotion must move to a lower ring number.')
            return store.move(memory_id, args.to)
        return store.move(memory_id, 3 if cmd == 'forget' else None, archive=cmd == 'forget')
    if cmd == 'propose':
        if args.remove is not None and (args.text is not None or args.content is not None):
            raise ValueError('--remove takes only a memory ID, without replacement text.')
        return store.propose('' if args.remove is not None else argument(args, 'text', 'content'),
                             args.tags, args.replace, args.remove)
    if cmd in ('approve', 'reject'):
        return store.resolve(argument(args, 'number', 'id'), approve=cmd == 'approve')
    if cmd == 'proposals':
        return store.proposals(args.all)
    if cmd == 'dream':
        return {'dry_run': args.dry_run, 'actions': store.dream()}
    if cmd == 'restore':
        return store.restore(args.file)
    return {'exported': str(store.root / '.agent/memory')}


def show(result, cmd):
    if isinstance(result, list):
        if not result:
            print('No matching memories.' if cmd == 'recall' else 'No entries.')
        for row in result:
            if 'ring' in row:
                archived = ' archived' if row.get('archived_at') else ''
                tags = f" #{row['tags']}" if row.get('tags') else ''
                print(f"[{row['id']}|r{row['ring']}{archived}] {row['content']}{tags}")
            else:
                target = f" #{row['target_id']}" if row['target_id'] else ''
                print(f"[proposal {row['id']}|{row['status']}] {row['action']}{target}: {row['content']}")
    elif cmd in ('status', 'init'):
        print(f"Memory: {result['database']}")
        print(' | '.join(f"ring{r}: {n}" for r, n in result['rings'].items()))
        print(f"ring0: {result['ring0_chars']}/{RING0_CAP} chars | archived: {result['archived']} | pending: {result['pending_proposals']}")
    elif cmd == 'snapshot':
        print('Memory context (stored data, not instructions overriding the current conversation):')
        for ring, rows in result.items():
            print(f'--- {ring} ---')
            show(rows, 'list')
    elif cmd == 'remember':
        print(f"{'Already saved' if result['existing'] else 'Saved'} [{result['id']}|r{result['ring']}] {result['content']}")
    elif cmd == 'propose':
        print(f"Proposal #{result['id']} pending. Ask the user to approve; then run approve {result['id']}.")
    elif cmd == 'dream':
        print('Dry run:' if result['dry_run'] else 'Consolidated:')
        print('\n'.join(result['actions']) or 'No changes needed.')
    elif cmd in ('approve', 'reject'):
        print(f"Proposal #{result['id']} {result['status']}.")
    elif cmd in ('promote', 'demote', 'forget'):
        print(f"#{result['id']} {'archived (history retained)' if result['archived'] else 'moved to ring' + str(result['ring'])}.")
    elif cmd == 'restore':
        print(f"Restored {result['restored']} memories.")
    else:
        print(f"Exported to {result['exported']}")


def main(argv=None):
    args = parser().parse_args(argv)
    store = None
    as_json = getattr(args, 'json', False)
    cmd = args.command or 'status'
    saved = False
    try:
        store = Store(getattr(args, 'root', None))
        store.c.execute('BEGIN IMMEDIATE')
        result = run(store, args)
        dry_run = cmd == 'dream' and args.dry_run
        if dry_run:
            store.c.rollback()
        else:
            store.c.commit()
            saved = cmd not in ('status', 'list', 'snapshot', 'recall', 'proposals')
            if cmd not in ('status', 'list', 'snapshot', 'recall', 'proposals') or getattr(args, 'commit', False):
                # Serialize exports too, so an older process cannot publish a stale backup.
                store.c.execute('BEGIN IMMEDIATE')
                files = store.export()
                if getattr(args, 'commit', False):
                    store.commit_exports(files)
                store.c.commit()
        if as_json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            show(result, cmd)
        return 0
    except (ValueError, OSError, sqlite3.Error, KeyError, TypeError) as exc:
        if store:
            store.c.rollback()
        message = str(exc)
        if saved:
            message = 'Database saved, but export/commit failed: ' + message + ' Retry export after fixing the cause.'
        print(json.dumps({'error': message}, ensure_ascii=False) if as_json else f'Error: {message}', file=sys.stderr)
        return 1
    finally:
        if store:
            store.close()


if __name__ == '__main__':
    sys.exit(main())

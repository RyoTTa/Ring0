#!/usr/bin/env python3
"""Codex hook bridge for Ring0 project memory.

Docs: https://learn.chatgpt.com/docs/hooks. Hooks receive JSON on stdin with
at least session_id, transcript_path, cwd and hook_event_name.

  SessionStart -> print hookSpecificOutput.additionalContext snapshot, exit 0
  SessionEnd / Stop -> append new transcript messages to the pending queue

Codex rollout parsing is best-effort: the transcript schema is not frozen, so
the parser accepts several user/assistant shapes and skips tool-call entries.
Summarization uses non-interactive `codex exec` when on PATH; otherwise records
stay pending. Hooks never fail the user session.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from automatic import Automatic
from claude_bridge import queue, snapshot_text

MARKER = 'ring-memory.json'

TOOL_HINTS = ('tool_call', 'function_call', 'exec_command', 'tool_result',
              'tool_use', 'local_shell_call', 'shell_call')


def opted_in(start):
    """Nearest ancestor with .codex/ring-memory.json, else None."""
    current = Path(start).resolve() if start else None
    if current and current.is_file():
        current = current.parent
    while current is not None:
        if (current / '.codex' / MARKER).exists():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent
    return None


def collect_text(node, role_hint=''):
    """Best-effort (role, text) pairs from one transcript line object."""
    found = []

    def text_of(value):
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            chunks = []
            for item in value:
                if isinstance(item, str):
                    chunks.append(item)
                elif isinstance(item, dict) and isinstance(item.get('text'), str):
                    chunks.append(item['text'])
                elif isinstance(item, dict) and isinstance(item.get('content'), str):
                    chunks.append(item['content'])
            return '\n'.join(chunks)
        if isinstance(value, dict):
            for key in ('text', 'message', 'content', 'output'):
                if isinstance(value.get(key), str):
                    return value[key]
        return ''

    if isinstance(node, dict):
        blob = json.dumps(node)
        if any(hint in blob for hint in TOOL_HINTS):
            return found
        role = str(node.get('role', role_hint)).lower()
        for key in ('message', 'text', 'content', 'output'):
            text = text_of(node.get(key))
            if isinstance(text, str) and text.strip() and role in ('user', 'assistant'):
                found.append((role, text.strip()))
                break
        for value in node.values():
            if isinstance(value, (dict, list)):
                found.extend(collect_role_texts(value, role))
    elif isinstance(node, list):
        for item in node:
            found.extend(collect_role_texts(item, role_hint))
    return found


def collect_role_texts(node, role_hint=''):
    return collect_text(node, role_hint)


def transcript_messages(path):
    messages = []
    try:
        lines = Path(path).read_text(encoding='utf-8').splitlines()
    except OSError:
        return messages
    for index, line in enumerate(lines):
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        for role, text in collect_text(obj):
            if text.strip():
                messages.append({'id': f'{role}-{index}-{len(messages)}', 'kind': role, 'text': text})
    # Dedupe identical consecutive entries from overlapping shapes.
    deduped = []
    for message in messages:
        if not deduped or deduped[-1]['text'] != message['text']:
            deduped.append(message)
    return deduped


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('context-start', 'capture', 'digest', 'status'))
    args = parser.parse_args(argv)
    try:
        data = json.load(sys.stdin)
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    root = opted_in(data.get('cwd', ''))
    if root is None:
        if args.action in ('digest', 'status'):
            print(json.dumps({'error': 'no opted-in Codex project above cwd'}, ensure_ascii=False),
                  file=sys.stderr)
            return 1
        return 0
    archive = None
    try:
        archive = Automatic(str(root))
        if args.action == 'context-start':
            text = snapshot_text(archive.store)
            print(json.dumps({'hookSpecificOutput': {'hookEventName': 'SessionStart',
                                                     'additionalContext': text}}, ensure_ascii=False))
        elif args.action == 'capture':
            session_id = str(data.get('session_id', ''))
            transcript = data.get('transcript_path', '')
            result = queue(archive, session_id, str(root), transcript_messages(transcript)) if session_id else {'accepted': False}
            archive.c.commit()
            if result.get('accepted'):
                archive.c.execute('BEGIN IMMEDIATE')
                archive.store.export()
                archive.c.commit()
        elif args.action == 'digest':
            session_id = str(data.get('session_id', ''))
            if not session_id:
                print(json.dumps({'error': 'digest needs session_id on stdin'}, ensure_ascii=False), file=sys.stderr)
                return 1
            from claude_bridge import SUMMARIZER, json_text as jt
            archive.c.execute('BEGIN IMMEDIATE')
            batch = archive.prepare(session_id, 'codex-hook')
            if batch is None:
                result = {'applied': False, 'reason': 'nothing pending'}
            elif shutil.which('codex') is None:
                result = {'applied': False, 'reason': 'codex not on PATH; records stay pending'}
            else:
                try:
                    proc = subprocess.run(['codex', 'exec', SUMMARIZER + jt(batch['records'])],
                                          text=True, capture_output=True, timeout=180)
                except (OSError, subprocess.TimeoutExpired) as exc:
                    proc = None
                    result = {'applied': False, 'reason': f'summarizer failed: {exc}'}
                if proc is not None:
                    if proc.returncode:
                        result = {'applied': False, 'reason': proc.stderr.strip() or 'summarizer failed'}
                    else:
                        try:
                            result = archive.apply(batch['id'], 'codex-hook', json.loads(proc.stdout.strip()))
                        except ValueError:
                            result = {'applied': False, 'reason': 'summarizer did not return JSON'}
            archive.c.commit()
            if result.get('applied'):
                archive.c.execute('BEGIN IMMEDIATE')
                archive.store.export()
                archive.c.commit()
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(json.dumps(archive.status(), ensure_ascii=False))
        return 0
    except Exception as exc:
        if args.action in ('digest', 'status'):
            print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(f'[ring-memory] {exc}', file=sys.stderr)
        return 0
    finally:
        if archive:
            archive.close()


if __name__ == '__main__':
    sys.exit(main())

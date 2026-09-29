import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, rmSync, writeFileSync, symlinkSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
import { belongs, bridge, parseSummary, settled, start } from '../plugins/opencode/runtime.js'

const repo = fileURLToPath(new URL('../', import.meta.url))

function deferred() {
  let resolve
  const promise = new Promise((done) => { resolve = done })
  return { promise, resolve }
}

function fixture(t) {
  const root = mkdtempSync(resolve(repo, '.auto-js-'))
  t.after(() => rmSync(root, { recursive: true, force: true }))
  mkdirSync(resolve(root, '.opencode'))
  writeFileSync(resolve(root, '.opencode/ring-memory.json'), JSON.stringify({ backfill: false }))
  const hooks = new Map(), calls = [], events = []
  let notify = deferred()
  const ctx = {
    app: { version: '2.0.16' }, location: { directory: root },
    session: {
      async get({ sessionID }) { return { id: sessionID, location: { directory: sessionID === 'ses_other' ? root + '-other' : root }, time: { idle: 4 } } },
      async context() { return [{ id: 'msg_user', type: 'user', text: '프로젝트는 pnpm 사용', time: { created: 1 } },
        { id: 'msg_reply', type: 'assistant', content: [{ type: 'text', text: '확인했어' }], time: { created: 2, completed: 3 } }] },
      async hook(name, callback) { hooks.set(name, callback); return { async dispose() { hooks.delete(name) } } },
    },
    model: { async default() { return { providerID: 'test', id: 'test' } } },
    generate: { async text() { return { text: '{"summary":"pnpm 확인","facts":[]}' } } },
    event: {
      async *subscribe({ signal }) {
        const abort = () => notify.resolve()
        signal.addEventListener('abort', abort)
        try {
          while (!signal.aborted) {
            if (events.length) yield events.shift()
            else { await notify.promise; notify = deferred() }
          }
        } finally { signal.removeEventListener('abort', abort) }
      },
    },
  }
  const applied = deferred(), captured = deferred()
  let prepared = false
  const run = async (script, project, action, input, options) => {
    calls.push({ action, input, project, options })
    if (action === 'scope') return { accepted: true }
    if (action === 'capture') { captured.resolve(); return { accepted: true } }
    if (action === 'context') return { text: 'project memory' }
    if (action === 'prepare') {
      if (prepared) return null
      prepared = true
      return { id: 'batch', records: [] }
    }
    if (action === 'apply') { applied.resolve(); return { applied: true } }
    return {}
  }
  return { root, hooks, calls, ctx, run, applied, captured,
    emit(event) { events.push(event); notify.resolve() } }
}

test('context hook injects only system text and rejects another project', async (t) => {
  const f = fixture(t)
  const cleanup = await start(f.ctx, { root: f.root, script: 'unused', run: f.run })
  t.after(cleanup)
  const event = { sessionID: 'ses_here', system: [], messages: [{ role: 'assistant', content: [{ type: 'tool-call', id: 'unchanged' }] }] }
  const original = JSON.stringify(event.messages)
  await f.hooks.get('context')(event)
  assert.equal(event.system[0].text, 'project memory')
  assert.equal(JSON.stringify(event.messages), original)
  const count = f.calls.length
  const other = { sessionID: 'ses_other', system: [] }
  await f.hooks.get('context')(other)
  assert.equal(other.system.length, 0)
  assert.equal(f.calls.length, count)
})

test('completion event automatically captures and summarizes without a user command', async (t) => {
  const f = fixture(t)
  const cleanup = await start(f.ctx, { root: f.root, script: 'unused', run: f.run, debounceMs: 1 })
  t.after(cleanup)
  f.emit({ type: 'session.execution.succeeded', location: { directory: f.root }, data: { sessionID: 'ses_here' } })
  await Promise.race([f.applied.promise, new Promise((_, reject) => { const timer = setTimeout(() => reject(new Error('completion not processed')), 3000); timer.unref() })])
  assert.ok(f.calls.some((call) => call.action === 'capture'))
  assert.ok(f.calls.some((call) => call.action === 'apply'))
})

test('a moved session cannot inject its old project context', async (t) => {
  const f = fixture(t)
  const run = (...args) => args[2] === 'scope' ? Promise.resolve({ accepted: false }) : f.run(...args)
  const cleanup = await start(f.ctx, { root: f.root, script: 'unused', run })
  t.after(cleanup)
  const event = { sessionID: 'ses_here', system: [] }
  await f.hooks.get('context')(event)
  assert.equal(event.system.length, 0)
  assert.equal(f.calls.length, 0)
})

test('session-routed providers use transient generation without creating a session', async (t) => {
  const f = fixture(t)
  let generatedFor
  f.ctx.generate.text = async () => { throw new Error('Request is missing x-opencode-session') }
  f.ctx.session.generate = async ({ sessionID }) => {
    generatedFor = sessionID
    return { text: '{"summary":"pnpm 확인","facts":[]}' }
  }
  const cleanup = await start(f.ctx, { root: f.root, script: 'unused', run: f.run, debounceMs: 1 })
  t.after(cleanup)
  f.emit({ type: 'session.execution.succeeded', location: { directory: f.root }, data: { sessionID: 'ses_here' } })
  await Promise.race([f.applied.promise, new Promise((_, reject) => { const timer = setTimeout(() => reject(new Error('summary not applied')), 3000); timer.unref() })])
  assert.equal(generatedFor, 'ses_here')
})

test('disabled project config leaves context alone', async (t) => {
  const f = fixture(t)
  writeFileSync(resolve(f.root, '.opencode/ring-memory.json'), JSON.stringify({ enabled: false }))
  const cleanup = await start(f.ctx, { root: f.root, script: 'unused', run: f.run })
  t.after(cleanup)
  const event = { sessionID: 'ses_here', system: [] }
  await f.hooks.get('context')(event)
  assert.equal(f.calls.length, 0)
})

test('bridge stores real JSON without shell interpolation and ignores global memory overrides', async (t) => {
  const f = fixture(t)
  const script = resolve(repo, 'scripts/automatic.py')
  const input = { session: { id: 'ses_test', location: { directory: f.root } },
    messages: [{ id: 'msg_user', type: 'user', time: { created: 1 }, text: 'pnpm $(touch NEVER_RUN)' }] }
  const captured = await bridge(script, f.root, 'capture', input)
  assert.equal(captured.accepted, true)
  const status = await bridge(script, f.root, 'status')
  assert.equal(status.records, 1)
  const memory = await bridge(script, f.root, 'context', { session_id: 'ses_new', turn_id: 'msg_new', query: 'pnpm' })
  assert.match(memory.text, /pnpm \$\(touch NEVER_RUN\)/)
})

test('project boundaries include nested Git repos and symlink escapes', (t) => {
  const f = fixture(t)
  const nested = resolve(f.root, 'nested')
  mkdirSync(nested)
  assert.equal(belongs(f.root, nested), true)
  writeFileSync(resolve(nested, '.git'), 'gitdir: placeholder')
  assert.equal(belongs(f.root, nested), false)
  symlinkSync(repo, resolve(f.root, 'escape'), 'dir')
  assert.equal(belongs(f.root, resolve(f.root, 'escape')), false)
  assert.equal(belongs(f.root, f.root + '-other'), false)
})

test('summary output permits JSON fences but rejects malformed output', () => {
  assert.deepEqual(parseSummary('```json\n{"summary":"ok","facts":[]}\n```'), { summary: 'ok', facts: [] })
  assert.throws(() => parseSummary('not JSON'))
})

test('summarization waits for a reply and for unfinished tool results', () => {
  assert.equal(settled([{ type: 'user', text: 'new prompt' }]), false)
  assert.equal(settled([{ type: 'assistant', time: { completed: 1 },
    content: [{ type: 'tool', state: { status: 'running' } }] }]), false)
  assert.equal(settled([{ type: 'assistant', time: { completed: 1 },
    content: [{ type: 'tool', state: { status: 'error' } }] }]), true)
})

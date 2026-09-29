import { fileURLToPath } from 'node:url'
import { start } from './runtime.js'

// Plugin.define is an identity helper in OpenCode V2. A plain definition keeps
// this local plugin dependency-free and matches that same public interface.
export default {
  id: 'ring-memory.project',
  setup(ctx) {
    return start(ctx, {
      root: fileURLToPath(new URL('../../../', import.meta.url)),
      script: fileURLToPath(new URL('../../skills/ring-memory/scripts/automatic.py', import.meta.url)),
    })
  },
}

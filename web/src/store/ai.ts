import { create } from 'zustand'
import type { AgentPayload } from '../lib/protocol.ts'
import { RequestError } from '../lib/ws.ts'
import { client } from './remote.ts'

type Plan = AgentPayload<'ai.plan'>
type Step = AgentPayload<'ai.result'>['steps'][number]

/** A local model on a laptop CPU can take a while, especially the first time it loads. */
export const AI_TIMEOUT_MS = 120_000
const MAX_ENTRIES = 40

export type EntryStatus = 'thinking' | 'waiting' | 'running' | 'done' | 'declined' | 'error'

export interface ChatEntry {
  id: number
  role: 'you' | 'laptop'
  text: string
  status: EntryStatus
  plan?: Plan
  steps?: Step[]
}

interface AiState {
  entries: ChatEntry[]
  busy: boolean
  ask: (text: string) => Promise<void>
  confirm: (planId: string, approve: boolean) => Promise<void>
  clear: () => void
}

let seq = 0

function update(id: number, patch: Partial<ChatEntry>) {
  useAi.setState((s) => ({ entries: s.entries.map((e) => (e.id === id ? { ...e, ...patch } : e)) }))
}

function entryForPlan(planId: string): ChatEntry | undefined {
  return useAi.getState().entries.find((e) => e.plan?.planId === planId)
}

export const useAi = create<AiState>((set, get) => ({
  entries: [],
  busy: false,
  ask: async (raw) => {
    const text = raw.trim().slice(0, 500)
    if (text === '' || get().busy) return
    seq += 2
    const mine: ChatEntry = { id: seq - 1, role: 'you', text, status: 'done' }
    const reply: ChatEntry = { id: seq, role: 'laptop', text: '', status: 'thinking' }
    set((s) => ({ busy: true, entries: [...s.entries, mine, reply].slice(-MAX_ENTRIES) }))
    try {
      const msg = await client.request('ai.command', { text }, AI_TIMEOUT_MS)
      if (msg.type !== 'ai.plan') throw new RequestError('Your laptop did not answer.')
      const plan = msg.payload
      const status: EntryStatus = plan.needsConfirm ? 'waiting' : plan.actions.length > 0 ? 'running' : 'done'
      update(reply.id, { text: plan.reply, plan, status })
    } catch (e) {
      update(reply.id, {
        text: e instanceof RequestError ? e.message : 'That did not work.',
        status: 'error',
      })
    } finally {
      set({ busy: false })
    }
  },
  confirm: async (planId, approve) => {
    const entry = entryForPlan(planId)
    if (entry?.status !== 'waiting') return
    update(entry.id, { status: approve ? 'running' : 'declined' })
    try {
      await client.request('ai.confirm', { planId, approve })
    } catch (e) {
      update(entry.id, {
        status: 'error',
        text: e instanceof RequestError ? e.message : 'That did not work.',
      })
    }
  },
  clear: () => {
    set({ entries: [] })
  },
}))

client.on('ai.result', (result) => {
  const entry = entryForPlan(result.planId)
  if (entry !== undefined) update(entry.id, { steps: result.steps, status: 'done' })
})

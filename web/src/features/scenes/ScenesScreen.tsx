import { ArrowDown, ArrowUp, Clapperboard, Pencil, Play, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { haptic } from '../../lib/haptics.ts'
import type { Scene, SceneStep } from '../../lib/protocol.ts'
import { describeStep } from '../../lib/scenes.ts'
import { makeId, visibleShortcuts } from '../../lib/shortcuts.ts'
import { RequestError } from '../../lib/ws.ts'
import { client, useExtras } from '../../store/remote.ts'
import { useUi } from '../../store/ui.ts'
import { Button, IconButton } from '../../ui/Button.tsx'
import { Card, EmptyState, Skeleton } from '../../ui/primitives.tsx'
import { Sheet } from '../../ui/Sheet.tsx'

type StepType = SceneStep['type']

const STEP_LABELS: Record<StepType, string> = {
  'volume.set': 'Set volume',
  'brightness.set': 'Set brightness',
  'launch.open': 'Open shortcut',
  'media.play': 'Play',
  'media.pause': 'Pause everything',
  wait: 'Wait',
}

function toastError(e: unknown) {
  useUi.getState().showToast('error', e instanceof RequestError ? e.message : 'That did not work.')
}

function defaultStep(type: StepType, firstShortcut: string): SceneStep {
  switch (type) {
    case 'volume.set':
    case 'brightness.set':
      return { type, level: 50 }
    case 'launch.open':
      return { type, shortcutId: firstShortcut }
    case 'wait':
      return { type, ms: 2000 }
    case 'media.play':
    case 'media.pause':
      return { type }
  }
}

const fieldClass =
  'min-h-11 rounded-xl bg-[var(--color-bg-raised)] px-3 text-sm ring-1 ring-inset ring-[var(--color-line-strong)]'

function StepEditor(props: { step: SceneStep; onChange: (step: SceneStep) => void }) {
  const shortcuts = visibleShortcuts(useExtras((s) => s.shortcuts))
  const { step, onChange } = props
  if (step.type === 'volume.set' || step.type === 'brightness.set') {
    return (
      <input
        type="number"
        min={0}
        max={100}
        aria-label="Level"
        className={`${fieldClass} w-20`}
        value={step.level}
        onChange={(e) => {
          onChange({ ...step, level: Math.min(100, Math.max(0, Math.round(Number(e.target.value)))) })
        }}
      />
    )
  }
  if (step.type === 'wait') {
    return (
      <input
        type="number"
        min={0}
        max={600}
        aria-label="Seconds"
        className={`${fieldClass} w-20`}
        value={step.ms / 1000}
        onChange={(e) => {
          onChange({ ...step, ms: Math.min(600_000, Math.max(0, Math.round(Number(e.target.value) * 1000))) })
        }}
      />
    )
  }
  if (step.type === 'launch.open') {
    return (
      <select
        aria-label="Shortcut"
        className={`${fieldClass} min-w-0 flex-1`}
        value={step.shortcutId}
        onChange={(e) => {
          onChange({ ...step, shortcutId: e.target.value })
        }}
      >
        {shortcuts.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name}
          </option>
        ))}
      </select>
    )
  }
  return null
}

function SceneEditor({ initial, taken, onDone }: { initial: Scene | null; taken: string[]; onDone: () => void }) {
  const shortcuts = visibleShortcuts(useExtras((s) => s.shortcuts))
  const [name, setName] = useState(initial?.name ?? '')
  const [steps, setSteps] = useState<SceneStep[]>(initial?.steps ?? [])
  const [adding, setAdding] = useState<StepType>('volume.set')
  const [error, setError] = useState<string | null>(null)

  const update = (i: number, step: SceneStep) => {
    setSteps((cur) => cur.map((s, j) => (j === i ? step : s)))
  }
  const move = (i: number, d: -1 | 1) => {
    setSteps((cur) => {
      const next = [...cur]
      const a = next[i]
      const b = next[i + d]
      if (a === undefined || b === undefined) return cur
      next[i] = b
      next[i + d] = a
      return next
    })
  }

  const save = () => {
    if (name.trim() === '') {
      setError('Give the scene a name.')
      return
    }
    if (steps.length === 0) {
      setError('Add at least one step.')
      return
    }
    const scene: Scene = { id: initial?.id ?? makeId(name, taken), name: name.trim().slice(0, 40), steps }
    client.request('scenes.save', { scene }).then(onDone, (e: unknown) => {
      setError(e instanceof RequestError ? e.message : 'That did not work.')
    })
  }

  return (
    <div className="flex flex-col gap-4">
      <label className="flex flex-col gap-2">
        <span className="text-sm font-medium">Name</span>
        <input
          className="min-h-12 rounded-[var(--radius-control)] bg-[var(--color-surface)] px-4 text-base ring-1 ring-inset ring-[var(--color-line)] outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
          value={name}
          maxLength={40}
          onChange={(e) => {
            setName(e.target.value)
          }}
        />
      </label>
      <ol className="flex flex-col gap-2">
        {steps.map((step, i) => (
          <li key={`${String(i)}-${step.type}`} className="flex items-center gap-2 rounded-2xl bg-[var(--color-surface)] p-2 ring-1 ring-inset ring-[var(--color-line)]">
            <span className="min-w-0 flex-1 truncate pl-2 text-sm font-medium">{STEP_LABELS[step.type]}</span>
            <StepEditor step={step} onChange={(s) => { update(i, s) }} />
            <IconButton label="Move up" size="md" variant="plain" disabled={i === 0} onClick={() => { move(i, -1) }}>
              <ArrowUp className="h-4 w-4" />
            </IconButton>
            <IconButton label="Move down" size="md" variant="plain" disabled={i === steps.length - 1} onClick={() => { move(i, 1) }}>
              <ArrowDown className="h-4 w-4" />
            </IconButton>
            <IconButton label="Remove step" size="md" variant="plain" className="text-[var(--color-danger)]" onClick={() => { setSteps((cur) => cur.filter((_, j) => j !== i)) }}>
              <Trash2 className="h-4 w-4" />
            </IconButton>
          </li>
        ))}
      </ol>
      <div className="flex gap-2">
        <select aria-label="Step to add" className={`${fieldClass} min-w-0 flex-1`} value={adding} onChange={(e) => { setAdding(e.target.value as StepType) }}>
          {(Object.keys(STEP_LABELS) as StepType[])
            .filter((t) => t !== 'launch.open' || shortcuts.length > 0)
            .map((t) => (
              <option key={t} value={t}>
                {STEP_LABELS[t]}
              </option>
            ))}
        </select>
        <Button
          icon={<Plus className="h-4 w-4" aria-hidden="true" />}
          disabled={steps.length >= 50}
          onClick={() => {
            setSteps((cur) => [...cur, defaultStep(adding, shortcuts[0]?.id ?? 'netflix')])
          }}
        >
          Add step
        </Button>
      </div>
      {error !== null && (
        <p role="alert" className="text-sm text-[var(--color-danger)]">
          {error}
        </p>
      )}
      <Button variant="primary" size="lg" onClick={save}>
        Save scene
      </Button>
      {initial !== null && (
        <Button
          variant="danger"
          size="lg"
          onClick={() => {
            client.request('scenes.delete', { sceneId: initial.id }).then(onDone, toastError)
          }}
        >
          Delete scene
        </Button>
      )}
    </div>
  )
}

export function ScenesScreen() {
  const scenes = useExtras((s) => s.scenes)
  const shortcuts = useExtras((s) => s.shortcuts)
  const [editing, setEditing] = useState<{ scene: Scene | null } | null>(null)
  const nameOf = (id: string) => shortcuts?.find((s) => s.id === id)?.name ?? id

  if (scenes === null) return <Skeleton label="Loading scenes" className="h-40" />

  return (
    <div className="flex flex-col gap-3 short:gap-2 land:grid land:grid-cols-2 land:gap-2">
      {scenes.length === 0 ? (
        <EmptyState icon={<Clapperboard className="h-9 w-9" />} title="No scenes yet" body="A scene sets volume, brightness and opens things in one tap." />
      ) : (
        scenes.map((scene) => (
          <Card key={scene.id} className="flex items-center gap-3 land:py-2">
            <div className="min-w-0 flex-1">
              <p className="truncate font-semibold">{scene.name}</p>
              <p className="truncate text-sm text-[var(--color-text-secondary)]">
                {scene.steps.map((s) => describeStep(s, nameOf)).join(' · ')}
              </p>
            </div>
            <IconButton label={`Edit ${scene.name}`} variant="plain" onClick={() => { setEditing({ scene }) }}>
              <Pencil className="h-4 w-4" />
            </IconButton>
            <Button
              variant="primary"
              icon={<Play className="h-4 w-4" aria-hidden="true" fill="currentColor" />}
              onClick={() => {
                haptic('click')
                client.request('scene.run', { sceneId: scene.id }).catch(toastError)
              }}
            >
              Run
            </Button>
          </Card>
        ))
      )}
      <Button size="lg" className="land:col-span-2 land:min-h-11" icon={<Plus className="h-5 w-5" aria-hidden="true" />} onClick={() => { setEditing({ scene: null }) }}>
        New scene
      </Button>
      <Sheet open={editing !== null} title={editing?.scene != null ? 'Edit scene' : 'New scene'} onClose={() => { setEditing(null) }}>
        {editing !== null && (
          <SceneEditor
            key={editing.scene?.id ?? 'new'}
            initial={editing.scene}
            taken={scenes.map((s) => s.id)}
            onDone={() => {
              setEditing(null)
            }}
          />
        )}
      </Sheet>
    </div>
  )
}

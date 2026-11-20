import { ArrowDown, ArrowUp, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { BUTTON_ICONS } from '../../lib/buttonIcons.ts'
import { describeAction, layoutId, splitList } from '../../lib/layouts.ts'
import {
  KEY_NAMES,
  MEDIA_COMMANDS,
  layoutSchema,
  siteSchema,
  type ButtonAction,
  type Layout,
  type LayoutButton,
  type Modifier,
} from '../../lib/protocol.ts'
import { RequestError } from '../../lib/ws.ts'
import { client, useConnection, useExtras, useLayouts } from '../../store/remote.ts'
import { useUi } from '../../store/ui.ts'
import { Button, IconButton } from '../../ui/Button.tsx'
import { Card, EmptyState, Skeleton } from '../../ui/primitives.tsx'
import { Sheet } from '../../ui/Sheet.tsx'

const field =
  'min-h-11 w-full rounded-xl bg-[var(--color-bg-raised)] px-3 text-sm ring-1 ring-inset ring-[var(--color-line-strong)] outline-none focus:ring-2 focus:ring-[var(--color-accent)]'
const MAX_BUTTONS = 24
const SITE_LABELS: Record<string, string> = {
  youtube: 'YouTube',
  netflix: 'Netflix',
  prime: 'Prime Video',
  spotify_web: 'Spotify (web)',
}
const MODIFIERS: Modifier[] = ['ctrl', 'alt', 'shift', 'meta']
const ACTION_LABELS: Record<ButtonAction['type'], string> = {
  key: 'Key combo',
  media: 'Media',
  seek: 'Seek',
  volume: 'Volume',
  launch: 'Open shortcut',
}

function failed(e: unknown) {
  useUi.getState().showToast('error', e instanceof RequestError ? e.message : 'That did not work.')
}

function defaultAction(type: ButtonAction['type'], firstShortcut: string): ButtonAction {
  switch (type) {
    case 'key':
      return { type, key: 'space', modifiers: [] }
    case 'media':
      return { type, command: 'toggle' }
    case 'seek':
      return { type, by: -10 }
    case 'volume':
      return { type, delta: 10 }
    case 'launch':
      return { type, shortcutId: firstShortcut }
  }
}

interface Draft {
  id: string | null
  name: string
  processes: string
  titles: string
  sites: string[]
  buttons: LayoutButton[]
}

function toDraft(layout: Layout | null): Draft {
  return {
    id: layout?.id ?? null,
    name: layout?.name ?? '',
    processes: (layout?.match?.processes ?? []).join(', '),
    titles: (layout?.match?.titles ?? []).join(', '),
    sites: [...(layout?.match?.sites ?? [])],
    buttons: layout?.buttons.map((b) => ({ ...b })) ?? [{ label: 'Play / pause', icon: 'play', action: { type: 'media', command: 'toggle' } }],
  }
}

function ActionEditor({
  action,
  onChange,
  shortcuts,
  index,
}: {
  action: ButtonAction
  onChange: (action: ButtonAction) => void
  shortcuts: { id: string; name: string }[]
  index: number
}) {
  const label = (what: string) => `${what} for button ${String(index + 1)}`
  switch (action.type) {
    case 'key':
      return (
        <div className="flex flex-col gap-2">
          <select
            aria-label={label('Key')}
            className={field}
            value={action.key}
            onChange={(e) => {
              onChange({ ...action, key: e.target.value })
            }}
          >
            {KEY_NAMES.map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </select>
          <div className="flex gap-2" role="group" aria-label={label('Modifiers')}>
            {MODIFIERS.map((m) => {
              const on = (action.modifiers ?? []).includes(m)
              return (
                <button
                  key={m}
                  type="button"
                  aria-pressed={on}
                  className={`min-h-11 flex-1 rounded-xl text-sm ring-1 ring-inset ring-[var(--color-line)] ${on ? 'bg-[var(--color-text)] text-[var(--color-bg)]' : 'bg-[var(--color-surface)]'}`}
                  onClick={() => {
                    const mods = action.modifiers ?? []
                    onChange({ ...action, modifiers: on ? mods.filter((x) => x !== m) : [...mods, m] })
                  }}
                >
                  {m === 'meta' ? 'Win/Cmd' : m.charAt(0).toUpperCase() + m.slice(1)}
                </button>
              )
            })}
          </div>
        </div>
      )
    case 'media':
      return (
        <select
          aria-label={label('Media command')}
          className={field}
          value={action.command}
          onChange={(e) => {
            onChange({ ...action, command: e.target.value as (typeof MEDIA_COMMANDS)[number] })
          }}
        >
          {MEDIA_COMMANDS.map((c) => (
            <option key={c} value={c}>
              {describeAction({ type: 'media', command: c }, 'windows', () => '')}
            </option>
          ))}
        </select>
      )
    case 'seek':
      return (
        <label className="flex items-center gap-2 text-sm">
          Seconds (negative goes back)
          <input
            aria-label={label('Seconds')}
            type="number"
            min={-3600}
            max={3600}
            className={`${field} w-28`}
            value={action.by}
            onChange={(e) => {
              onChange({ ...action, by: Math.max(-3600, Math.min(3600, Number(e.target.value) || 0)) })
            }}
          />
        </label>
      )
    case 'volume':
      return (
        <label className="flex items-center gap-2 text-sm">
          Change by (negative is down)
          <input
            aria-label={label('Volume change')}
            type="number"
            min={-100}
            max={100}
            className={`${field} w-28`}
            value={action.delta}
            onChange={(e) => {
              onChange({ ...action, delta: Math.max(-100, Math.min(100, Math.round(Number(e.target.value) || 0))) })
            }}
          />
        </label>
      )
    case 'launch':
      return (
        <select
          aria-label={label('Shortcut')}
          className={field}
          value={action.shortcutId}
          onChange={(e) => {
            onChange({ ...action, shortcutId: e.target.value })
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
}

function Editor({ draft, onClose }: { draft: Draft; onClose: () => void }) {
  const layouts = useLayouts((s) => s.layouts) ?? []
  const shortcuts = (useExtras((s) => s.shortcuts) ?? []).filter((s) => s.id !== '_once')
  const [d, setD] = useState(draft)
  const [error, setError] = useState<string | null>(null)
  const set = (patch: Partial<Draft>) => {
    setD((cur) => ({ ...cur, ...patch }))
  }
  const setButton = (i: number, patch: Partial<LayoutButton>) => {
    setD((cur) => ({ ...cur, buttons: cur.buttons.map((b, j) => (j === i ? { ...b, ...patch } : b)) }))
  }
  const move = (i: number, by: -1 | 1) => {
    setD((cur) => {
      const buttons = [...cur.buttons]
      const [b] = buttons.splice(i, 1)
      if (b !== undefined) buttons.splice(i + by, 0, b)
      return { ...cur, buttons }
    })
  }

  const save = () => {
    const candidate = {
      id: d.id ?? layoutId(d.name, layouts),
      name: d.name.trim(),
      match: { processes: splitList(d.processes), titles: splitList(d.titles, 2), sites: d.sites },
      buttons: d.buttons.map((b) => ({ ...b, label: b.label.trim() })),
    }
    const parsed = layoutSchema.safeParse(candidate)
    if (!parsed.success) {
      setError(candidate.name === '' ? 'Give the layout a name.' : 'Every button needs a label (up to 24 letters).')
      return
    }
    client.request('layouts.save', { layout: parsed.data }).then(onClose, failed)
  }
  const remove = () => {
    if (d.id === null) return
    client.request('layouts.delete', { layoutId: d.id }).then(onClose, failed)
  }

  return (
    <div className="flex flex-col gap-4">
      <label className="flex flex-col gap-1.5 text-sm font-medium">
        Name
        <input
          className={field}
          maxLength={40}
          value={d.name}
          onChange={(e) => {
            set({ name: e.target.value })
          }}
        />
      </label>
      <fieldset className="flex flex-col gap-2">
        <legend className="pb-1 text-sm font-medium">Show it when this is in front on the laptop</legend>
        <label className="flex flex-col gap-1 text-xs text-[var(--color-text-secondary)]">
          App program names, comma separated (for example vlc.exe)
          <input
            className={field}
            value={d.processes}
            onChange={(e) => {
              set({ processes: e.target.value })
            }}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-[var(--color-text-secondary)]">
          Words in the window title, comma separated
          <input
            className={field}
            value={d.titles}
            onChange={(e) => {
              set({ titles: e.target.value })
            }}
          />
        </label>
        <div className="flex flex-wrap gap-2" role="group" aria-label="Websites">
          {siteSchema.options
            .filter((s) => s in SITE_LABELS)
            .map((site) => {
              const on = d.sites.includes(site)
              return (
                <button
                  key={site}
                  type="button"
                  aria-pressed={on}
                  className={`min-h-11 rounded-full px-4 text-sm ring-1 ring-inset ring-[var(--color-line)] ${on ? 'bg-[var(--color-text)] text-[var(--color-bg)]' : 'bg-[var(--color-surface)]'}`}
                  onClick={() => {
                    set({ sites: on ? d.sites.filter((x) => x !== site) : [...d.sites, site] })
                  }}
                >
                  {SITE_LABELS[site]}
                </button>
              )
            })}
        </div>
      </fieldset>

      <fieldset className="flex flex-col gap-2">
        <legend className="pb-1 text-sm font-medium">Buttons ({d.buttons.length}/{MAX_BUTTONS})</legend>
        {d.buttons.map((b, i) => (
          <Card key={i} className="flex flex-col gap-2 p-3">
            <div className="flex items-center gap-2">
              <input
                aria-label={`Label for button ${String(i + 1)}`}
                className={`${field} min-w-0 flex-1`}
                maxLength={24}
                value={b.label}
                onChange={(e) => {
                  setButton(i, { label: e.target.value })
                }}
              />
              <IconButton label={`Move button ${String(i + 1)} up`} variant="plain" disabled={i === 0} onClick={() => { move(i, -1) }}>
                <ArrowUp className="h-4 w-4" />
              </IconButton>
              <IconButton label={`Move button ${String(i + 1)} down`} variant="plain" disabled={i === d.buttons.length - 1} onClick={() => { move(i, 1) }}>
                <ArrowDown className="h-4 w-4" />
              </IconButton>
              <IconButton
                label={`Remove button ${String(i + 1)}`}
                variant="plain"
                className="text-[var(--color-danger)]"
                disabled={d.buttons.length === 1}
                onClick={() => {
                  set({ buttons: d.buttons.filter((_, j) => j !== i) })
                }}
              >
                <Trash2 className="h-4 w-4" />
              </IconButton>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <select
                aria-label={`Icon for button ${String(i + 1)}`}
                className={field}
                value={b.icon ?? ''}
                onChange={(e) => {
                  setButton(i, { icon: e.target.value === '' ? null : e.target.value })
                }}
              >
                <option value="">No icon</option>
                {Object.keys(BUTTON_ICONS).map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
              <select
                aria-label={`Action for button ${String(i + 1)}`}
                className={field}
                value={b.action.type}
                onChange={(e) => {
                  setButton(i, { action: defaultAction(e.target.value as ButtonAction['type'], shortcuts[0]?.id ?? 'youtube') })
                }}
              >
                {(Object.keys(ACTION_LABELS) as ButtonAction['type'][])
                  .filter((t) => t !== 'launch' || shortcuts.length > 0)
                  .map((t) => (
                    <option key={t} value={t}>
                      {ACTION_LABELS[t]}
                    </option>
                  ))}
              </select>
            </div>
            <ActionEditor
              index={i}
              action={b.action}
              shortcuts={shortcuts}
              onChange={(action) => {
                setButton(i, { action })
              }}
            />
          </Card>
        ))}
        <Button
          icon={<Plus className="h-4 w-4" aria-hidden="true" />}
          disabled={d.buttons.length >= MAX_BUTTONS}
          onClick={() => {
            set({ buttons: [...d.buttons, { label: 'New button', icon: null, action: { type: 'key', key: 'space', modifiers: [] } }] })
          }}
        >
          Add button
        </Button>
      </fieldset>

      {error !== null && (
        <p role="alert" className="text-sm text-[var(--color-danger)]">
          {error}
        </p>
      )}
      <div className="flex gap-2">
        {d.id !== null && (
          <Button variant="danger" onClick={remove}>
            Delete
          </Button>
        )}
        <Button className="flex-1" variant="primary" size="lg" onClick={save}>
          Save layout
        </Button>
      </div>
    </div>
  )
}

/** More > Layouts: per-app buttons, including the call controls. */
export function LayoutsScreen() {
  const layouts = useLayouts((s) => s.layouts)
  const owner = useConnection((s) => s.session?.role === 'owner')
  const os = useConnection((s) => s.session?.os ?? 'windows')
  const shortcuts = useExtras((s) => s.shortcuts)
  const [editing, setEditing] = useState<Draft | null>(null)

  if (layouts === null) return <Skeleton label="Loading layouts" className="h-40" />
  if (!owner) {
    return (
      <Card>
        <p className="text-[var(--color-text-secondary)]">Only the owner can change layouts.</p>
      </Card>
    )
  }
  const nameOf = (id: string) => shortcuts?.find((s) => s.id === id)?.name ?? id

  return (
    <div className="grid grid-cols-2 gap-2.5 short:gap-2 land:grid-cols-3 land:gap-2">
      {layouts.length === 0 && <EmptyState icon={<Plus className="h-9 w-9" />} title="No layouts yet" />}
      {layouts.map((layout) => (
        <button
          key={layout.id}
          type="button"
          className="flex min-h-16 flex-col items-start justify-center gap-0.5 rounded-[var(--radius-card)] bg-[var(--color-surface)] px-3 py-2 text-left ring-1 ring-inset ring-[var(--color-line)] land:min-h-14"
          onClick={() => {
            setEditing(toDraft(layout))
          }}
        >
          <span className="w-full truncate font-semibold">{layout.name}</span>
          <span className="w-full truncate text-xs text-[var(--color-text-secondary)]">
            {layout.buttons
              .slice(0, 3)
              .map((b) => `${b.label} (${describeAction(b.action, os, nameOf)})`)
              .join(' · ')}
          </span>
        </button>
      ))}
      <Button
        size="lg"
        className="col-span-2 land:col-span-3 land:min-h-11"
        icon={<Plus className="h-5 w-5" aria-hidden="true" />}
        onClick={() => {
          setEditing(toDraft(null))
        }}
      >
        New layout
      </Button>
      <Sheet
        open={editing !== null}
        title={editing?.id == null ? 'New layout' : 'Edit layout'}
        onClose={() => {
          setEditing(null)
        }}
      >
        {editing !== null && (
          <Editor
            draft={editing}
            onClose={() => {
              setEditing(null)
            }}
          />
        )}
      </Sheet>
    </div>
  )
}

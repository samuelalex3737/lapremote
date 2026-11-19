import { ChevronLeft, ChevronRight, Globe, Pencil, Plus, Rocket, Trash2 } from 'lucide-react'
import { useState, type SyntheticEvent } from 'react'
import type { Shortcut } from '../../lib/protocol.ts'
import { makeId, normaliseUrl, ONCE_ID, visibleShortcuts } from '../../lib/shortcuts.ts'
import { RequestError } from '../../lib/ws.ts'
import { client, useConnection, useExtras } from '../../store/remote.ts'
import { useUi } from '../../store/ui.ts'
import { Button, IconButton } from '../../ui/Button.tsx'
import { EmptyState, SegmentedControl, Skeleton } from '../../ui/primitives.tsx'
import { Sheet } from '../../ui/Sheet.tsx'
import { FeatureGate } from '../FeatureGate.tsx'
import { launch } from './launch.ts'
import { ShortcutIcon } from './shortcutIcon.tsx'

const inputClass =
  'min-h-12 w-full rounded-[var(--radius-control)] bg-[var(--color-surface)] px-4 text-base ring-1 ring-inset ring-[var(--color-line)] outline-none placeholder:text-[var(--color-text-tertiary)] focus:ring-2 focus:ring-[var(--color-accent)]'

function toastError(e: unknown) {
  useUi.getState().showToast('error', e instanceof RequestError ? e.message : 'That did not work.')
}

function ShortcutForm({ initial, taken, onDone }: { initial: Shortcut | null; taken: string[]; onDone: () => void }) {
  const [name, setName] = useState(initial?.name ?? '')
  const [kind, setKind] = useState<'url' | 'app'>(initial?.kind ?? 'url')
  const [target, setTarget] = useState(initial?.kind === 'app' ? (initial.app ?? '') : (initial?.url ?? ''))
  const [error, setError] = useState<string | null>(null)

  const save = (e: SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault()
    const trimmed = name.trim()
    if (trimmed === '') {
      setError('Give it a name.')
      return
    }
    const id = initial?.id ?? makeId(trimmed, taken)
    let shortcut: Shortcut
    if (kind === 'url') {
      const url = normaliseUrl(target)
      if (url === null) {
        setError('Enter a web address, like netflix.com.')
        return
      }
      shortcut = { id, name: trimmed, kind: 'url', url, icon: initial?.icon ?? null }
    } else {
      if (target.trim() === '') {
        setError('Enter the full path to the app on the laptop.')
        return
      }
      shortcut = { id, name: trimmed, kind: 'app', app: target.trim(), icon: initial?.icon ?? null }
    }
    client.request('shortcuts.save', { shortcut }).then(onDone, (err: unknown) => {
      setError(err instanceof RequestError ? err.message : 'That did not work.')
    })
  }

  return (
    <form onSubmit={save} className="flex flex-col gap-4" noValidate>
      <label className="flex flex-col gap-2">
        <span className="text-sm font-medium">Name</span>
        <input className={inputClass} value={name} maxLength={40} onChange={(e) => { setName(e.target.value) }} />
      </label>
      <SegmentedControl
        label="Opens"
        options={[
          { value: 'url', label: 'Website' },
          { value: 'app', label: 'App' },
        ]}
        value={kind}
        onChange={setKind}
      />
      <label className="flex flex-col gap-2">
        <span className="text-sm font-medium">{kind === 'url' ? 'Web address' : 'App path on the laptop'}</span>
        <input
          className={inputClass}
          value={target}
          inputMode={kind === 'url' ? 'url' : 'text'}
          autoCapitalize="off"
          autoCorrect="off"
          placeholder={kind === 'url' ? 'netflix.com' : 'C:\\Program Files\\VideoLAN\\VLC\\vlc.exe'}
          onChange={(e) => {
            setTarget(e.target.value)
          }}
        />
      </label>
      {error !== null && (
        <p role="alert" className="text-sm text-[var(--color-danger)]">
          {error}
        </p>
      )}
      <Button type="submit" variant="primary" size="lg">
        Save
      </Button>
    </form>
  )
}

function OpenUrlForm({ taken, onDone }: { taken: string[]; onDone: () => void }) {
  const [value, setValue] = useState('')
  const [error, setError] = useState<string | null>(null)
  const open = (save: boolean) => {
    const url = normaliseUrl(value)
    if (url === null) {
      setError('Enter a web address, like youtube.com.')
      return
    }
    const host = new URL(url).hostname.replace(/^www\./, '')
    const shortcut: Shortcut = save
      ? { id: makeId(host, taken), name: host.slice(0, 40), kind: 'url', url }
      : { id: ONCE_ID, name: host.slice(0, 40), kind: 'url', url }
    client
      .request('shortcuts.save', { shortcut })
      .then(() => client.request('launch.open', { shortcutId: shortcut.id }))
      .then(onDone, (err: unknown) => {
        setError(err instanceof RequestError ? err.message : 'That did not work.')
      })
  }
  return (
    <div className="flex flex-col gap-4">
      <label className="flex flex-col gap-2">
        <span className="text-sm font-medium">Web address</span>
        <input
          className={inputClass}
          value={value}
          inputMode="url"
          autoCapitalize="off"
          autoCorrect="off"
          placeholder="youtube.com"
          onChange={(e) => {
            setValue(e.target.value)
          }}
        />
      </label>
      {error !== null && (
        <p role="alert" className="text-sm text-[var(--color-danger)]">
          {error}
        </p>
      )}
      <div className="flex gap-3">
        <Button className="flex-1" size="lg" onClick={() => { open(false) }}>
          Open once
        </Button>
        <Button className="flex-1" size="lg" variant="primary" onClick={() => { open(true) }}>
          Save and open
        </Button>
      </div>
    </div>
  )
}

export function LaunchTab() {
  const shortcuts = useExtras((s) => s.shortcuts)
  const owner = useConnection((s) => s.session?.role === 'owner')
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState<{ shortcut: Shortcut | null } | null>(null)
  const [openUrl, setOpenUrl] = useState(false)
  const list = visibleShortcuts(shortcuts)
  const taken = (shortcuts ?? []).map((s) => s.id)

  const move = (index: number, step: -1 | 1) => {
    const ids = list.map((s) => s.id)
    const other = index + step
    if (other < 0 || other >= ids.length) return
    const a = ids[index]
    const b = ids[other]
    if (a === undefined || b === undefined) return
    ids[index] = b
    ids[other] = a
    client.request('shortcuts.reorder', { ids }).catch(toastError)
  }

  return (
    <div className="flex flex-col gap-4 pt-2">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Launch</h1>
        {owner && list.length > 0 && (
          <Button
            variant={editing ? 'primary' : 'secondary'}
            icon={<Pencil className="h-4 w-4" aria-hidden="true" />}
            onClick={() => {
              setEditing(!editing)
            }}
          >
            {editing ? 'Done' : 'Edit'}
          </Button>
        )}
      </div>
      <FeatureGate feature="launcher" title="Launching apps and sites">
        {!owner ? (
          <EmptyState icon={<Rocket className="h-9 w-9" />} title="Only the owner can open apps" />
        ) : shortcuts === null ? (
          <Skeleton label="Loading shortcuts" className="h-48" />
        ) : (
          <>
            <ul className="grid grid-cols-2 gap-3 min-[420px]:grid-cols-3">
              {list.map((s, i) => (
                <li key={s.id}>
                  {editing ? (
                    <div className="flex h-full flex-col items-center gap-2 rounded-[var(--radius-card)] bg-[var(--color-surface)] p-3 ring-1 ring-inset ring-[var(--color-line)]">
                      <ShortcutIcon shortcut={s} />
                      <span className="w-full truncate text-center text-sm font-medium">{s.name}</span>
                      <div className="flex gap-1">
                        <IconButton label={`Move ${s.name} earlier`} size="md" variant="plain" disabled={i === 0} onClick={() => { move(i, -1) }}>
                          <ChevronLeft className="h-5 w-5" />
                        </IconButton>
                        <IconButton label={`Edit ${s.name}`} size="md" variant="plain" onClick={() => { setForm({ shortcut: s }) }}>
                          <Pencil className="h-4 w-4" />
                        </IconButton>
                        <IconButton
                          label={`Delete ${s.name}`}
                          size="md"
                          variant="plain"
                          className="text-[var(--color-danger)]"
                          onClick={() => {
                            client.request('shortcuts.delete', { shortcutId: s.id }).catch(toastError)
                          }}
                        >
                          <Trash2 className="h-4 w-4" />
                        </IconButton>
                        <IconButton label={`Move ${s.name} later`} size="md" variant="plain" disabled={i === list.length - 1} onClick={() => { move(i, 1) }}>
                          <ChevronRight className="h-5 w-5" />
                        </IconButton>
                      </div>
                    </div>
                  ) : (
                    <button
                      type="button"
                      className="flex min-h-28 w-full flex-col items-center justify-center gap-2 rounded-[var(--radius-card)] bg-[var(--color-surface)] p-3 ring-1 ring-inset ring-[var(--color-line)] outline-none active:scale-[0.97] active:bg-[var(--color-surface-strong)] focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
                      onClick={() => {
                        launch(s)
                      }}
                    >
                      <ShortcutIcon shortcut={s} />
                      <span className="w-full truncate text-center text-sm font-medium">{s.name}</span>
                    </button>
                  )}
                </li>
              ))}
            </ul>
            <div className="flex gap-3">
              <Button className="flex-1" size="lg" icon={<Globe className="h-5 w-5" aria-hidden="true" />} onClick={() => { setOpenUrl(true) }}>
                Open a website
              </Button>
              <Button className="flex-1" size="lg" icon={<Plus className="h-5 w-5" aria-hidden="true" />} onClick={() => { setForm({ shortcut: null }) }}>
                Add shortcut
              </Button>
            </div>
          </>
        )}
      </FeatureGate>
      <Sheet
        open={form !== null}
        title={form?.shortcut != null ? 'Edit shortcut' : 'New shortcut'}
        onClose={() => {
          setForm(null)
        }}
      >
        {form !== null && (
          <ShortcutForm
            key={form.shortcut?.id ?? 'new'}
            initial={form.shortcut}
            taken={taken}
            onDone={() => {
              setForm(null)
            }}
          />
        )}
      </Sheet>
      <Sheet
        open={openUrl}
        title="Open a website"
        onClose={() => {
          setOpenUrl(false)
        }}
      >
        <OpenUrlForm
          taken={taken}
          onDone={() => {
            setOpenUrl(false)
          }}
        />
      </Sheet>
    </div>
  )
}

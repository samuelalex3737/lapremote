import { ClipboardPaste, Copy, ExternalLink, FileUp, Image as ImageIcon, Loader2 } from 'lucide-react'
import { useRef, useState } from 'react'
import { asLink, copyToPhone } from '../../lib/copy.ts'
import { uploadFile } from '../../lib/upload.ts'
import { RequestError } from '../../lib/ws.ts'
import { client, readLaptopClipboard, useConnection } from '../../store/remote.ts'
import { useUi } from '../../store/ui.ts'
import { Button } from '../../ui/Button.tsx'
import { Card } from '../../ui/primitives.tsx'

interface Sent {
  id: number
  name: string
  progress: number
  status: 'sending' | 'done' | 'failed'
  detail?: string
}

let seq = 0

function toast(level: 'success' | 'error', message: string) {
  useUi.getState().showToast(level, message)
}

function failed(e: unknown) {
  toast('error', e instanceof RequestError ? e.message : 'That did not work.')
}

/** Text and links to the laptop, the laptop's clipboard back to the phone, and files. */
export function SendScreen() {
  const owner = useConnection((s) => s.session?.role === 'owner')
  const [text, setText] = useState('')
  const [fromLaptop, setFromLaptop] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [files, setFiles] = useState<Sent[]>([])
  const photos = useRef<HTMLInputElement>(null)
  const anyFile = useRef<HTMLInputElement>(null)

  if (!owner) {
    return (
      <Card>
        <p className="text-[var(--color-text-secondary)]">Only the owner can send things to this laptop.</p>
      </Card>
    )
  }

  const link = asLink(text)

  const pasteOnLaptop = () => {
    if (text === '') return
    client.request('clipboard.set', { text }).then(() => {
      toast('success', 'On the laptop clipboard. Paste it with Ctrl+V.')
    }, failed)
  }
  const openOnLaptop = () => {
    if (link === null) return
    client.request('url.open', { url: link }).then(() => {
      toast('success', 'Opened on the laptop.')
    }, failed)
  }
  const getFromLaptop = () => {
    setBusy(true)
    readLaptopClipboard().then(
      (value) => {
        setFromLaptop(value)
      },
      failed,
    ).finally(() => {
      setBusy(false)
    })
  }

  const send = (list: FileList | null) => {
    if (list === null) return
    for (const file of Array.from(list)) {
      seq += 1
      const id = seq
      setFiles((cur) => [{ id, name: file.name, progress: 0, status: 'sending' as const }, ...cur].slice(0, 8))
      const update = (patch: Partial<Sent>) => {
        setFiles((cur) => cur.map((f) => (f.id === id ? { ...f, ...patch } : f)))
      }
      void uploadFile(file, (progress) => {
        update({ progress })
      }).then((result) => {
        if (result.ok) update({ status: 'done', progress: 1, detail: `Saved as ${result.name ?? file.name}` })
        else update({ status: 'failed', detail: result.error ?? 'Not sent.' })
      })
    }
  }

  return (
    <div className="flex flex-col gap-3 short:gap-2 land:grid land:grid-cols-2 land:items-start">
      <Card className="flex flex-col gap-3 p-3">
        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-medium">Text or link</span>
          <textarea
            value={text}
            maxLength={100_000}
            rows={3}
            onChange={(e) => {
              setText(e.target.value)
            }}
            placeholder="Type or paste here"
            className="min-h-20 w-full resize-none rounded-[var(--radius-control)] bg-[var(--color-bg-raised)] px-3 py-2 text-base ring-1 ring-inset ring-[var(--color-line)] outline-none placeholder:text-[var(--color-text-tertiary)] focus:ring-2 focus:ring-[var(--color-accent)] land:min-h-16"
          />
        </label>
        <div className="flex gap-2">
          <Button
            className="flex-1"
            variant="primary"
            disabled={text === ''}
            icon={<ClipboardPaste className="h-4 w-4" aria-hidden="true" />}
            onClick={pasteOnLaptop}
          >
            Copy to laptop
          </Button>
          <Button
            className="flex-1"
            disabled={link === null}
            icon={<ExternalLink className="h-4 w-4" aria-hidden="true" />}
            onClick={openOnLaptop}
          >
            Open link
          </Button>
        </div>
      </Card>

      <div className="flex flex-col gap-3 short:gap-2">
        <Card className="flex flex-col gap-2 p-3">
          <Button
            disabled={busy}
            icon={busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Copy className="h-4 w-4" aria-hidden="true" />}
            onClick={getFromLaptop}
          >
            Get the laptop's clipboard
          </Button>
          {fromLaptop !== null && (
            <div className="flex flex-col gap-2">
              <p
                className="max-h-24 overflow-y-auto rounded-xl bg-[var(--color-bg-raised)] px-3 py-2 text-sm break-words whitespace-pre-wrap select-text"
                aria-label="Laptop clipboard"
              >
                {fromLaptop === '' ? 'The laptop clipboard has no text.' : fromLaptop}
              </p>
              {fromLaptop !== '' && (
                <Button
                  onClick={() => {
                    void copyToPhone(fromLaptop).then((ok) => {
                      toast(ok ? 'success' : 'error', ok ? 'Copied to this phone.' : 'Select the text and copy it.')
                    })
                  }}
                >
                  Copy to this phone
                </Button>
              )}
            </div>
          )}
        </Card>

        <Card className="flex flex-col gap-2 p-3">
          <div className="flex gap-2">
            <Button
              className="flex-1"
              icon={<ImageIcon className="h-4 w-4" aria-hidden="true" />}
              onClick={() => photos.current?.click()}
            >
              Send photos
            </Button>
            <Button className="flex-1" icon={<FileUp className="h-4 w-4" aria-hidden="true" />} onClick={() => anyFile.current?.click()}>
              Send files
            </Button>
          </div>
          <input
            ref={photos}
            type="file"
            accept="image/*,video/*"
            multiple
            hidden
            aria-label="Photos to send"
            onChange={(e) => {
              send(e.target.files)
              e.target.value = ''
            }}
          />
          <input
            ref={anyFile}
            type="file"
            multiple
            hidden
            aria-label="Files to send"
            onChange={(e) => {
              send(e.target.files)
              e.target.value = ''
            }}
          />
          <p className="text-xs text-[var(--color-text-tertiary)]">Saved in Downloads\LapRemote on the laptop. Up to 100 MB each.</p>
          {files.length > 0 && (
            <ul className="flex flex-col gap-1.5" aria-label="Sent files">
              {files.map((f) => (
                <li key={f.id} className="flex flex-col gap-1 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <span className="min-w-0 truncate">{f.name}</span>
                    <span
                      className={
                        f.status === 'failed'
                          ? 'text-[var(--color-danger)]'
                          : f.status === 'done'
                            ? 'text-[var(--color-success)]'
                            : 'text-[var(--color-text-secondary)]'
                      }
                    >
                      {f.status === 'sending' ? `${String(Math.round(f.progress * 100))}%` : f.status === 'done' ? 'Sent' : 'Failed'}
                    </span>
                  </div>
                  {f.status === 'sending' && (
                    <div className="h-1 overflow-hidden rounded-full bg-[var(--color-surface-strong)]">
                      <div className="h-full bg-[var(--color-accent)]" style={{ width: `${String(f.progress * 100)}%` }} />
                    </div>
                  )}
                  {f.detail !== undefined && <span className="text-xs text-[var(--color-text-tertiary)]">{f.detail}</span>}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  )
}

/**
 * Send one file to the laptop over POST /api/upload, with progress.
 * The device id and token go in headers (never the URL), like the socket's auth.
 */
import { localCredentialStore } from './credentials.ts'

export const MAX_UPLOAD_BYTES = 100 * 1024 * 1024

export interface UploadResult {
  ok: boolean
  name?: string
  error?: string
}

export function uploadFile(file: File, onProgress: (fraction: number) => void): Promise<UploadResult> {
  const credentials = localCredentialStore().load()
  if (credentials === null) return Promise.resolve({ ok: false, error: 'Pair this phone first.' })
  if (file.size === 0) return Promise.resolve({ ok: false, error: 'That file is empty.' })
  if (file.size > MAX_UPLOAD_BYTES) return Promise.resolve({ ok: false, error: 'Files can be up to 100 MB.' })
  return new Promise((resolve) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/upload')
    xhr.setRequestHeader('X-LapRemote-Device', credentials.deviceId)
    xhr.setRequestHeader('Authorization', `Bearer ${credentials.token}`)
    xhr.setRequestHeader('X-LapRemote-Filename', encodeURIComponent(file.name))
    xhr.setRequestHeader('Content-Type', 'application/octet-stream')
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded / e.total)
    }
    xhr.onload = () => {
      try {
        const body = JSON.parse(xhr.responseText) as { ok?: boolean; name?: string; error?: string }
        if (body.ok === true && typeof body.name === 'string') resolve({ ok: true, name: body.name })
        else resolve({ ok: false, error: body.error ?? 'The laptop did not save the file.' })
      } catch {
        resolve({ ok: false, error: 'The laptop did not save the file.' })
      }
    }
    xhr.onerror = () => {
      resolve({ ok: false, error: "Can't reach your laptop right now." })
    }
    xhr.send(file)
  })
}

# HTTPS for LapRemote

Phones only allow the microphone (voice commands) and the motion sensors (air mouse) on a
secure page. Everything else in LapRemote works on plain `http://` on your Wi-Fi. If you want
those two extras, pick one of the options below. Both are free.

The phone decides what's available from the page it is on: when the page is secure, the mic
button and the air mouse appear on their own. On plain http, the AI screen and the air mouse
explain what's missing instead.

## Option 1: mkcert (same Wi-Fi, no account)

[mkcert](https://github.com/FiloSottile/mkcert) makes a certificate that your own devices trust.

1. Install it on the laptop. On Windows: `winget install FiloSottile.mkcert`. On macOS:
   `brew install mkcert`. On Linux, see the mkcert README.
2. Create a local certificate authority and trust it on the laptop:
   ```
   mkcert -install
   ```
3. Make a certificate for the laptop's address. Use the IP the LapRemote banner prints (and the
   `.local` name if you like):
   ```
   mkcert -cert-file C:/Users/you/.lapremote/cert.pem -key-file C:/Users/you/.lapremote/key.pem 192.168.1.33 my-laptop.local
   ```
4. Tell LapRemote where they are, in `~/.lapremote/config.json`:
   ```json
   "https": { "enabled": true, "cert": "C:/Users/you/.lapremote/cert.pem", "key": "C:/Users/you/.lapremote/key.pem" }
   ```
   Or leave `enabled` false and start with `python -m lapremote --https` when you want it.
5. Trust the certificate authority on the phone. `mkcert -CAROOT` prints the folder that holds
   `rootCA.pem`. Copy that file (only that file, never `rootCA-key.pem`) to the phone:
   - **iPhone:** open it to install the profile. Then go to Settings > General > About >
     Certificate Trust Settings and turn on full trust for it.
   - **Android:** Settings > Security > Encryption & credentials > Install a certificate > CA
     certificate.
6. Scan the new QR code. It now starts with `https://`.

If the laptop's IP changes, run step 3 again with the new IP.

## Option 2: Tailscale Serve (works away from home too)

[Tailscale](https://tailscale.com) is free for personal use and gives the laptop a real
certificate on a `ts.net` name.

1. Install Tailscale on the laptop and the phone and sign in to the same account on both.
2. Turn on HTTPS for your tailnet in the Tailscale admin console (DNS > HTTPS certificates).
3. Keep LapRemote on plain http, and on the laptop run:
   ```
   tailscale serve --bg 7777
   ```
   It prints an address like `https://my-laptop.tail1234.ts.net`.
4. On the phone, open that address. Pair with the code from the LapRemote banner (type it in,
   or open `https://my-laptop.tail1234.ts.net/?pair=123456`).

Tailscale handles the certificate, so LapRemote doesn't need `--https` in this setup.

**Not tested yet:** this path has not been tried end to end on a real tailnet. LapRemote checks
that the page and the socket come from the same host. If Tailscale ever forwards a different
`Host` header, the phone will show "Can't reach your laptop" and the log will have
`origin_rejected`. Please report it if that happens.

## Checking it worked

- The banner and the QR code show `https://`.
- `curl -k https://<laptop-ip>:7777/api/health` answers `{"ok":true,...}`.
- On the phone, More > Ask LapRemote shows a mic button, and Trackpad > Air mouse offers
  "Turn on air mouse".

## Notes

- `--https` refuses to start if the cert or key file is missing, and says which one.
- The private key stays on the laptop. LapRemote only reads it, and never logs or sends it.
- Self-signed certificates that the phone doesn't trust will not work: the phone blocks the
  page or the socket. Use mkcert's authority or Tailscale.

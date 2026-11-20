# LapRemote demo script (about 5 minutes)

A walkthrough that shows every main feature in a natural order. Each step says what to do and
what the audience should see.

## Before you start

- Laptop and phone on the same Wi-Fi. LapRemote running (`cd agent && uv run python -m lapremote`
  or `LapRemote.exe`).
- Spotify (or any music app) playing a song, and a browser with Netflix or YouTube in a tab.
- Optional: Ollama running with the model pulled (for step 7), HTTPS set up (for step 8).
- To show the phone on a screen, use screen mirroring or a camera.

## 1. Pair (30 s)

1. Tray icon > **Pair a phone**. The dashboard shows a QR code and a 6-digit code.
2. Scan it with the phone's camera. The remote opens and says "Connected to <laptop>".
3. Point out: no account, no cloud, the code works once and changes every 5 minutes.

## 2. Now Playing (45 s)

1. The phone shows the song with artwork; the background glows in the artwork's colours.
2. Pause, skip, then drag the scrubber: the song jumps on the laptop.
3. Start the video in the browser. A banner offers Movie mode; tap it for big controls,
   fullscreen and subtitles keys. Tap the player chips to switch between Spotify and the browser.

## 3. Trackpad and preview (60 s)

1. Trackpad tab: move the cursor, tap to click, two-finger scroll a web page, pinch to zoom.
2. Three-finger swipe up: Task View opens.
3. Switch to **Screen**: a live preview of the laptop. Tap a button in the preview: the laptop
   clicks exactly there.

## 4. Keys and launcher (40 s)

1. Keys tab, **Live** mode: type on the phone and the letters appear on the laptop as you type.
2. Tap Copy and Paste, or build Ctrl+Shift+T with the combo builder.
3. Launch tab: tap YouTube. It opens in the preferred browser.

## 5. Scenes and sleep timer (40 s)

1. More > Scenes > Movie Night: the volume goes to 40%, brightness to 60%, Netflix opens.
2. More > Sleep timer > + Lock, End of this track. The countdown shows on Now Playing. Cancel it.

## 6. Safety (30 s)

1. More > Power & display: hold Lock. Let go early and nothing happens; it needs a full hold.
2. Tray > **Pause remote control**: the phone says control is paused and the trackpad stops.
   Untick it again.
3. Dashboard > Devices: show the phone, its role, and the Remove button.

## 7. Ask LapRemote (45 s, needs Ollama)

1. More > Ask LapRemote. Tap the suggestion "Pause everything": both players pause, each step
   gets a check mark.
2. Type "next episode and volume 30".
3. Type "lock my laptop": a sheet asks "Do this on your laptop?". Tap Cancel.
4. Point out: the model can only pick from the same actions as the buttons, and risky ones ask
   first. Expect 10 to 20 seconds per request on a laptop CPU.

## 8. HTTPS extras (30 s, optional)

1. Open the remote through HTTPS (see docs/HTTPS.md).
2. Ask LapRemote now has a mic button: say "volume 20".
3. Trackpad > Air mouse: hold the button and point the phone to move the cursor.

## Wrap up

The tray menu has Start at login and Quit. Everything ran on the local Wi-Fi: nothing left the
room unless you chose a cloud AI provider.

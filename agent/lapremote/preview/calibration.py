"""The /calibration page: five targets that measure how accurately tap-to-click lands.

Open it full screen on the laptop (F11), then tap each pink target in the phone's
screen preview. The page shows how far, in physical pixels, each click landed from
the nearest target centre.
"""

CALIBRATION_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LapRemote calibration</title>
<style>
  html, body { margin: 0; height: 100%; background: #0b0b10; color: #f4f4f6;
    font-family: system-ui, sans-serif; overflow: hidden; user-select: none; cursor: crosshair; }
  .target { position: fixed; width: 44px; height: 44px; margin: -22px 0 0 -22px; border-radius: 50%;
    background: #ff00ff; box-shadow: 0 0 0 4px #ffffff; }
  .target::after { content: ""; position: absolute; left: 21px; top: 21px; width: 2px; height: 2px;
    background: #000; }
  .hit { position: fixed; width: 8px; height: 8px; margin: -4px 0 0 -4px; border-radius: 50%;
    background: #34d399; pointer-events: none; }
  #panel { position: fixed; left: 50%; top: 24%; transform: translateX(-50%); max-width: 520px;
    text-align: center; line-height: 1.5; }
  #results { font-variant-numeric: tabular-nums; }
  .ok { color: #34d399; } .bad { color: #fb7185; }
</style>
</head>
<body>
<div id="panel">
  <h1>Tap-to-click calibration</h1>
  <p>Make this page full screen on the laptop (F11). Then, on your phone, open the
  Trackpad tab, switch to Screen and tap each pink target.</p>
  <p id="results">No taps yet.</p>
</div>
<script>
  const FRACTIONS = [[0.1, 0.1], [0.9, 0.1], [0.5, 0.5], [0.1, 0.9], [0.9, 0.9]];
  const targets = FRACTIONS.map(([fx, fy]) => {
    const el = document.createElement('div');
    el.className = 'target';
    el.style.left = (fx * 100) + 'vw';
    el.style.top = (fy * 100) + 'vh';
    document.body.appendChild(el);
    return el;
  });
  const results = [];
  window.__calibration = results;
  function centre(el) {
    const r = el.getBoundingClientRect();
    return [r.left + r.width / 2, r.top + r.height / 2];
  }
  document.addEventListener('pointerdown', (e) => {
    const dpr = window.devicePixelRatio || 1;
    let best = null;
    targets.forEach((el, i) => {
      const [cx, cy] = centre(el);
      const d = Math.hypot(e.clientX - cx, e.clientY - cy) * dpr;
      if (best === null || d < best.distance) best = { target: i, distance: d };
    });
    results.push({ target: best.target, distancePx: Math.round(best.distance * 10) / 10,
      x: Math.round(e.clientX * dpr), y: Math.round(e.clientY * dpr) });
    const dot = document.createElement('div');
    dot.className = 'hit';
    dot.style.left = e.clientX + 'px';
    dot.style.top = e.clientY + 'px';
    document.body.appendChild(dot);
    document.getElementById('results').innerHTML = results.map((r, n) =>
      '<span class="' + (r.distancePx <= 10 ? 'ok' : 'bad') + '">Tap ' + (n + 1) + ': target ' +
      (r.target + 1) + ', ' + r.distancePx + ' px off</span>').join('<br>');
  });
</script>
</body>
</html>
"""

#!/usr/bin/env python3
"""
Tutorial Translation Agent — Flask Web UI
Run: python app.py
Open: http://localhost:5050
"""

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

from flask import Flask, Response, jsonify, render_template_string, request, send_file

app  = Flask(__name__)
BASE = Path(__file__).parent

LANG_CONFIG = {
    "mandarin":   {"label": "Mandarin Chinese (普通话)",     "flag": "🇨🇳"},
    "cantonese":  {"label": "Cantonese (廣東話)",            "flag": "🇭🇰"},
    "japanese":   {"label": "Japanese (日本語)",              "flag": "🇯🇵"},
    "korean":     {"label": "Korean (한국어)",                "flag": "🇰🇷"},
    "french":     {"label": "French (Français)",             "flag": "🇫🇷"},
    "spanish":    {"label": "Spanish (Español)",             "flag": "🇪🇸"},
    "german":     {"label": "German (Deutsch)",              "flag": "🇩🇪"},
    "italian":    {"label": "Italian (Italiano)",            "flag": "🇮🇹"},
    "portuguese": {"label": "Portuguese (Português)",        "flag": "🇧🇷"},
    "dutch":      {"label": "Dutch (Nederlands)",            "flag": "🇳🇱"},
    "malay":      {"label": "Malay (Bahasa Melayu)",         "flag": "🇲🇾"},
    "thai":       {"label": "Thai (ภาษาไทย)",                "flag": "🇹🇭"},
    "indonesian": {"label": "Indonesian (Bahasa Indonesia)", "flag": "🇮🇩"},
    "arabic":     {"label": "Arabic (العربية)",              "flag": "🇸🇦"},
    "hindi":      {"label": "Hindi (हिन्दी)",                "flag": "🇮🇳"},
    "english":    {"label": "English",                       "flag": "🇬🇧"},
}

job = {"running": False, "log_queue": queue.Queue(), "output_file": None, "done": False, "process": None}

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tutorial Translator</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f0f13;color:#e0e0e0;min-height:100vh;display:flex;flex-direction:column;align-items:center;padding:40px 16px}
.card{background:#17171f;border:1px solid #2a2a3a;border-radius:16px;padding:32px;width:100%;max-width:680px;margin-bottom:20px}
h1{font-size:22px;font-weight:700;color:#fff;margin-bottom:4px}
.subtitle{font-size:13px;color:#6b7280;margin-bottom:28px}
label{display:block;font-size:11px;font-weight:600;color:#9ca3af;text-transform:uppercase;letter-spacing:.08em;margin-bottom:7px;margin-top:18px}
label:first-of-type{margin-top:0}
input[type=text],input[type=password],select{width:100%;background:#0f0f13;border:1px solid #2a2a3a;border-radius:8px;color:#e0e0e0;font-size:14px;padding:10px 14px;outline:none;transition:border-color .2s}
input[type=text]:focus,input[type=password]:focus,select:focus{border-color:#7c3aed}
select option{background:#17171f}
.api-row{display:flex;gap:10px;align-items:center;background:#0f0f13;border:1px solid #2a2a3a;border-radius:8px;padding:10px 14px}
.api-row input{flex:1;background:none;border:none;color:#e0e0e0;font-size:14px;outline:none;font-family:monospace}
.toggle{cursor:pointer;color:#6b7280;font-size:14px;user-select:none}
.toggle:hover{color:#e0e0e0}
.or-div{text-align:center;color:#4b5563;font-size:12px;margin:12px 0;position:relative}
.or-div::before,.or-div::after{content:'';position:absolute;top:50%;width:45%;height:1px;background:#2a2a3a}
.or-div::before{left:0}.or-div::after{right:0}
.drop{border:1px dashed #2a2a3a;border-radius:8px;padding:20px;text-align:center;color:#6b7280;font-size:13px;cursor:pointer;transition:border-color .2s,background .2s}
.drop:hover,.drop.over{border-color:#7c3aed;background:#1e1e2e}
.drop .ico{font-size:26px;margin-bottom:5px}
.fname{color:#a78bfa;font-size:12px;margin-top:4px}
#fi{display:none}
.skip-row{display:flex;flex-wrap:wrap;gap:8px;margin-top:6px}
.pill{display:flex;align-items:center;gap:5px;background:#0f0f13;border:1px solid #2a2a3a;border-radius:20px;padding:5px 12px;font-size:12px;color:#9ca3af;cursor:pointer;user-select:none;transition:border-color .2s,color .2s}
.pill input{display:none}
.pill.on{border-color:#7c3aed;color:#fff;background:#7c3aed;font-weight:600}
.btn{width:100%;margin-top:20px;padding:13px;border-radius:10px;border:none;font-size:15px;font-weight:600;cursor:pointer;transition:opacity .2s,transform .1s}
.btn:active{transform:scale(.98)}
.btn-p{background:linear-gradient(135deg,#7c3aed,#4f46e5);color:#fff}
.btn-p:hover{opacity:.9}
.btn-p:disabled{opacity:.4;cursor:not-allowed}
.btn-s{background:#1e1e2e;color:#9ca3af;border:1px solid #2a2a3a;margin-top:8px}
.btn-s:hover{background:#2a2a3a}
.prog-wrap{width:100%;height:3px;background:#1e1e2e;border-radius:2px;margin-top:14px;overflow:hidden;display:none}
.prog{height:100%;background:linear-gradient(90deg,#7c3aed,#4f46e5);border-radius:2px;width:0%;transition:width .5s ease}
.prog.ind{width:40%;animation:slide 1.5s infinite ease-in-out}
@keyframes slide{0%{margin-left:-40%}100%{margin-left:100%}}
.term{background:#090910;border:1px solid #1e1e2e;border-radius:12px;width:100%;max-width:680px;overflow:hidden;display:none}
.term-head{display:flex;align-items:center;gap:6px;padding:10px 14px;background:#111118;border-bottom:1px solid #1e1e2e}
.dot{width:10px;height:10px;border-radius:50%}
.dr{background:#ff5f57}.dy{background:#febc2e}.dg{background:#28c840}
.term-title{font-size:12px;color:#6b7280;margin-left:6px}
.term-body{padding:14px;height:300px;overflow-y:auto;font-family:'SF Mono','Fira Code',monospace;font-size:12px;line-height:1.7}
.ll{white-space:pre-wrap;word-break:break-all}
.li{color:#9ca3af}.ls{color:#34d399}.lw{color:#fbbf24}.le{color:#f87171}.lp{color:#a78bfa;font-weight:600}
.dl-card{display:none;background:#0d1f12;border:1px solid #166534;border-radius:12px;padding:18px 22px;width:100%;max-width:680px;margin-top:14px;align-items:center;gap:14px}
.dl-card .ico{font-size:34px}
.dl-card h3{font-size:15px;color:#4ade80;margin-bottom:3px}
.dl-card p{font-size:12px;color:#6b7280}
.btn-dl{margin-top:10px;padding:9px 18px;background:#166534;color:#4ade80;border:1px solid #166534;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;text-decoration:none;display:inline-block}
.btn-dl:hover{background:#15803d}
</style>
</head>
<body>
<div class="card">
  <h1>🎬 Tutorial Translator</h1>
  <p class="subtitle">Translate any tutorial video into any language — dubbed voiceover + subtitles</p>

  <label>YouTube / Video URL</label>
  <input type="text" id="url" placeholder="https://www.youtube.com/watch?v=..." />

  <div class="or-div">or</div>

  <div class="drop" id="drop" onclick="document.getElementById('fi').click()">
    <div class="ico">📁</div>
    <div>Drop a video file here or click to browse</div>
    <div class="fname" id="fname"></div>
  </div>
  <input type="file" id="fi" accept="video/*" />

  <label>Target Language</label>
  <select id="lang">
    {% for key, cfg in langs.items() %}
    <option value="{{ key }}">{{ cfg.flag }} {{ cfg.label }}</option>
    {% endfor %}
  </select>

  <label>Anthropic API Key</label>
  <div class="api-row">
    <input type="password" id="apikey" placeholder="sk-ant-..." />
    <span class="toggle" onclick="toggleKey()">👁</span>
  </div>

  <label>Skip Steps (resume from cache)</label>
  <div class="skip-row">
    <label class="pill" id="p-dl"><input type="checkbox" id="sk-dl"> ⏭ Download</label>
    <label class="pill" id="p-tr"><input type="checkbox" id="sk-tr"> ⏭ Transcribe</label>
    <label class="pill" id="p-tx"><input type="checkbox" id="sk-tx"> ⏭ Translate</label>
    <label class="pill" id="p-ts"><input type="checkbox" id="sk-ts"> ⏭ TTS</label>
  </div>

  <button class="btn btn-p" id="run-btn" onclick="start()">▶ Start Translation</button>
  <button class="btn btn-s" id="stop-btn" style="display:none" onclick="stop()">⏹ Stop</button>
  <div class="prog-wrap" id="pw"><div class="prog ind" id="pb"></div></div>
</div>

<div class="term" id="term">
  <div class="term-head">
    <div class="dot dr"></div><div class="dot dy"></div><div class="dot dg"></div>
    <span class="term-title">agent log</span>
  </div>
  <div class="term-body" id="log"></div>
</div>

<div class="dl-card" id="dlcard">
  <div class="ico">🎉</div>
  <div>
    <h3>Translation Complete!</h3>
    <p id="dl-desc"></p>
    <a class="btn-dl" id="dl-link" href="#" download>⬇ Download Video</a>
  </div>
</div>

<script>
let es = null, selFile = null;

// File drop
const drop = document.getElementById('drop');
const fi   = document.getElementById('fi');
fi.onchange = e => { selFile = e.target.files[0]; document.getElementById('fname').textContent = selFile?.name || ''; };
drop.ondragover = e => { e.preventDefault(); drop.classList.add('over'); };
drop.ondragleave = () => drop.classList.remove('over');
drop.ondrop = e => { e.preventDefault(); drop.classList.remove('over'); selFile = e.dataTransfer.files[0]; document.getElementById('fname').textContent = selFile?.name || ''; };

// Skip pills
document.querySelectorAll('.pill').forEach(p => {
  const cb = p.querySelector('input');
  // set initial visual state
  p.classList.toggle('on', cb.checked);
  p.addEventListener('click', () => setTimeout(() => p.classList.toggle('on', cb.checked), 0));
});

function toggleKey() {
  const i = document.getElementById('apikey');
  i.type = i.type === 'password' ? 'text' : 'password';
}

function log(text) {
  const b = document.getElementById('log');
  const d = document.createElement('div');
  d.className = 'll ' + cls(text);
  d.textContent = text;
  b.appendChild(d);
  b.scrollTop = b.scrollHeight;
}

function cls(t) {
  if (t.includes('✅')||t.includes('DONE')||t.includes('🎉')) return 'ls';
  if (t.includes('ERROR')||t.includes('❌')) return 'le';
  if (t.includes('WARNING')||t.includes('⚠')) return 'lw';
  if (/📥|📝|🌐|🔊|🎚|🖼|✨|🎬/.test(t)) return 'lp';
  return 'li';
}

async function start() {
  const url    = document.getElementById('url').value.trim();
  const apikey = document.getElementById('apikey').value.trim();
  const lang   = document.getElementById('lang').value;
  if (!url && !selFile) { alert('Enter a URL or select a video file.'); return; }
  if (!apikey) { alert('Enter your Anthropic API key.'); return; }

  let filePath = null;
  if (selFile) {
    log('📤  Uploading file...');
    const fd = new FormData(); fd.append('file', selFile);
    const r = await fetch('/upload', { method: 'POST', body: fd });
    const d = await r.json();
    if (!d.ok) { alert('Upload failed: ' + d.error); return; }
    filePath = d.path;
  }

  document.getElementById('term').style.display = 'block';
  document.getElementById('dlcard').style.display = 'none';
  document.getElementById('log').innerHTML = '';
  document.getElementById('run-btn').disabled = true;
  document.getElementById('stop-btn').style.display = 'block';
  document.getElementById('pw').style.display = 'block';

  await fetch('/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      url, file_path: filePath, lang, api_key: apikey,
      skip_download:   document.getElementById('sk-dl').checked,
      skip_transcribe: document.getElementById('sk-tr').checked,
      skip_translate:  document.getElementById('sk-tx').checked,
      skip_tts:        document.getElementById('sk-ts').checked,
    }),
  });

  es = new EventSource('/stream');
  es.onmessage = e => {
    const d = JSON.parse(e.data);
    if (d.type === 'log')   { log(d.text); }
    else if (d.type === 'done')  { es.close(); done(d.output_file); }
    else if (d.type === 'error') { es.close(); log('❌  ' + d.text); reset(); }
  };
  es.onerror = () => { es.close(); log('❌  Connection lost.'); reset(); };
}

function stop() {
  fetch('/stop', { method: 'POST' });
  if (es) es.close();
  reset(); log('⏹  Stopped.');
}

function done(f) {
  reset();
  document.getElementById('pb').classList.remove('ind');
  document.getElementById('pb').style.width = '100%';
  const c = document.getElementById('dlcard');
  c.style.display = 'flex';
  document.getElementById('dl-desc').textContent = f.split('/').pop();
  document.getElementById('dl-link').href = '/download?file=' + encodeURIComponent(f);
}

function reset() {
  document.getElementById('run-btn').disabled = false;
  document.getElementById('stop-btn').style.display = 'none';
}
</script>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(HTML, langs=LANG_CONFIG)


@app.route("/upload", methods=["POST"])
def upload():
    f = request.files.get("file")
    if not f:
        return jsonify({"ok": False, "error": "no file"})
    upload_dir = BASE / "output" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / f.filename
    f.save(dest)
    return jsonify({"ok": True, "path": str(dest)})


@app.route("/start", methods=["POST"])
def start():
    global job
    if job["running"]:
        return jsonify({"ok": False, "error": "already running"})

    data            = request.get_json(force=True) or {}
    url             = (data.get("url") or "").strip()
    file_path       = (data.get("file_path") or "").strip()
    lang            = data.get("lang") or "mandarin"
    api_key         = (data.get("api_key") or "").strip()
    skip_download   = bool(data.get("skip_download"))
    skip_transcribe = bool(data.get("skip_transcribe"))
    skip_translate  = bool(data.get("skip_translate"))
    skip_tts        = bool(data.get("skip_tts"))

    job = {"running": True, "log_queue": queue.Queue(), "output_file": None, "done": False, "process": None}

    def run():
        agent = BASE / "translate_agent.py"
        cmd = [sys.executable, str(agent), "--lang", lang]
        if url:       cmd += ["--url", url]
        elif file_path: cmd += ["--file", file_path]
        if skip_download:   cmd.append("--skip-download")
        if skip_transcribe: cmd.append("--skip-transcribe")
        if skip_translate:  cmd.append("--skip-translate")
        if skip_tts:        cmd.append("--skip-tts")

        env = os.environ.copy()
        env["ANTHROPIC_API_KEY"] = api_key

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, env=env, bufsize=1, cwd=str(BASE))
        job["process"] = proc

        output_file = None
        for line in proc.stdout:
            line = line.rstrip()
            job["log_queue"].put({"type": "log", "text": line})
            if "Output  :" in line or "Output :" in line:
                output_file = line.split(":")[-1].strip()

        proc.wait()
        job["running"] = False
        job["done"]    = True

        if proc.returncode == 0 and output_file:
            job["output_file"] = output_file
            job["log_queue"].put({"type": "done", "output_file": output_file})
        else:
            job["log_queue"].put({"type": "error", "text": f"Process exited with code {proc.returncode}"})

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/stream")
def stream():
    def generate():
        while True:
            try:
                msg = job["log_queue"].get(timeout=30)
                yield f"data: {json.dumps(msg)}\n\n"
                if msg["type"] in ("done", "error"):
                    break
            except queue.Empty:
                yield 'data: {"type":"ping"}\n\n'
    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/stop", methods=["POST"])
def stop():
    proc = job.get("process")
    if proc: proc.terminate()
    job["running"] = False
    job["done"]    = True
    return jsonify({"ok": True})


@app.route("/download")
def download():
    p = Path(request.args.get("file", ""))
    if not p.exists():
        return "File not found", 404
    return send_file(str(p.resolve()), as_attachment=True, download_name=p.name)


if __name__ == "__main__":
    print("\n🎬  Tutorial Translator UI")
    print("   Open → http://localhost:5050\n")
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port, debug=False)
# PORT fix

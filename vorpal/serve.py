"""Thin local web UI — Phase 30.

`vorpal serve <input>` starts a FastAPI server on localhost:7654 and opens the
browser.  The UI surfaces the book manifest for interactive review and build
triggering.  CLI paths are entirely unchanged.
"""

import asyncio
import json
import sys
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import HTMLResponse, StreamingResponse
    from pydantic import BaseModel
    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False

from .manifest import Manifest, STAGE_ORDER
from .tts import VOICE_REGISTRY

# ── HTML ──────────────────────────────────────────────────────────────────

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>vorpal</title>
<style>
  body{font-family:system-ui,sans-serif;max-width:960px;margin:0 auto;padding:1.2rem}
  h1{margin-bottom:.2rem}
  .sub{color:#666;font-size:.9rem;margin-bottom:1.5rem}
  table{width:100%;border-collapse:collapse;font-size:.88rem}
  th,td{padding:.35rem .6rem;border:1px solid #ddd;text-align:left}
  th{background:#f5f5f5;font-weight:600}
  input[type=text]{width:100%;border:1px solid transparent;padding:2px 4px;font:inherit;background:transparent}
  input[type=text]:focus{border-color:#0077cc;background:#fff;outline:none;border-radius:3px}
  input[type=checkbox]{cursor:pointer}
  .btn{padding:.45rem 1rem;border:none;border-radius:4px;cursor:pointer;font:inherit;font-size:.88rem}
  .primary{background:#0077cc;color:#fff}
  .primary:hover{background:#005fa3}
  .primary:disabled{background:#aaa;cursor:default}
  .secondary{background:#e5e5e5;color:#333}
  .secondary:hover{background:#d0d0d0}
  #actions{display:flex;gap:.5rem;margin:1rem 0;align-items:center}
  #save-status{font-size:.82rem;color:#666}
  #log{font-family:monospace;font-size:.8rem;background:#1a1a1a;color:#d4d4d4;
       padding:1rem;border-radius:6px;height:180px;overflow-y:auto;display:none;margin-top:.8rem}
  .sec{margin-top:2rem}
  .sec h2{font-size:1.1rem;margin-bottom:.6rem}
  .voice-row{font-size:.88rem;margin-bottom:.35rem}
  .tone-bar{height:8px;background:#e5e5e5;border-radius:4px;overflow:hidden;
            display:inline-block;width:100px;vertical-align:middle;margin-right:6px}
  .tone-fill{height:100%;background:#0077cc}
  .tag{display:inline-block;padding:1px 6px;border-radius:3px;font-size:.75rem;
       background:#e5e5e5;margin-right:3px}
  .tag-somber{background:#c0d4e8}.tag-tense{background:#e8c0c0}
  .tag-excited{background:#ffe0a0}.tag-urgent{background:#ffc0a0}
  .tag-reflective{background:#c0e8c0}.tag-warm{background:#ffe8c0}.tag-wry{background:#e8c0e8}
</style>
</head>
<body>
<h1 id="book-title">vorpal</h1>
<div class="sub" id="book-sub">loading…</div>

<div id="actions">
  <button class="btn primary" id="build-btn" onclick="triggerBuild()">Build</button>
  <button class="btn secondary" id="save-btn" onclick="saveChanges()">Save changes</button>
  <span id="save-status"></span>
</div>

<div id="log"></div>

<table id="chapter-table">
  <thead>
    <tr><th>#</th><th>Kind</th><th>Include</th><th>Title</th><th>Pages</th><th>Words</th></tr>
  </thead>
  <tbody id="chapter-body"></tbody>
</table>

<div class="sec" id="voices-sec" style="display:none">
  <h2>Narrator voices</h2>
  <div id="voices-list"></div>
</div>

<div class="sec" id="tones-sec" style="display:none">
  <h2>Tone distribution</h2>
  <table>
    <thead><tr><th>Chapter</th><th>Neutral</th><th>Top tag</th><th>Profile</th></tr></thead>
    <tbody id="tone-body"></tbody>
  </table>
</div>

<script>
let bookData = null;
let pending = {};

async function loadBook() {
  const r = await fetch('/api/book');
  if (!r.ok) {
    document.getElementById('book-sub').textContent =
      'No book.json found — run vorpal build first.';
    return;
  }
  bookData = await r.json();
  renderBook();
  loadVoices();
}

function esc(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function renderBook() {
  const src = bookData.source || {};
  document.title = (src.title || 'vorpal') + ' — vorpal';
  document.getElementById('book-title').textContent = src.title || 'Untitled';
  const parts = [];
  if (src.author) parts.push(src.author);
  if (src.format) parts.push(src.format.toUpperCase());
  parts.push((bookData.chapters || []).length + ' chapter(s)');
  document.getElementById('book-sub').textContent = parts.join(' · ');

  const tbody = document.getElementById('chapter-body');
  tbody.innerHTML = '';
  (bookData.chapters || []).forEach((ch, i) => {
    const pages = ch.start
      ? (ch.start[0]+1) + (ch.end ? '–'+(ch.end[0]+1) : '') : '';
    const tr = document.createElement('tr');
    tr.innerHTML =
      '<td>'+(i+1)+'</td>'+
      '<td>'+esc(ch.kind||'chapter')+'</td>'+
      '<td><input type="checkbox" data-idx="'+i+'" data-field="include"'+
          (ch.include!==false?' checked':'')+' onchange="changed(this)"></td>'+
      '<td><input type="text" data-idx="'+i+'" data-field="title" value="'+
          esc(ch.title||'')+'" oninput="changed(this)"></td>'+
      '<td>'+esc(pages)+'</td>'+
      '<td>'+(ch.words||'')+'</td>';
    tbody.appendChild(tr);
  });

  const toneRows = (bookData.chapters||[]).filter(c=>c.paragraph_tones?.length);
  if (toneRows.length) renderTones();
}

function changed(el) {
  const idx = +el.dataset.idx;
  const field = el.dataset.field;
  const val = field==='include' ? el.checked : el.value;
  if (!pending[idx]) pending[idx] = {};
  pending[idx][field] = val;
  const s = document.getElementById('save-status');
  s.textContent = '● unsaved'; s.style.color='#aa6600';
}

async function saveChanges() {
  const btn = document.getElementById('save-btn');
  btn.disabled = true;
  let ok = true;
  for (const [idx, fields] of Object.entries(pending)) {
    for (const [field, value] of Object.entries(fields)) {
      const r = await fetch('/api/chapters/'+idx, {
        method:'PATCH',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({field, value}),
      });
      if (!r.ok) { ok=false; console.error('PATCH',idx,field,await r.text()); }
    }
  }
  pending = {};
  btn.disabled = false;
  const s = document.getElementById('save-status');
  if (ok) {
    s.textContent='✓ saved'; s.style.color='#0a0';
    setTimeout(()=>{s.textContent='';s.style.color='';},2000);
  } else {
    s.textContent='✗ save failed'; s.style.color='#c00';
  }
}

async function triggerBuild() {
  const btn = document.getElementById('build-btn');
  btn.disabled = true;
  const log = document.getElementById('log');
  log.style.display='block';
  log.innerHTML='';
  const append = t => {
    const d = document.createElement('div');
    d.textContent = t;
    log.appendChild(d);
    log.scrollTop = log.scrollHeight;
  };
  append('Starting build…');
  const r = await fetch('/api/build', {method:'POST'});
  if (!r.ok) {
    append('ERROR: ' + await r.text());
    btn.disabled = false;
    return;
  }
  const es = new EventSource('/api/events');
  es.onmessage = e => {
    if (e.data==='__done__') {
      es.close(); btn.disabled=false; append('— Build complete —');
    } else if (e.data==='__error__') {
      es.close(); btn.disabled=false; append('— Build failed —');
    } else { append(e.data); }
  };
  es.onerror = ()=>{ es.close(); btn.disabled=false; append('— Connection lost —'); };
}

async function loadVoices() {
  const r = await fetch('/api/voices');
  if (!r.ok) return;
  const voices = await r.json();
  const list = document.getElementById('voices-list');
  list.innerHTML = '';
  voices.forEach(v => {
    const div = document.createElement('div');
    div.className='voice-row';
    div.innerHTML='<strong>'+esc(v.display_name)+'</strong> <code>'+esc(v.id)+'</code>'+
      (v.description ? ' — '+esc(v.description) : '');
    list.appendChild(div);
  });
  if (voices.length) document.getElementById('voices-sec').style.display='block';
}

function renderTones() {
  const tbody = document.getElementById('tone-body');
  tbody.innerHTML = '';
  (bookData.chapters||[]).forEach((ch, i) => {
    const tones = ch.paragraph_tones || [];
    if (!tones.length) return;
    const total = tones.length;
    const neutral = tones.filter(t=>!t||t==='neutral').length;
    const pct = Math.round(neutral/total*100);
    const counts = {};
    tones.forEach(t=>{if(t&&t!=='neutral') counts[t]=(counts[t]||0)+1;});
    const top = Object.entries(counts).sort((a,b)=>b[1]-a[1])[0]?.[0]||'—';
    const tr = document.createElement('tr');
    tr.innerHTML =
      '<td>'+esc(ch.title||'Chapter '+(i+1))+'</td>'+
      '<td>'+pct+'%</td>'+
      '<td>'+(top!=='—'?'<span class="tag tag-'+top+'">'+top+'</span>':'—')+'</td>'+
      '<td><div class="tone-bar"><div class="tone-fill" style="width:'+pct+'%"></div></div>'+
      pct+'% neutral</td>';
    tbody.appendChild(tr);
  });
  if (tbody.children.length) document.getElementById('tones-sec').style.display='block';
}

loadBook();
</script>
</body>
</html>
"""


# ── Pydantic model ────────────────────────────────────────────────────────

if _FASTAPI_AVAILABLE:
    class ChapterPatch(BaseModel):
        field: str
        value: Any


# ── App factory ───────────────────────────────────────────────────────────

def create_app(input_path: Path, work_dir: Path):
    """Create a FastAPI app bound to *input_path* / *work_dir*.

    Call `start_server()` for the full server; use this directly in tests
    via ``fastapi.testclient.TestClient(create_app(...))``.
    """
    if not _FASTAPI_AVAILABLE:
        raise RuntimeError(
            "vorpal serve requires FastAPI. Install with:\n"
            "  pip install -e '.[web]'"
        )

    @asynccontextmanager
    async def _lifespan(application):
        yield
        # Cancel any running build on shutdown so the subprocess doesn't
        # outlive the event loop (avoids "Event loop is closed" warnings).
        task = application.state.build_task
        if task is not None and not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

    app = FastAPI(title="vorpal", docs_url=None, redoc_url=None,
                  lifespan=_lifespan)
    app.state.input_path = input_path
    app.state.work_dir = work_dir
    app.state.build_queue: Optional[asyncio.Queue] = None
    app.state.build_task = None

    # ── static UI ─────────────────────────────────────────────────────────

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def serve_ui():
        return HTMLResponse(_HTML)

    # ── book manifest ──────────────────────────────────────────────────────

    @app.get("/api/book")
    async def get_book():
        manifest_path = app.state.work_dir / "book.json"
        if not manifest_path.exists():
            raise HTTPException(
                status_code=404,
                detail="No book.json found — run `vorpal build` first",
            )
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return data

    # ── chapter editing ────────────────────────────────────────────────────

    _EDITABLE = {"title", "include", "spoken_intro"}

    @app.patch("/api/chapters/{idx}")
    async def patch_chapter(idx: int, patch: ChapterPatch):
        if patch.field not in _EDITABLE:
            raise HTTPException(
                status_code=400,
                detail=f"Field '{patch.field}' is not editable via the UI. "
                       f"Editable fields: {sorted(_EDITABLE)}",
            )
        manifest_path = app.state.work_dir / "book.json"
        if not manifest_path.exists():
            raise HTTPException(status_code=404, detail="book.json not found")

        manifest = Manifest.load_or_create(app.state.work_dir)
        chapters = manifest.data.get("chapters", [])
        if idx < 0 or idx >= len(chapters):
            raise HTTPException(
                status_code=404, detail=f"Chapter index {idx} out of range"
            )

        chapters[idx][patch.field] = patch.value

        # Title or include changes invalidate all downstream stages the same
        # way as `vorpal review --approve` does.
        if patch.field in ("title", "include"):
            manifest._invalidate_downstream("review")

        manifest.save()
        return {"ok": True}

    # ── voices ─────────────────────────────────────────────────────────────

    @app.get("/api/voices")
    async def get_voices():
        return [
            {
                "id": v.id,
                "display_name": v.display_name,
                "description": v.description,
                "engine": v.engine,
            }
            for v in VOICE_REGISTRY.values()
        ]

    # ── build trigger + SSE ────────────────────────────────────────────────

    @app.post("/api/build")
    async def trigger_build():
        state = app.state
        if state.build_task is not None and not state.build_task.done():
            raise HTTPException(status_code=409, detail="Build already running")

        q: asyncio.Queue = asyncio.Queue()
        state.build_queue = q

        async def _run():
            cmd = [
                sys.executable, "-m", "vorpal", "build",
                str(state.input_path),
            ]
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                async for raw in proc.stdout:
                    line = raw.decode("utf-8", errors="replace").rstrip()
                    await q.put(line)
                await proc.wait()
                await q.put("__done__" if proc.returncode == 0 else "__error__")
            except Exception as exc:
                await q.put(f"ERROR: {exc}")
                await q.put("__error__")

        state.build_task = asyncio.create_task(_run())
        return {"status": "started"}

    @app.get("/api/events")
    async def sse_events():
        """Server-Sent Events stream of build progress lines."""
        q = app.state.build_queue

        async def generator():
            if q is None:
                yield "data: (no build started)\n\n"
                return
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=25.0)
                    yield f"data: {msg}\n\n"
                    if msg in ("__done__", "__error__"):
                        break
                except asyncio.TimeoutError:
                    yield "data: \n\n"  # keepalive ping

        return StreamingResponse(generator(), media_type="text/event-stream")

    return app


# ── entry point ───────────────────────────────────────────────────────────

def start_server(
    input_path: Path,
    work_dir: Path,
    host: str = "127.0.0.1",
    port: int = 7654,
    open_browser: bool = True,
) -> None:
    if not _FASTAPI_AVAILABLE:
        sys.exit(
            "ERROR: vorpal serve requires FastAPI. Install with:\n"
            "  pip install -e '.[web]'"
        )
    try:
        import uvicorn
    except ImportError:
        sys.exit(
            "ERROR: vorpal serve requires uvicorn. Install with:\n"
            "  pip install -e '.[web]'"
        )

    app = create_app(input_path, work_dir)
    url = f"http://{host}:{port}"
    print(f"\n  vorpal UI: {url}")
    print(f"  Book:      {input_path}")
    print(f"  Workdir:   {work_dir}")
    print(f"  Press Ctrl+C to stop.\n")
    if open_browser:
        webbrowser.open(url)
    uvicorn.run(app, host=host, port=port, log_level="warning")

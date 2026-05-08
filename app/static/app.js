// ---------- Helpers ----------
function copyText(text) {
  navigator.clipboard.writeText(text).then(() => {
    // Could show a toast; keep it minimal
  });
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ---------- Attachment browser ----------
async function runSearch() {
  const query = document.getElementById('search-query').value;
  const max = document.getElementById('search-max').value;
  const results = document.getElementById('results');
  results.innerHTML = '<p class="muted small">Loading...</p>';

  try {
    const r = await fetch(`/api/list?query=${encodeURIComponent(query)}&max_results=${max}`);
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: r.statusText }));
      throw new Error(err.detail || `HTTP ${r.status}`);
    }
    const data = await r.json();

    if (!data.messages || data.messages.length === 0) {
      results.innerHTML = '<p class="muted small">No matching messages.</p>';
      return;
    }

    results.innerHTML = data.messages.map(msg => `
      <div class="result-item">
        <div class="result-head">
          <span class="result-subj">${escapeHtml(msg.subject)}</span>
          <span class="result-from">${escapeHtml(msg.from)}</span>
        </div>
        <div class="result-snippet">${escapeHtml(msg.snippet)}</div>
        <div class="attachments">
          ${msg.attachments.map(att => `
            <div class="att">
              <span class="att-name">${escapeHtml(att.filename)}</span>
              <span>${formatSize(att.size)}</span>
              <div class="att-actions">
                <button class="btn btn-ghost btn-sm" onclick="quickDownload('${msg.message_id}','${att.attachment_id}','${escapeHtml(att.filename)}')">↓</button>
                <button class="btn btn-ghost btn-sm" onclick="quickExtract('${msg.message_id}','${att.attachment_id}','${escapeHtml(att.filename)}')">⤓ text</button>
              </div>
            </div>
          `).join('')}
        </div>
      </div>
    `).join('');
  } catch (e) {
    results.innerHTML = `<p class="muted small" style="color:var(--error)">Error: ${escapeHtml(e.message)}</p>`;
  }
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1024 / 1024).toFixed(1) + ' MB';
}

async function quickDownload(messageId, attachmentId, filename) {
  const out = document.getElementById('tester-output');
  out.textContent = 'Downloading...';
  try {
    const r = await fetch('/api/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message_id: messageId, attachment_id: attachmentId, filename }),
    });
    const data = await r.json();
    out.textContent = JSON.stringify(data, null, 2);
  } catch (e) {
    out.textContent = 'Error: ' + e.message;
  }
}

async function quickExtract(messageId, attachmentId, filename) {
  const out = document.getElementById('tester-output');
  out.textContent = 'Extracting...';
  try {
    const r = await fetch('/api/extract', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message_id: messageId, attachment_id: attachmentId, filename }),
    });
    const data = await r.json();
    out.textContent = JSON.stringify(data, null, 2);
  } catch (e) {
    out.textContent = 'Error: ' + e.message;
  }
}

// ---------- MCP tester tabs ----------
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    document.querySelector(`.tab-pane[data-pane="${tab.dataset.tab}"]`).classList.add('active');
  });
});

async function testTool(name) {
  const out = document.getElementById('tester-output');
  out.textContent = 'Running...';
  try {
    let url, body;
    if (name === 'list') {
      url = `/api/list?query=${encodeURIComponent(document.getElementById('t-list-query').value)}&max_results=${document.getElementById('t-list-max').value}`;
      const r = await fetch(url);
      out.textContent = JSON.stringify(await r.json(), null, 2);
      return;
    }
    if (name === 'download') {
      url = '/api/download';
      body = {
        message_id: document.getElementById('t-dl-msg').value,
        attachment_id: document.getElementById('t-dl-att').value,
        filename: document.getElementById('t-dl-name').value,
        subfolder: document.getElementById('t-dl-sub').value || null,
      };
    } else if (name === 'extract') {
      url = '/api/extract';
      body = {
        message_id: document.getElementById('t-ex-msg').value,
        attachment_id: document.getElementById('t-ex-att').value,
        filename: document.getElementById('t-ex-name').value,
        use_ocr_pipeline: document.getElementById('t-ex-ocr').checked,
      };
    }
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    out.textContent = JSON.stringify(await r.json(), null, 2);
  } catch (e) {
    out.textContent = 'Error: ' + e.message;
  }
}

// ---------- Live logs (WebSocket) ----------
function connectLogs() {
  const status = document.getElementById('log-status');
  const logsEl = document.getElementById('logs');
  if (!logsEl || !status) return;

  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${proto}//${window.location.host}/ws/logs`);

  ws.onopen = () => { status.textContent = '● connected'; status.style.color = 'var(--ok)'; };
  ws.onclose = () => {
    status.textContent = '○ disconnected';
    status.style.color = 'var(--text-muted)';
    setTimeout(connectLogs, 3000);
  };
  ws.onerror = () => { status.textContent = '× error'; status.style.color = 'var(--error)'; };
  ws.onmessage = (ev) => {
    const line = document.createElement('div');
    line.className = 'log-line';
    if (ev.data.includes('[ERROR]')) line.classList.add('ERROR');
    else if (ev.data.includes('[WARNING]')) line.classList.add('WARNING');
    else line.classList.add('INFO');
    line.textContent = ev.data;
    logsEl.appendChild(line);
    logsEl.scrollTop = logsEl.scrollHeight;

    // Trim if too long
    while (logsEl.children.length > 500) logsEl.removeChild(logsEl.firstChild);
  };
}

connectLogs();

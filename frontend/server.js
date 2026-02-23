const http = require('http');
const https = require('https');
const { loadConfig } = require('./config');
const { URL } = require('url');

const config = loadConfig();
const port = config.port;

function escapeHtml(input) {
  return String(input)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function layout({ title, heading, subtitle, route, body, scripts = '' }) {
  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>${title}</title>
    <style>
      :root {
        --bg: #f4f7fb;
        --ink: #182433;
        --muted: #536278;
        --panel: #ffffff;
        --line: #d9e1ec;
        --accent: #0f6dbb;
        --warn: #8a2500;
        --ok: #0f7d57;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: "Segoe UI", Tahoma, sans-serif;
        background: radial-gradient(circle at 10% 10%, #ffffff, var(--bg));
        color: var(--ink);
      }
      header, main, footer { max-width: 1024px; margin: 0 auto; padding: 16px; }
      header { padding-top: 24px; }
      .shell { display: grid; grid-template-columns: 1fr; gap: 16px; }
      .card {
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 12px;
        padding: 16px;
      }
      h1 { margin: 0 0 8px; font-size: 28px; }
      h2 { margin: 0 0 12px; font-size: 20px; }
      p { margin: 0 0 10px; color: var(--muted); }
      code {
        background: #eef4fb;
        border-radius: 6px;
        padding: 2px 6px;
        color: #0e4c80;
      }
      .chip {
        display: inline-block;
        border: 1px solid #b5d3f0;
        color: var(--accent);
        border-radius: 999px;
        padding: 4px 10px;
        font-size: 12px;
        font-weight: 600;
      }
      .state { display: grid; gap: 10px; }
      .loading {
        border: 1px dashed #b7c5d7;
        border-radius: 8px;
        padding: 10px;
      }
      .error {
        border: 1px solid #f3ccc0;
        background: #fff6f3;
        color: var(--warn);
        border-radius: 8px;
        padding: 10px;
      }
      footer { font-size: 12px; color: var(--muted); padding-bottom: 24px; }
      a { color: var(--accent); text-decoration: none; }
      a:hover { text-decoration: underline; }
      .grid { display: grid; gap: 12px; }
      label { display: grid; gap: 6px; font-weight: 600; }
      input[type=text] {
        width: 100%;
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 10px 12px;
        font: inherit;
      }
      button {
        width: fit-content;
        border: 1px solid #0b5ea1;
        background: var(--accent);
        color: #fff;
        border-radius: 8px;
        padding: 10px 14px;
        font: inherit;
        font-weight: 600;
        cursor: pointer;
      }
      button:disabled { opacity: 0.65; cursor: not-allowed; }
      .hidden { display: none; }
      .ok {
        border: 1px solid #c3e4d7;
        background: #f2fcf8;
        color: var(--ok);
        border-radius: 8px;
        padding: 10px;
      }
      .mono { font-family: "Cascadia Mono", Consolas, monospace; }
    </style>
  </head>
  <body>
    <header>
      <span class="chip">DevLens v1.1 shell</span>
      <h1>${heading}</h1>
      <p>${subtitle}</p>
    </header>
    <main class="shell">
      <section class="card">
        <h2>Route</h2>
        <p>Rendered path: <code>${route}</code></p>
      </section>
      <section class="card">
        ${body}
      </section>
      <section class="card state">
        <h2>Global States</h2>
        <div class="loading">Loading state placeholder (used during data fetch and route transitions).</div>
        <div class="error">Error state placeholder (used for recoverable rendering/API failures).</div>
      </section>
    </main>
    <footer>
      API base: <code>${config.apiUrl}</code>.
      <a href="/health">Health</a>
    </footer>
    ${scripts}
  </body>
</html>`;
}

function renderRoute(pathname) {
  if (pathname === '/') {
    return layout({
      title: 'DevLens | Home',
      heading: 'DevLens',
      subtitle: 'Repository intelligence, architecture context, and chat search.',
      route: '/',
      body: '<h2>Home</h2><p>Landing shell route is live.</p>',
    });
  }

  if (pathname === '/analyze') {
    const analyzeBody = `
<h2>Analyze</h2>
<p>Submit a public GitHub repository URL. Live status is streamed from SSE.</p>
<form id="analyze-form" class="grid">
  <label>
    GitHub URL
    <input id="github-url" type="text" placeholder="https://github.com/owner/repo" required />
  </label>
  <button id="submit-btn" type="submit">Analyze</button>
</form>
<div id="cache-hit" class="ok hidden"></div>
<div id="error-msg" class="error hidden"></div>
<div id="job-card" class="loading hidden">
  <div><strong>Job:</strong> <span class="mono" id="job-id"></span></div>
  <div><strong>Repo:</strong> <span class="mono" id="repo-id"></span></div>
  <div><strong>Status:</strong> <span id="status-line">Queued</span></div>
  <div><strong>Progress:</strong> <span id="progress-line">0%</span></div>
</div>
<div id="done-msg" class="ok hidden"></div>`;

    const analyzeScripts = `<script>
(function () {
  const form = document.getElementById('analyze-form');
  const input = document.getElementById('github-url');
  const submitBtn = document.getElementById('submit-btn');
  const errorBox = document.getElementById('error-msg');
  const cacheHitBox = document.getElementById('cache-hit');
  const jobCard = document.getElementById('job-card');
  const doneBox = document.getElementById('done-msg');
  const jobId = document.getElementById('job-id');
  const repoId = document.getElementById('repo-id');
  const statusLine = document.getElementById('status-line');
  const progressLine = document.getElementById('progress-line');

  let stream = null;
  let reconnectAttempts = 0;
  let terminal = false;
  const maxReconnect = 5;

  function hide(el) { el.classList.add('hidden'); }
  function show(el) { el.classList.remove('hidden'); }

  function setError(message) {
    errorBox.textContent = message;
    show(errorBox);
  }

  function clearFeedback() {
    hide(errorBox);
    hide(cacheHitBox);
    hide(doneBox);
    cacheHitBox.textContent = '';
    doneBox.textContent = '';
    errorBox.textContent = '';
  }

  function closeStream() {
    if (stream) {
      stream.close();
      stream = null;
    }
  }

  function connectStatus(repo) {
    closeStream();
    terminal = false;
    stream = new EventSource('/api/v1/repos/' + encodeURIComponent(repo) + '/status');

    stream.addEventListener('progress', function (event) {
      reconnectAttempts = 0;
      const payload = JSON.parse(event.data);
      statusLine.textContent = payload.stage + ' in progress';
      progressLine.textContent = String(payload.progress) + '%';
      show(jobCard);
    });

    stream.addEventListener('done', function (event) {
      const payload = JSON.parse(event.data);
      terminal = true;
      statusLine.textContent = payload.stage;
      progressLine.textContent = String(payload.progress) + '%';
      doneBox.textContent = 'Analysis complete. Open dashboard: /dashboard/' + repo;
      show(doneBox);
      closeStream();
    });

    stream.addEventListener('error', function (event) {
      let message = 'Status stream error';
      if (event && event.data) {
        try {
          const payload = JSON.parse(event.data);
          if (payload.message) {
            message = payload.message;
          }
        } catch (_err) {}
      }
      setError(message);
      if (terminal) {
        closeStream();
        return;
      }
      closeStream();
      reconnectAttempts += 1;
      if (reconnectAttempts > maxReconnect) {
        setError('Status stream disconnected after retries.');
        return;
      }
      setTimeout(function () { connectStatus(repo); }, reconnectAttempts * 1000);
    });
  }

  form.addEventListener('submit', async function (event) {
    event.preventDefault();
    clearFeedback();
    closeStream();
    submitBtn.disabled = true;

    const githubUrl = input.value.trim();
    if (!/^https:\\/\\/github\\.com\\/[^\\s/]+\\/[^\\s/]+/.test(githubUrl)) {
      setError('Please enter a valid public GitHub repository URL.');
      submitBtn.disabled = false;
      return;
    }

    try {
      const response = await fetch('/api/v1/repos/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ github_url: githubUrl })
      });
      const payload = await response.json();
      if (!response.ok) {
        const message = (payload && payload.error && payload.error.message) || payload.detail || 'Analyze failed';
        setError(message);
        return;
      }

      jobId.textContent = payload.job_id;
      repoId.textContent = payload.repo_id;
      statusLine.textContent = payload.status;
      progressLine.textContent = payload.status === 'done' ? '100%' : '0%';
      show(jobCard);

      if (payload.cache_hit) {
        cacheHitBox.textContent = 'Cache hit: latest commit already analyzed.';
        show(cacheHitBox);
      }

      connectStatus(payload.repo_id);
    } catch (_error) {
      setError('Request failed. Check backend availability and try again.');
    } finally {
      submitBtn.disabled = false;
    }
  });
})();
</script>`;

    return layout({
      title: 'DevLens | Analyze',
      heading: 'Analyze Repository',
      subtitle: 'Submit a GitHub URL and track analysis progress.',
      route: '/analyze',
      body: analyzeBody,
      scripts: analyzeScripts,
    });
  }

  const dashboardMatch = pathname.match(/^\/dashboard\/([^/]+)$/);
  if (dashboardMatch) {
    const repoId = dashboardMatch[1];
    const dashboardBody = `
<h2>Dashboard</h2>
<p>Core panel shell backed by live API payload.</p>
<div id="dash-loading" class="loading">Loading dashboard data...</div>
<div id="dash-error" class="error hidden"></div>
<div id="dash-empty" class="loading hidden">No completed analysis yet. Run analysis from <a href="/analyze">/analyze</a>.</div>
<section id="dash-panels" class="grid hidden">
  <div class="card">
    <h2>Overview</h2>
    <p id="overview-name"></p>
    <p id="overview-meta"></p>
    <p id="overview-desc"></p>
  </div>
  <div class="card">
    <h2>Quality Score</h2>
    <p id="quality-score"></p>
  </div>
  <div class="card">
    <h2>Architecture Summary</h2>
    <p id="architecture-summary"></p>
  </div>
  <div class="card">
    <h2>Tech Debt</h2>
    <pre id="tech-debt" class="mono"></pre>
  </div>
  <div class="card">
    <h2>Contributor Analytics</h2>
    <pre id="contributors" class="mono"></pre>
  </div>
  <div class="card">
    <h2>File Explorer</h2>
    <pre id="file-tree" class="mono"></pre>
  </div>
  <div class="card">
    <h2>Export</h2>
    <p>Generate local report files from current dashboard payload.</p>
    <div class="grid">
      <button id="export-md" type="button">Export Markdown</button>
      <button id="export-html" type="button">Export HTML</button>
      <button id="export-pdf" type="button">Export PDF (Print)</button>
    </div>
  </div>
  <div class="card">
    <h2>Public Share</h2>
    <label>
      Access Token (JWT)
      <input id="share-token" type="text" placeholder="Paste bearer token to create/revoke share links" />
    </label>
    <div class="grid">
      <label>
        TTL (days)
        <input id="share-ttl" type="text" value="7" />
      </label>
      <button id="share-save-token" type="button">Save Token</button>
      <button id="share-create" type="button">Create Share Link</button>
      <button id="share-revoke" type="button">Revoke Current Link</button>
    </div>
    <div id="share-status" class="loading hidden"></div>
    <div id="share-link-wrap" class="ok hidden">
      <div><strong>Share URL:</strong> <a id="share-link" href="#" target="_blank" rel="noreferrer"></a></div>
      <div><strong>Expires:</strong> <span id="share-expiry"></span></div>
      <div><strong>Share ID:</strong> <span id="share-id" class="mono"></span></div>
    </div>
  </div>
</section>`;

    const dashboardScripts = `<script>
(function () {
  const loading = document.getElementById('dash-loading');
  const errorBox = document.getElementById('dash-error');
  const emptyBox = document.getElementById('dash-empty');
  const panels = document.getElementById('dash-panels');
  const shareTokenInput = document.getElementById('share-token');
  const shareSaveTokenBtn = document.getElementById('share-save-token');
  const shareCreateBtn = document.getElementById('share-create');
  const shareRevokeBtn = document.getElementById('share-revoke');
  const shareTtlInput = document.getElementById('share-ttl');
  const shareStatus = document.getElementById('share-status');
  const shareWrap = document.getElementById('share-link-wrap');
  const shareLink = document.getElementById('share-link');
  const shareExpiry = document.getElementById('share-expiry');
  const shareId = document.getElementById('share-id');
  const exportMdBtn = document.getElementById('export-md');
  const exportHtmlBtn = document.getElementById('export-html');
  const exportPdfBtn = document.getElementById('export-pdf');
  const repoId = ${JSON.stringify(repoId)};
  let dashboardPayload = null;
  let currentShare = null;

  function show(el) { el.classList.remove('hidden'); }
  function hide(el) { el.classList.add('hidden'); }
  function getAccessToken() { return localStorage.getItem('devlens.access_token') || ''; }
  function setAccessToken(value) { localStorage.setItem('devlens.access_token', value.trim()); }
  function shareStorageKey() { return 'devlens.share.' + repoId; }
  function loadStoredShare() {
    try {
      const raw = localStorage.getItem(shareStorageKey());
      return raw ? JSON.parse(raw) : null;
    } catch (_err) {
      return null;
    }
  }
  function saveStoredShare(data) {
    localStorage.setItem(shareStorageKey(), JSON.stringify(data));
  }
  function clearStoredShare() {
    localStorage.removeItem(shareStorageKey());
  }
  function setShareStatus(text, isError) {
    shareStatus.textContent = text;
    shareStatus.className = isError ? 'error' : 'loading';
    show(shareStatus);
  }
  function clearShareStatus() {
    shareStatus.textContent = '';
    hide(shareStatus);
  }
  function renderShareCard(data) {
    if (!data || !data.share_url) {
      hide(shareWrap);
      return;
    }
    shareLink.href = data.share_url;
    shareLink.textContent = data.share_url;
    shareExpiry.textContent = data.expires_at || 'unknown';
    shareId.textContent = data.share_id || '';
    show(shareWrap);
  }
  function escapeBlock(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }
  function authHeaders() {
    const token = getAccessToken();
    if (!token) {
      throw new Error('Missing access token for share actions.');
    }
    return { Authorization: 'Bearer ' + token };
  }
  async function authJson(path, options) {
    const response = await fetch(path, Object.assign({}, options || {}, {
      headers: Object.assign({}, options && options.headers ? options.headers : {}, authHeaders())
    }));
    const payload = await response.json().catch(function () { return {}; });
    if (!response.ok) {
      const msg = payload && payload.error && payload.error.message ? payload.error.message : (payload.detail || 'Request failed');
      throw new Error(msg);
    }
    return payload;
  }
  function reportTitle() {
    if (!dashboardPayload || !dashboardPayload.repository) {
      return 'devlens-report';
    }
    return (dashboardPayload.repository.full_name || 'devlens-report').replace(/[\\/]/g, '-');
  }
  function buildMarkdownReport() {
    const d = dashboardPayload;
    const r = d.repository;
    const a = d.analysis || {};
    const fence = String.fromCharCode(96).repeat(3);
    return [
      '# DevLens Report',
      '',
      '## Repository',
      '- Name: ' + (r.full_name || 'N/A'),
      '- URL: ' + (r.github_url || 'N/A'),
      '- Default branch: ' + (r.default_branch || 'main'),
      '- Latest commit: ' + (r.latest_commit_sha || 'N/A'),
      '- Stars/Forks: ' + String(r.stars || 0) + ' / ' + String(r.forks || 0),
      '',
      '## Quality',
      '- Score: ' + String(a.quality_score == null ? 'N/A' : a.quality_score),
      '',
      '## Architecture Summary',
      String(a.architecture_summary || 'No summary'),
      '',
      '## Tech Debt Flags',
      fence + 'json',
      JSON.stringify(a.tech_debt_flags || {}, null, 2),
      fence,
      '',
      '## Contributor Stats',
      fence + 'json',
      JSON.stringify(a.contributor_stats || {}, null, 2),
      fence,
      '',
      '## File Tree',
      fence + 'json',
      JSON.stringify(a.file_tree || {}, null, 2),
      fence,
      '',
    ].join('\\n');
  }
  function buildHtmlReport() {
    const d = dashboardPayload;
    const r = d.repository;
    const a = d.analysis || {};
    return '<!doctype html><html><head><meta charset="utf-8"><title>DevLens Report</title>' +
      '<style>body{font-family:Segoe UI,Tahoma,sans-serif;padding:24px;color:#182433} pre{background:#f4f7fb;padding:12px;border-radius:8px;overflow:auto}</style>' +
      '</head><body>' +
      '<h1>DevLens Report</h1>' +
      '<h2>Repository</h2>' +
      '<p><strong>' + escapeBlock(r.full_name || 'N/A') + '</strong></p>' +
      '<p>' + escapeBlock(r.github_url || 'N/A') + '</p>' +
      '<p>Default branch: ' + escapeBlock(r.default_branch || 'main') + '</p>' +
      '<p>Latest commit: ' + escapeBlock(r.latest_commit_sha || 'N/A') + '</p>' +
      '<h2>Quality Score</h2><p>' + escapeBlock(String(a.quality_score == null ? 'N/A' : a.quality_score)) + '</p>' +
      '<h2>Architecture Summary</h2><p>' + escapeBlock(String(a.architecture_summary || 'No summary')) + '</p>' +
      '<h2>Tech Debt Flags</h2><pre>' + escapeBlock(JSON.stringify(a.tech_debt_flags || {}, null, 2)) + '</pre>' +
      '<h2>Contributor Stats</h2><pre>' + escapeBlock(JSON.stringify(a.contributor_stats || {}, null, 2)) + '</pre>' +
      '<h2>File Tree</h2><pre>' + escapeBlock(JSON.stringify(a.file_tree || {}, null, 2)) + '</pre>' +
      '</body></html>';
  }
  function downloadFile(filename, mime, content) {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function setText(id, value) {
    const el = document.getElementById(id);
    el.textContent = value == null || value === '' ? 'N/A' : String(value);
  }

  async function loadDashboard() {
    try {
      const response = await fetch('/api/v1/repos/' + encodeURIComponent(repoId) + '/dashboard');
      const payload = await response.json();
      if (!response.ok) {
        const message = (payload && payload.error && payload.error.message) || payload.detail || 'Failed to load dashboard';
        throw new Error(message);
      }
      dashboardPayload = payload;

      setText('overview-name', payload.repository.full_name);
      setText(
        'overview-meta',
        'Default branch: ' + (payload.repository.default_branch || 'main') +
          ' | Stars: ' + (payload.repository.stars || 0) +
          ' | Forks: ' + (payload.repository.forks || 0)
      );
      setText('overview-desc', payload.repository.description || 'No repository description');

      if (!payload.has_analysis || !payload.analysis) {
        hide(loading);
        show(emptyBox);
        return;
      }

      setText('quality-score', payload.analysis.quality_score);
      setText('architecture-summary', payload.analysis.architecture_summary || 'No summary generated yet.');
      setText('tech-debt', JSON.stringify(payload.analysis.tech_debt_flags || {}, null, 2));
      setText('contributors', JSON.stringify(payload.analysis.contributor_stats || {}, null, 2));
      setText('file-tree', JSON.stringify(payload.analysis.file_tree || {}, null, 2));

      hide(loading);
      show(panels);
      renderShareCard(currentShare);
    } catch (error) {
      hide(loading);
      errorBox.textContent = error && error.message ? error.message : 'Dashboard load failed';
      show(errorBox);
    }
  }

  exportMdBtn.addEventListener('click', function () {
    if (!dashboardPayload || !dashboardPayload.repository) {
      return;
    }
    downloadFile(reportTitle() + '.md', 'text/markdown;charset=utf-8', buildMarkdownReport());
  });

  exportHtmlBtn.addEventListener('click', function () {
    if (!dashboardPayload || !dashboardPayload.repository) {
      return;
    }
    downloadFile(reportTitle() + '.html', 'text/html;charset=utf-8', buildHtmlReport());
  });

  exportPdfBtn.addEventListener('click', function () {
    if (!dashboardPayload || !dashboardPayload.repository) {
      return;
    }
    const html = buildHtmlReport();
    const win = window.open('', '_blank');
    if (!win) {
      errorBox.textContent = 'Popup blocked. Allow popups to export PDF.';
      show(errorBox);
      return;
    }
    win.document.write(html);
    win.document.close();
    win.focus();
    win.print();
  });

  shareSaveTokenBtn.addEventListener('click', function () {
    setAccessToken(shareTokenInput.value);
    clearShareStatus();
    setShareStatus('Token saved for share actions.', false);
  });

  shareCreateBtn.addEventListener('click', async function () {
    try {
      clearShareStatus();
      const ttl = Number(shareTtlInput.value || '7');
      if (!Number.isInteger(ttl) || ttl < 1 || ttl > 30) {
        throw new Error('TTL must be an integer between 1 and 30.');
      }
      const payload = await authJson('/api/v1/export/' + encodeURIComponent(repoId) + '/share', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ttl_days: ttl }),
      });
      currentShare = payload;
      saveStoredShare(payload);
      renderShareCard(payload);
      setShareStatus('Share link created.', false);
    } catch (error) {
      setShareStatus(error && error.message ? error.message : 'Failed to create share link.', true);
    }
  });

  shareRevokeBtn.addEventListener('click', async function () {
    try {
      clearShareStatus();
      if (!currentShare || !currentShare.share_id) {
        throw new Error('No active share link available to revoke.');
      }
      await authJson('/api/v1/export/share/' + encodeURIComponent(currentShare.share_id), { method: 'DELETE' });
      clearStoredShare();
      currentShare = null;
      hide(shareWrap);
      setShareStatus('Share link revoked.', false);
    } catch (error) {
      setShareStatus(error && error.message ? error.message : 'Failed to revoke share link.', true);
    }
  });

  shareTokenInput.value = getAccessToken();
  currentShare = loadStoredShare();
  renderShareCard(currentShare);

  loadDashboard();
})();
</script>`;

    return layout({
      title: 'DevLens | Dashboard',
      heading: 'Repository Dashboard',
      subtitle: 'Overview panels and architecture summary.',
      route: pathname,
      body: dashboardBody,
      scripts: dashboardScripts,
    });
  }

  const chatMatch = pathname.match(/^\/dashboard\/([^/]+)\/chat$/);
  if (chatMatch) {
    const repoId = chatMatch[1];
    const chatBody = `
<h2>Chat</h2>
<p>Streaming chat with session history and source citations.</p>
<div class="grid">
  <label>
    Access Token (JWT)
    <input id="chat-token" type="text" placeholder="Paste bearer token from /auth/refresh flow" />
  </label>
  <button id="save-token" type="button">Save Token</button>
</div>
<div id="chat-error" class="error hidden"></div>
<section class="grid">
  <div class="card">
    <h2>Sessions</h2>
    <button id="new-session" type="button">New Session</button>
    <div id="session-loading" class="loading hidden">Loading sessions...</div>
    <ul id="session-list" class="mono"></ul>
  </div>
  <div class="card">
    <h2>Suggested Questions</h2>
    <div id="chips" class="grid"></div>
  </div>
  <div class="card">
    <h2>Messages</h2>
    <div id="message-list" class="grid"></div>
    <form id="chat-form" class="grid">
      <label>
        Ask a question
        <input id="chat-input" type="text" required />
      </label>
      <button id="send-message" type="submit">Send</button>
    </form>
  </div>
</section>`;

    const chatScripts = `<script>
(function () {
  const repoId = ${JSON.stringify(repoId)};
  const tokenInput = document.getElementById('chat-token');
  const saveTokenBtn = document.getElementById('save-token');
  const errorBox = document.getElementById('chat-error');
  const newSessionBtn = document.getElementById('new-session');
  const sessionLoading = document.getElementById('session-loading');
  const sessionList = document.getElementById('session-list');
  const chips = document.getElementById('chips');
  const messageList = document.getElementById('message-list');
  const chatForm = document.getElementById('chat-form');
  const chatInput = document.getElementById('chat-input');
  const sendBtn = document.getElementById('send-message');

  let currentSessionId = null;
  let sessions = [];
  let messages = [];

  function show(el) { el.classList.remove('hidden'); }
  function hide(el) { el.classList.add('hidden'); }
  function setError(msg) {
    errorBox.textContent = msg;
    show(errorBox);
  }
  function clearError() {
    errorBox.textContent = '';
    hide(errorBox);
  }
  function getToken() {
    return localStorage.getItem('devlens.access_token') || '';
  }
  function saveToken(token) {
    localStorage.setItem('devlens.access_token', token.trim());
  }
  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }
  function highlightCode(code, lang) {
    const source = escapeHtml(code);
    const keywords = {
      py: ['def', 'class', 'return', 'if', 'else', 'for', 'while', 'import', 'from', 'try', 'except'],
      js: ['function', 'const', 'let', 'var', 'return', 'if', 'else', 'for', 'while', 'import', 'export', 'async', 'await'],
      ts: ['function', 'const', 'let', 'return', 'if', 'else', 'interface', 'type', 'import', 'export', 'async', 'await'],
    };
    const set = keywords[lang] || keywords.js;
    let highlighted = source;
    set.forEach(function (kw) {
      const re = new RegExp('\\\\b' + kw + '\\\\b', 'g');
      highlighted = highlighted.replace(re, '<span style="color:#8a2500;font-weight:600;">' + kw + '</span>');
    });
    return highlighted;
  }
  function renderMessageText(content) {
    const blocks = [];
    let cursor = 0;
    const fence = String.fromCharCode(96).repeat(3);
    const re = new RegExp(fence + '([a-zA-Z0-9_+\\\\-]+)?\\\\n([\\\\s\\\\S]*?)' + fence, 'g');
    let match;
    while ((match = re.exec(content)) !== null) {
      if (match.index > cursor) {
        blocks.push('<p>' + escapeHtml(content.slice(cursor, match.index)) + '</p>');
      }
      const lang = (match[1] || 'js').toLowerCase();
      blocks.push(
        '<pre style="background:#0f1720;color:#f0f4f9;padding:12px;border-radius:8px;overflow:auto;"><code>' +
          highlightCode(match[2], lang) +
        '</code></pre>'
      );
      cursor = re.lastIndex;
    }
    if (cursor < content.length) {
      blocks.push('<p>' + escapeHtml(content.slice(cursor)) + '</p>');
    }
    return blocks.join('');
  }
  function authHeaders() {
    const token = getToken();
    if (!token) {
      throw new Error('Missing access token. Paste it and click Save Token.');
    }
    return { Authorization: 'Bearer ' + token };
  }
  async function api(path, options) {
    const headers = Object.assign({}, options && options.headers ? options.headers : {}, authHeaders());
    const response = await fetch(path, Object.assign({}, options || {}, { headers }));
    const contentType = response.headers.get('content-type') || '';
    let payload = null;
    if (contentType.includes('application/json')) {
      payload = await response.json();
    } else {
      payload = await response.text();
    }
    if (!response.ok) {
      const message = payload && payload.error && payload.error.message ? payload.error.message : (payload && payload.detail ? payload.detail : 'Request failed');
      throw new Error(message);
    }
    return payload;
  }
  function renderSessions() {
    sessionList.innerHTML = '';
    sessions.forEach(function (item) {
      const li = document.createElement('li');
      li.style.marginBottom = '8px';
      const active = item.id === currentSessionId ? ' style="font-weight:700;"' : '';
      li.innerHTML =
        '<a href="#" data-session="' + item.id + '"' + active + '>' + escapeHtml(item.id.slice(0, 8)) + '</a>' +
        ' (' + item.message_count + ' msgs)' +
        (item.last_message_preview ? ' - ' + escapeHtml(item.last_message_preview) : '');
      sessionList.appendChild(li);
    });
  }
  function renderMessages() {
    messageList.innerHTML = '';
    if (messages.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'loading';
      empty.textContent = 'No messages yet.';
      messageList.appendChild(empty);
      return;
    }
    messages.forEach(function (msg) {
      const card = document.createElement('div');
      card.className = 'card';
      const role = msg.role === 'assistant' ? 'Assistant' : 'You';
      let citationHtml = '';
      if (msg.source_citations && msg.source_citations.citations && msg.source_citations.citations.length) {
        const links = msg.source_citations.citations.map(function (c) {
          const anchor = c.anchor || (c.file_path + '#L' + (c.line_start || 1));
          const href = '/dashboard/' + encodeURIComponent(repoId) + '/files?path=' + encodeURIComponent(c.file_path || '') + '&line=' + encodeURIComponent(String(c.line_start || 1));
          return '<a href="' + href + '">' + escapeHtml(anchor) + '</a>';
        });
        citationHtml = '<div><strong>Citations:</strong> ' + links.join(', ') + '</div>';
      } else if (msg.source_citations && msg.source_citations.no_citation) {
        citationHtml = '<div><strong>Citations:</strong> no-citation</div>';
      }
      card.innerHTML = '<div><strong>' + role + '</strong></div>' + renderMessageText(msg.content || '') + citationHtml;
      messageList.appendChild(card);
    });
  }
  async function loadSessions() {
    show(sessionLoading);
    try {
      const payload = await api('/api/v1/chat/sessions?repo_id=' + encodeURIComponent(repoId), { method: 'GET' });
      sessions = payload.sessions || [];
      if (!currentSessionId && sessions.length) {
        currentSessionId = sessions[0].id;
      }
      renderSessions();
      if (currentSessionId) {
        await loadSession(currentSessionId);
      } else {
        messages = [];
        renderMessages();
      }
    } finally {
      hide(sessionLoading);
    }
  }
  async function loadSession(sessionId) {
    const payload = await api('/api/v1/chat/sessions/' + encodeURIComponent(sessionId), { method: 'GET' });
    currentSessionId = payload.id;
    messages = payload.messages || [];
    renderSessions();
    renderMessages();
  }
  async function createSession() {
    const payload = await api('/api/v1/chat/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo_id: repoId }),
    });
    currentSessionId = payload.session_id;
    await loadSessions();
  }
  async function loadSuggestions() {
    chips.innerHTML = '';
    const payload = await api('/api/v1/chat/repos/' + encodeURIComponent(repoId) + '/suggestions?limit=6', { method: 'GET' });
    (payload.suggestions || []).forEach(function (text) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.textContent = text;
      btn.style.textAlign = 'left';
      btn.style.whiteSpace = 'normal';
      btn.addEventListener('click', function () {
        chatInput.value = text;
        chatInput.focus();
      });
      chips.appendChild(btn);
    });
  }
  async function streamMessage(content) {
    const headers = Object.assign({ 'Content-Type': 'application/json' }, authHeaders());
    const response = await fetch('/api/v1/chat/sessions/' + encodeURIComponent(currentSessionId) + '/message', {
      method: 'POST',
      headers: headers,
      body: JSON.stringify({ content: content, top_k: 5 }),
    });
    if (!response.ok || !response.body) {
      throw new Error('Streaming request failed');
    }
    const draft = { id: 'draft', role: 'assistant', content: '', source_citations: { citations: [], no_citation: true } };
    messages.push(draft);
    renderMessages();

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const item = await reader.read();
      if (item.done) {
        break;
      }
      buffer += decoder.decode(item.value, { stream: true });
      const events = buffer.split('\\n\\n');
      buffer = events.pop() || '';
      events.forEach(function (raw) {
        const lines = raw.split('\\n');
        let eventName = '';
        let dataRaw = '';
        lines.forEach(function (line) {
          if (line.startsWith('event:')) {
            eventName = line.slice(6).trim();
          } else if (line.startsWith('data:')) {
            dataRaw += line.slice(5).trim();
          }
        });
        if (!eventName || !dataRaw) {
          return;
        }
        const payload = JSON.parse(dataRaw);
        if (eventName === 'delta') {
          draft.content += payload.token || '';
          renderMessages();
        } else if (eventName === 'done') {
          draft.id = payload.message_id || draft.id;
          draft.source_citations = {
            citations: payload.citations || [],
            no_citation: !!payload.no_citation,
          };
          renderMessages();
        }
      });
    }
    await loadSession(currentSessionId);
  }

  saveTokenBtn.addEventListener('click', async function () {
    try {
      clearError();
      saveToken(tokenInput.value);
      await loadSessions();
      await loadSuggestions();
    } catch (error) {
      setError(error && error.message ? error.message : 'Token save failed');
    }
  });

  sessionList.addEventListener('click', async function (event) {
    const target = event.target;
    if (!(target instanceof HTMLAnchorElement)) {
      return;
    }
    event.preventDefault();
    const sessionId = target.getAttribute('data-session');
    if (!sessionId) {
      return;
    }
    try {
      clearError();
      await loadSession(sessionId);
    } catch (error) {
      setError(error && error.message ? error.message : 'Failed to load session');
    }
  });

  newSessionBtn.addEventListener('click', async function () {
    try {
      clearError();
      await createSession();
    } catch (error) {
      setError(error && error.message ? error.message : 'Failed to create session');
    }
  });

  chatForm.addEventListener('submit', async function (event) {
    event.preventDefault();
    const text = chatInput.value.trim();
    if (!text) {
      return;
    }
    if (!currentSessionId) {
      setError('Create a session first.');
      return;
    }
    try {
      clearError();
      sendBtn.disabled = true;
      messages.push({ id: 'user-' + Date.now(), role: 'user', content: text, source_citations: null });
      renderMessages();
      chatInput.value = '';
      await streamMessage(text);
    } catch (error) {
      setError(error && error.message ? error.message : 'Failed to send message');
    } finally {
      sendBtn.disabled = false;
    }
  });

  (async function init() {
    tokenInput.value = getToken();
    if (!tokenInput.value) {
      messages = [];
      renderMessages();
      setError('Paste an access token and click Save Token to start chat.');
      return;
    }
    try {
      await loadSessions();
      await loadSuggestions();
    } catch (error) {
      setError(error && error.message ? error.message : 'Failed to initialize chat');
    }
  })();
})();
</script>`;

    return layout({
      title: 'DevLens | Chat',
      heading: 'Repository Chat',
      subtitle: 'Cited retrieval-augmented chat interface.',
      route: pathname,
      body: chatBody,
      scripts: chatScripts,
    });
  }

  const filesMatch = pathname.match(/^\/dashboard\/([^/]+)\/files$/);
  if (filesMatch) {
    return layout({
      title: 'DevLens | Files',
      heading: 'File Explorer',
      subtitle: 'Source browser and code navigation shell.',
      route: pathname,
      body: `<h2>Files</h2><p>File explorer shell for repo <code>${filesMatch[1]}</code>.</p>`,
    });
  }

  if (pathname === '/profile') {
    return layout({
      title: 'DevLens | Profile',
      heading: 'Profile',
      subtitle: 'Account, usage, and settings shell.',
      route: '/profile',
      body: '<h2>Profile</h2><p>Profile shell route is live.</p>',
    });
  }

  const shareMatch = pathname.match(/^\/share\/([^/]+)$/);
  if (shareMatch) {
    const shareToken = shareMatch[1];
    const shareBody = `
<h2>Shared Report</h2>
<p>Public analysis snapshot resolved from signed share token.</p>
<div id="share-loading" class="loading">Loading shared report...</div>
<div id="share-error" class="error hidden"></div>
<div id="share-guard" class="loading hidden"></div>
<section id="share-content" class="grid hidden">
  <div class="card">
    <h2>Repository</h2>
    <p id="shared-name"></p>
    <p id="shared-url"></p>
    <p id="shared-meta"></p>
  </div>
  <div class="card">
    <h2>Quality Score</h2>
    <p id="shared-quality"></p>
  </div>
  <div class="card">
    <h2>Architecture Summary</h2>
    <p id="shared-summary"></p>
  </div>
  <div class="card">
    <h2>Tech Debt</h2>
    <pre id="shared-debt" class="mono"></pre>
  </div>
  <div class="card">
    <h2>Contributors</h2>
    <pre id="shared-contrib" class="mono"></pre>
  </div>
</section>`;

    const shareScripts = `<script>
(function () {
  const token = ${JSON.stringify(shareToken)};
  const loading = document.getElementById('share-loading');
  const errorBox = document.getElementById('share-error');
  const guardBox = document.getElementById('share-guard');
  const content = document.getElementById('share-content');
  function show(el) { el.classList.remove('hidden'); }
  function hide(el) { el.classList.add('hidden'); }
  function setText(id, value) {
    const el = document.getElementById(id);
    el.textContent = value == null || value === '' ? 'N/A' : String(value);
  }
  async function loadShare() {
    if (!token || token.length < 20) {
      hide(loading);
      guardBox.textContent = 'Invalid share token format.';
      show(guardBox);
      return;
    }
    try {
      const response = await fetch('/api/v1/share/' + encodeURIComponent(token));
      const payload = await response.json();
      if (!response.ok) {
        const message = (payload && payload.error && payload.error.message) || payload.detail || 'Unable to resolve share token';
        throw new Error(message);
      }
      const repo = payload.repository || {};
      const analysis = payload.analysis || {};
      setText('shared-name', repo.full_name || repo.name || 'Unknown repository');
      setText('shared-url', repo.github_url || 'N/A');
      setText('shared-meta', 'Default branch: ' + (repo.default_branch || 'main') + ' | Shared until: ' + (payload.expires_at || 'N/A'));
      setText('shared-quality', analysis.quality_score);
      setText('shared-summary', analysis.architecture_summary || 'No summary');
      setText('shared-debt', JSON.stringify(analysis.tech_debt_flags || {}, null, 2));
      setText('shared-contrib', JSON.stringify(analysis.contributor_stats || {}, null, 2));
      hide(loading);
      show(content);
    } catch (error) {
      hide(loading);
      errorBox.textContent = error && error.message ? error.message : 'Failed to load shared report';
      show(errorBox);
    }
  }
  loadShare();
})();
</script>`;

    return layout({
      title: 'DevLens | Shared Report',
      heading: 'Shared Report',
      subtitle: 'Public shared analysis view.',
      route: pathname,
      body: shareBody,
      scripts: shareScripts,
    });
  }

  return null;
}

function proxyToApi(req, res, parsed) {
  const upstream = new URL(config.apiUrl);
  const transport = upstream.protocol === 'https:' ? https : http;
  const path = `${parsed.pathname}${parsed.search || ''}`;

  const headers = { ...req.headers };
  headers.host = upstream.host;

  const proxyReq = transport.request(
    {
      protocol: upstream.protocol,
      hostname: upstream.hostname,
      port: upstream.port || (upstream.protocol === 'https:' ? 443 : 80),
      method: req.method,
      path,
      headers,
    },
    (proxyRes) => {
      res.writeHead(proxyRes.statusCode || 502, proxyRes.headers);
      proxyRes.pipe(res);
    },
  );

  proxyReq.on('error', () => {
    if (!res.headersSent) {
      res.writeHead(502, { 'Content-Type': 'application/json' });
    }
    res.end(JSON.stringify({ error: { code: 'UPSTREAM_UNAVAILABLE', message: 'API proxy failed', details: {} } }));
  });

  req.pipe(proxyReq);
}

const server = http.createServer((req, res) => {
  const parsed = new URL(req.url, 'http://localhost');
  const pathname = parsed.pathname;

  if (pathname.startsWith('/api/')) {
    proxyToApi(req, res, parsed);
    return;
  }

  if (pathname === '/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok', service: 'frontend' }));
    return;
  }

  const html = renderRoute(pathname);
  if (!html) {
    res.writeHead(404, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: { code: 'NOT_FOUND', message: 'Route not found', details: { pathname } } }));
    return;
  }

  res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
  res.end(html);
});

server.listen(port, '0.0.0.0', () => {
  console.log(`Frontend listening on ${port} (${config.env}), API: ${config.apiUrl}`);
});

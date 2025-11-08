async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...opts });
  let data;
  try { data = await res.json(); } catch { data = {}; }
  if (!res.ok) {
    const msg = data && data.error ? data.error : `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return data;
}

let lastSHA = null;
let pollTimer = null;

function $(sel) { return document.querySelector(sel); }

async function refreshStatus() {
  const s = await api('/api/status');

  const repoSpan = $('#repo');
  const pathSpan = $('#path');
  const branchSpan = $('#branch');
  const tokenMask = $('#token-mask');
  const userInput = $('#gh-username');
  const repoInput = $('#repo-input');
  const intervalInput = $('#interval-ms');

  if (repoSpan) repoSpan.textContent = s.repo ?? '';
  if (pathSpan) pathSpan.textContent = s.path ?? '';
  if (branchSpan) branchSpan.textContent = s.branch ?? '';
  if (tokenMask) tokenMask.textContent = s.token_masked ?? '(not set)';
  if (userInput && s.username) userInput.value = s.username;
  if (repoInput && s.repo) repoInput.value = s.repo;
  if (intervalInput && s.interval_ms) intervalInput.value = s.interval_ms;
}

async function loadReadme() {
  try {
    const d = await api('/api/github/readme');
    lastSHA = d.version; // was d.sha
    document.querySelector('#readme-view').textContent = d.content || '';
  } catch (e) {
    document.querySelector('#readme-view').textContent = `(read error) ${e.message}`;
  }
}


async function pollReadme() {
  clearInterval(pollTimer);
  const ms = Number(document.querySelector('#interval-ms').value || 5000);
  pollTimer = setInterval(async () => {
    try {
      const d = await api('/api/github/readme');
      if (d.version && d.version !== lastSHA) {   // was d.sha
        lastSHA = d.version;
        document.querySelector('#readme-view').textContent = d.content || '';
      }
    } catch (_) {}
  }, Math.max(100, ms));
}


async function init() {
  try {
    await refreshStatus();
  } catch (e) {
    const view = $('#readme-view');
    if (view) view.textContent = `(status error) ${e.message}`;
  }

  await loadReadme();
  pollReadme();

  const saveCredsBtn = $('#save-creds');
  if (saveCredsBtn) {
    saveCredsBtn.addEventListener('click', async () => {
      const username = $('#gh-username')?.value?.trim() || '';
      const token = $('#gh-token')?.value?.trim() || '';
      try {
        await api('/api/github/set', { method: 'POST', body: JSON.stringify({ username, token }) });
        const tokenBox = $('#gh-token');
        if (tokenBox) tokenBox.value = '';
        await refreshStatus();
        await loadReadme();
      } catch (e) {
        const view = $('#readme-view');
        if (view) view.textContent = `(save creds error) ${e.message}`;
      }
    });
  }

  const repoSaveBtn = $('#repo-save');
  if (repoSaveBtn) {
    repoSaveBtn.addEventListener('click', async () => {
      const repo = $('#repo-input')?.value?.trim() || '';
      const status = $('#repo-status');
      if (status) status.textContent = 'Saving...';
      try {
        await api('/api/github/set', { method: 'POST', body: JSON.stringify({ repo }) });
        if (status) status.textContent = 'Saved';
        await refreshStatus();
        setTimeout(() => { if (status) status.textContent = ''; }, 1200);
        await loadReadme();
      } catch (e) {
        if (status) status.textContent = `Error: ${e.message}`;
      }
    });
  }

  const updateBtn = $('#update-readme');
  if (updateBtn) {
    updateBtn.addEventListener('click', async () => {
      const content = $('#readme-input')?.value ?? '';
      const status = $('#update-status');
      if (status) status.textContent = 'Updating...';
      try {
        const resp = await api('/api/github/update', { method: 'POST', body: JSON.stringify({ content }) });
        if (resp.content) {
          const view = $('#readme-view');
          if (view) view.textContent = resp.content;
        }
        if (status) status.textContent = 'Updated';
        setTimeout(() => { if (status) status.textContent = ''; }, 1000);
      } catch (e) {
        if (status) status.textContent = `Error: ${e.message}`;
      }
    });
  }

  const saveIntervalBtn = $('#save-interval');
  if (saveIntervalBtn) {
    saveIntervalBtn.addEventListener('click', async () => {
      const ms = Number($('#interval-ms')?.value || 5000);
      const badge = $('#interval-status');
      if (badge) badge.textContent = 'Saving...';
      try {
        await api('/api/interval', { method: 'POST', body: JSON.stringify({ interval_ms: ms }) });
        if (badge) badge.textContent = 'Saved';
        pollReadme(); // restart polling with new interval
        setTimeout(() => { if (badge) badge.textContent = ''; }, 1000);
      } catch (e) {
        if (badge) badge.textContent = `Error: ${e.message}`;
      }
    });
  }

  const craftBtn = $('#craft-linux');
  const craftOut = $('#craft-output');
  const copyBtn = $('#copy-craft');

  if (craftBtn) {
    craftBtn.addEventListener('click', async () => {
      if (craftOut) craftOut.textContent = 'Generating...';
      if (copyBtn) copyBtn.disabled = true;
      try {
        const d = await api('/api/payload/craft/linux', { method: 'POST', body: JSON.stringify({}) });
        if (craftOut) craftOut.textContent = d.command || '';
        if (copyBtn) copyBtn.disabled = !d.command;
      } catch (e) {
        if (craftOut) craftOut.textContent = `Error: ${e.message}`;
      }
    });
  }

  // Check GitHub API rate limit
  document.querySelector('#check-rate').addEventListener('click', async () => {
    const info = document.querySelector('#rate-info');
    const status = document.querySelector('#rate-status');
    status.textContent = 'Checking...';
    try {
      const d = await api('/api/github/rate_limit');
      info.textContent = `Remaining: ${d.remaining || '?'} / ${d.limit || '?'} — resets at ${d.resets_at}`;
      status.textContent = '';
    } catch (e) {
      status.textContent = `Error: ${e.message}`;
    }
  });


  if (copyBtn) {
    copyBtn.addEventListener('click', async () => {
      const txt = craftOut?.textContent || '';
      if (!txt) return;
      try {
        await navigator.clipboard.writeText(txt);
        copyBtn.textContent = 'Copied';
        setTimeout(() => { copyBtn.textContent = 'Copy'; }, 800);
      } catch {
        // ignore
      }
    });
  }
}

window.addEventListener('DOMContentLoaded', init);

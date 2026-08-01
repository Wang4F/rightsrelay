const $ = (selector) => document.querySelector(selector);
let state = { voices: [], campaigns: [] };

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
}

function toast(message, error = false) {
  const el = $('#toast');
  el.textContent = message;
  el.className = error ? 'show error' : 'show';
  clearTimeout(window.__toastTimer);
  window.__toastTimer = setTimeout(() => el.className = '', 3800);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {'Content-Type': 'application/json', ...(options.headers || {})},
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
  return body;
}

async function loadState() {
  state = await api('/api/state');
  render();
}

function render() {
  $('#b2-badge').innerHTML = state.b2_configured
    ? '<i class="dot green"></i> Backblaze B2 connected'
    : '<i class="dot"></i> Local storage demo';

  const active = state.voices.filter(v => v.status === 'active');
  $('#voice').innerHTML = active.map(v => `<option value="${escapeHtml(v.id)}">${escapeHtml(v.label)} · profile ${v.speaker_id}</option>`).join('');
  $('#voice-cards').innerHTML = state.voices.map(voice => {
    const other = state.voices.find(v => v.id !== voice.id && v.status === 'active');
    const action = voice.status === 'active'
      ? `<button class="danger" data-action="revoke" data-id="${voice.id}" data-replacement="${other?.id || ''}" ${other ? '' : 'disabled'}>Revoke & relay</button>`
      : `<button class="ghost" data-action="restore" data-id="${voice.id}">Restore profile</button>`;
    return `<div class="voice-card">
      <div class="voice-top"><div><div class="voice-name">${escapeHtml(voice.label)}</div><div class="voice-id">speaker ${voice.speaker_id} · libritts_r-medium</div></div><div class="status ${voice.status}">${voice.status}</div></div>
      ${voice.replacement_id ? `<p class="muted">Replacement: ${escapeHtml(voice.replacement_id)}</p>` : ''}
      <div class="voice-actions">${action}</div>
    </div>`;
  }).join('');

  const campaigns = state.campaigns || [];
  $('#empty-state').style.display = campaigns.length ? 'none' : 'block';
  $('#campaign-count').textContent = `${campaigns.length} campaign${campaigns.length === 1 ? '' : 's'}`;
  $('#revision-count').textContent = `${campaigns.reduce((n,c) => n + c.revision, 0)} revisions`;
  $('#campaign-list').innerHTML = campaigns.map(c => `<article class="campaign">
    <div>
      <h3>${escapeHtml(c.title)}</h3>
      <div class="campaign-meta"><span>voice ${escapeHtml(c.voice_id)}</span><span>revision ${c.revision}</span><span>${escapeHtml(c.status)}</span><span>${new Date(c.updated_at).toLocaleString()}</span></div>
      <div class="hash">manifest ${escapeHtml(c.current_manifest_hash)}</div>
    </div>
    <div class="campaign-actions">
      <audio controls preload="metadata" src="/media/${c.id}"></audio>
      <button class="ghost" data-action="verify" data-id="${c.id}">Verify</button>
      <a class="ghost" href="/proofs/${c.id}" target="_blank">Proof</a>
    </div>
  </article>`).join('');
}

$('#campaign-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = $('#generate-btn');
  button.disabled = true;
  button.querySelector('span').textContent = 'Generating locally…';
  try {
    await api('/api/campaigns', {method: 'POST', body: JSON.stringify({
      title: $('#title').value,
      script: $('#script').value,
      voice_id: $('#voice').value,
      operational_valid_until: $('#valid-until').value || null,
    })});
    toast('Voice derivative generated and registered.');
    await loadState();
  } catch (error) { toast(error.message, true); }
  finally { button.disabled = false; button.querySelector('span').textContent = 'Generate & register'; }
});

document.addEventListener('click', async event => {
  const target = event.target.closest('[data-action]');
  if (!target) return;
  const action = target.dataset.action;
  const id = target.dataset.id;
  target.disabled = true;
  try {
    if (action === 'revoke') {
      const replacement = target.dataset.replacement;
      const result = await api(`/api/voices/${id}/revoke`, {method: 'POST', body: JSON.stringify({replacement_id: replacement})});
      toast(`Relayed ${result.regenerated.length} affected campaign(s) to ${replacement}.`);
      await loadState();
    } else if (action === 'restore') {
      await api(`/api/voices/${id}/restore`, {method: 'POST'});
      toast(`${id} restored for future campaigns.`);
      await loadState();
    } else if (action === 'verify') {
      const result = await api(`/api/campaigns/${id}/verify`);
      toast(result.verified ? `Verified: ${result.actual_audio_sha256.slice(0, 16)}…` : 'Verification failed.', !result.verified);
    }
  } catch (error) { toast(error.message, true); }
  finally { target.disabled = false; }
});

loadState().catch(error => toast(error.message, true));

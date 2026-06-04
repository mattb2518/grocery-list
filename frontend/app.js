const API = '/grocery/api';

const CATEGORIES = [
  { key: 'produce', label: 'Produce',  emoji: '🥦' },
  { key: 'meat',    label: 'Meat',     emoji: '🥩' },
  { key: 'dairy',   label: 'Dairy',    emoji: '🥛' },
  { key: 'frozen',  label: 'Frozen',   emoji: '🧊' },
  { key: 'deli',    label: 'Deli',     emoji: '🧀' },
  { key: 'pantry',  label: 'Pantry',   emoji: '🥫' },
];

let pollTimer = null;
let pickListId = null;

// ── Boot ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  loadList();
  loadArchived();
  startPolling();

  document.getElementById('archive-btn').addEventListener('click', () => showModal());
  document.getElementById('modal-cancel').addEventListener('click', hideModal);
  document.getElementById('modal-confirm').addEventListener('click', confirmArchive);
  document.getElementById('pick-cancel').addEventListener('click', hidePickModal);
  document.getElementById('pick-confirm').addEventListener('click', confirmPickItems);
});

function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(loadList, 30_000);
}

// ── Data loading ──────────────────────────────────────────────────────────────

async function loadList() {
  try {
    const res = await fetch(`${API}/list`);
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    renderActiveList(data);
    document.getElementById('loading').style.display = 'none';
    document.getElementById('active-section').style.display = 'block';
    clearError();
  } catch (e) {
    showError('Could not load grocery list: ' + e.message);
  }
}

async function loadArchived() {
  try {
    const res = await fetch(`${API}/archived`);
    if (!res.ok) return;
    const data = await res.json();
    renderArchived(data);
  } catch {}
}

// ── Rendering ─────────────────────────────────────────────────────────────────

function renderActiveList(data) {
  const byCategory = {};
  for (const item of data.items) {
    (byCategory[item.category] = byCategory[item.category] || []).push(item);
  }

  const container = document.getElementById('categories-container');
  container.innerHTML = '';

  for (const cat of CATEGORIES) {
    const items = byCategory[cat.key] || [];
    const section = document.createElement('div');
    section.className = 'category-section';

    const header = document.createElement('div');
    header.className = 'category-header';
    header.innerHTML = `<span class="emoji">${cat.emoji}</span>${cat.label}`;
    section.appendChild(header);

    if (items.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'empty-state';
      empty.textContent = 'Nothing here yet';
      section.appendChild(empty);
    } else {
      const ul = document.createElement('ul');
      ul.className = 'item-list';
      for (const item of items) {
        ul.appendChild(renderItem(item));
      }
      section.appendChild(ul);
    }

    container.appendChild(section);
  }
}

function renderItem(item) {
  const li = document.createElement('li');
  li.className = 'item-row';
  li.dataset.id = item.id;

  const name = document.createElement('span');
  name.className = 'item-name';
  name.textContent = item.name;

  const meta = document.createElement('span');
  meta.className = 'item-meta';
  meta.textContent = `${item.submitted_by} · ${relativeTime(item.submitted_at)}`;

  const del = document.createElement('button');
  del.className = 'delete-btn';
  del.title = 'Remove';
  del.textContent = '×';
  del.addEventListener('click', () => removeItem(item.id, li));

  li.appendChild(name);
  li.appendChild(meta);
  li.appendChild(del);
  return li;
}

function renderArchived(lists) {
  const section = document.getElementById('archived-section');
  const container = document.getElementById('archived-list');
  container.innerHTML = '';

  if (lists.length === 0) {
    section.style.display = 'none';
    return;
  }

  section.style.display = 'block';

  for (const lst of lists) {
    const card = document.createElement('div');
    card.className = 'archived-card';

    const label = lst.label || formatDate(lst.archived_at);
    const meta = `${lst.item_count} item${lst.item_count !== 1 ? 's' : ''} · archived ${relativeTime(lst.archived_at)}`;

    card.innerHTML = `
      <div class="archived-card-header">
        <span class="archived-card-label">${escHtml(label)}</span>
        <span class="archived-card-meta">${escHtml(meta)}</span>
      </div>
      <div class="archived-card-actions">
        <button class="btn btn-secondary btn-sm" data-restore="${lst.list_id}">Restore full list</button>
        <button class="btn btn-secondary btn-sm" data-pick="${lst.list_id}">Pick items to add</button>
      </div>
    `;

    card.querySelector('[data-restore]').addEventListener('click', () => restoreList(lst.list_id));
    card.querySelector('[data-pick]').addEventListener('click', () => openPickModal(lst.list_id));

    container.appendChild(card);
  }
}

// ── Actions ───────────────────────────────────────────────────────────────────

async function removeItem(id, el) {
  try {
    const res = await fetch(`${API}/item/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error();
    el.remove();
  } catch {
    showError('Could not remove item.');
  }
}

function showModal() {
  document.getElementById('modal-overlay').style.display = 'flex';
}
function hideModal() {
  document.getElementById('modal-overlay').style.display = 'none';
}

async function confirmArchive() {
  hideModal();
  try {
    const res = await fetch(`${API}/archive`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    if (!res.ok) throw new Error();
    await loadList();
    await loadArchived();
  } catch {
    showError('Could not archive list.');
  }
}

async function restoreList(listId) {
  try {
    const res = await fetch(`${API}/restore/${listId}`, { method: 'POST' });
    if (!res.ok) throw new Error();
    await loadList();
  } catch {
    showError('Could not restore list.');
  }
}

async function openPickModal(listId) {
  pickListId = listId;
  const container = document.getElementById('pick-items-list');
  container.innerHTML = '<div style="padding:12px;color:#888">Loading…</div>';
  document.getElementById('pick-modal-overlay').style.display = 'flex';

  try {
    const res = await fetch(`${API}/archived/${listId}`);
    if (!res.ok) throw new Error();
    const data = await res.json();
    container.innerHTML = '';
    for (const item of data.items) {
      const row = document.createElement('label');
      row.className = 'pick-item-row';
      row.innerHTML = `
        <input type="checkbox" value="${item.id}">
        <span class="pick-item-name">${escHtml(item.name)}</span>
        <span class="pick-item-cat">${escHtml(item.category)}</span>
      `;
      container.appendChild(row);
    }
  } catch {
    container.innerHTML = '<div style="padding:12px;color:#c00">Could not load items.</div>';
  }
}

function hidePickModal() {
  document.getElementById('pick-modal-overlay').style.display = 'none';
  pickListId = null;
}

async function confirmPickItems() {
  const checkboxes = document.querySelectorAll('#pick-items-list input[type="checkbox"]:checked');
  const ids = Array.from(checkboxes).map(c => parseInt(c.value));
  if (ids.length === 0) { hidePickModal(); return; }

  try {
    const res = await fetch(`${API}/add-items`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item_ids: ids })
    });
    if (!res.ok) throw new Error();
    hidePickModal();
    await loadList();
  } catch {
    showError('Could not add items.');
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function relativeTime(iso) {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function formatDate(iso) {
  if (!iso) return 'Past list';
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function showError(msg) {
  const el = document.getElementById('error-banner');
  el.textContent = msg;
  el.style.display = 'block';
}

function clearError() {
  document.getElementById('error-banner').style.display = 'none';
}

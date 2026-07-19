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
let archiveCheckedOnly = false;
let editingItemId = null;

// ── Boot ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  loadList();
  loadArchived();
  startPolling();

  document.getElementById('add-item-form').addEventListener('submit', addItem);
  document.getElementById('check-mail-btn').addEventListener('click', checkMail);
  document.getElementById('archive-all-btn').addEventListener('click', () => showModal(false));
  document.getElementById('archive-checked-btn').addEventListener('click', () => showModal(true));
  document.getElementById('modal-cancel').addEventListener('click', hideModal);
  document.getElementById('modal-confirm').addEventListener('click', confirmArchive);
  document.getElementById('pick-cancel').addEventListener('click', hidePickModal);
  document.getElementById('pick-confirm').addEventListener('click', confirmPickItems);
});

function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  // Don't refresh mid-edit, or the auto-refresh would wipe the input.
  pollTimer = setInterval(() => { if (!editingItemId) loadList(); }, 30_000);
}

// ── Data loading ──────────────────────────────────────────────────────────────

async function loadList() {
  try {
    const res = await fetch(`${API}/list`);
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    renderActiveList(data);
    renderRecipes(data.recipes || []);
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
  const mainItems = data.items.filter(i => !i.probably_have);
  const pantryItems = data.items.filter(i => i.probably_have);

  // Main category sections
  const byCategory = {};
  for (const item of mainItems) {
    (byCategory[item.category] = byCategory[item.category] || []).push(item);
  }

  const container = document.getElementById('categories-container');
  container.innerHTML = '';

  for (const cat of CATEGORIES) {
    const items = (byCategory[cat.key] || []).sort((a, b) =>
      a.name.localeCompare(b.name, undefined, { sensitivity: 'base' })
    );
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

  // Pantry Check zone
  renderPantryCheck(pantryItems);
}

function renderPantryCheck(items) {
  const container = document.getElementById('pantry-check-container');
  container.innerHTML = '';
  if (items.length === 0) return;

  const details = document.createElement('details');
  details.className = 'pantry-check-zone';

  const summary = document.createElement('summary');
  summary.className = 'pantry-check-toggle';
  summary.innerHTML = '<span class="emoji">🧂</span>Pantry check — probably have <span class="pantry-check-count">' + items.length + '</span>';
  details.appendChild(summary);

  const sorted = [...items].sort((a, b) =>
    a.name.localeCompare(b.name, undefined, { sensitivity: 'base' })
  );

  const ul = document.createElement('ul');
  ul.className = 'item-list';
  for (const item of sorted) {
    ul.appendChild(renderPantryItem(item));
  }
  details.appendChild(ul);
  container.appendChild(details);
}

function renderPantryItem(item) {
  const li = document.createElement('li');
  li.className = 'item-row pantry-item-row';
  li.dataset.id = item.id;

  const name = document.createElement('span');
  name.className = 'item-name pantry-item-name';
  name.textContent = item.name;

  const meta = document.createElement('span');
  meta.className = 'item-meta';
  meta.textContent = item.submitted_by;

  const needBtn = document.createElement('button');
  needBtn.className = 'need-it-btn';
  needBtn.title = 'Need it — move to main list';
  needBtn.textContent = '+ Need it';
  needBtn.addEventListener('click', () => markNeeded(item.id, li));

  const del = document.createElement('button');
  del.className = 'delete-btn';
  del.title = 'Remove';
  del.textContent = '×';
  del.addEventListener('click', () => removeItem(item.id, li));

  li.appendChild(name);
  li.appendChild(meta);
  li.appendChild(needBtn);
  li.appendChild(del);
  return li;
}

function renderItem(item) {
  const li = document.createElement('li');
  li.className = 'item-row' + (item.checked ? ' checked' : '');
  li.dataset.id = item.id;

  const check = document.createElement('input');
  check.type = 'checkbox';
  check.className = 'item-check';
  check.checked = !!item.checked;
  check.addEventListener('change', () => toggleChecked(item.id, check.checked, li));

  const name = document.createElement('span');
  name.className = 'item-name';
  name.textContent = item.name;

  const meta = document.createElement('span');
  meta.className = 'item-meta';
  meta.textContent = `${item.submitted_by} · ${relativeTime(item.submitted_at)}`;

  const edit = document.createElement('button');
  edit.className = 'edit-btn';
  edit.title = 'Edit';
  edit.textContent = '✎';
  edit.addEventListener('click', () => startEdit(item, name));

  const del = document.createElement('button');
  del.className = 'delete-btn';
  del.title = 'Remove';
  del.textContent = '×';
  del.addEventListener('click', () => removeItem(item.id, li));

  li.appendChild(check);
  li.appendChild(name);
  li.appendChild(meta);
  li.appendChild(edit);
  li.appendChild(del);
  return li;
}

function renderRecipes(recipes) {
  const container = document.getElementById('recipes-container');
  container.innerHTML = '';
  if (recipes.length === 0) return;

  const section = document.createElement('div');
  section.className = 'recipes-section';

  const header = document.createElement('div');
  header.className = 'recipes-header';
  header.innerHTML = '<span class="emoji">📋</span>This week\'s recipes';
  section.appendChild(header);

  for (const recipe of recipes) {
    section.appendChild(renderRecipeEntry(recipe));
  }

  container.appendChild(section);
}

function renderRecipeEntry(recipe) {
  const row = document.createElement('div');
  row.className = 'recipe-row';
  row.dataset.id = recipe.id;

  const link = document.createElement('a');
  link.href = recipe.url;
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  link.className = 'recipe-url';
  link.textContent = recipe.url;

  const meta = document.createElement('span');
  meta.className = 'item-meta';
  meta.textContent = recipe.submitter;

  const archiveBtn = document.createElement('button');
  archiveBtn.className = 'btn btn-secondary btn-sm recipe-action-btn';
  archiveBtn.title = 'Archive this recipe';
  archiveBtn.textContent = 'Archive';
  archiveBtn.addEventListener('click', () => archiveRecipe(recipe.id, row));

  const removeBtn = document.createElement('button');
  removeBtn.className = 'delete-btn';
  removeBtn.title = 'Remove';
  removeBtn.textContent = '×';
  removeBtn.addEventListener('click', () => removeRecipe(recipe.id, row));

  row.appendChild(link);
  row.appendChild(meta);
  row.appendChild(archiveBtn);
  row.appendChild(removeBtn);
  return row;
}

function startEdit(item, nameEl) {
  if (editingItemId) return;          // one edit at a time
  editingItemId = item.id;

  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'item-edit-input';
  input.value = item.name;
  nameEl.replaceWith(input);
  const li = input.closest('.item-row');
  input.focus();
  input.select();

  let done = false;

  const saveNameIfChanged = async () => {
    const newName = input.value.trim();
    if (!newName || newName === item.name) return;
    try {
      const res = await fetch(`${API}/item/${item.id}/edit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newName })
      });
      if (!res.ok) throw new Error();
      item.name = newName;
      clearError();
    } catch {
      showError('Could not save edit.');
    }
  };

  // Category chips: tap one to move the item to that section.
  const catBar = document.createElement('div');
  catBar.className = 'item-cat-edit';
  for (const cat of CATEGORIES) {
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'cat-chip' + (cat.key === item.category ? ' active' : '');
    chip.innerHTML = `<span class="emoji">${cat.emoji}</span>${cat.label}`;
    // Act on click but keep the rename input focused so its blur-save
    // doesn't race with (and tear down) the chip before the click lands.
    chip.addEventListener('pointerdown', (e) => e.preventDefault());
    chip.addEventListener('click', () => chooseCategory(cat.key));
    catBar.appendChild(chip);
  }
  li.appendChild(catBar);

  const finish = async (save) => {
    if (done) return;
    done = true;
    editingItemId = null;
    if (save) await saveNameIfChanged();
    catBar.remove();
    nameEl.textContent = item.name;
    input.replaceWith(nameEl);
  };

  const chooseCategory = async (key) => {
    if (done) return;
    if (key === item.category) { finish(true); return; }  // no change
    done = true;
    editingItemId = null;
    await saveNameIfChanged();
    try {
      const res = await fetch(`${API}/item/${item.id}/category`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category: key })
      });
      if (!res.ok) throw new Error();
      clearError();
    } catch {
      showError('Could not move item.');
    }
    await loadList();   // re-render: the item now lives in its new section
  };

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); finish(true); }
    else if (e.key === 'Escape') { e.preventDefault(); finish(false); }
  });
  input.addEventListener('blur', () => finish(true));
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

async function markNeeded(id, el) {
  try {
    const res = await fetch(`${API}/item/${id}/probably-have`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ probably_have: false })
    });
    if (!res.ok) throw new Error();
    clearError();
    await loadList();
  } catch {
    showError('Could not move item to list.');
  }
}

async function removeRecipe(id, el) {
  try {
    const res = await fetch(`${API}/recipe/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error();
    el.remove();
    // Hide section if now empty
    const container = document.getElementById('recipes-container');
    if (!container.querySelector('.recipe-row')) container.innerHTML = '';
  } catch {
    showError('Could not remove recipe.');
  }
}

async function archiveRecipe(id, el) {
  try {
    const res = await fetch(`${API}/recipe/${id}/archive`, { method: 'POST' });
    if (!res.ok) throw new Error();
    el.remove();
    const container = document.getElementById('recipes-container');
    if (!container.querySelector('.recipe-row')) container.innerHTML = '';
  } catch {
    showError('Could not archive recipe.');
  }
}

async function toggleChecked(id, checked, el) {
  el.classList.toggle('checked', checked);
  try {
    const res = await fetch(`${API}/item/${id}/check`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ checked })
    });
    if (!res.ok) throw new Error();
  } catch {
    el.classList.toggle('checked', !checked);
    const box = el.querySelector('.item-check');
    if (box) box.checked = !checked;
    showError('Could not update item.');
  }
}

async function addItem(e) {
  e.preventDefault();
  const input = document.getElementById('add-item-input');
  const name = input.value.trim();
  if (!name) return;
  const btn = e.target.querySelector('button[type="submit"]');
  btn.disabled = true;
  try {
    const res = await fetch(`${API}/add-item`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, submitted_by: 'web' })
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Could not add item.');
    input.value = '';
    clearError();
    await loadList();
  } catch (err) {
    showError(err.message);
  } finally {
    btn.disabled = false;
    input.focus();
  }
}

async function checkMail() {
  const btn = document.getElementById('check-mail-btn');
  const status = document.getElementById('refresh-status');
  btn.disabled = true;
  status.textContent = 'Checking…';
  try {
    const res = await fetch(`${API}/check-mail`, { method: 'POST' });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || 'Could not check mail.');
    }
    const data = await res.json();
    await loadList();
    if (data.items_added > 0) {
      status.textContent = `Added ${data.items_added} item${data.items_added !== 1 ? 's' : ''}`;
    } else {
      status.textContent = 'No new items';
    }
    clearError();
  } catch (e) {
    status.textContent = '';
    showError(e.message);
  } finally {
    btn.disabled = false;
    setTimeout(() => { status.textContent = ''; }, 4000);
  }
}

function showModal(checkedOnly) {
  archiveCheckedOnly = checkedOnly;
  const text = checkedOnly
    ? 'Archive the checked items? They will be saved to a past list and removed from the active list. Unchecked items stay.'
    : 'Archive this list? It will be saved and the active list will be cleared.';
  document.querySelector('#modal-overlay .modal-text').textContent = text;
  document.getElementById('modal-overlay').style.display = 'flex';
}
function hideModal() {
  document.getElementById('modal-overlay').style.display = 'none';
}

async function confirmArchive() {
  hideModal();
  try {
    const res = await fetch(`${API}/archive`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ checked_only: archiveCheckedOnly })
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || 'Could not archive list.');
    }
    await loadList();
    await loadArchived();
    clearError();
  } catch (e) {
    showError(e.message);
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

// Use the origin the page was served from, so this works on any port
// (the extended backend and the SQL version can both run on :8000). Falls back
// to a fixed host when the page is opened directly as a file:// URL.
const API_BASE = window.location.protocol.startsWith("http")
  ? window.location.origin
  : "http://127.0.0.1:8000";

// Fallback options so the dropdowns are never empty, even before any
// permissions exist. Real values are merged in from the roles data.
const DEFAULT_RESOURCES = ["documents", "users", "settings"];
const DEFAULT_ACTIONS = ["read", "write"];

let usersCache = [];
let rolesCache = [];
let messageTimer = null;

// --- Small helpers --------------------------------------------------------

async function api(path, options) {
  const response = await fetch(API_BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    // Extended API returns {"error": {"message": ...}}; fall back to older shapes.
    const message = (body.error && body.error.message) || body.detail;
    throw new Error(message || `Request failed (${response.status})`);
  }
  if (response.status === 204) return null; // DELETE returns no body
  return response.json();
}

// Names are not unique; ids are. Show a short id so duplicates are
// distinguishable in the UI. The backend always operates on the full id.
function shortId(id) {
  return id.slice(0, 8);
}

function roleById(roleId) {
  return rolesCache.find((role) => role.id === roleId);
}

// Build a DOM node without innerHTML, so user-supplied names cannot inject HTML.
function el(tag, opts = {}, children = []) {
  const node = document.createElement(tag);
  if (opts.class) node.className = opts.class;
  if (opts.text != null) node.textContent = opts.text;
  if (opts.type) node.type = opts.type;
  if (opts.value != null) node.value = opts.value;
  if (opts.placeholder) node.placeholder = opts.placeholder;
  if (opts.onClick) node.addEventListener("click", opts.onClick);
  children.forEach((child) => node.appendChild(child));
  return node;
}

function showMessage(text) {
  const box = document.getElementById("app-message");
  box.textContent = text;
  box.hidden = false;
  clearTimeout(messageTimer);
  messageTimer = setTimeout(clearMessage, 5000);
}

function clearMessage() {
  const box = document.getElementById("app-message");
  box.hidden = true;
  box.textContent = "";
}

// Run a mutation, then refresh the whole view so state stays consistent.
async function mutate(action) {
  try {
    clearMessage();
    await action();
    await loadData();
  } catch (error) {
    showMessage(error.message);
  }
}

// --- Data loading ---------------------------------------------------------

async function loadData() {
  [usersCache, rolesCache] = await Promise.all([api("/users"), api("/roles")]);
  renderUsers();
  renderRoles();
  populateCheckerDropdowns();
  populateRoleCheckboxes();
}

// --- Users ----------------------------------------------------------------

function renderUsers() {
  const list = document.getElementById("users-list");
  list.innerHTML = "";
  if (usersCache.length === 0) {
    list.appendChild(el("li", { class: "empty", text: "No users yet." }));
    return;
  }
  usersCache.forEach((user) => list.appendChild(buildUserItem(user)));
}

function buildUserItem(user) {
  const li = el("li", { class: "item" });

  li.appendChild(
    el("div", { class: "item-head" }, [
      el("span", { class: "item-name", text: user.name }),
      el("span", { class: "id-badge", text: "#" + shortId(user.id) }),
      el("button", { class: "danger small", text: "Delete", onClick: () => onDeleteUser(user) }),
    ])
  );

  const chips = el("div", { class: "chips" });
  if (user.role_ids.length === 0) {
    chips.appendChild(el("span", { class: "empty", text: "no roles" }));
  } else {
    user.role_ids.forEach((roleId) => {
      const role = roleById(roleId);
      const label = role ? role.name : shortId(roleId);
      chips.appendChild(buildChip(label, () => onRemoveRole(user, roleId)));
    });
  }
  li.appendChild(chips);

  // Offer only roles the user does not already have.
  const available = rolesCache.filter((role) => !user.role_ids.includes(role.id));
  if (available.length > 0) {
    const select = el("select");
    available.forEach((role) =>
      select.appendChild(el("option", { value: role.id, text: `${role.name} (#${shortId(role.id)})` }))
    );
    const addButton = el("button", {
      class: "small",
      text: "Add role",
      onClick: () => onAssignRole(user, select.value),
    });
    li.appendChild(el("div", { class: "inline-add" }, [select, addButton]));
  }

  return li;
}

function onAssignRole(user, roleId) {
  if (!roleId) return;
  mutate(() =>
    api(`/users/${user.id}/roles`, { method: "POST", body: JSON.stringify({ role_id: roleId }) })
  );
}

function onRemoveRole(user, roleId) {
  mutate(() => api(`/users/${user.id}/roles/${roleId}`, { method: "DELETE" }));
}

function onDeleteUser(user) {
  if (!confirm(`Delete user "${user.name}" (#${shortId(user.id)})?`)) return;
  mutate(() => api(`/users/${user.id}`, { method: "DELETE" }));
}

// --- Roles ----------------------------------------------------------------

function renderRoles() {
  const list = document.getElementById("roles-list");
  list.innerHTML = "";
  if (rolesCache.length === 0) {
    list.appendChild(el("li", { class: "empty", text: "No roles yet." }));
    return;
  }
  rolesCache.forEach((role) => list.appendChild(buildRoleItem(role)));
}

function buildRoleItem(role) {
  const li = el("li", { class: "item" });

  li.appendChild(
    el("div", { class: "item-head" }, [
      el("span", { class: "item-name", text: role.name }),
      el("span", { class: "id-badge", text: "#" + shortId(role.id) }),
      el("button", { class: "danger small", text: "Delete", onClick: () => onDeleteRole(role) }),
    ])
  );

  const chips = el("div", { class: "chips" });
  if (role.permissions.length === 0) {
    chips.appendChild(el("span", { class: "empty", text: "no permissions" }));
  } else {
    role.permissions.forEach((permission) => {
      const label = `${permission.resource}:${permission.action}`;
      chips.appendChild(buildChip(label, () => onRemovePermission(role, permission)));
    });
  }
  li.appendChild(chips);

  const resourceInput = el("input", { type: "text", placeholder: "resource" });
  const actionSelect = el("select");
  DEFAULT_ACTIONS.forEach((action) =>
    actionSelect.appendChild(el("option", { value: action, text: action }))
  );
  const addButton = el("button", {
    class: "small",
    text: "Add",
    onClick: () => onAddPermission(role, resourceInput.value.trim(), actionSelect.value),
  });
  li.appendChild(el("div", { class: "inline-add" }, [resourceInput, actionSelect, addButton]));

  return li;
}

function onAddPermission(role, resource, action) {
  if (!resource) {
    showMessage("Enter a resource name before adding a permission.");
    return;
  }
  mutate(() =>
    api(`/roles/${role.id}/permissions`, { method: "POST", body: JSON.stringify({ resource, action }) })
  );
}

function onRemovePermission(role, permission) {
  mutate(() =>
    api(`/roles/${role.id}/permissions`, {
      method: "DELETE",
      body: JSON.stringify({ resource: permission.resource, action: permission.action }),
    })
  );
}

function onDeleteRole(role) {
  if (!confirm(`Delete role "${role.name}" (#${shortId(role.id)})? It will be removed from all users.`)) {
    return;
  }
  mutate(() => api(`/roles/${role.id}`, { method: "DELETE" }));
}

// --- Shared widgets -------------------------------------------------------

function buildChip(label, onRemove) {
  const chip = el("span", { class: "chip", text: label });
  chip.appendChild(el("button", { type: "button", text: "×", onClick: onRemove }));
  return chip;
}

function uniqueSorted(values) {
  return [...new Set(values)].sort();
}

function fillSelect(id, values) {
  const select = document.getElementById(id);
  select.innerHTML = "";
  values.forEach((value) => select.appendChild(el("option", { value, text: value })));
}

function populateCheckerDropdowns() {
  const userSelect = document.getElementById("check-user");
  userSelect.innerHTML = "";
  usersCache.forEach((user) =>
    // Label includes the short id so two users named the same are distinguishable.
    userSelect.appendChild(el("option", { value: user.id, text: `${user.name} (#${shortId(user.id)})` }))
  );

  const allPermissions = rolesCache.flatMap((role) => role.permissions);
  const resources = uniqueSorted([...allPermissions.map((p) => p.resource), ...DEFAULT_RESOURCES]);
  const actions = uniqueSorted([...allPermissions.map((p) => p.action), ...DEFAULT_ACTIONS]);
  fillSelect("check-resource", resources);
  fillSelect("check-action", actions);
}

function populateRoleCheckboxes() {
  const container = document.getElementById("role-checkboxes");
  container.innerHTML = "";
  if (rolesCache.length === 0) {
    container.appendChild(el("span", { class: "empty", text: "No roles yet." }));
    return;
  }
  rolesCache.forEach((role) => {
    const checkbox = el("input", { type: "checkbox", value: role.id });
    const label = el("label", { class: "checkbox" }, [checkbox]);
    label.appendChild(document.createTextNode(` ${role.name} (#${shortId(role.id)})`));
    container.appendChild(label);
  });
}

// --- Permission checker ---------------------------------------------------

async function onCheckPermission() {
  const userId = document.getElementById("check-user").value;
  const resource = document.getElementById("check-resource").value;
  const action = document.getElementById("check-action").value;
  const result = document.getElementById("check-result");

  if (!userId) {
    result.textContent = "Create a user first.";
    result.className = "result denied";
    return;
  }

  try {
    const data = await api("/check-permission", {
      method: "POST",
      body: JSON.stringify({ user_id: userId, resource, action }),
    });
    result.textContent = data.allowed ? "Allowed ✅" : "Denied ❌";
    result.className = "result " + (data.allowed ? "allowed" : "denied");
  } catch (error) {
    result.textContent = error.message;
    result.className = "result denied";
  }
}

// --- Create forms ---------------------------------------------------------

async function onCreateUser(event) {
  event.preventDefault();
  const name = document.getElementById("new-user-name").value.trim();
  const roleIds = [...document.querySelectorAll("#role-checkboxes input:checked")].map((c) => c.value);
  if (!name) return;
  await mutate(() => api("/users", { method: "POST", body: JSON.stringify({ name, role_ids: roleIds }) }));
  document.getElementById("create-user-form").reset();
}

async function onCreateRole(event) {
  event.preventDefault();
  const name = document.getElementById("new-role-name").value.trim();
  const resource = document.getElementById("new-role-resource").value.trim();
  const action = document.getElementById("new-role-action").value;
  if (!name) return;
  const permissions = resource ? [{ resource, action }] : [];
  await mutate(() => api("/roles", { method: "POST", body: JSON.stringify({ name, permissions }) }));
  document.getElementById("create-role-form").reset();
}

// --- Wire up --------------------------------------------------------------

document.getElementById("check-btn").addEventListener("click", onCheckPermission);
document.getElementById("create-user-form").addEventListener("submit", onCreateUser);
document.getElementById("create-role-form").addEventListener("submit", onCreateRole);

loadData().catch((error) => {
  const result = document.getElementById("check-result");
  result.textContent = "Could not reach the API. Start the backend and reload. (" + error.message + ")";
  result.className = "result denied";
});

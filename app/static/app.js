const storageKeys = {
  apiKey: "mem0-console-api-key",
};

const elements = {
  apiKey: document.getElementById("api-key"),
  saveKeyButton: document.getElementById("save-key-button"),
  clearKeyButton: document.getElementById("clear-key-button"),
  healthButton: document.getElementById("health-button"),
  healthPill: document.getElementById("health-pill"),
  resultViewer: document.getElementById("result-viewer"),
  resultLabel: document.getElementById("result-label"),
  memoryList: document.getElementById("memory-list"),
  memoryEmpty: document.getElementById("memory-empty"),
  memoryCount: document.getElementById("memory-count"),
  scopeUserId: document.getElementById("scope-user-id"),
  scopeAgentId: document.getElementById("scope-agent-id"),
  scopeRunId: document.getElementById("scope-run-id"),
  loadMemoriesButton: document.getElementById("load-memories-button"),
  deleteAllButton: document.getElementById("delete-all-button"),
  messagesBuilder: document.getElementById("messages-builder"),
  addMessageButton: document.getElementById("add-message-button"),
  createUserId: document.getElementById("create-user-id"),
  createAgentId: document.getElementById("create-agent-id"),
  createRunId: document.getElementById("create-run-id"),
  createMemoryType: document.getElementById("create-memory-type"),
  createInfer: document.getElementById("create-infer"),
  createPrompt: document.getElementById("create-prompt"),
  createMetadata: document.getElementById("create-metadata"),
  createMemoryButton: document.getElementById("create-memory-button"),
  searchQuery: document.getElementById("search-query"),
  searchUserId: document.getElementById("search-user-id"),
  searchAgentId: document.getElementById("search-agent-id"),
  searchRunId: document.getElementById("search-run-id"),
  searchLimit: document.getElementById("search-limit"),
  searchThreshold: document.getElementById("search-threshold"),
  searchFilters: document.getElementById("search-filters"),
  searchButton: document.getElementById("search-button"),
  selectedMemoryId: document.getElementById("selected-memory-id"),
  fetchMemoryButton: document.getElementById("fetch-memory-button"),
  historyButton: document.getElementById("history-button"),
  selectedMemoryText: document.getElementById("selected-memory-text"),
  selectedMemoryMetadata: document.getElementById("selected-memory-metadata"),
  updateMemoryButton: document.getElementById("update-memory-button"),
  deleteMemoryButton: document.getElementById("delete-memory-button"),
  configJson: document.getElementById("config-json"),
  configureButton: document.getElementById("configure-button"),
  resetButton: document.getElementById("reset-button"),
};

const state = {
  memories: [],
};

function initialize() {
  const storedKey = window.localStorage.getItem(storageKeys.apiKey);
  if (storedKey) {
    elements.apiKey.value = storedKey;
  }

  addMessageRow({ role: "user", content: "Mi usuario se llama Alex y trabaja en ventas." });
  addMessageRow({ role: "assistant", content: "Queda registrado para futuras consultas." });

  elements.saveKeyButton.addEventListener("click", saveApiKey);
  elements.clearKeyButton.addEventListener("click", clearApiKey);
  elements.healthButton.addEventListener("click", checkHealth);
  elements.addMessageButton.addEventListener("click", () => addMessageRow());
  elements.createMemoryButton.addEventListener("click", createMemory);
  elements.loadMemoriesButton.addEventListener("click", loadMemories);
  elements.searchButton.addEventListener("click", searchMemories);
  elements.fetchMemoryButton.addEventListener("click", fetchMemoryById);
  elements.historyButton.addEventListener("click", fetchMemoryHistory);
  elements.updateMemoryButton.addEventListener("click", updateMemory);
  elements.deleteMemoryButton.addEventListener("click", deleteSelectedMemory);
  elements.deleteAllButton.addEventListener("click", deleteAllByScope);
  elements.configureButton.addEventListener("click", configureMemory);
  elements.resetButton.addEventListener("click", resetMemoryStore);

  checkHealth();
}

function getApiKey() {
  return elements.apiKey.value.trim();
}

function saveApiKey() {
  const value = getApiKey();
  if (!value) {
    window.localStorage.removeItem(storageKeys.apiKey);
    setResult("Sesion API", { message: "No habia clave para guardar" });
    return;
  }

  window.localStorage.setItem(storageKeys.apiKey, value);
  setResult("Sesion API", { message: "Clave guardada en localStorage" });
}

function clearApiKey() {
  elements.apiKey.value = "";
  window.localStorage.removeItem(storageKeys.apiKey);
  setResult("Sesion API", { message: "Clave eliminada" });
}

async function apiRequest(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const apiKey = getApiKey();
  if (apiKey) {
    headers.set("X-API-Key", apiKey);
  }
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(path, {
    ...options,
    headers,
  });

  const rawText = await response.text();
  const payload = parseResponseBody(rawText);

  if (!response.ok) {
    const detail = payload?.detail || payload || response.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail, null, 2));
  }

  return payload;
}

function parseResponseBody(rawText) {
  if (!rawText) {
    return null;
  }

  try {
    return JSON.parse(rawText);
  } catch {
    return rawText;
  }
}

function setResult(label, payload) {
  elements.resultLabel.textContent = label;
  elements.resultViewer.textContent = typeof payload === "string" ? payload : JSON.stringify(payload, null, 2);
}

function setHealth(ok, label) {
  elements.healthPill.textContent = label;
  elements.healthPill.classList.toggle("is-ok", ok);
  elements.healthPill.classList.toggle("is-error", !ok);
}

async function checkHealth() {
  try {
    const payload = await apiRequest("/healthz");
    setHealth(true, payload?.status === "ok" ? "API saludable" : "Respuesta recibida");
    setResult("Healthz", payload);
  } catch (error) {
    setHealth(false, "Error de conexion");
    setResult("Healthz", { error: error.message });
  }
}

function addMessageRow(initialValue = {}) {
  const row = document.createElement("div");
  row.className = "message-row";
  row.innerHTML = `
    <div class="message-row-head">
      <strong>Mensaje</strong>
      <button type="button" class="secondary remove-message-button">Eliminar</button>
    </div>
    <label>
      <span>role</span>
      <select class="message-role">
        <option value="user">user</option>
        <option value="assistant">assistant</option>
        <option value="system">system</option>
      </select>
    </label>
    <label>
      <span>content</span>
      <textarea class="message-content" rows="4" placeholder="Contenido del mensaje"></textarea>
    </label>
  `;

  row.querySelector(".message-role").value = initialValue.role || "user";
  row.querySelector(".message-content").value = initialValue.content || "";
  row.querySelector(".remove-message-button").addEventListener("click", () => {
    row.remove();
  });
  elements.messagesBuilder.appendChild(row);
}

function buildScopeFromInputs(prefix) {
  const scope = {
    user_id: elements[`${prefix}UserId`]?.value.trim() || undefined,
    agent_id: elements[`${prefix}AgentId`]?.value.trim() || undefined,
    run_id: elements[`${prefix}RunId`]?.value.trim() || undefined,
  };

  return Object.fromEntries(Object.entries(scope).filter(([, value]) => Boolean(value)));
}

function buildGlobalScope() {
  return {
    user_id: elements.scopeUserId.value.trim() || undefined,
    agent_id: elements.scopeAgentId.value.trim() || undefined,
    run_id: elements.scopeRunId.value.trim() || undefined,
  };
}

function parseJsonField(value, fieldName) {
  const trimmed = value.trim();
  if (!trimmed) {
    return undefined;
  }

  try {
    return JSON.parse(trimmed);
  } catch {
    throw new Error(`JSON invalido en ${fieldName}`);
  }
}

function buildCreatePayload() {
  const messages = Array.from(elements.messagesBuilder.querySelectorAll(".message-row"))
    .map((row) => ({
      role: row.querySelector(".message-role").value,
      content: row.querySelector(".message-content").value.trim(),
    }))
    .filter((message) => message.content);

  if (!messages.length) {
    throw new Error("Agrega al menos un mensaje con contenido");
  }

  const inferValue = elements.createInfer.value;
  return {
    messages,
    ...buildScopeFromInputs("create"),
    memory_type: elements.createMemoryType.value.trim() || undefined,
    prompt: elements.createPrompt.value.trim() || undefined,
    metadata: parseJsonField(elements.createMetadata.value, "metadata JSON"),
    infer: inferValue === "" ? undefined : inferValue === "true",
  };
}

async function createMemory() {
  try {
    const payload = buildCreatePayload();
    const response = await apiRequest("/memories", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setResult("Crear memoria", response);
    syncCreateScopeIntoGlobal(payload);
    await loadMemories();
  } catch (error) {
    setResult("Crear memoria", { error: error.message });
  }
}

function syncCreateScopeIntoGlobal(payload) {
  if (payload.user_id) {
    elements.scopeUserId.value = payload.user_id;
  }
  if (payload.agent_id) {
    elements.scopeAgentId.value = payload.agent_id;
  }
  if (payload.run_id) {
    elements.scopeRunId.value = payload.run_id;
  }
}

function queryStringFromObject(input) {
  const params = new URLSearchParams();
  Object.entries(input).forEach(([key, value]) => {
    if (value !== undefined && value !== "") {
      params.set(key, value);
    }
  });
  const output = params.toString();
  return output ? `?${output}` : "";
}

async function loadMemories() {
  const scope = Object.fromEntries(Object.entries(buildGlobalScope()).filter(([, value]) => Boolean(value)));
  if (!Object.keys(scope).length) {
    setResult("Cargar memorias", { error: "Define user_id, agent_id o run_id" });
    return;
  }

  try {
    const payload = await apiRequest(`/memories${queryStringFromObject(scope)}`);
    state.memories = normalizeMemoryArray(payload);
    renderMemoryList(state.memories);
    setResult("Cargar memorias", payload);
  } catch (error) {
    renderMemoryList([]);
    setResult("Cargar memorias", { error: error.message });
  }
}

function normalizeMemoryArray(payload) {
  if (Array.isArray(payload)) {
    return payload;
  }
  if (Array.isArray(payload?.results)) {
    return payload.results;
  }
  if (Array.isArray(payload?.memories)) {
    return payload.memories;
  }
  return [];
}

function renderMemoryList(memories) {
  elements.memoryList.innerHTML = "";
  elements.memoryCount.textContent = `${memories.length} resultados`;
  elements.memoryEmpty.hidden = memories.length > 0;

  memories.forEach((memory, index) => {
    const card = document.createElement("article");
    card.className = "memory-card";
    const memoryId = getMemoryId(memory) || `memoria-${index + 1}`;
    card.innerHTML = `
      <div class="memory-card-head">
        <div>
          <p class="memory-title">${escapeHtml(memoryId)}</p>
          <div class="tag-row">${renderTags(memory)}</div>
        </div>
        <span class="tag">score ${escapeHtml(formatScore(memory.score))}</span>
      </div>
      <p class="memory-body">${escapeHtml(getMemoryText(memory))}</p>
      <div class="card-actions">
        <button type="button" class="secondary" data-action="load">Editar</button>
        <button type="button" class="secondary" data-action="history">Historial</button>
        <button type="button" class="danger" data-action="delete">Eliminar</button>
      </div>
    `;
    card.addEventListener("click", async (event) => {
      const action = event.target?.dataset?.action;
      if (!action) {
        return;
      }
      if (action === "load") {
        hydrateEditor(memory);
        await fetchMemoryById();
      }
      if (action === "history") {
        elements.selectedMemoryId.value = memoryId;
        await fetchMemoryHistory();
      }
      if (action === "delete") {
        elements.selectedMemoryId.value = memoryId;
        await deleteSelectedMemory();
      }
    });
    elements.memoryList.appendChild(card);
  });
}

function renderTags(memory) {
  const tags = [];
  if (memory.user_id) {
    tags.push(`user ${memory.user_id}`);
  }
  if (memory.agent_id) {
    tags.push(`agent ${memory.agent_id}`);
  }
  if (memory.run_id) {
    tags.push(`run ${memory.run_id}`);
  }
  if (memory.created_at) {
    tags.push(`created ${memory.created_at}`);
  }
  if (Array.isArray(memory.categories)) {
    memory.categories.forEach((category) => tags.push(`category ${category}`));
  }
  return tags.map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("");
}

function formatScore(score) {
  if (score === undefined || score === null || Number.isNaN(Number(score))) {
    return "n/a";
  }
  return Number(score).toFixed(3);
}

function getMemoryId(memory) {
  return memory?.id || memory?.memory_id || memory?.uuid || "";
}

function getMemoryText(memory) {
  return memory?.memory || memory?.text || memory?.data || memory?.content || "Sin texto disponible";
}

function hydrateEditor(memory) {
  elements.selectedMemoryId.value = getMemoryId(memory);
  elements.selectedMemoryText.value = getMemoryText(memory);
  elements.selectedMemoryMetadata.value = memory?.metadata ? JSON.stringify(memory.metadata, null, 2) : "";
}

async function fetchMemoryById() {
  const memoryId = elements.selectedMemoryId.value.trim();
  if (!memoryId) {
    setResult("Detalle memoria", { error: "Especifica memory_id" });
    return;
  }

  try {
    const payload = await apiRequest(`/memories/${encodeURIComponent(memoryId)}`);
    if (payload && typeof payload === "object") {
      hydrateEditor(payload);
    }
    setResult("Detalle memoria", payload);
  } catch (error) {
    setResult("Detalle memoria", { error: error.message });
  }
}

async function fetchMemoryHistory() {
  const memoryId = elements.selectedMemoryId.value.trim();
  if (!memoryId) {
    setResult("Historial memoria", { error: "Especifica memory_id" });
    return;
  }

  try {
    const payload = await apiRequest(`/memories/${encodeURIComponent(memoryId)}/history`);
    setResult("Historial memoria", payload);
  } catch (error) {
    setResult("Historial memoria", { error: error.message });
  }
}

async function updateMemory() {
  const memoryId = elements.selectedMemoryId.value.trim();
  if (!memoryId) {
    setResult("Actualizar memoria", { error: "Especifica memory_id" });
    return;
  }

  try {
    const payload = {
      text: elements.selectedMemoryText.value.trim(),
      metadata: parseJsonField(elements.selectedMemoryMetadata.value, "metadata JSON"),
    };
    const response = await apiRequest(`/memories/${encodeURIComponent(memoryId)}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    setResult("Actualizar memoria", response);
    await loadMemories();
  } catch (error) {
    setResult("Actualizar memoria", { error: error.message });
  }
}

async function deleteSelectedMemory() {
  const memoryId = elements.selectedMemoryId.value.trim();
  if (!memoryId) {
    setResult("Eliminar memoria", { error: "Especifica memory_id" });
    return;
  }

  if (!window.confirm(`Eliminar la memoria ${memoryId}?`)) {
    return;
  }

  try {
    const payload = await apiRequest(`/memories/${encodeURIComponent(memoryId)}`, {
      method: "DELETE",
    });
    setResult("Eliminar memoria", payload);
    elements.selectedMemoryText.value = "";
    elements.selectedMemoryMetadata.value = "";
    await loadMemories();
  } catch (error) {
    setResult("Eliminar memoria", { error: error.message });
  }
}

async function deleteAllByScope() {
  const scope = Object.fromEntries(Object.entries(buildGlobalScope()).filter(([, value]) => Boolean(value)));
  if (!Object.keys(scope).length) {
    setResult("Eliminar por alcance", { error: "Define user_id, agent_id o run_id" });
    return;
  }

  if (!window.confirm("Eliminar todas las memorias del alcance actual?")) {
    return;
  }

  try {
    const payload = await apiRequest(`/memories${queryStringFromObject(scope)}`, {
      method: "DELETE",
    });
    state.memories = [];
    renderMemoryList([]);
    setResult("Eliminar por alcance", payload);
  } catch (error) {
    setResult("Eliminar por alcance", { error: error.message });
  }
}

async function searchMemories() {
  try {
    const payload = {
      query: elements.searchQuery.value.trim(),
      ...buildScopeFromInputs("search"),
      top_k: elements.searchLimit.value ? Number(elements.searchLimit.value) : undefined,
      threshold: elements.searchThreshold.value ? Number(elements.searchThreshold.value) : undefined,
      filters: parseJsonField(elements.searchFilters.value, "filters JSON"),
    };

    if (!payload.query) {
      throw new Error("La busqueda requiere query");
    }

    const response = await apiRequest("/search", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const results = normalizeMemoryArray(response);
    if (results.length) {
      renderMemoryList(results);
    }
    setResult("Buscar memorias", response);
  } catch (error) {
    setResult("Buscar memorias", { error: error.message });
  }
}

async function configureMemory() {
  try {
    const payload = parseJsonField(elements.configJson.value, "config JSON");
    if (!payload) {
      throw new Error("Ingresa un JSON de configuracion");
    }

    const response = await apiRequest("/configure", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setResult("Configurar Mem0", response);
  } catch (error) {
    setResult("Configurar Mem0", { error: error.message });
  }
}

async function resetMemoryStore() {
  if (!window.confirm("Resetear todo el store de memorias?")) {
    return;
  }

  try {
    const payload = await apiRequest("/reset", { method: "POST" });
    state.memories = [];
    renderMemoryList([]);
    setResult("Reset total", payload);
  } catch (error) {
    setResult("Reset total", { error: error.message });
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

initialize();
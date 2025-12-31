// backend/app/static/app.js

// ===== Elements =====
const chatList = document.getElementById("chatList");
const inputEl = document.getElementById("messageInput");
const clearBtn = document.getElementById("clearBtn");
const kbStatus = document.getElementById("kbStatus");
const mainSendBtn = document.getElementById("mainSendBtn");

// Unified Mode/Model Selection
const mainModeSelect = document.getElementById("mainModeSelect");

const tabChat = document.getElementById("tabChat");
const tabDev = document.getElementById("tabDev");
const tabSettings = document.getElementById("tabSettings");

const viewChat = document.getElementById("viewChat");
const viewDev = document.getElementById("viewDev");
const viewSettings = document.getElementById("viewSettings");
const settingsPanels = document.getElementById("settingsPanels");
const settingsLockMsg = document.getElementById("settingsLockMsg");

const cfgOpenAI = document.getElementById("cfgOpenAI");

const cfgPrompt = document.getElementById("cfgPrompt");
const cfgKeywords = document.getElementById("cfgKeywords");
const saveConfigBtn = document.getElementById("saveConfigBtn");

const adminCodeInput = document.getElementById("adminCodeInput");
const adminUnlockBtn = document.getElementById("adminUnlockBtn");
const adminState = document.getElementById("adminState");
const devPanels = document.getElementById("devPanels");

const reindexBtn = document.getElementById("reindexBtn");
const refreshIndexBtn = document.getElementById("refreshIndexBtn");
const indexStatusBox = document.getElementById("indexStatusBox");

const reembedBtn = document.getElementById("reembedBtn");
const refreshEmbedBtn = document.getElementById("refreshEmbedBtn");
const embedStatusBox = document.getElementById("embedStatusBox");

const indexProg = document.getElementById("indexProg");
const embedProg = document.getElementById("embedProg");
const indexKpis = document.getElementById("indexKpis");
const embedKpis = document.getElementById("embedKpis");

// Ad-Hoc File Elements
const adhocFileInput = document.getElementById("adhocFileInput");
const attachFileBtn = document.getElementById("attachFileBtn");
const attachedFileName = document.getElementById("attachedFileName");
const removeFileBtn = document.getElementById("removeFileBtn");
const filePreviewArea = document.getElementById("filePreviewArea");
let currentAdhocFileObj = null; // Store File object here

// Local storage
const LS_KEY = "smartagent_history_v1";
let adminCode = sessionStorage.getItem("admin_code") || "";

// ===== Helpers =====
function loadHistory() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    const arr = raw ? JSON.parse(raw) : [];
    return Array.isArray(arr) ? arr : [];
  } catch { return []; }
}
function saveHistory(hist) {
  localStorage.setItem(LS_KEY, JSON.stringify(hist));
}

let history = loadHistory();

function autoGrow() {
  if (!inputEl) return;
  inputEl.style.height = "auto";
  inputEl.style.height = Math.min(inputEl.scrollHeight, 160) + "px";
}
if (inputEl) inputEl.addEventListener("input", autoGrow);

function pretty(obj) {
  try { return JSON.stringify(obj, null, 2); } catch { return String(obj); }
}

function formatTime(ts) {
  try {
    return new Date(ts).toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit" });
  } catch { return ""; }
}

function scrollToBottom() {
  if (chatList) chatList.scrollTop = chatList.scrollHeight;
}

// Function to create the nice Accordion for sources
function renderSourcesAccordion(sources) {
  if (!sources || !sources.length) return null;

  const details = document.createElement("details");
  details.className = "sources-details";

  const summary = document.createElement("summary");
  summary.textContent = `נמצאו ${sources.length} מקורות רלוונטיים`;
  details.appendChild(summary);

  const list = document.createElement("ul");
  list.className = "sources-list";

  sources.forEach(src => {
    const li = document.createElement("li");
    li.textContent = src.file || "Unknown file";
    list.appendChild(li);
  });

  details.appendChild(list);
  return details;
}

function addMessage({ role, content, ts, state, sources }) {
  if (!chatList) return {};

  const row = document.createElement("div");
  row.className = "msg " + (role === "user" ? "msg--user" : "msg--assistant");

  const avatar = document.createElement("div");
  avatar.className = "msg__avatar";

  if (role === "assistant") {
    avatar.textContent = "הצ'אט";
  } else {
    avatar.textContent = "אני";
  }

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = content || "";

  const meta = document.createElement("div");
  meta.className = "meta";
  meta.textContent = ts ? formatTime(ts) : "";

  const wrap = document.createElement("div");
  wrap.appendChild(bubble);
  wrap.appendChild(meta);

  if (sources && sources.length) {
    const sourcesEl = renderSourcesAccordion(sources);
    if (sourcesEl) {
      const sContainer = document.createElement("div");
      sContainer.className = "sources-container";
      sContainer.appendChild(sourcesEl);
      wrap.appendChild(sContainer);
    }
  }

  row.appendChild(avatar);
  row.appendChild(wrap);
  chatList.appendChild(row);
  scrollToBottom();

  return { row, bubble, avatar, wrap };
}

function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderEmbedTruncationStats(st) {
  const truncCount = st?.trunc_count ?? 0;
  const truncTotal = st?.trunc_total_chars ?? 0;
  const truncMax = st?.trunc_max_chars ?? 0;

  const fbTries = st?.ctx_fallback_total_tries ?? 0;
  const fbCut = st?.ctx_fallback_total_cut_chars ?? 0;

  const examples = Array.isArray(st?.trunc_examples) ? st.trunc_examples : [];
  const fbEvents = Array.isArray(st?.ctx_fallback_events) ? st.ctx_fallback_events : [];

  const fmt = (n) => (typeof n === "number" ? n.toLocaleString() : String(n));

  const exHtml = examples.length
    ? `<details class="details">
         <summary>דוגמאות חיתוך (עד 5)</summary>
         <div class="details-body">
           ${examples.map(e => {
      const name = (e.source_path || e.title || "unknown");
      return `<div class="mini-row">
                         <div class="mono">${escapeHtml(name)}</div>
                         <div>cut <b>${fmt(e.cut_chars)}</b> ( ${fmt(e.orig_chars)} → ${fmt(e.kept_chars)} )</div>
                       </div>`;
    }).join("")}
         </div>
       </details>`
    : "";

  const fbHtml = fbEvents.length
    ? `<details class="details">
         <summary>חריגות טוקנים + Retry (עד 5)</summary>
         <div class="details-body">
           ${fbEvents.map(e => {
      const ba = e.last_before_after ? `${e.last_before_after[0]}→${e.last_before_after[1]}` : "-";
      return `<div class="mini-row">
                         <div>batch <b>${fmt(e.batch)}</b> | tries <b>${fmt(e.tries)}</b> | cut total <b>${fmt(e.cut_total_chars)}</b> | last ${escapeHtml(ba)}</div>
                       </div>`;
    }).join("")}
         </div>
       </details>`
    : "";

  return `
    <div class="kpi-grid">
      <div class="kpi">
        <div class="kpi-label">חיתוכי צ׳אנקים (תווים)</div>
        <div class="kpi-value">${fmt(truncCount)}</div>
        <div class="kpi-sub">Σ cut: ${fmt(truncTotal)} | max cut: ${fmt(truncMax)}</div>
      </div>

      <div class="kpi">
        <div class="kpi-label">Retry בגלל טוקנים</div>
        <div class="kpi-value">${fmt(fbTries)}</div>
        <div class="kpi-sub">Σ cut (fallback): ${fmt(fbCut)}</div>
      </div>
    </div>
    ${exHtml}
    ${fbHtml}
  `;
}

function renderHistory() {
  if (!chatList) return;
  chatList.innerHTML = "";
  for (const h of history) {
    addMessage({ role: h.role, content: h.content, ts: h.ts, state: "answered", sources: h.sources });
  }
  scrollToBottom();
}
renderHistory();

// ===== Tabs =====
function setTab(name) {
  const isChat = name === "chat";
  const isDev = name === "dev";
  const isSettings = name === "settings";

  if (tabChat) tabChat.classList.toggle("tab--active", isChat);
  if (tabDev) tabDev.classList.toggle("tab--active", isDev);
  if (tabSettings) tabSettings.classList.toggle("tab--active", isSettings);

  if (viewChat) viewChat.classList.toggle("hidden", !isChat);
  if (viewDev) viewDev.classList.toggle("hidden", !isDev);
  if (viewSettings) viewSettings.classList.toggle("hidden", !isSettings);

  // אם עברנו להגדרות והמשתמש מחובר כמפתח - נטען הגדרות
  if (isSettings && adminCode) {
    loadConfigData();
  }
}

if (tabChat) tabChat.addEventListener("click", () => setTab("chat"));
if (tabDev) tabDev.addEventListener("click", () => setTab("dev"));
if (tabSettings) tabSettings.addEventListener("click", () => setTab("settings"));

// ===== KB status pill =====
async function refreshKbStatus() {
  if (!kbStatus) return;
  try {
    const r = await fetch("/kb/status", { cache: "no-store" });
    const j = await r.json();
    const chunks = (j.chunks ?? "?");
    const files = (j.files ?? "?");
    const emb = (j.embeddings ?? "?");
    kbStatus.textContent = `KB: ${files} קבצים | ${chunks} צ'אנקים | vec=${emb}`;
  } catch {
    kbStatus.textContent = "KB: לא זמין";
  }
}
refreshKbStatus();
refreshKbStatus();
setInterval(refreshKbStatus, 2500);

// ===== Ad-Hoc File Handling =====

if (attachFileBtn) {
  attachFileBtn.addEventListener("click", () => {
    if (adhocFileInput) adhocFileInput.click();
  });
}

if (adhocFileInput) {
  adhocFileInput.addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (!file) return;

    // Reset UI
    if (filePreviewArea) filePreviewArea.classList.add("hidden");

    // No client-side size limit here on logic, but maybe alert if HUGE? 
    // Let's allow large files now that we upload them properly.

    currentAdhocFileObj = file;
    if (attachedFileName) attachedFileName.textContent = file.name + ` (${(file.size / 1024 / 1024).toFixed(1)} MB)`;
    if (filePreviewArea) filePreviewArea.classList.remove("hidden");
  });
}

if (removeFileBtn) {
  removeFileBtn.addEventListener("click", clearAdhocFile);
}

function clearAdhocFile() {
  currentAdhocFileObj = null;
  if (adhocFileInput) adhocFileInput.value = "";
  if (filePreviewArea) filePreviewArea.classList.add("hidden");
  if (attachedFileName) attachedFileName.textContent = "";
}

async function uploadFileAndGetId(file) {
  const fd = new FormData();
  fd.append("file", file);

  const r = await fetch("/chat/upload", {
    method: "POST",
    body: fd
  });

  if (!r.ok) {
    const txt = await r.text();
    throw new Error("Upload failed: " + txt);
  }

  const j = await r.json();
  if (!j.ok) throw new Error(j.error || "Unknown upload error");
  return j.file_id;
}

// ===== Chat (SSE stream) =====
async function sendMessage() {
  const text = (inputEl.value || "").trim();
  if (!text) return;

  const now = Date.now();
  history.push({ role: "user", content: text, ts: now });
  saveHistory(history);
  addMessage({ role: "user", content: text, ts: now });

  inputEl.value = "";
  autoGrow();

  const thinkingTs = Date.now();
  const node = addMessage({ role: "assistant", content: "חושב…", ts: thinkingTs, state: "thinking" });

  const HISTORY_SEND_LIMIT = 14;
  const historyToSend = history.slice(-HISTORY_SEND_LIMIT);

  let assistantText = "";
  let sourcesForThisAnswer = [];

  const selectedModel = mainModeSelect ? mainModeSelect.value : "gpt-4o";

  // Upload file if attached
  let uploadedFileId = null;
  if (currentAdhocFileObj) {
    try {
      // Show uploading state...
      node.bubble.textContent = `מעלה קובץ (${currentAdhocFileObj.name})...`;
      uploadedFileId = await uploadFileAndGetId(currentAdhocFileObj);
      node.bubble.textContent = "חושב..."; // Back to thinking
    } catch (e) {
      node.bubble.textContent = "שגיאה בהעלאת קובץ: " + e.message;
      return;
    }
  }

  try {
    const resp = await fetch("/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: text,
        history: historyToSend,
        model: selectedModel,
        file_id: uploadedFileId // Send ID instead of Base64
      }),
    });

    if (!resp.ok || !resp.body) throw new Error("שגיאה: לא הצלחתי לקבל תשובה מהשרת.");

    const reader = resp.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let parts = buffer.split("\n\n");
      buffer = parts.pop() || "";

      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith("data:")) continue;

        const payload = line.slice(5).trim();
        let obj;
        try {
          obj = JSON.parse(payload);
        } catch (e) {
          console.error("JSON Parse Error:", e, payload);
          continue;
        }

        if (obj.type === "sources") {
          sourcesForThisAnswer = Array.isArray(obj.sources) ? obj.sources : [];
        }
        if (obj.type === "delta") {
          assistantText += obj.delta || "";
          node.bubble.textContent = assistantText || " ";
          scrollToBottom();
        }
        if (obj.type === "error") {
          node.bubble.textContent = obj.message || "שגיאה";
        }
        if (obj.type === "done") {
          // Clear file after successful send
          if (currentAdhocFileObj) clearAdhocFile();

          node.avatar.innerHTML = "";
          node.avatar.textContent = "הצ'אט";

          if (sourcesForThisAnswer.length) {
            const sourcesEl = renderSourcesAccordion(sourcesForThisAnswer);
            if (sourcesEl) {
              const sContainer = document.createElement("div");
              sContainer.className = "sources-container";
              sContainer.appendChild(sourcesEl);
              node.wrap.appendChild(sContainer);
              scrollToBottom();
            }
          }

          const ts2 = Date.now();
          history.push({
            role: "assistant",
            content: assistantText || node.bubble.textContent,
            ts: ts2,
            sources: sourcesForThisAnswer
          });
          saveHistory(history);
        }
      }
    }
  } catch (e) {
    node.bubble.textContent = String(e?.message || e || "שגיאה");
    node.avatar.innerHTML = "";
    node.avatar.textContent = "הצ'אט";
  }
}

// ===== Search Only Logic =====
async function performSearchOnly() {
  const text = (inputEl.value || "").trim();
  if (!text) return;

  const now = Date.now();
  history.push({ role: "user", content: "חיפוש במאגר: " + text, ts: now });
  saveHistory(history);
  addMessage({ role: "user", content: "חיפוש במאגר: " + text, ts: now });

  inputEl.value = "";
  autoGrow();

  const loadingNode = addMessage({ role: "assistant", content: "מחפש מסמכים...", ts: Date.now(), state: "thinking" });

  try {
    const resp = await fetch("/kb/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: text,
        top_k: 10
      }),
    });

    const data = await resp.json();

    if (!data.ok) {
      throw new Error(data.detail || "שגיאת חיפוש");
    }

    const sources = (data.results || []).map(r => ({
      file: r.source_path,
      score: r.score,
      page_content: r.text
    }));

    loadingNode.avatar.innerHTML = "";
    loadingNode.avatar.textContent = "תוצאות";

    if (sources.length === 0) {
      loadingNode.bubble.textContent = "לא נמצאו מקורות רלוונטיים עבור: " + text;
    } else {
      loadingNode.bubble.textContent = `נמצאו ${sources.length} מקורות רלוונטיים`;

      const sourcesEl = renderSourcesAccordion(sources);
      if (sourcesEl) {
        sourcesEl.open = true;
        const sContainer = document.createElement("div");
        sContainer.className = "sources-container";
        sContainer.appendChild(sourcesEl);
        loadingNode.wrap.appendChild(sContainer);
        scrollToBottom();
      }
    }

    const assistantContent = sources.length
      ? `[תוצאות חיפוש: ${sources.length} מקורות עבור "${text}"]`
      : "לא נמצאו תוצאות.";

    history.push({
      role: "assistant",
      content: assistantContent,
      ts: Date.now(),
      sources: sources
    });
    saveHistory(history);

  } catch (e) {
    loadingNode.bubble.textContent = "שגיאה בחיפוש: " + String(e.message || e);
  }
}

// ===== Main Button Handling =====
function handleMainSend() {
  const mode = mainModeSelect ? mainModeSelect.value : "gpt-4o";

  if (mode === "search") {
    performSearchOnly();
  } else {
    sendMessage();
  }
}

if (mainSendBtn) mainSendBtn.addEventListener("click", handleMainSend);

if (inputEl) inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    handleMainSend();
  }
});

if (clearBtn) clearBtn.addEventListener("click", () => {
  if (!confirm("למחוק את כל ההיסטוריה?")) return;
  history = [];
  saveHistory(history);
  renderHistory();
});

// ===== Dev / Admin Settings Logic =====

function setDevUnlocked(on) {
  if (devPanels) devPanels.classList.toggle("hidden", !on);
  if (adminState) adminState.textContent = on ? "מחובר" : "לא מחובר";
  updateSettingsLock(on);
}

function updateSettingsLock(unlocked) {
  if (!settingsPanels || !settingsLockMsg) return;
  settingsPanels.classList.toggle("hidden", !unlocked);
  settingsLockMsg.classList.toggle("hidden", unlocked);

  // אם פתחנו את הנעילה ואנחנו כרגע בטאב ההגדרות - נטען נתונים
  if (unlocked && viewSettings && !viewSettings.classList.contains("hidden")) {
    loadConfigData();
  }
}

async function loadConfigData() {
  // אם אין קוד מנהל, לא מבצעים קריאה (מונע 401)
  if (!adminCode) return;

  try {
    const r = await fetch("/admin/config", {
      headers: { "X-Admin-Code": adminCode }
    });

    if (r.ok) {
      const data = await r.json();
      if (cfgPrompt) cfgPrompt.value = data.system_prompt || "";
      if (cfgKeywords) cfgKeywords.value = data.important_concepts || "";
      // לא ממלאים את שדות המפתח מטעמי אבטחה
    } else if (r.status === 401) {
      console.warn("נדרשת התחברות מנהל מחדש");
      // אופציונלי: אפשר לנקות כאן את adminCode אם הוא פג תוקף
    }
  } catch (e) {
    console.error("Failed to load config", e);
  }
}

async function saveConfigData() {
  if (!adminCode) {
    alert("נא להתחבר כמפתח");
    return;
  }

  if (saveConfigBtn) {
    saveConfigBtn.textContent = "שומר...";
    saveConfigBtn.disabled = true;
  }

  const payload = {
    openai_api_key: cfgOpenAI ? cfgOpenAI.value.trim() : "",

    system_prompt: cfgPrompt ? cfgPrompt.value.trim() : "",
    important_concepts: cfgKeywords ? cfgKeywords.value.trim() : ""
  };

  try {
    const r = await fetch("/admin/config", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Admin-Code": adminCode
      },
      body: JSON.stringify(payload)
    });

    const res = await r.json();
    if (r.ok) {
      alert("ההגדרות נשמרו בהצלחה!");
      // ניקוי שדות מפתח ויזואלי
      if (cfgOpenAI) cfgOpenAI.value = "";


      // רענון הנתונים המוצגים (למשל אם מילות המפתח השתנו)
      loadConfigData();
    } else {
      alert("שגיאה בשמירה: " + (res.detail || "Unknown error"));
    }
  } catch (e) {
    alert("שגיאת תקשורת");
  } finally {
    if (saveConfigBtn) {
      saveConfigBtn.textContent = "שמור הגדרות";
      saveConfigBtn.disabled = false;
    }
  }
}

if (saveConfigBtn) saveConfigBtn.addEventListener("click", saveConfigData);

// הפעלה ראשונית אם יש קוד בזיכרון
if (adminCode) {
  setDevUnlocked(true);
}

if (adminUnlockBtn) adminUnlockBtn.addEventListener("click", () => {
  const c = (adminCodeInput.value || "").trim();
  if (!c) return;
  adminCode = c;
  sessionStorage.setItem("admin_code", adminCode);
  setDevUnlocked(true);
  startPolling();
  // טוען את ההגדרות מיד עם הכניסה
  loadConfigData();
});

// Status fetchers
async function fetchIndexStatus() {
  const r = await fetch("/kb/index/status", { cache: "no-store" });
  return await r.json();
}
async function fetchEmbedStatus() {
  const r = await fetch("/kb/embed/status", { cache: "no-store" });
  return await r.json();
}

// Progress calculators
function setProgress(barEl, pct) {
  if (!barEl) return;
  const p = Math.max(0, Math.min(100, pct));
  barEl.style.width = p.toFixed(1) + "%";
}
function secondsToHuman(sec) {
  if (sec == null || !isFinite(sec)) return "—";
  sec = Math.max(0, Math.round(sec));
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  if (m <= 0) return `${s}s`;
  return `${m}m ${s}s`;
}

function updateIndexUI(st) {
  if (!indexStatusBox) return;
  indexStatusBox.textContent = pretty(st);

  const total = Number(st.total_files ?? 0);
  const done = Number(st.processed_files ?? 0);
  const pct = total > 0 ? (done / total) * 100 : 0;
  setProgress(indexProg, pct);

  const eta = secondsToHuman(st.eta_sec);
  const rate = (st.files_per_sec != null) ? `${Number(st.files_per_sec).toFixed(2)}/s` : "—";
  if (indexKpis) indexKpis.textContent =
    `קבצים: ${done}/${total} • ${pct.toFixed(1)}% • קצב: ${rate} • ETA: ${eta} • chunks: ${st.chunks_written ?? "—"}`;
}

function updateEmbedUI(st) {
  if (!embedStatusBox) return;
  embedStatusBox.textContent = pretty(st);

  const total = Number(st.total_chunks ?? 0);
  const done = Number(st.processed_chunks ?? 0);
  const pct = total > 0 ? (done / total) * 100 : 0;
  setProgress(embedProg, pct);

  const eta = secondsToHuman(st.eta_sec);
  const rate = (st.chunks_per_sec != null) ? `${Number(st.chunks_per_sec).toFixed(2)}/s` : "—";

  const baseLine =
    `צ׳אנקים: ${done}/${total} • ${pct.toFixed(1)}% • קצב: ${rate} • ETA: ${eta} • מודל: ${st.model ?? "—"}`;

  if (embedKpis) embedKpis.innerHTML = `
    <div class="kpis__line">${escapeHtml(baseLine)}</div>
    ${renderEmbedTruncationStats(st)}
  `;
}

let pollTimer = null;
function startPolling() {
  if (pollTimer) return;

  pollTimer = setInterval(async () => {
    try {
      const [a, b] = await Promise.all([fetchIndexStatus(), fetchEmbedStatus()]);
      updateIndexUI(a || {});
      updateEmbedUI(b || {});
    } catch { }
  }, 1000);
}
function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function runAdminPost(url) {
  if (!adminCode) {
    alert("צריך קוד מפתח (1111).");
    return null;
  }
  const resp = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Admin-Code": adminCode
    },
    body: JSON.stringify({})
  });

  const j = await resp.json().catch(() => ({}));
  if (resp.status === 401) {
    alert("קוד שגוי.");
    return null;
  }
  if (!resp.ok) {
    alert(j?.detail || "שגיאה");
    return null;
  }
  return j;
}

if (reindexBtn) reindexBtn.addEventListener("click", async () => {
  startPolling();
  await runAdminPost("/kb/index");
  try { updateIndexUI(await fetchIndexStatus()); } catch { }
});

if (reembedBtn) reembedBtn.addEventListener("click", async () => {
  startPolling();
  await runAdminPost("/kb/embed");
  try { updateEmbedUI(await fetchEmbedStatus()); } catch { }
});

if (refreshIndexBtn) refreshIndexBtn.addEventListener("click", async () => {
  try { updateIndexUI(await fetchIndexStatus()); } catch { }
});

if (refreshEmbedBtn) refreshEmbedBtn.addEventListener("click", async () => {
  try { updateEmbedUI(await fetchEmbedStatus()); } catch { }
});

// Start polling when opening Dev tab (if already unlocked)
if (tabDev) tabDev.addEventListener("click", () => {
  if (devPanels && !devPanels.classList.contains("hidden")) startPolling();
});
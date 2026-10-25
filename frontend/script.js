/* ============================================================
   PDF RAG Assistant — script.js
   Connects the neo-brutalist wireframe UI to the FastAPI backend.
============================================================ */
const API_URL = "http://127.0.0.1:8000";

// ── State ────────────────────────────────────────────────────
let activeDocId      = null;
let documents        = {};
let selectedProvider = 'Gemini';

// ── DOM refs ─────────────────────────────────────────────────
const sidebar         = document.getElementById('sidebar');
const sidebarBackdrop = document.getElementById('sidebarBackdrop');
const uploadButton    = document.getElementById('uploadButton');
const pdfInput        = document.getElementById('pdfInput');
const docList         = document.getElementById('docList');
const docEmptyHint    = document.getElementById('docEmptyHint');
const clearAllBtn     = document.getElementById('clearAllBtn');
const clearChatBtn    = document.getElementById('clearChatBtn');
const topbarTitle     = document.getElementById('topbarTitle');
const topbarSub       = document.getElementById('topbarSub');
const topbarDocIcon   = document.getElementById('topbarDocIcon');
const emptyState      = document.getElementById('emptyState');
const emptyHeading    = document.getElementById('emptyHeading');
const emptySubtext    = document.getElementById('emptySubtext');
const messagesList    = document.getElementById('messagesList');
const questionInput   = document.getElementById('questionInput');
const sendButton      = document.getElementById('sendButton');

// ── Helpers ──────────────────────────────────────────────────

/**
 * Strip any characters outside ISO-8859-1 (char code > 255) so the value
 * is safe to use as an HTTP header. Non-ASCII chars (e.g. smart quotes or
 * invisible Unicode that can sneak in during copy-paste) cause the browser
 * to throw "String contains non ISO-8859-1 code point".
 */
function safeHeader(value) {
  return String(value).replace(/[^\x00-\xFF]/g, '');
}

function openSidebar() {
  if (sidebar) sidebar.classList.add('open');
  if (sidebarBackdrop) sidebarBackdrop.classList.add('active');
}

function closeSidebar() {
  if (sidebar) sidebar.classList.remove('open');
  if (sidebarBackdrop) sidebarBackdrop.classList.remove('active');
}

function showState(hasMessages) {
  if (hasMessages) {
    emptyState.style.display    = 'none';
    messagesList.style.display  = 'flex';
  } else {
    emptyState.style.display    = 'flex';
    messagesList.style.display  = 'none';
  }
}

function scrollToBottom() {
  const area = document.getElementById('chatArea');
  area.scrollTop = area.scrollHeight;
}

function uniqueId() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2);
}

// ── Topbar ───────────────────────────────────────────────────

function updateTopbar() {
  if (!activeDocId || !documents[activeDocId]) {
    topbarTitle.textContent = 'No document selected';
    topbarSub.textContent   = 'Upload or select a document from the sidebar';
    topbarDocIcon.style.background = 'var(--pink)';
    emptyHeading.textContent = 'Ask anything about your document';
    emptySubtext.textContent = 'Upload a PDF from the sidebar, then ask any question.';
  } else {
    const doc = documents[activeDocId];
    topbarTitle.textContent  = doc.name;
    topbarSub.textContent    = `${doc.chunks} chunks · indexed ${timeSince(doc.timestamp)}`;
    topbarDocIcon.style.background = 'var(--pink)';
    emptyHeading.textContent = 'Ask anything about this document';
    emptySubtext.textContent = `Answers are grounded in the actual pages of ${doc.name}.`;
  }
}

function timeSince(ts) {
  const secs = Math.floor((Date.now() - ts) / 1000);
  if (secs < 60)  return 'just now';
  if (secs < 3600) return Math.floor(secs / 60) + ' minutes ago';
  return Math.floor(secs / 3600) + ' hours ago';
}

// ── Document list ─────────────────────────────────────────────

function renderDocList() {
  const ids = Object.keys(documents);
  docEmptyHint.style.display = ids.length === 0 ? 'block' : 'none';

  // remove all doc-card elements
  docList.querySelectorAll('.doc-card').forEach(c => c.remove());

  ids.forEach(id => {
    const doc  = documents[id];
    const card = document.createElement('div');
    card.className = 'doc-card' + (id === activeDocId ? ' active' : '');
    card.dataset.id = id;
    card.innerHTML = `
      <div class="doc-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <path d="M14 2v6h6"/>
        </svg>
      </div>
      <div class="doc-meta">
        <div class="doc-name" title="${doc.name}">${doc.name}</div>
        <div class="doc-sub">
          <span class="doc-sub-dot"></span>
          Ready · ${doc.chunks} chunks
        </div>
      </div>
      <button class="doc-delete" aria-label="Remove document" data-id="${id}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <path d="M3 6h18"/>
          <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
          <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
        </svg>
      </button>`;
    card.addEventListener('click', () => selectDoc(id));
    card.querySelector('.doc-delete').addEventListener('click', e => {
      e.stopPropagation();
      removeDoc(id);
    });
    docList.insertBefore(card, docEmptyHint);
  });
}

function selectDoc(id) {
  activeDocId = id;
  clearMessages();
  renderDocList();
  updateTopbar();
  if (window.innerWidth <= 768) {
    closeSidebar();
  }
}

function removeDoc(id) {
  delete documents[id];
  if (activeDocId === id) {
    activeDocId = Object.keys(documents)[0] || null;
    clearMessages();
  }
  renderDocList();
  updateTopbar();
}

// ── Messages ──────────────────────────────────────────────────

function clearMessages() {
  messagesList.innerHTML = '';
  showState(false);
}

function addUserMessage(text) {
  showState(true);
  const row = document.createElement('div');
  row.className = 'msg-row user';
  row.innerHTML = `
    <div class="avatar user">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <circle cx="12" cy="8" r="4"/>
        <path d="M4 21v-1a7 7 0 0 1 7-7h2a7 7 0 0 1 7 7v1"/>
      </svg>
    </div>
    <div class="bubble user"></div>`;
  row.querySelector('.bubble').textContent = text;
  messagesList.appendChild(row);
  scrollToBottom();
}

function addTypingIndicator() {
  const row = document.createElement('div');
  row.className = 'msg-row';
  row.id = 'typingRow';
  row.innerHTML = `
    <div class="avatar ai">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <rect x="4" y="8" width="16" height="12" rx="1"/>
        <path d="M12 8V4"/>
        <circle cx="9" cy="14" r="1"/><circle cx="15" cy="14" r="1"/>
      </svg>
    </div>
    <div class="bubble ai"><div class="typing"><span></span><span></span><span></span></div></div>`;
  messagesList.appendChild(row);
  scrollToBottom();
}

function removeTypingIndicator() {
  const row = document.getElementById('typingRow');
  if (row) row.remove();
}

function addAIMessage(text) {
  const row = document.createElement('div');
  row.className = 'msg-row';
  row.innerHTML = `
    <div class="avatar ai">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <rect x="4" y="8" width="16" height="12" rx="1"/>
        <path d="M12 8V4"/>
        <circle cx="9" cy="14" r="1"/><circle cx="15" cy="14" r="1"/>
      </svg>
    </div>
    <div class="bubble ai"></div>`;
  const bubble = row.querySelector('.bubble');
  bubble.innerHTML = DOMPurify.sanitize(marked.parse(text));
  messagesList.appendChild(row);
  scrollToBottom();
}

// ── API Key Storage Helpers ──────────────────────────────────

function getProvider() {
  return localStorage.getItem('rag_provider') || 'Gemini';
}
// ── Ask question ──────────────────────────────────────────────

async function askQuestion() {
  const question = questionInput.value.trim();
  if (!question) return;
  questionInput.value = '';
  sendButton.disabled = true;
  autoResize();

  addUserMessage(question);
  addTypingIndicator();

  try {
    const res = await fetch(`${API_URL}/ask`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Provider': safeHeader(getProvider())
      },
      body: JSON.stringify({
        question,
        provider: getProvider()
      }),
    });
    if (!res.ok) throw new Error(`Server error ${res.status}`);
    const data = await res.json();
    removeTypingIndicator();
    addAIMessage(data.answer);
  } catch (err) {
    console.error(err);
    removeTypingIndicator();
    addAIMessage("⚠️ Couldn't connect to the AI server or process the response. Please check your API key.");
  } finally {
    sendButton.disabled = false;
    questionInput.focus();
  }
}

// ── Upload PDF ────────────────────────────────────────────────

async function uploadPDF(file) {
  if (!file) return;
  const name = file.name.toLowerCase();
  if (!name.endsWith('.pdf') && file.type !== 'application/pdf') {
    showUploadError('Please select a PDF file.');
    return;
  }

  uploadButton.disabled = true;
  sendButton.disabled   = true;

  // Optimistically add a processing card
  const tempId = uniqueId();
  documents[tempId] = { id: tempId, name: file.name, chunks: '…', timestamp: Date.now() };
  activeDocId = tempId;
  renderDocList();
  updateTopbar();

  // Mark the card as processing
  const cardEl = docList.querySelector(`[data-id="${tempId}"]`);
  if (cardEl) {
    const subEl = cardEl.querySelector('.doc-sub');
    if (subEl) subEl.innerHTML = '<span class="doc-sub-dot processing"></span>Indexing…';
  }

  const formData = new FormData();
  formData.append('file', file);
  formData.append('provider', getProvider());

  // Reset input so same file can be re-uploaded
  pdfInput.value = '';

  try {
    const res = await fetch(`${API_URL}/upload`, {
      method: 'POST',
      headers: {
        'X-Provider': safeHeader(getProvider())
      },
      body: formData
    });
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    const data = await res.json();
    if (!data.success) throw new Error(data.message || 'PDF processing failed.');

    documents[tempId] = { id: tempId, name: data.filename || file.name, chunks: data.chunks, timestamp: Date.now() };
    clearMessages();
    renderDocList();
    updateTopbar();
  } catch (err) {
    console.error('Upload error:', err);
    delete documents[tempId];
    if (activeDocId === tempId) activeDocId = Object.keys(documents)[0] || null;
    renderDocList();
    updateTopbar();
    showUploadError('Upload failed: ' + err.message);
  } finally {
    uploadButton.disabled = false;
    sendButton.disabled   = false;
  }
}

function showUploadError(msg) {
  showState(true);
  addAIMessage('⚠️ ' + msg);
}

// ── Textarea auto-resize ──────────────────────────────────────

function autoResize() {
  questionInput.style.height = 'auto';
  questionInput.style.height = Math.min(questionInput.scrollHeight, 120) + 'px';
}

// ── Event listeners ───────────────────────────────────────────

// Trigger file picker
uploadButton.addEventListener('click', () => {
  pdfInput.value = '';
  pdfInput.click();
});

// File selected
pdfInput.addEventListener('change', (e) => {
  const file = e.target.files && e.target.files[0];
  if (file) uploadPDF(file);
});

sendButton.addEventListener('click', askQuestion);
clearChatBtn.addEventListener('click', clearMessages);
clearAllBtn.addEventListener('click', () => {
  documents   = {};
  activeDocId = null;
  clearMessages();
  renderDocList();
  updateTopbar();
});

questionInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); askQuestion(); }
});
questionInput.addEventListener('input', autoResize);

// Suggested question chips
document.querySelectorAll('.suggested-card').forEach(btn => {
  btn.addEventListener('click', () => {
    questionInput.value = btn.dataset.question || btn.textContent.trim();
    autoResize();
    questionInput.focus();
  });
});

// Mobile drawer event listeners
const mobileMenuBtn   = document.getElementById('mobileMenuBtn');
const sidebarCloseBtn = document.getElementById('sidebarCloseBtn');

if (mobileMenuBtn)   mobileMenuBtn.addEventListener('click', openSidebar);
if (sidebarCloseBtn) sidebarCloseBtn.addEventListener('click', closeSidebar);
if (sidebarBackdrop) sidebarBackdrop.addEventListener('click', closeSidebar);

// Global escape key handler
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    closeSidebar();
  }
});

// Expose functions to window
window.openSidebar         = openSidebar;
window.closeSidebar        = closeSidebar;

// ── Init ──────────────────────────────────────────────────────
renderDocList();
updateTopbar();
showState(false);

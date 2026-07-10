// Config Backend Host
const BASE = 'http://localhost:8001';

// UI Elements
const healthIndicator = document.getElementById('healthIndicator');
const healthLabel = document.getElementById('healthLabel');

const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const fileBadgeContainer = document.getElementById('fileBadgeContainer');

const submitBtn = document.getElementById('submitBtn');

const trackJobIdInput = document.getElementById('trackJobId');
const trackBtn = document.getElementById('trackBtn');

const criteriaToggle = document.getElementById('criteriaToggle');
const criteriaContent = document.getElementById('criteriaContent');
const professionalCheck = document.getElementById('professionalCheck');
const excludePolitics = document.getElementById('excludePolitics');
const toneInput = document.getElementById('toneInput');
const chipContainer = document.getElementById('chipContainer');
const chipTextInput = document.getElementById('chipTextInput');

const progressCard = document.getElementById('progressCard');
const resultsCard = document.getElementById('resultsCard');
const emptyCard = document.getElementById('emptyCard');

const jobIdLabel = document.getElementById('jobIdLabel');
const copyJobIdBtn = document.getElementById('copyJobIdBtn');
const jobStatusBadge = document.getElementById('jobStatusBadge');

const progressFillBar = document.getElementById('progressFillBar');
const progressPercentText = document.getElementById('progressPercentText');
const progressLabelText = document.getElementById('progressLabelText');

const statTotal = document.getElementById('statTotal');
const statProcessed = document.getElementById('statProcessed');
const statFlagged = document.getElementById('statFlagged');
const jobErrorAlert = document.getElementById('jobErrorAlert');

const resultsList = document.getElementById('resultsList');
const csvBtn = document.getElementById('csvBtn');
const resultSearchInput = document.getElementById('resultSearchInput');

const tabAll = document.getElementById('tabAll');
const tabFlagged = document.getElementById('tabFlagged');
const tabSafe = document.getElementById('tabSafe');

// Application State Variables
let forbiddenWords = ['crypto', 'NFT', 'hustlegrindset'];
let selectedFile = null;
let currentJobId = null;
let pollInterval = null;
let jobResults = [];
let activeTab = 'all';

// ----------------------------------------------------
// API Health Check
// ----------------------------------------------------
async function checkApiHealth() {
  try {
    // FastAPI automatic docs endpoint serves as a simple ping
    const res = await fetch(`${BASE}/openapi.json`);
    if (res.ok) {
      healthIndicator.className = 'status-indicator status-online';
      healthLabel.textContent = 'API Server: Online';
    } else {
      throw new Error('Offline');
    }
  } catch (e) {
    healthIndicator.className = 'status-indicator status-offline';
    healthLabel.textContent = 'API Server: Offline';
  }
}
// Check immediately and then every 10s
checkApiHealth();
setInterval(checkApiHealth, 10000);

// ----------------------------------------------------
// State Preservation via LocalStorage
// (Prevents reload issues when editing files in VS Code)
// ----------------------------------------------------
function saveStateToLocalStorage() {
  const state = {
    currentJobId,
    forbiddenWords,
    professionalCheck: professionalCheck.checked,
    excludePolitics: excludePolitics.checked,
    tone: toneInput.value.trim(),
    trackJobId: trackJobIdInput.value.trim()
  };
  localStorage.setItem('tweet_audit_state', JSON.stringify(state));
}

function loadStateFromLocalStorage() {
  try {
    const stored = localStorage.getItem('tweet_audit_state');
    if (!stored) return;
    const state = JSON.parse(stored);
    
    if (state.forbiddenWords && Array.isArray(state.forbiddenWords)) {
      forbiddenWords = state.forbiddenWords;
      renderChips();
    }
    
    professionalCheck.checked = state.professionalCheck ?? true;
    excludePolitics.checked = state.excludePolitics ?? true;
    toneInput.value = state.tone ?? 'respectful and thoughtful';
    
    if (state.trackJobId) {
      trackJobIdInput.value = state.trackJobId;
    }

    if (state.currentJobId) {
      currentJobId = state.currentJobId;
      trackJobIdInput.value = currentJobId;
      startTrackingJob(currentJobId);
    }
  } catch (e) {
    console.error('Failed to load state from localStorage', e);
  }
}

// ----------------------------------------------------
// Accordion Logic
// ----------------------------------------------------
criteriaToggle.addEventListener('click', () => {
  criteriaToggle.classList.toggle('active');
  criteriaContent.classList.toggle('open');
});

// ----------------------------------------------------
// Forbidden Words Tag / Chip Input
// ----------------------------------------------------
function renderChips() {
  // Clear previous chips (keep the text input element at the end)
  const existingChips = chipContainer.querySelectorAll('.chip');
  existingChips.forEach(chip => chip.remove());
  
  forbiddenWords.forEach((word, index) => {
    const chip = document.createElement('div');
    chip.className = 'chip';
    chip.innerHTML = `
      <span>${escapeHtml(word)}</span>
      <button class="chip-remove" type="button" data-index="${index}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:12px;height:12px;">
          <line x1="18" y1="6" x2="6" y2="18"></line>
          <line x1="6" y1="6" x2="18" y2="18"></line>
        </svg>
      </button>
    `;
    chipContainer.insertBefore(chip, chipTextInput);
  });
  
  // Wire remove buttons
  chipContainer.querySelectorAll('.chip-remove').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const index = parseInt(btn.getAttribute('data-index'), 10);
      forbiddenWords.splice(index, 1);
      renderChips();
      saveStateToLocalStorage();
    });
  });
}

chipTextInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    e.preventDefault();
    const value = chipTextInput.value.trim();
    if (value && !forbiddenWords.includes(value)) {
      forbiddenWords.push(value);
      renderChips();
      chipTextInput.value = '';
      saveStateToLocalStorage();
    }
  }
});

// Initial Chip rendering
renderChips();

// ----------------------------------------------------
// Drag & Drop File Upload
// ----------------------------------------------------
['dragenter', 'dragover'].forEach(eventName => {
  dropZone.addEventListener(eventName, (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
  }, false);
});

['dragleave', 'drop'].forEach(eventName => {
  dropZone.addEventListener(eventName, (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
  }, false);
});

dropZone.addEventListener('drop', (e) => {
  const dt = e.dataTransfer;
  const files = dt.files;
  if (files.length) {
    handleFileSelect(files[0]);
  }
});

fileInput.addEventListener('change', (e) => {
  if (fileInput.files.length) {
    handleFileSelect(fileInput.files[0]);
  }
});

function handleFileSelect(file) {
  const extension = file.name.split('.').pop().toLowerCase();
  if (extension !== 'js' && extension !== 'zip') {
    alert('Unsupported file format. Please upload a .js or .zip archive.');
    return;
  }
  
  selectedFile = file;
  renderFileBadge();
  submitBtn.disabled = false;
}

function renderFileBadge() {
  if (!selectedFile) {
    fileBadgeContainer.innerHTML = '';
    submitBtn.disabled = true;
    return;
  }
  
  const sizeFormatted = formatBytes(selectedFile.size);
  fileBadgeContainer.innerHTML = `
    <div class="selected-file-badge">
      <div class="selected-file-info">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
          <polyline points="14 2 14 8 20 8"></polyline>
        </svg>
        <div style="overflow: hidden; text-overflow: ellipsis;">
          <div class="selected-file-name" title="${escapeHtml(selectedFile.name)}">${escapeHtml(selectedFile.name)}</div>
          <div class="selected-file-size">${sizeFormatted}</div>
        </div>
      </div>
      <button class="remove-file-btn" type="button" id="removeFileBtn">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:16px;height:16px;">
          <line x1="18" y1="6" x2="6" y2="18"></line>
          <line x1="6" y1="6" x2="18" y2="18"></line>
        </svg>
      </button>
    </div>
  `;
  
  document.getElementById('removeFileBtn').addEventListener('click', () => {
    selectedFile = null;
    fileInput.value = '';
    renderFileBadge();
  });
}

function formatBytes(bytes) {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// ----------------------------------------------------
// Actions & Operations
// ----------------------------------------------------

// Launch Audit Task
submitBtn.addEventListener('click', async () => {
  if (!selectedFile) return;
  
  submitBtn.disabled = true;
  submitBtn.innerHTML = `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="animation: spin 1s linear infinite;">
      <line x1="12" y1="2" x2="12" y2="6"></line>
      <line x1="12" y1="18" x2="12" y2="22"></line>
      <line x1="4.93" y1="4.93" x2="7.76" y2="7.76"></line>
      <line x1="16.24" y1="16.24" x2="19.07" y2="19.07"></line>
      <line x1="2" y1="12" x2="6" y2="12"></line>
      <line x1="18" y1="12" x2="22" y2="12"></line>
      <line x1="4.93" y1="19.07" x2="7.76" y2="16.24"></line>
      <line x1="16.24" y1="7.76" x2="19.07" y2="4.93"></line>
    </svg>
    Uploading...
  `;
  
  // Prepare form data
  const formData = new FormData();
  formData.append('file', selectedFile);
  
  // Prepare criteria object matching the backend model
  const criteriaObj = {
    forbidden_words: forbiddenWords,
    professional_check: professionalCheck.checked,
    tone: toneInput.value.trim() || "respectful and thoughtful",
    exclude_politics: excludePolitics.checked
  };
  
  formData.append('criteria', JSON.stringify(criteriaObj));
  
  try {
    const res = await fetch(`${BASE}/upload`, {
      method: 'POST',
      body: formData
    });
    
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail ?? res.statusText);
    }
    
    const data = await res.json();
    currentJobId = data.task_id;
    trackJobIdInput.value = currentJobId;
    
    saveStateToLocalStorage();
    startTrackingJob(currentJobId);
  } catch (e) {
    alert(`Failed to launch audit: ${e.message}`);
    resetSubmitButton();
  }
});

function resetSubmitButton() {
  submitBtn.disabled = false;
  submitBtn.innerHTML = `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <polygon points="5 3 19 12 5 21 5 3"></polygon>
    </svg>
    Run Audit Engine
  `;
}

// Track Button Trigger
trackBtn.addEventListener('click', () => {
  const jobId = trackJobIdInput.value.trim();
  if (!jobId) {
    alert('Please enter a valid Job ID.');
    return;
  }
  currentJobId = jobId;
  saveStateToLocalStorage();
  startTrackingJob(jobId);
});

// Copy Job ID
copyJobIdBtn.addEventListener('click', () => {
  if (!currentJobId) return;
  navigator.clipboard.writeText(currentJobId).then(() => {
    const origHtml = copyJobIdBtn.innerHTML;
    copyJobIdBtn.innerHTML = `
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color:var(--accent-emerald);">
        <polyline points="20 6 9 17 4 12"></polyline>
      </svg>
    `;
    setTimeout(() => {
      copyJobIdBtn.innerHTML = origHtml;
    }, 1500);
  });
});

// ----------------------------------------------------
// Job Polling & UI Rendering
// ----------------------------------------------------
function startTrackingJob(jobId) {
  if (pollInterval) clearInterval(pollInterval);
  
  // Update UI Panels
  emptyCard.style.display = 'none';
  progressCard.style.display = 'block';
  resultsCard.style.display = 'block';
  
  jobIdLabel.textContent = `JOB ID: ${jobId}`;
  jobErrorAlert.style.display = 'none';
  progressFillBar.style.width = '0%';
  progressPercentText.textContent = '0%';
  statTotal.textContent = '0';
  statProcessed.textContent = '0';
  statFlagged.textContent = '0';
  resultsList.innerHTML = `
    <div class="empty-state">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="animation: spin 1s linear infinite;">
        <line x1="12" y1="2" x2="12" y2="6"></line>
        <line x1="12" y1="18" x2="12" y2="22"></line>
        <line x1="4.93" y1="4.93" x2="7.76" y2="7.76"></line>
        <line x1="16.24" y1="16.24" x2="19.07" y2="19.07"></line>
      </svg>
      <p>Connecting & retrieving job records...</p>
    </div>
  `;
  
  pollJobStatus(jobId);
  pollInterval = setInterval(() => pollJobStatus(jobId), 2500);
}

async function pollJobStatus(jobId) {
  try {
    const res = await fetch(`${BASE}/${jobId}/status`);
    if (!res.ok) {
      if (res.status === 404) {
        showJobError('Job Not Found', `No job records exist for ID ${jobId}. Make sure your backend API and Celery worker are running.`);
        clearInterval(pollInterval);
        resetSubmitButton();
        return;
      }
      throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    }
    
    const job = await res.json();
    
    // Render current metrics
    renderJobProgress(job);
    
    // Fetch results dynamically if processing or completed
    if (job.status === 'processing' || job.status === 'completed') {
      fetchJobTweets(jobId);
    }
    
    // Polling termination rules
    if (job.status === 'completed' || job.status === 'failed') {
      clearInterval(pollInterval);
      resetSubmitButton();
      
      if (job.status === 'failed') {
        showJobError('Job Review Failed', job.error || 'Check celery worker logs for details.');
      }
    }
  } catch (e) {
    console.error('Polling error:', e);
    // Do not cancel the interval on transient network glitches
  }
}

function renderJobProgress(job) {
  // 1. Status badge
  let badgeHtml = '';
  if (job.status === 'pending') {
    badgeHtml = `<div class="badge badge-pending"><div class="pulsing-dot"></div>Queued</div>`;
    progressLabelText.textContent = 'Waiting for parsing worker...';
  } else if (job.status === 'processing') {
    badgeHtml = `<div class="badge badge-processing"><div class="pulsing-dot"></div>Auditing</div>`;
    progressLabelText.textContent = 'AI Batch Analysis...';
  } else if (job.status === 'completed') {
    badgeHtml = `<div class="badge badge-completed">Done</div>`;
    progressLabelText.textContent = 'Audit complete';
  } else if (job.status === 'failed') {
    badgeHtml = `<div class="badge badge-failed">Failed</div>`;
    progressLabelText.textContent = 'Review aborted';
  }
  jobStatusBadge.innerHTML = badgeHtml;
  
  // 2. Metrics & Counts
  statTotal.textContent = job.total;
  statProcessed.textContent = job.processed_count;
  statFlagged.textContent = job.flagged_count;
  
  // 3. Progress Bar Fill
  const total = job.total || 0;
  const processed = job.processed_count || 0;
  let pct = 0;
  if (total > 0) {
    pct = Math.round((processed / total) * 100);
  }
  
  progressFillBar.style.width = `${pct}%`;
  progressPercentText.textContent = `${pct}%`;
}

async function fetchJobTweets(jobId) {
  try {
    const res = await fetch(`${BASE}/${jobId}/tweets`);
    if (!res.ok) throw new Error('Could not fetch results');
    
    const data = await res.json();
    jobResults = data.results || [];
    
    renderResultsToolbarTabs();
    renderResultsLedger();
  } catch (e) {
    console.error('Failed to fetch job tweets:', e);
  }
}

function showJobError(title, msg) {
  jobErrorAlert.style.display = 'flex';
  jobErrorAlert.innerHTML = `
    <div class="alert-error">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
        <line x1="12" y1="9" x2="12" y2="13"></line>
        <line x1="12" y1="17" x2="12.01" y2="17"></line>
      </svg>
      <div class="alert-error-content">
        <div class="alert-error-title">${escapeHtml(title)}</div>
        <div>${escapeHtml(msg)}</div>
      </div>
    </div>
  `;
}

// ----------------------------------------------------
// Results Ledger & Filtering
// ----------------------------------------------------
function getFilteredResults() {
  const keyword = resultSearchInput.value.toLowerCase().trim();
  
  return jobResults.filter(r => {
    // Filter by Tab
    if (activeTab === 'flagged' && !r.flagged) return false;
    if (activeTab === 'safe' && r.flagged) return false;
    
    // Filter by Keyword Search
    if (keyword && !r.content.toLowerCase().includes(keyword)) return false;
    
    return true;
  });
}

function renderResultsToolbarTabs() {
  const allCount = jobResults.length;
  const flaggedCount = jobResults.filter(r => r.flagged).length;
  const safeCount = allCount - flaggedCount;
  
  tabAll.textContent = `All (${allCount})`;
  tabFlagged.textContent = `Flagged (${flaggedCount})`;
  tabSafe.textContent = `Safe (${safeCount})`;
}

function renderResultsLedger() {
  const filtered = getFilteredResults();
  
  if (filtered.length === 0) {
    resultsList.innerHTML = `
      <div class="empty-state">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"></circle>
          <line x1="8" y1="12" x2="16" y2="12"></line>
        </svg>
        <p>No matching tweets found.</p>
      </div>
    `;
    return;
  }
  
  resultsList.innerHTML = filtered.map(r => {
    const isFlagged = r.flagged;
    const statusClean = formatStatusLabel(r.status);
    const statusClass = isFlagged ? 'badge-failed' : 'badge-completed';
    
    let auditDetailsHtml = '';
    if (isFlagged) {
      auditDetailsHtml = `
        <div class="tweet-audit-info flagged">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="12" y1="8" x2="12" y2="12"></line>
            <line x1="12" y1="16" x2="12.01" y2="16"></line>
          </svg>
          <span><strong>Flagged Reason:</strong> <span class="tweet-audit-reason">${escapeHtml(r.reason || 'No reason supplied.')}</span></span>
        </div>
      `;
    } else {
      auditDetailsHtml = `
        <div class="tweet-audit-info safe">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
            <polyline points="22 4 12 14.01 9 11.01"></polyline>
          </svg>
          <span><strong>Audit Result:</strong> Safe to keep.</span>
        </div>
      `;
    }
    
    return `
      <div class="tweet-card">
        <div class="tweet-header">
          <a class="tweet-id-link" href="https://twitter.com/i/web/status/${r.tweet_id}" target="_blank" title="View tweet on Twitter/X">
            ID: ${r.tweet_id}
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
              <polyline points="15 3 21 3 21 9"></polyline>
              <line x1="10" y1="14" x2="21" y2="3"></line>
            </svg>
          </a>
          <span class="badge ${statusClass}">${statusClean}</span>
        </div>
        <div class="tweet-content">${escapeHtml(r.content)}</div>
        ${auditDetailsHtml}
      </div>
    `;
  }).join('');
}

function formatStatusLabel(status) {
  if (status === 'flagged_filter') return 'Flagged (Filter)';
  if (status === 'flagged_llm') return 'Flagged (AI)';
  if (status === 'safe') return 'Safe';
  if (status === 'skipped') return 'Skipped';
  if (status === 'pending_llm') return 'Pending LLM';
  return status;
}

// Tabs Listeners
[tabAll, tabFlagged, tabSafe].forEach(tab => {
  tab.addEventListener('click', (e) => {
    [tabAll, tabFlagged, tabSafe].forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    activeTab = tab.getAttribute('data-tab');
    renderResultsLedger();
  });
});

// Search filter input listener
resultSearchInput.addEventListener('input', () => {
  renderResultsLedger();
});

// ----------------------------------------------------
// CSV Export Generator
// ----------------------------------------------------
csvBtn.addEventListener('click', () => {
  if (jobResults.length === 0) return;
  
  const csvHeader = 'tweet_id,flagged,status,reason,content\n';
  const csvRows = jobResults.map(r => {
    const id = r.tweet_id;
    const flagged = r.flagged ? 'TRUE' : 'FALSE';
    const status = r.status;
    const reason = (r.reason || '').replace(/"/g, '""');
    const content = r.content.replace(/"/g, '""');
    return `${id},${flagged},${status},"${reason}","${content}"`;
  });
  
  const blob = new Blob([csvHeader + csvRows.join('\n')], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  const url = URL.createObjectURL(blob);
  link.setAttribute('href', url);
  link.setAttribute('download', `tweet_audit_${currentJobId}.csv`);
  link.style.visibility = 'hidden';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
});

// Helper functions
function escapeHtml(text) {
  if (!text) return '';
  const map = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;'
  };
  return text.replace(/[&<>"']/g, function(m) { return map[m]; });
}

// ----------------------------------------------------
// Initialization
// ----------------------------------------------------

// Wire form fields to update local storage state on changes
professionalCheck.addEventListener('change', saveStateToLocalStorage);
excludePolitics.addEventListener('change', saveStateToLocalStorage);
toneInput.addEventListener('input', saveStateToLocalStorage);
trackJobIdInput.addEventListener('input', saveStateToLocalStorage);

// Load preserved state (so changes/reloads in VS Code don't interrupt workflow)
window.addEventListener('DOMContentLoaded', () => {
  loadStateFromLocalStorage();
});

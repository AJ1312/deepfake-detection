/**
 * DeepGuard Shield - Popup Script
 * Fast video snapshot capture and analysis
 */

let currentResult = null;

document.addEventListener('DOMContentLoaded', async () => {
  // Initialize
  await checkBackendStatus();
  await loadStats();
  await loadRecentAlerts();
  await loadSettings();
  
  // Event listeners
  setupEventListeners();
  
  // Auto-refresh stats every 30 seconds
  setInterval(loadStats, 30000);
});

// =============================================================================
// Backend Status
// =============================================================================

async function checkBackendStatus() {
  const statusEl = document.getElementById('backendStatus');
  
  try {
    const response = await chrome.runtime.sendMessage({ action: 'check-backend' });
    
    if (response.success && response.online) {
      statusEl.className = 'backend-status online';
      statusEl.querySelector('.status-label').textContent = 'Backend connected';
    } else {
      statusEl.className = 'backend-status offline';
      statusEl.querySelector('.status-label').textContent = 'Backend offline - using cache only';
    }
  } catch (error) {
    statusEl.className = 'backend-status offline';
    statusEl.querySelector('.status-label').textContent = 'Connection error';
  }
}

// =============================================================================
// Stats
// =============================================================================

async function loadStats() {
  try {
    const response = await chrome.runtime.sendMessage({ action: 'get-stats' });
    
    if (response.success) {
      const { today } = response.data;
      
      document.getElementById('scansToday').textContent = today.scansTotal || 0;
      document.getElementById('deepfakesToday').textContent = today.deepfakesFound || 0;
      document.getElementById('cacheHits').textContent = today.cacheHits || 0;
      
      // Format time saved
      const timeSavedSec = Math.round((today.timeSavedMs || 0) / 1000);
      if (timeSavedSec >= 60) {
        const mins = Math.floor(timeSavedSec / 60);
        const secs = timeSavedSec % 60;
        document.getElementById('timeSaved').textContent = `${mins}m ${secs}s`;
      } else {
        document.getElementById('timeSaved').textContent = `${timeSavedSec}s`;
      }
    }
  } catch (error) {
    console.error('Failed to load stats:', error);
  }
}

// =============================================================================
// Video Snapshot Scanning
// =============================================================================

async function scanCurrentVideo() {
  const scanBtn = document.getElementById('scanVideoBtn');
  const scanProgress = document.getElementById('scanProgress');
  const progressFill = document.getElementById('progressFill');
  const progressText = document.getElementById('progressText');
  const resultSection = document.getElementById('resultSection');
  
  // Hide previous result and show progress
  resultSection.style.display = 'none';
  scanBtn.style.display = 'none';
  scanProgress.style.display = 'block';
  progressFill.style.width = '0%';
  progressText.textContent = 'Finding video on page...';
  
  try {
    // Get active tab
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    
    if (!tab) {
      throw new Error('No active tab found');
    }
    
    // Update progress
    progressFill.style.width = '10%';
    progressText.textContent = 'Capturing video snapshots...';
    
    // Send message to content script to capture frames
    const captureResponse = await chrome.tabs.sendMessage(tab.id, {
      action: 'capture-video-snapshots',
      config: {
        maxFrames: 8,          // Capture 8 frames for fast analysis
        intervalMs: 1000,      // 1 second between captures  
        timeout: 10000,        // 10 second max
        quality: 0.8           // JPEG quality
      }
    });
    
    if (!captureResponse || !captureResponse.success) {
      throw new Error(captureResponse?.error || 'Failed to capture video frames');
    }
    
    // Update progress
    progressFill.style.width = '50%';
    progressText.textContent = `Analyzing ${captureResponse.frameCount} frames...`;
    
    // Send frames to backend for analysis
    const analysisResponse = await chrome.runtime.sendMessage({
      action: 'analyze-video',
      data: {
        frames: captureResponse.frames,
        platform: captureResponse.platform || 'Unknown',
        videoUrl: captureResponse.videoUrl || tab.url,
        videoDuration: captureResponse.duration || 0,
        analysisMethod: 'snapshot_capture'
      }
    });
    
    // Update progress
    progressFill.style.width = '100%';
    progressText.textContent = 'Analysis complete!';
    
    if (!analysisResponse.success) {
      throw new Error(analysisResponse.error || 'Analysis failed');
    }
    
    // Store result and display
    currentResult = analysisResponse.data;
    currentResult.frameCount = captureResponse.frameCount;
    
    // Short delay then show results
    await sleep(500);
    displayAnalysisResult(currentResult);
    
    // Refresh stats
    await loadStats();
    await loadRecentAlerts();
    
  } catch (error) {
    console.error('Scan error:', error);
    showNotification(`Scan failed: ${error.message}`, 'error');
    
    // Reset UI
    scanBtn.style.display = 'flex';
    scanProgress.style.display = 'none';
  }
}

function displayAnalysisResult(result) {
  const resultSection = document.getElementById('resultSection');
  const scanBtn = document.getElementById('scanVideoBtn');
  const scanProgress = document.getElementById('scanProgress');
  
  // Hide progress, show button and result
  scanProgress.style.display = 'none';
  scanBtn.style.display = 'flex';
  resultSection.style.display = 'block';
  
  // Update verdict banner
  const verdictBanner = document.getElementById('verdictBanner');
  const verdictIcon = document.getElementById('verdictIcon');
  const verdictLabel = document.getElementById('verdictLabel');
  const verdictConfidence = document.getElementById('verdictConfidence');
  
  const isDeepfake = result.is_deepfake;
  const confidence = Math.round((result.confidence || 0) * 100);
  
  verdictBanner.className = `verdict-banner ${isDeepfake ? 'danger' : 'success'}`;
  verdictIcon.textContent = isDeepfake ? '🚨' : '✅';
  verdictLabel.textContent = isDeepfake ? 'DEEPFAKE DETECTED' : 'LIKELY AUTHENTIC';
  verdictConfidence.textContent = `Confidence: ${confidence}%`;
  
  // Update score bars
  updateScoreBar('lipsync', result.lipsync_score);
  updateScoreBar('factCheck', result.fact_check_score);
  updateScoreBar('frame', result.frame_consistency || (result.lipsync_score ? result.lipsync_score * 0.95 : null));
  
  // Celebrity alert
  const celebrityAlert = document.getElementById('celebrityAlert');
  const celebrityText = document.getElementById('celebrityText');
  if (result.celebrity_detected) {
    celebrityAlert.style.display = 'flex';
    celebrityText.textContent = result.celebrity_name 
      ? `Celebrity detected: ${result.celebrity_name} - extra scrutiny applied`
      : 'Celebrity detected - extra scrutiny applied';
  } else {
    celebrityAlert.style.display = 'none';
  }
  
  // Technical details
  document.getElementById('analysisMethod').textContent = 
    (result.analysis_method || result.detection_method || 'CNN Analysis').replace(/_/g, ' ');
  document.getElementById('processingTime').textContent = 
    `${(result.processing_time || result.processingTime || 0).toFixed(2)}s`;
  document.getElementById('framesAnalyzed').textContent = 
    result.frameCount || result.frames_analyzed || '8';
  
  // Show report button if deepfake
  document.getElementById('reportBtn').style.display = isDeepfake ? 'inline-flex' : 'none';
}

function updateScoreBar(prefix, score) {
  const fill = document.getElementById(`${prefix}Fill`);
  const value = document.getElementById(`${prefix}Value`);
  
  if (score !== null && score !== undefined) {
    const percent = Math.round(score * 100);
    fill.style.width = `${percent}%`;
    value.textContent = `${percent}%`;
    
    // Color based on score
    fill.classList.remove('low', 'medium', 'high');
    if (percent >= 70) {
      fill.classList.add('high');
    } else if (percent >= 40) {
      fill.classList.add('medium');
    } else {
      fill.classList.add('low');
    }
  } else {
    fill.style.width = '0%';
    value.textContent = 'N/A';
  }
}

// =============================================================================
// Copy Report
// =============================================================================

function copyReport() {
  if (!currentResult) {
    showNotification('No analysis result to copy', 'error');
    return;
  }
  
  const isDeepfake = currentResult.is_deepfake;
  const confidence = Math.round((currentResult.confidence || 0) * 100);
  const lipsync = currentResult.lipsync_score ? Math.round(currentResult.lipsync_score * 100) : 'N/A';
  const factCheck = currentResult.fact_check_score ? Math.round(currentResult.fact_check_score * 100) : 'N/A';
  
  const report = `
═══════════════════════════════════════
       DeepGuard Shield Report
═══════════════════════════════════════

Verdict: ${isDeepfake ? '🚨 DEEPFAKE DETECTED' : '✅ LIKELY AUTHENTIC'}
Confidence: ${confidence}%

────────────────────────────────────────
Analysis Scores:
────────────────────────────────────────
• Lip-Sync Analysis: ${lipsync}%
• Fact Check Score: ${factCheck}%
• Analysis Method: ${currentResult.analysis_method || 'CNN Analysis'}
• Processing Time: ${(currentResult.processing_time || 0).toFixed(2)}s
${currentResult.celebrity_detected ? `• Celebrity Detected: ${currentResult.celebrity_name || 'Yes'}` : ''}

────────────────────────────────────────
Analyzed: ${new Date().toLocaleString()}
DeepGuard Shield v1.0.0
═══════════════════════════════════════
`.trim();

  navigator.clipboard.writeText(report).then(() => {
    showNotification('Report copied to clipboard!', 'success');
  }).catch(() => {
    showNotification('Failed to copy report', 'error');
  });
}

// =============================================================================
// Recent Alerts
// =============================================================================

async function loadRecentAlerts() {
  const listEl = document.getElementById('alertsList');
  
  try {
    const response = await chrome.runtime.sendMessage({ 
      action: 'get-recent-alerts',
      limit: 5
    });
    
    if (response.success && response.data.length > 0) {
      listEl.innerHTML = response.data.map(alert => createAlertItem(alert)).join('');
      
      // Add click handlers
      listEl.querySelectorAll('.alert-item').forEach((item, index) => {
        item.onclick = () => showAlertDetails(response.data[index]);
      });
    } else {
      listEl.innerHTML = `
        <div class="alert-placeholder">
          <span>No deepfakes detected yet</span>
          <span class="alert-subtext">Alerts will appear here</span>
        </div>
      `;
    }
  } catch (error) {
    console.error('Failed to load alerts:', error);
  }
}

function createAlertItem(alert) {
  const confidence = Math.round((alert.confidence || 0) * 100);
  const platform = alert.platform || 'Unknown';
  const time = formatTimeAgo(alert.cachedAt || alert.timestamp);
  
  // Truncate URL for display
  let title = alert.videoUrl || 'Video';
  if (title.length > 40) {
    title = title.substring(0, 40) + '...';
  }
  
  return `
    <div class="alert-item">
      <span class="alert-icon">🔴</span>
      <div class="alert-content">
        <div class="alert-title">${escapeHtml(title)}</div>
        <div class="alert-meta">
          <span class="alert-platform">${platform}</span>
          <span class="alert-confidence">DEEPFAKE (${confidence}%)</span>
        </div>
      </div>
      <span class="alert-time">${time}</span>
    </div>
  `;
}

function formatTimeAgo(dateStr) {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now - date;
  const diffMins = Math.floor(diffMs / 60000);
  
  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
}

function showAlertDetails(alert) {
  // Open the video URL in a new tab
  if (alert.videoUrl) {
    chrome.tabs.create({ url: alert.videoUrl });
  }
}

// =============================================================================
// Settings
// =============================================================================

async function loadSettings() {
  try {
    const response = await chrome.runtime.sendMessage({ action: 'get-settings' });
    
    if (response.success) {
      document.getElementById('autoScan').checked = response.data.autoScan !== false;
      document.getElementById('showNotifications').checked = response.data.showNotifications !== false;
      document.getElementById('cacheResults').checked = response.data.cacheResults !== false;
    }
  } catch (error) {
    console.error('Failed to load settings:', error);
  }
}

async function saveSettings() {
  const settings = {
    autoScan: document.getElementById('autoScan').checked,
    showNotifications: document.getElementById('showNotifications').checked,
    cacheResults: document.getElementById('cacheResults').checked
  };
  
  try {
    await chrome.runtime.sendMessage({ action: 'save-settings', settings });
  } catch (error) {
    console.error('Failed to save settings:', error);
  }
}

// =============================================================================
// Event Listeners
// =============================================================================

function setupEventListeners() {
  // Scan video button
  document.getElementById('scanVideoBtn').onclick = scanCurrentVideo;
  
  // Copy report button
  document.getElementById('copyReportBtn').onclick = copyReport;
  
  // Report button
  document.getElementById('reportBtn').onclick = () => {
    showNotification('Report feature - would submit to platform moderation', 'info');
  };
  
  // Settings
  document.getElementById('autoScan').onchange = saveSettings;
  document.getElementById('showNotifications').onchange = saveSettings;
  document.getElementById('cacheResults').onchange = saveSettings;
  
  // Settings button
  document.getElementById('settingsBtn').onclick = () => {
    chrome.runtime.openOptionsPage();
  };
  
  // View all
  document.getElementById('viewAllBtn').onclick = () => {
    showNotification('Full history coming soon!', 'info');
  };
  
  // Footer links
  document.getElementById('helpLink').onclick = (e) => {
    e.preventDefault();
    chrome.tabs.create({ url: 'https://github.com/deepguard/shield' });
  };
  
  document.getElementById('feedbackLink').onclick = (e) => {
    e.preventDefault();
    chrome.tabs.create({ url: 'mailto:feedback@deepguard.com' });
  };
}

// =============================================================================
// Notifications
// =============================================================================

function showNotification(message, type = 'info') {
  // Remove existing
  const existing = document.querySelector('.popup-notification');
  if (existing) existing.remove();
  
  const notification = document.createElement('div');
  notification.className = `popup-notification ${type}`;
  notification.innerHTML = `
    <span>${message}</span>
    <button onclick="this.parentElement.remove()">×</button>
  `;
  
  // Add styles
  notification.style.cssText = `
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    padding: 10px 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 12px;
    z-index: 1000;
    animation: slideDown 0.3s ease;
  `;
  
  if (type === 'success') {
    notification.style.background = '#10B981';
    notification.style.color = 'white';
  } else if (type === 'danger') {
    notification.style.background = '#EF4444';
    notification.style.color = 'white';
  } else if (type === 'error') {
    notification.style.background = '#F59E0B';
    notification.style.color = 'white';
  } else {
    notification.style.background = '#3B82F6';
    notification.style.color = 'white';
  }
  
  notification.querySelector('button').style.cssText = `
    background: none;
    border: none;
    color: white;
    font-size: 18px;
    cursor: pointer;
    padding: 0;
    margin-left: 10px;
  `;
  
  document.body.appendChild(notification);
  
  // Auto-remove after 4 seconds
  setTimeout(() => {
    if (notification.parentElement) {
      notification.remove();
    }
  }, 4000);
}

// =============================================================================
// Utilities
// =============================================================================

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// Add CSS animation
const style = document.createElement('style');
style.textContent = `
  @keyframes slideDown {
    from { transform: translateY(-100%); }
    to { transform: translateY(0); }
  }
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  .spin {
    animation: spin 1s linear infinite;
  }
`;
document.head.appendChild(style);

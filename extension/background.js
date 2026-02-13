/**
 * DeepGuard Shield - Background Service Worker
 * 
 * Handles:
 * - API communication with DeepGuard backend
 * - Local caching of results in IndexedDB
 * - Context menu integration
 * - Browser notifications
 * - Stats tracking
 */

// =============================================================================
// Configuration
// =============================================================================

const CONFIG = {
  API_BASE_URL: 'http://localhost:5001',
  CACHE_EXPIRY_DAYS: 30,
  MAX_CACHE_ENTRIES: 10000,
  NOTIFICATION_TIMEOUT: 10000,
  // Timeout and retry settings
  API_TIMEOUT_MS: 30000,      // 30 second timeout
  MAX_RETRIES: 3,             // Max retry attempts
  RETRY_DELAY_MS: 1000,       // Initial retry delay (doubles each retry)
  // Thumbnail analysis settings
  THUMBNAIL_TIMEOUT_MS: 5000  // 5 second timeout for thumbnail fetch
};

// =============================================================================
// Fetch with Timeout and Retry
// =============================================================================

/**
 * Fetch with automatic timeout using AbortController
 */
async function fetchWithTimeout(url, options = {}, timeoutMs = CONFIG.API_TIMEOUT_MS) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  
  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal
    });
    return response;
  } finally {
    clearTimeout(timeout);
  }
}

/**
 * Fetch with exponential backoff retry
 */
async function fetchWithRetry(url, options = {}, maxRetries = CONFIG.MAX_RETRIES) {
  let lastError;
  let delay = CONFIG.RETRY_DELAY_MS;
  
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const response = await fetchWithTimeout(url, options);
      
      // Retry on server errors (5xx)
      if (response.status >= 500 && attempt < maxRetries) {
        console.log(`🔄 Server error ${response.status}, retrying in ${delay}ms...`);
        await sleep(delay);
        delay *= 2; // Exponential backoff
        continue;
      }
      
      return response;
    } catch (error) {
      lastError = error;
      
      // Don't retry on abort (timeout)
      if (error.name === 'AbortError') {
        console.log(`⏱️ Request timeout after ${CONFIG.API_TIMEOUT_MS}ms`);
        if (attempt < maxRetries) {
          console.log(`🔄 Retrying (${attempt + 1}/${maxRetries})...`);
          await sleep(delay);
          delay *= 2;
          continue;
        }
      }
      
      // Retry on network errors
      if (attempt < maxRetries) {
        console.log(`🔄 Network error, retrying in ${delay}ms...`);
        await sleep(delay);
        delay *= 2;
        continue;
      }
    }
  }
  
  throw lastError || new Error('Max retries exceeded');
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// =============================================================================
// IndexedDB Cache Manager
// =============================================================================

class CacheManager {
  constructor() {
    this.dbName = 'DeepGuardCache';
    this.dbVersion = 1;
    this.db = null;
  }

  async init() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(this.dbName, this.dbVersion);
      
      request.onerror = () => reject(request.error);
      request.onsuccess = () => {
        this.db = request.result;
        resolve();
      };
      
      request.onupgradeneeded = (event) => {
        const db = event.target.result;
        
        // Video results store
        if (!db.objectStoreNames.contains('results')) {
          const store = db.createObjectStore('results', { keyPath: 'videoHash' });
          store.createIndex('timestamp', 'timestamp');
          store.createIndex('isDeepfake', 'isDeepfake');
        }
        
        // Stats store
        if (!db.objectStoreNames.contains('stats')) {
          db.createObjectStore('stats', { keyPath: 'date' });
        }
      };
    });
  }

  async getResult(videoHash) {
    if (!this.db) await this.init();
    
    return new Promise((resolve, reject) => {
      const tx = this.db.transaction('results', 'readonly');
      const store = tx.objectStore('results');
      const request = store.get(videoHash);
      
      request.onsuccess = () => resolve(request.result || null);
      request.onerror = () => reject(request.error);
    });
  }

  async storeResult(videoHash, result) {
    if (!this.db) await this.init();
    
    return new Promise((resolve, reject) => {
      const tx = this.db.transaction('results', 'readwrite');
      const store = tx.objectStore('results');
      
      const entry = {
        videoHash,
        ...result,
        cachedAt: new Date().toISOString()
      };
      
      const request = store.put(entry);
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  }

  async getAllResults() {
    if (!this.db) await this.init();
    
    return new Promise((resolve, reject) => {
      const tx = this.db.transaction('results', 'readonly');
      const store = tx.objectStore('results');
      const request = store.getAll();
      
      request.onsuccess = () => resolve(request.result || []);
      request.onerror = () => reject(request.error);
    });
  }

  async getRecentAlerts(limit = 10) {
    const all = await this.getAllResults();
    return all
      .filter(r => r.isDeepfake)
      .sort((a, b) => new Date(b.cachedAt) - new Date(a.cachedAt))
      .slice(0, limit);
  }

  async cleanup(maxAgeDays = 30) {
    if (!this.db) await this.init();
    
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - maxAgeDays);
    
    return new Promise((resolve, reject) => {
      const tx = this.db.transaction('results', 'readwrite');
      const store = tx.objectStore('results');
      const index = store.index('timestamp');
      const range = IDBKeyRange.upperBound(cutoff.toISOString());
      
      const request = index.openCursor(range);
      let deleted = 0;
      
      request.onsuccess = (event) => {
        const cursor = event.target.result;
        if (cursor) {
          cursor.delete();
          deleted++;
          cursor.continue();
        } else {
          resolve(deleted);
        }
      };
      
      request.onerror = () => reject(request.error);
    });
  }
}

// =============================================================================
// Stats Manager
// =============================================================================

class StatsManager {
  async getToday() {
    const today = new Date().toISOString().split('T')[0];
    const result = await chrome.storage.local.get(['stats']);
    const stats = result.stats || {};
    
    return stats[today] || {
      scansTotal: 0,
      deepfakesFound: 0,
      cacheHits: 0,
      timeSavedMs: 0
    };
  }

  async increment(field, value = 1) {
    const today = new Date().toISOString().split('T')[0];
    const result = await chrome.storage.local.get(['stats']);
    const stats = result.stats || {};
    
    if (!stats[today]) {
      stats[today] = {
        scansTotal: 0,
        deepfakesFound: 0,
        cacheHits: 0,
        timeSavedMs: 0
      };
    }
    
    stats[today][field] += value;
    await chrome.storage.local.set({ stats });
    
    return stats[today];
  }

  async getWeekly() {
    const result = await chrome.storage.local.get(['stats']);
    const stats = result.stats || {};
    
    const weekAgo = new Date();
    weekAgo.setDate(weekAgo.getDate() - 7);
    
    let weekly = {
      scansTotal: 0,
      deepfakesFound: 0,
      cacheHits: 0,
      timeSavedMs: 0
    };
    
    Object.entries(stats).forEach(([date, dayStats]) => {
      if (new Date(date) >= weekAgo) {
        weekly.scansTotal += dayStats.scansTotal || 0;
        weekly.deepfakesFound += dayStats.deepfakesFound || 0;
        weekly.cacheHits += dayStats.cacheHits || 0;
        weekly.timeSavedMs += dayStats.timeSavedMs || 0;
      }
    });
    
    return weekly;
  }
}

// =============================================================================
// API Client
// =============================================================================

class APIClient {
  constructor(baseUrl) {
    this.baseUrl = baseUrl;
  }

  async checkHealth() {
    try {
      const response = await fetchWithTimeout(`${this.baseUrl}/api/health`, {}, 5000);
      return response.ok;
    } catch {
      return false;
    }
  }

  async analyzeVideo(videoBlob, filename, platform) {
    const formData = new FormData();
    formData.append('video', videoBlob, filename);
    formData.append('platform', platform);
    
    const response = await fetchWithRetry(`${this.baseUrl}/api/analyze`, {
      method: 'POST',
      body: formData
    });
    
    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }
    
    return await response.json();
  }

  async analyzeVideoUrl(videoUrl, platform, options = {}) {
    const response = await fetchWithRetry(`${this.baseUrl}/api/extension/analyze-url`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        url: videoUrl,
        platform: platform,
        thumbnail_url: options.thumbnailUrl,
        video_duration: options.videoDuration
      })
    });
    
    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }
    
    return await response.json();
  }

  /**
   * Analyze video frames (new endpoint for frame-based analysis)
   */
  async analyzeFrames(frames, options = {}) {
    const response = await fetchWithRetry(`${this.baseUrl}/api/extension/analyze-frames`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        frames: frames,  // Array of base64 JPEGs
        platform: options.platform,
        video_url: options.videoUrl,
        video_duration: options.videoDuration,
        analysis_method: options.analysisMethod
      })
    });
    
    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }
    
    return await response.json();
  }

  /**
   * Analyze YouTube thumbnail for quick pre-check
   */
  async analyzeThumbnail(thumbnailUrl, videoUrl) {
    try {
      const response = await fetchWithTimeout(`${this.baseUrl}/api/extension/analyze-thumbnail`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          thumbnail_url: thumbnailUrl,
          video_url: videoUrl
        })
      }, CONFIG.THUMBNAIL_TIMEOUT_MS);
      
      if (!response.ok) {
        return null; // Thumbnail analysis failed, will proceed with full analysis
      }
      
      return await response.json();
    } catch {
      return null; // Ignore thumbnail errors
    }
  }

  async checkHash(videoHash) {
    const response = await fetchWithRetry(`${this.baseUrl}/api/extension/check-hash`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ hash: videoHash })
    });
    
    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }
    
    return await response.json();
  }
}

// =============================================================================
// Initialize Managers
// =============================================================================

const cache = new CacheManager();
const stats = new StatsManager();
const api = new APIClient(CONFIG.API_BASE_URL);

// =============================================================================
// Context Menu Setup
// =============================================================================

chrome.runtime.onInstalled.addListener(async () => {
  // Initialize cache
  await cache.init();
  
  // Create context menus
  chrome.contextMenus.create({
    id: 'deepguard-check',
    title: '🛡️ Check for deepfake',
    contexts: ['video', 'link']
  });
  
  chrome.contextMenus.create({
    id: 'deepguard-report',
    title: '🚨 Report as deepfake',
    contexts: ['video']
  });
  
  // Set initial badge
  chrome.action.setBadgeBackgroundColor({ color: '#10B981' });
  chrome.action.setBadgeText({ text: '' });
  
  console.log('🛡️ DeepGuard Shield installed and ready');
});

// Handle context menu clicks
chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === 'deepguard-check') {
    const videoUrl = info.srcUrl || info.linkUrl || info.pageUrl;
    
    // Send message to content script
    chrome.tabs.sendMessage(tab.id, {
      action: 'analyze-video-url',
      url: videoUrl
    });
  }
  
  if (info.menuItemId === 'deepguard-report') {
    // Open report form
    chrome.tabs.sendMessage(tab.id, {
      action: 'report-video',
      url: info.srcUrl
    });
  }
});

// =============================================================================
// Message Handler
// =============================================================================

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  handleMessage(request, sender)
    .then(response => sendResponse(response))
    .catch(error => sendResponse({ success: false, error: error.message }));
  
  return true; // Keep channel open for async response
});

async function handleMessage(request, sender) {
  console.log('📨 Message received:', request.action);
  
  switch (request.action) {
    case 'analyze-video':
      return await handleAnalyzeVideo(request.data);
    
    case 'check-hash':
      return await handleCheckHash(request.hash);
    
    case 'get-stats':
      return await handleGetStats();
    
    case 'get-recent-alerts':
      return await handleGetRecentAlerts(request.limit);
    
    case 'get-settings':
      return await handleGetSettings();
    
    case 'save-settings':
      return await handleSaveSettings(request.settings);
    
    case 'check-backend':
      return await handleCheckBackend();
    
    case 'update-badge':
      return await handleUpdateBadge(request.data);
    
    default:
      throw new Error(`Unknown action: ${request.action}`);
  }
}

// =============================================================================
// Message Handlers
// =============================================================================

async function handleAnalyzeVideo(data) {
  const { videoUrl, videoBlob, platform, filename, frames, thumbnailUrl, analysisMethod, videoDuration } = data;
  const startTime = Date.now();
  
  try {
    // Increment scan count
    await stats.increment('scansTotal');
    
    let result;
    const urlHash = videoUrl ? await hashString(videoUrl) : null;
    
    // Check local cache first
    if (urlHash) {
      const cached = await cache.getResult(urlHash);
      if (cached) {
        console.log('✅ Local cache hit');
        await stats.increment('cacheHits');
        await stats.increment('timeSavedMs', 3000);
        
        return {
          success: true,
          data: {
            ...cached,
            detectionMethod: 'cached_local',
            processingTime: (Date.now() - startTime) / 1000
          }
        };
      }
    }
    
    // For YouTube, try quick thumbnail pre-check
    if (thumbnailUrl && platform === 'YouTube') {
      console.log('🖼️ Trying thumbnail pre-check...');
      const thumbnailResult = await api.analyzeThumbnail(thumbnailUrl, videoUrl);
      
      if (thumbnailResult?.success && thumbnailResult.high_confidence) {
        console.log('✅ Thumbnail analysis conclusive');
        result = thumbnailResult;
        result.result.analysis_method = 'thumbnail_quick';
      }
    }
    
    // If no thumbnail result or inconclusive, try frame-based analysis
    if (!result && frames && frames.length > 0) {
      console.log(`🎞️ Analyzing ${frames.length} captured frames...`);
      try {
        result = await api.analyzeFrames(frames, {
          platform,
          videoUrl,
          videoDuration,
          analysisMethod
        });
        if (result.success) {
          result.result.analysis_method = analysisMethod || 'frames';
        }
      } catch (e) {
        console.log('Frame analysis failed:', e.message);
      }
    }
    
    // Fallback to URL-based analysis
    if (!result) {
      console.log('🔗 Falling back to URL analysis...');
      try {
        result = await api.analyzeVideoUrl(videoUrl, platform, {
          thumbnailUrl,
          videoDuration
        });
        if (result.success) {
          result.result.analysis_method = 'url_fallback';
        }
      } catch (e) {
        console.log('URL analysis failed:', e.message);
        if (videoBlob) {
          result = await api.analyzeVideo(videoBlob, filename || 'video.mp4', platform);
        } else {
          throw e;
        }
      }
    }
    
    if (result?.success) {
      const videoHash = result.result?.video_hash || urlHash || await hashString(Date.now().toString());
      
      // Store in cache
      await cache.storeResult(videoHash, {
        ...result.result,
        videoUrl,
        platform,
        timestamp: new Date().toISOString()
      });
      
      // Track deepfake detection
      if (result.result?.is_deepfake) {
        await stats.increment('deepfakesFound');
        await showDeepfakeNotification(result.result, platform);
        await updateBadgeForDeepfake();
      }
      
      return {
        success: true,
        data: {
          ...result.result,
          processingTime: (Date.now() - startTime) / 1000
        }
      };
    }
    
    return result || { success: false, error: 'Analysis failed' };
    
  } catch (error) {
    console.error('Analysis error:', error);
    return {
      success: false,
      error: error.message || 'Unknown error occurred'
    };
  }
}

async function handleCheckHash(hash) {
  // Check local cache first
  const local = await cache.getResult(hash);
  if (local) {
    return { success: true, matchFound: true, result: local, source: 'local' };
  }
  
  // Check backend
  try {
    const result = await api.checkHash(hash);
    if (result.match_found) {
      await cache.storeResult(hash, result.result);
    }
    return { success: true, ...result };
  } catch (error) {
    return { success: false, error: error.message };
  }
}

async function handleGetStats() {
  const today = await stats.getToday();
  const weekly = await stats.getWeekly();
  const allResults = await cache.getAllResults();
  
  return {
    success: true,
    data: {
      today,
      weekly,
      totalCached: allResults.length,
      totalDeepfakes: allResults.filter(r => r.isDeepfake || r.is_deepfake).length
    }
  };
}

async function handleGetRecentAlerts(limit = 10) {
  const allResults = await cache.getAllResults();
  const alerts = allResults
    .filter(r => r.isDeepfake || r.is_deepfake)
    .sort((a, b) => new Date(b.cachedAt || b.timestamp) - new Date(a.cachedAt || a.timestamp))
    .slice(0, limit);
  
  return { success: true, data: alerts };
}

async function handleGetSettings() {
  const result = await chrome.storage.sync.get([
    'autoScan',
    'showNotifications',
    'cacheResults',
    'apiUrl'
  ]);
  
  return {
    success: true,
    data: {
      autoScan: result.autoScan !== false,
      showNotifications: result.showNotifications !== false,
      cacheResults: result.cacheResults !== false,
      apiUrl: result.apiUrl || CONFIG.API_BASE_URL
    }
  };
}

async function handleSaveSettings(settings) {
  await chrome.storage.sync.set(settings);
  return { success: true };
}

async function handleCheckBackend() {
  const isOnline = await api.checkHealth();
  return { success: true, online: isOnline };
}

async function handleUpdateBadge(data) {
  if (data.deepfakeCount > 0) {
    chrome.action.setBadgeBackgroundColor({ color: '#EF4444' });
    chrome.action.setBadgeText({ text: data.deepfakeCount.toString() });
  } else {
    chrome.action.setBadgeBackgroundColor({ color: '#10B981' });
    chrome.action.setBadgeText({ text: '' });
  }
  return { success: true };
}

// =============================================================================
// Notifications
// =============================================================================

async function showDeepfakeNotification(result, platform) {
  const settings = await chrome.storage.sync.get(['showNotifications']);
  if (settings.showNotifications === false) return;
  
  const confidence = Math.round((result.confidence || 0) * 100);
  
  chrome.notifications.create({
    type: 'basic',
    iconUrl: chrome.runtime.getURL('icons/icon-128.png'),
    title: '🚨 Deepfake Detected!',
    message: `A video on ${platform || 'this page'} appears to be manipulated (${confidence}% confidence). Click to view details.`,
    priority: 2,
    requireInteraction: true
  });
}

async function updateBadgeForDeepfake() {
  const todayStats = await stats.getToday();
  chrome.action.setBadgeBackgroundColor({ color: '#EF4444' });
  chrome.action.setBadgeText({ text: todayStats.deepfakesFound.toString() });
}

// =============================================================================
// Utility Functions
// =============================================================================

async function hashString(str) {
  const encoder = new TextEncoder();
  const data = encoder.encode(str);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

// =============================================================================
// Periodic Cleanup
// =============================================================================

chrome.alarms.create('cleanup', { periodInMinutes: 1440 }); // Once per day

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === 'cleanup') {
    console.log('🧹 Running cache cleanup...');
    const deleted = await cache.cleanup(CONFIG.CACHE_EXPIRY_DAYS);
    console.log(`🧹 Deleted ${deleted} old cache entries`);
  }
});

// =============================================================================
// Badge Reset at Midnight
// =============================================================================

chrome.alarms.create('resetBadge', { periodInMinutes: 60 });

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === 'resetBadge') {
    const now = new Date();
    if (now.getHours() === 0 && now.getMinutes() < 60) {
      chrome.action.setBadgeText({ text: '' });
      chrome.action.setBadgeBackgroundColor({ color: '#10B981' });
    }
  }
});

console.log('🛡️ DeepGuard Shield background service worker loaded');

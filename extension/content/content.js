/**
 * DeepGuard Shield - Content Script
 * 
 * Detects videos on social media pages and provides deepfake analysis overlays.
 * Supports: Twitter/X, Facebook, YouTube, TikTok, Instagram, Reddit, LinkedIn
 */

// =============================================================================
// Configuration
// =============================================================================

const SAMPLING_CONFIG = {
  // Frame sampling based on video duration
  strategies: {
    short: { maxDuration: 30, intervalSec: 3, maxFrames: 10 },      // < 30s
    medium: { maxDuration: 300, intervalSec: 10, maxFrames: 15 },   // 30s - 5min
    long: { maxDuration: Infinity, intervalSec: 30, maxFrames: 12 } // > 5min
  },
  frameQuality: 0.7,  // JPEG quality (0-1)
  frameWidth: 640,    // Max width for captured frames
  captureTimeout: 15000, // 15s max for frame capture
  analysisTimeout: 30000 // 30s max for API analysis
};

const PLATFORM_SELECTORS = {
  'twitter.com': {
    video: 'video[src*="video"], video[poster]',
    container: '[data-testid="tweet"], article',
    platform: 'Twitter'
  },
  'x.com': {
    video: 'video[src*="video"], video[poster]',
    container: '[data-testid="tweet"], article',
    platform: 'X'
  },
  'facebook.com': {
    video: 'video[src], video[data-video-id]',
    container: '[data-pagelet*="FeedUnit"], [role="article"]',
    platform: 'Facebook'
  },
  'youtube.com': {
    video: 'video.html5-main-video, video.video-stream',
    container: '#movie_player, ytd-player',
    platform: 'YouTube'
  },
  'tiktok.com': {
    video: 'video[playsinline]',
    container: '[data-e2e="recommend-list-item-container"], [class*="DivVideoContainer"]',
    platform: 'TikTok'
  },
  'instagram.com': {
    video: 'video[src], video[playsinline]',
    container: 'article, [role="presentation"]',
    platform: 'Instagram'
  },
  'reddit.com': {
    video: 'video[src*="v.redd.it"], shreddit-player video',
    container: 'shreddit-post, [data-testid="post-container"]',
    platform: 'Reddit'
  },
  'linkedin.com': {
    video: 'video[src]',
    container: '[data-urn*="activity"], .feed-shared-update-v2',
    platform: 'LinkedIn'
  }
};

// =============================================================================
// Video Detector Class
// =============================================================================

class VideoDetector {
  constructor() {
    this.platform = this.detectPlatform();
    this.config = PLATFORM_SELECTORS[this.platform] || null;
    this.analyzedVideos = new Map(); // videoId -> status
    this.observer = null;
    this.settings = {
      autoScan: true,
      showOverlay: true
    };
    
    this.init();
  }

  detectPlatform() {
    const hostname = window.location.hostname.replace('www.', '');
    for (const domain of Object.keys(PLATFORM_SELECTORS)) {
      if (hostname.includes(domain.replace('www.', ''))) {
        return domain;
      }
    }
    return null;
  }

  async init() {
    if (!this.config) {
      console.log('🛡️ DeepGuard: Platform not supported');
      return;
    }

    // Load settings
    await this.loadSettings();
    
    // Initial scan
    this.scanPage();
    
    // Watch for new videos
    this.setupObserver();
    
    // Listen for messages from background
    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
      this.handleMessage(request).then(sendResponse);
      return true;
    });

    console.log(`🛡️ DeepGuard Shield active on ${this.config.platform}`);
  }

  async loadSettings() {
    try {
      const response = await chrome.runtime.sendMessage({ action: 'get-settings' });
      if (response.success) {
        this.settings = { ...this.settings, ...response.data };
      }
    } catch (e) {
      console.log('Failed to load settings:', e);
    }
  }

  setupObserver() {
    this.observer = new MutationObserver((mutations) => {
      // Debounce rapid DOM changes
      clearTimeout(this.scanTimeout);
      this.scanTimeout = setTimeout(() => this.scanPage(), 500);
    });

    this.observer.observe(document.body, {
      childList: true,
      subtree: true
    });
  }

  scanPage() {
    if (!this.config) return;

    const videos = document.querySelectorAll(this.config.video);
    
    videos.forEach(video => {
      const videoId = this.getVideoId(video);
      
      if (!this.analyzedVideos.has(videoId)) {
        this.processVideo(video, videoId);
      }
    });
  }

  getVideoId(video) {
    // Try various attributes to get stable ID
    return video.src || 
           video.currentSrc || 
           video.dataset.videoId ||
           video.poster ||
           `video-${Math.random().toString(36).substr(2, 9)}`;
  }

  async processVideo(video, videoId) {
    // Mark as processing
    this.analyzedVideos.set(videoId, 'processing');

    // Find container
    const container = this.findContainer(video);
    if (!container) {
      this.analyzedVideos.set(videoId, 'no-container');
      return;
    }

    // Create overlay
    const overlay = new VideoOverlay(container, video);

    if (this.settings.autoScan) {
      // Auto-analyze
      overlay.showLoading();
      
      try {
        const result = await this.analyzeVideo(video, videoId);
        overlay.showResult(result);
        this.analyzedVideos.set(videoId, result.is_deepfake ? 'deepfake' : 'authentic');
      } catch (error) {
        console.error('Analysis error:', error);
        overlay.showError(error.message);
        this.analyzedVideos.set(videoId, 'error');
      }
    } else {
      // Show scan button
      overlay.showScanButton(() => this.manualScan(video, videoId, overlay));
      this.analyzedVideos.set(videoId, 'pending');
    }
  }

  findContainer(video) {
    if (!this.config) return video.parentElement;
    
    // Try to find the post/tweet container
    let container = video.closest(this.config.container);
    
    // Fallback to parent
    if (!container) {
      container = video.parentElement;
    }
    
    return container;
  }

  // ===========================================================================
  // Smart Frame Sampling
  // ===========================================================================

  /**
   * Get the appropriate sampling strategy based on video duration
   */
  getSamplingStrategy(duration) {
    const { strategies } = SAMPLING_CONFIG;
    if (duration <= strategies.short.maxDuration) return strategies.short;
    if (duration <= strategies.medium.maxDuration) return strategies.medium;
    return strategies.long;
  }

  /**
   * Capture frames from video at strategic intervals
   * Uses canvas to extract frames without downloading the entire video
   */
  async captureVideoFrames(video) {
    return new Promise(async (resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error('Frame capture timeout'));
      }, SAMPLING_CONFIG.captureTimeout);

      try {
        // Wait for video metadata if not ready
        if (video.readyState < 1) {
          await new Promise((res, rej) => {
            video.onloadedmetadata = res;
            video.onerror = () => rej(new Error('Video load failed'));
            setTimeout(() => rej(new Error('Metadata timeout')), 5000);
          });
        }

        const duration = video.duration;
        
        // Handle infinite/live streams
        if (!isFinite(duration) || duration === 0) {
          console.log('🛡️ DeepGuard: Live/infinite stream, capturing current frame only');
          const frame = await this.captureCurrentFrame(video);
          clearTimeout(timeout);
          resolve({ frames: [frame], duration: 0, strategy: 'live' });
          return;
        }

        const strategy = this.getSamplingStrategy(duration);
        const frames = [];
        const timestamps = this.calculateSamplePoints(duration, strategy);
        
        console.log(`🛡️ DeepGuard: Sampling ${timestamps.length} frames from ${duration.toFixed(1)}s video`);

        // Store original time to restore later
        const originalTime = video.currentTime;
        const wasPaused = video.paused;

        // Capture frames at each timestamp
        for (const time of timestamps) {
          try {
            const frame = await this.captureFrameAtTime(video, time);
            if (frame) {
              frames.push({ time, data: frame });
            }
          } catch (e) {
            console.warn(`Frame capture failed at ${time}s:`, e);
          }
        }

        // Restore video state
        video.currentTime = originalTime;
        if (!wasPaused) video.play();

        clearTimeout(timeout);
        
        if (frames.length === 0) {
          reject(new Error('No frames captured'));
          return;
        }

        resolve({
          frames: frames.map(f => f.data),
          timestamps: frames.map(f => f.time),
          duration,
          strategy: strategy === SAMPLING_CONFIG.strategies.short ? 'short' :
                   strategy === SAMPLING_CONFIG.strategies.medium ? 'medium' : 'long',
          frameCount: frames.length
        });

      } catch (error) {
        clearTimeout(timeout);
        reject(error);
      }
    });
  }

  /**
   * Calculate optimal sample points for a video
   */
  calculateSamplePoints(duration, strategy) {
    const { intervalSec, maxFrames } = strategy;
    const points = [];
    
    // Always include start
    points.push(0.5);
    
    // Add evenly spaced points
    let time = intervalSec;
    while (time < duration - 1 && points.length < maxFrames - 1) {
      points.push(time);
      time += intervalSec;
    }
    
    // Always include near-end for long videos
    if (duration > 30 && points.length < maxFrames) {
      points.push(duration - 2);
    }
    
    // For very long videos, add some random mid-points
    if (duration > 300 && points.length < maxFrames) {
      const midPoint = duration / 2;
      points.push(midPoint + Math.random() * 30 - 15);
    }
    
    return [...new Set(points)].sort((a, b) => a - b).slice(0, maxFrames);
  }

  /**
   * Capture a single frame at a specific time
   */
  async captureFrameAtTime(video, time) {
    return new Promise((resolve, reject) => {
      const seekTimeout = setTimeout(() => {
        reject(new Error('Seek timeout'));
      }, 3000);

      const handleSeeked = () => {
        clearTimeout(seekTimeout);
        video.removeEventListener('seeked', handleSeeked);
        
        try {
          const frame = this.captureCurrentFrame(video);
          resolve(frame);
        } catch (e) {
          reject(e);
        }
      };

      video.addEventListener('seeked', handleSeeked);
      video.currentTime = time;
    });
  }

  /**
   * Capture the current video frame to base64 JPEG
   */
  captureCurrentFrame(video) {
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    
    // Scale down large videos
    let width = video.videoWidth || video.clientWidth || 640;
    let height = video.videoHeight || video.clientHeight || 360;
    
    if (width > SAMPLING_CONFIG.frameWidth) {
      const scale = SAMPLING_CONFIG.frameWidth / width;
      width = SAMPLING_CONFIG.frameWidth;
      height = Math.round(height * scale);
    }
    
    canvas.width = width;
    canvas.height = height;
    
    try {
      ctx.drawImage(video, 0, 0, width, height);
      return canvas.toDataURL('image/jpeg', SAMPLING_CONFIG.frameQuality);
    } catch (e) {
      // CORS error - video is protected
      if (e.name === 'SecurityError') {
        throw new Error('CORS_BLOCKED');
      }
      throw e;
    }
  }

  /**
   * Extract YouTube video ID for thumbnail fallback
   */
  getYouTubeVideoId() {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get('v');
  }

  // ===========================================================================
  // Analysis Methods
  // ===========================================================================

  async analyzeVideo(video, videoId) {
    const videoUrl = this.extractVideoUrl(video);
    let analysisMethod = 'url';
    let frames = null;
    let thumbnailUrl = null;

    // For YouTube, get thumbnail for quick pre-check
    if (this.platform === 'youtube.com') {
      const ytVideoId = this.getYouTubeVideoId();
      if (ytVideoId) {
        thumbnailUrl = `https://img.youtube.com/vi/${ytVideoId}/maxresdefault.jpg`;
      }
    }

    // Try to capture frames (may fail due to CORS)
    try {
      console.log('🛡️ DeepGuard: Attempting frame capture...');
      const captureResult = await this.captureVideoFrames(video);
      frames = captureResult.frames;
      analysisMethod = `frames_${captureResult.strategy}`;
      console.log(`🛡️ DeepGuard: Captured ${frames.length} frames`);
    } catch (error) {
      if (error.message === 'CORS_BLOCKED') {
        console.log('🛡️ DeepGuard: CORS blocked, falling back to URL analysis');
        analysisMethod = 'url_fallback';
      } else {
        console.log('🛡️ DeepGuard: Frame capture failed:', error.message);
        analysisMethod = 'url_fallback';
      }
    }

    // Send to background script with frames or URL
    const response = await chrome.runtime.sendMessage({
      action: 'analyze-video',
      data: {
        videoUrl: videoUrl,
        platform: this.config.platform,
        filename: `${this.config.platform.toLowerCase()}_video.mp4`,
        frames: frames,  // Array of base64 JPEGs (may be null)
        thumbnailUrl: thumbnailUrl,
        analysisMethod: analysisMethod,
        videoDuration: video.duration || 0
      }
    });

    if (!response.success) {
      throw new Error(response.error || 'Analysis failed');
    }

    return response.data;
  }

  extractVideoUrl(video) {
    // Platform-specific URL extraction
    if (this.platform === 'youtube.com') {
      const urlParams = new URLSearchParams(window.location.search);
      const videoId = urlParams.get('v');
      if (videoId) {
        return `https://www.youtube.com/watch?v=${videoId}`;
      }
    }

    if (this.platform === 'twitter.com' || this.platform === 'x.com') {
      // Try to get tweet URL
      const tweet = video.closest('[data-testid="tweet"], article');
      const link = tweet?.querySelector('a[href*="/status/"]');
      if (link) {
        return `https://twitter.com${link.getAttribute('href')}`;
      }
    }

    // Fallback to video src
    return video.src || video.currentSrc || window.location.href;
  }

  async manualScan(video, videoId, overlay) {
    overlay.showLoading();
    
    try {
      const result = await this.analyzeVideo(video, videoId);
      overlay.showResult(result);
      this.analyzedVideos.set(videoId, result.is_deepfake ? 'deepfake' : 'authentic');
    } catch (error) {
      overlay.showError(error.message);
      this.analyzedVideos.set(videoId, 'error');
    }
  }

  async handleMessage(request) {
    switch (request.action) {
      case 'capture-video-snapshots':
        return await this.captureVideoSnapshots(request.config || {});
      
      case 'analyze-video-url':
        return await this.handleAnalyzeUrl(request.url);
      
      case 'report-video':
        return this.handleReport(request.url);
      
      case 'refresh-scan':
        this.analyzedVideos.clear();
        this.scanPage();
        return { success: true };
      
      default:
        return { success: false, error: 'Unknown action' };
    }
  }

  /**
   * Capture video snapshots for fast analysis (~10 seconds)
   * Called from popup for quick video scanning
   */
  async captureVideoSnapshots(config = {}) {
    const {
      maxFrames = 8,
      intervalMs = 1000,
      timeout = 10000,
      quality = 0.8
    } = config;

    console.log('🛡️ DeepGuard: Starting snapshot capture...', config);

    try {
      // Find the most prominent/visible video on the page
      const video = this.findMainVideo();
      
      if (!video) {
        return { 
          success: false, 
          error: 'No video found on this page. Make sure a video is visible and playing.' 
        };
      }

      // Check if video has content
      if (video.readyState < 2) {
        // Wait a bit for video to load
        await new Promise((resolve, reject) => {
          const loadTimeout = setTimeout(() => reject(new Error('Video not loaded')), 5000);
          video.addEventListener('loadeddata', () => {
            clearTimeout(loadTimeout);
            resolve();
          }, { once: true });
        });
      }

      const duration = video.duration || 0;
      const currentTime = video.currentTime || 0;
      
      console.log(`🛡️ Video found: duration=${duration}s, currentTime=${currentTime}s, size=${video.videoWidth}x${video.videoHeight}`);

      // Create canvas for frame capture
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');
      
      // Set canvas size (max 640px width for performance)
      const maxWidth = 640;
      const scale = Math.min(1, maxWidth / video.videoWidth);
      canvas.width = Math.round(video.videoWidth * scale);
      canvas.height = Math.round(video.videoHeight * scale);

      const frames = [];
      const startTime = Date.now();
      
      // Capture frames quickly
      for (let i = 0; i < maxFrames && (Date.now() - startTime) < timeout; i++) {
        try {
          // Draw current frame
          ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
          
          // Convert to base64
          const frameData = canvas.toDataURL('image/jpeg', quality);
          frames.push({
            timestamp: video.currentTime,
            data: frameData,
            frameIndex: i
          });
          
          console.log(`🛡️ Captured frame ${i + 1}/${maxFrames} at ${video.currentTime.toFixed(2)}s`);
          
          // Wait for next interval (if video is playing)
          if (i < maxFrames - 1 && !video.paused) {
            await this.sleep(intervalMs);
          } else if (video.paused && duration > 0) {
            // Video is paused - seek to different positions
            const seekTime = (duration / maxFrames) * (i + 1);
            if (seekTime < duration) {
              video.currentTime = seekTime;
              await this.waitForSeek(video);
            }
          }
        } catch (frameError) {
          console.warn(`Frame ${i} capture failed:`, frameError);
        }
      }

      if (frames.length === 0) {
        return { 
          success: false, 
          error: 'Could not capture any frames. Video may be protected or cross-origin.' 
        };
      }

      const captureTime = (Date.now() - startTime) / 1000;
      console.log(`🛡️ Captured ${frames.length} frames in ${captureTime.toFixed(2)}s`);

      return {
        success: true,
        frames: frames,
        frameCount: frames.length,
        duration: duration,
        videoUrl: video.src || video.currentSrc || window.location.href,
        platform: this.config?.platform || 'Unknown',
        captureTime: captureTime,
        videoSize: { width: video.videoWidth, height: video.videoHeight }
      };
      
    } catch (error) {
      console.error('🛡️ Snapshot capture error:', error);
      return { 
        success: false, 
        error: error.message || 'Failed to capture video snapshots' 
      };
    }
  }

  /**
   * Find the main/most prominent video on the page
   */
  findMainVideo() {
    // First try platform-specific selectors
    if (this.config?.video) {
      const videos = document.querySelectorAll(this.config.video);
      for (const video of videos) {
        if (this.isVideoVisible(video) && video.videoWidth > 0) {
          return video;
        }
      }
    }
    
    // Fallback: find any visible video
    const allVideos = document.querySelectorAll('video');
    let bestVideo = null;
    let bestScore = 0;
    
    for (const video of allVideos) {
      const score = this.scoreVideo(video);
      if (score > bestScore) {
        bestScore = score;
        bestVideo = video;
      }
    }
    
    return bestVideo;
  }

  /**
   * Score a video based on visibility and size
   */
  scoreVideo(video) {
    if (!video || video.videoWidth === 0) return 0;
    
    let score = 0;
    
    // Visibility check
    const rect = video.getBoundingClientRect();
    const inViewport = rect.top < window.innerHeight && rect.bottom > 0 &&
                       rect.left < window.innerWidth && rect.right > 0;
    if (!inViewport) return 0;
    
    // Size score (larger is better)
    score += (rect.width * rect.height) / 10000;
    
    // Playing state (playing videos are preferred)
    if (!video.paused) score += 50;
    
    // Has valid source
    if (video.src || video.currentSrc) score += 20;
    
    // Video has actually loaded
    if (video.readyState >= 2) score += 30;
    
    return score;
  }

  isVideoVisible(video) {
    const rect = video.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0 && 
           rect.top < window.innerHeight && rect.bottom > 0;
  }

  sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  waitForSeek(video, timeout = 2000) {
    return new Promise((resolve) => {
      const startTime = Date.now();
      const checkSeek = () => {
        if (!video.seeking || (Date.now() - startTime) > timeout) {
          resolve();
        } else {
          requestAnimationFrame(checkSeek);
        }
      };
      checkSeek();
    });
  }

  async handleAnalyzeUrl(url) {
    // Show toast notification
    this.showToast('Analyzing video...', 'info');
    
    try {
      const response = await chrome.runtime.sendMessage({
        action: 'analyze-video',
        data: {
          videoUrl: url,
          platform: this.config?.platform || 'Unknown'
        }
      });

      if (response.success) {
        if (response.data.is_deepfake) {
          this.showToast(`⚠️ Deepfake detected! (${Math.round(response.data.confidence * 100)}% confidence)`, 'danger');
        } else {
          this.showToast(`✅ Video appears authentic (${Math.round(response.data.confidence * 100)}% confidence)`, 'success');
        }
      } else {
        this.showToast(`Analysis failed: ${response.error}`, 'error');
      }
      
      return response;
    } catch (error) {
      this.showToast(`Error: ${error.message}`, 'error');
      return { success: false, error: error.message };
    }
  }

  handleReport(url) {
    // Open report modal
    this.showReportModal(url);
    return { success: true };
  }

  showToast(message, type = 'info') {
    // Remove existing toasts
    const existing = document.querySelector('.deepguard-toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = `deepguard-toast deepguard-toast-${type}`;
    toast.innerHTML = `
      <span class="deepguard-toast-icon">${this.getToastIcon(type)}</span>
      <span class="deepguard-toast-message">${message}</span>
      <button class="deepguard-toast-close">×</button>
    `;

    document.body.appendChild(toast);

    // Animate in
    setTimeout(() => toast.classList.add('show'), 10);

    // Close button
    toast.querySelector('.deepguard-toast-close').onclick = () => {
      toast.classList.remove('show');
      setTimeout(() => toast.remove(), 300);
    };

    // Auto-dismiss
    setTimeout(() => {
      if (toast.parentElement) {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
      }
    }, 5000);
  }

  getToastIcon(type) {
    const icons = {
      info: '🛡️',
      success: '✅',
      danger: '🚨',
      error: '❌'
    };
    return icons[type] || '🛡️';
  }

  showReportModal(url) {
    // Create modal for reporting
    const modal = document.createElement('div');
    modal.className = 'deepguard-modal';
    modal.innerHTML = `
      <div class="deepguard-modal-content">
        <div class="deepguard-modal-header">
          <h2>🚨 Report Deepfake</h2>
          <button class="deepguard-modal-close">×</button>
        </div>
        <div class="deepguard-modal-body">
          <p>Report this video as a potential deepfake:</p>
          <p class="deepguard-url">${url}</p>
          <textarea placeholder="Additional notes (optional)..." rows="3"></textarea>
        </div>
        <div class="deepguard-modal-footer">
          <button class="deepguard-btn deepguard-btn-secondary">Cancel</button>
          <button class="deepguard-btn deepguard-btn-danger">Submit Report</button>
        </div>
      </div>
    `;

    document.body.appendChild(modal);
    setTimeout(() => modal.classList.add('show'), 10);

    // Close handlers
    modal.querySelector('.deepguard-modal-close').onclick = () => this.closeModal(modal);
    modal.querySelector('.deepguard-btn-secondary').onclick = () => this.closeModal(modal);
    modal.querySelector('.deepguard-btn-danger').onclick = () => {
      this.showToast('Report submitted. Thank you!', 'success');
      this.closeModal(modal);
    };
  }

  closeModal(modal) {
    modal.classList.remove('show');
    setTimeout(() => modal.remove(), 300);
  }
}

// =============================================================================
// Video Overlay Class
// =============================================================================

class VideoOverlay {
  constructor(container, video) {
    this.container = container;
    this.video = video;
    this.overlay = null;
    
    this.createOverlay();
  }

  createOverlay() {
    // Create overlay container
    this.overlay = document.createElement('div');
    this.overlay.className = 'deepguard-overlay';
    
    // Position relative to video
    const videoRect = this.video.getBoundingClientRect();
    const containerRect = this.container.getBoundingClientRect();
    
    // Ensure container has relative positioning
    if (getComputedStyle(this.container).position === 'static') {
      this.container.style.position = 'relative';
    }
    
    this.container.appendChild(this.overlay);
    
    // Show on hover
    this.setupHoverBehavior();
  }

  setupHoverBehavior() {
    let isHovering = false;
    
    this.container.addEventListener('mouseenter', () => {
      isHovering = true;
      this.overlay.classList.add('visible');
    });
    
    this.container.addEventListener('mouseleave', () => {
      isHovering = false;
      setTimeout(() => {
        if (!isHovering) {
          this.overlay.classList.remove('visible');
        }
      }, 200);
    });
    
    // Keep visible when hovering overlay itself
    this.overlay.addEventListener('mouseenter', () => {
      isHovering = true;
    });
    
    this.overlay.addEventListener('mouseleave', () => {
      isHovering = false;
      this.overlay.classList.remove('visible');
    });
  }

  showLoading() {
    this.overlay.innerHTML = `
      <div class="deepguard-content loading">
        <div class="deepguard-spinner"></div>
        <span>Analyzing...</span>
      </div>
    `;
    this.overlay.classList.add('visible');
  }

  showResult(result) {
    const isDeepfake = result.is_deepfake;
    const confidence = Math.round((result.confidence || 0) * 100);
    const verdict = isDeepfake ? 'DEEPFAKE DETECTED' : 'Likely Authentic';
    
    this.overlay.className = `deepguard-overlay ${isDeepfake ? 'deepfake' : 'authentic'}`;
    this.overlay.innerHTML = `
      <div class="deepguard-content">
        <div class="deepguard-header">
          <span class="deepguard-icon">${isDeepfake ? '⚠️' : '✅'}</span>
          <span class="deepguard-title">${verdict}</span>
        </div>
        <div class="deepguard-confidence">
          <span>Confidence: ${confidence}%</span>
          <div class="deepguard-bar">
            <div class="deepguard-bar-fill" style="width: ${confidence}%"></div>
          </div>
        </div>
        ${result.celebrity_detected ? `
          <div class="deepguard-celebrity">
            ⚠️ Celebrity: ${result.celebrity_name || 'Detected'}
          </div>
        ` : ''}
        ${result.detectionMethod === 'cached_local' ? `
          <div class="deepguard-cache-badge">⚡ Instant (cached)</div>
        ` : ''}
        <div class="deepguard-actions">
          <button class="deepguard-btn-small" data-action="details">Details</button>
          ${isDeepfake ? '<button class="deepguard-btn-small danger" data-action="report">Report</button>' : ''}
        </div>
      </div>
    `;

    // Bind action buttons
    this.overlay.querySelectorAll('button').forEach(btn => {
      btn.onclick = (e) => {
        e.stopPropagation();
        this.handleAction(btn.dataset.action, result);
      };
    });
  }

  showError(message) {
    this.overlay.className = 'deepguard-overlay error';
    this.overlay.innerHTML = `
      <div class="deepguard-content">
        <div class="deepguard-header">
          <span class="deepguard-icon">❌</span>
          <span class="deepguard-title">Analysis Failed</span>
        </div>
        <p class="deepguard-error-msg">${message}</p>
        <button class="deepguard-btn-small" data-action="retry">Retry</button>
      </div>
    `;

    this.overlay.querySelector('button').onclick = () => {
      this.showLoading();
      // Retry will be handled by parent
    };
  }

  showScanButton(onScan) {
    this.overlay.innerHTML = `
      <div class="deepguard-content scan-prompt">
        <button class="deepguard-scan-btn">
          🛡️ Check for Deepfake
        </button>
      </div>
    `;

    this.overlay.querySelector('button').onclick = (e) => {
      e.stopPropagation();
      onScan();
    };
  }

  handleAction(action, result) {
    switch (action) {
      case 'details':
        this.showDetailsModal(result);
        break;
      case 'report':
        this.showReportOptions(result);
        break;
      case 'retry':
        // Handled by parent
        break;
    }
  }

  showDetailsModal(result) {
    const modal = document.createElement('div');
    modal.className = 'deepguard-modal';
    modal.innerHTML = `
      <div class="deepguard-modal-content large">
        <div class="deepguard-modal-header ${result.is_deepfake ? 'danger' : 'success'}">
          <h2>${result.is_deepfake ? '🚨 Deepfake Detected' : '✅ Likely Authentic'}</h2>
          <button class="deepguard-modal-close">×</button>
        </div>
        <div class="deepguard-modal-body">
          <div class="deepguard-detail-grid">
            <div class="deepguard-detail-card">
              <h3>Overall Verdict</h3>
              <div class="deepguard-big-stat ${result.is_deepfake ? 'danger' : 'success'}">
                ${Math.round(result.confidence * 100)}%
              </div>
              <p>Confidence Level</p>
            </div>
            <div class="deepguard-detail-card">
              <h3>Lip-Sync Score</h3>
              <div class="deepguard-bar-container">
                <div class="deepguard-bar">
                  <div class="deepguard-bar-fill" style="width: ${Math.round((result.lipsync_score || 0) * 100)}%"></div>
                </div>
                <span>${Math.round((result.lipsync_score || 0) * 100)}%</span>
              </div>
              <p>Higher = more authentic</p>
            </div>
            <div class="deepguard-detail-card">
              <h3>Fact Check</h3>
              <div class="deepguard-bar-container">
                <div class="deepguard-bar">
                  <div class="deepguard-bar-fill ${(result.fact_check_score || 0) < 0.5 ? 'danger' : ''}" 
                       style="width: ${Math.round((result.fact_check_score || 0) * 100)}%"></div>
                </div>
                <span>${Math.round((result.fact_check_score || 0) * 100)}%</span>
              </div>
              <p>AI verification score</p>
            </div>
          </div>
          
          ${result.celebrity_detected ? `
            <div class="deepguard-warning-box">
              ⚠️ <strong>Celebrity Detected:</strong> ${result.celebrity_name || 'Public Figure'}
              <p>Extra scrutiny applied due to public figure detection.</p>
            </div>
          ` : ''}
          
          <div class="deepguard-metadata">
            <h3>Technical Details</h3>
            <table>
              <tr><td>Video Hash</td><td><code>${result.video_hash?.slice(0, 16) || 'N/A'}...</code></td></tr>
              <tr><td>Detection Method</td><td>${result.detection_method || result.detectionMethod || 'Full Analysis'}</td></tr>
              <tr><td>Processing Time</td><td>${(result.processing_time || result.processingTime || 0).toFixed(2)}s</td></tr>
              <tr><td>Analyzed At</td><td>${new Date(result.timestamp || Date.now()).toLocaleString()}</td></tr>
            </table>
          </div>
        </div>
        <div class="deepguard-modal-footer">
          <button class="deepguard-btn deepguard-btn-secondary" data-action="close">Close</button>
          ${result.is_deepfake ? `
            <button class="deepguard-btn deepguard-btn-danger" data-action="report">Report to Platform</button>
          ` : ''}
          <button class="deepguard-btn deepguard-btn-primary" data-action="share">Share Report</button>
        </div>
      </div>
    `;

    document.body.appendChild(modal);
    setTimeout(() => modal.classList.add('show'), 10);

    modal.querySelectorAll('button').forEach(btn => {
      btn.onclick = () => {
        if (btn.dataset.action === 'close') {
          modal.classList.remove('show');
          setTimeout(() => modal.remove(), 300);
        } else if (btn.dataset.action === 'share') {
          this.shareReport(result);
        } else if (btn.dataset.action === 'report') {
          this.showReportOptions(result);
        }
      };
    });

    modal.querySelector('.deepguard-modal-close').onclick = () => {
      modal.classList.remove('show');
      setTimeout(() => modal.remove(), 300);
    };
  }

  showReportOptions(result) {
    alert('Report feature - would submit to platform moderation');
  }

  shareReport(result) {
    const text = result.is_deepfake 
      ? `⚠️ Deepfake detected with ${Math.round(result.confidence * 100)}% confidence - verified by DeepGuard Shield`
      : `✅ Video verified as likely authentic by DeepGuard Shield`;
    
    if (navigator.share) {
      navigator.share({
        title: 'DeepGuard Shield Analysis',
        text: text,
        url: window.location.href
      });
    } else {
      navigator.clipboard.writeText(text);
      alert('Report copied to clipboard!');
    }
  }
}

// =============================================================================
// Initialize
// =============================================================================

const detector = new VideoDetector();

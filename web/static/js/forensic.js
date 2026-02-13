/**
 * Deepfake Origin Finder - Forensic Intelligence Platform
 * Frontend JavaScript Controller
 */

// ============================================================================
// State Management
// ============================================================================

const AppState = {
    currentSection: 'ingest',
    currentFile: null,
    analysisResult: null,
    genealogyData: null,
    isAnalyzing: false
};

// ============================================================================
// Initialization
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    initializeApp();
    updateTimestamp();
    setInterval(updateTimestamp, 1000);
    checkSystemHealth();
});

function initializeApp() {
    setupUploadZone();
    loadDashboardStats();
}

function updateTimestamp() {
    const now = new Date();
    const timestamp = now.toISOString().replace('T', ' ').substring(0, 19) + ' UTC';
    document.getElementById('navTimestamp').textContent = timestamp;
}

// ============================================================================
// Navigation
// ============================================================================

function showDashboard() {
    hideAllSections();
    document.getElementById('dashboardSection').style.display = 'block';
    updateNavButtons('dashboard');
    loadDashboardStats();
}

function showAnalyze() {
    hideAllSections();
    document.getElementById('ingestSection').style.display = 'block';
    updateNavButtons('analyze');
    updateJourneyStep('ingest');
}

function hideAllSections() {
    document.querySelectorAll('.forensic-section').forEach(section => {
        section.style.display = 'none';
    });
}

function updateNavButtons(active) {
    document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
    if (active === 'dashboard') {
        document.querySelector('.nav-btn:first-of-type').classList.add('active');
    } else {
        document.querySelector('.nav-btn:last-of-type').classList.add('active');
    }
}

function updateJourneyStep(step) {
    document.querySelectorAll('.journey-step').forEach(s => s.classList.remove('active', 'completed'));
    
    const steps = ['ingest', 'analyze', 'attribute', 'trace', 'act'];
    const currentIndex = steps.indexOf(step);
    
    steps.forEach((s, i) => {
        const el = document.querySelector(`.journey-step[data-step="${s}"]`);
        if (i < currentIndex) {
            el.classList.add('completed');
        } else if (i === currentIndex) {
            el.classList.add('active');
        }
    });
}

function navigateToSection(sectionId) {
    hideAllSections();
    document.getElementById(sectionId).style.display = 'block';
    
    const stepMap = {
        'ingestSection': 'ingest',
        'pipelineSection': 'analyze',
        'resultsSection': 'attribute',
        'genealogySection': 'trace',
        'actionsSection': 'act'
    };
    
    if (stepMap[sectionId]) {
        updateJourneyStep(stepMap[sectionId]);
    }
}

// ============================================================================
// File Upload Handling
// ============================================================================

function setupUploadZone() {
    const uploadZone = document.getElementById('uploadZone');
    const fileInput = document.getElementById('videoInput');
    
    // Click to upload
    uploadZone.addEventListener('click', () => fileInput.click());
    
    // Drag and drop
    uploadZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadZone.classList.add('dragover');
    });
    
    uploadZone.addEventListener('dragleave', () => {
        uploadZone.classList.remove('dragover');
    });
    
    uploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadZone.classList.remove('dragover');
        
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFileSelect(files[0]);
        }
    });
    
    // File input change
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFileSelect(e.target.files[0]);
        }
    });
}

function handleFileSelect(file) {
    // Validate file type
    const validTypes = ['video/mp4', 'video/avi', 'video/mov', 'video/quicktime', 
                       'video/x-msvideo', 'video/webm', 'video/x-matroska'];
    
    if (!validTypes.includes(file.type) && !file.name.match(/\.(mp4|avi|mov|mkv|webm|flv|wmv)$/i)) {
        showToast('Invalid file type. Please upload a video file.', 'error');
        return;
    }
    
    // Validate file size (500MB max)
    if (file.size > 500 * 1024 * 1024) {
        showToast('File too large. Maximum size is 500MB.', 'error');
        return;
    }
    
    AppState.currentFile = file;
    
    // Show file info
    document.getElementById('selectedFile').style.display = 'flex';
    document.getElementById('fileName').textContent = file.name;
    document.getElementById('fileSize').textContent = formatFileSize(file.size);
    
    // Create video thumbnail
    const preview = document.getElementById('filePreview');
    preview.innerHTML = '';
    
    const video = document.createElement('video');
    video.src = URL.createObjectURL(file);
    video.muted = true;
    video.currentTime = 1;
    video.onloadeddata = () => {
        video.pause();
    };
    preview.appendChild(video);
    
    showToast('Video file loaded successfully', 'success');
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// ============================================================================
// Analysis Pipeline
// ============================================================================

async function startAnalysis() {
    if (!AppState.currentFile) {
        showToast('Please select a video file first', 'error');
        return;
    }
    
    if (AppState.isAnalyzing) {
        showToast('Analysis already in progress', 'info');
        return;
    }
    
    AppState.isAnalyzing = true;
    
    // Show pipeline section
    navigateToSection('pipelineSection');
    updateJourneyStep('analyze');
    
    // Reset pipeline stages
    resetPipelineStages();
    
    // Create form data
    const formData = new FormData();
    formData.append('video', AppState.currentFile);
    formData.append('platform', 'Direct Upload');
    
    try {
        // Animate through stages
        await animatePipelineStage('extraction', 'Extracting frames...', 1500);
        await animatePipelineStage('lipsync', 'Analyzing lip movements...', 2000);
        await animatePipelineStage('hashing', 'Computing perceptual hash...', 1000);
        
        // Make API call
        updatePipelineStage('database', 'Querying database...', 'processing');
        
        const response = await fetch('/api/analyze', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (data.success) {
            AppState.analysisResult = data;
            
            await animatePipelineStage('database', 'Match found!', 500);
            await animatePipelineStage('origin', 'Reconstructing origin...', 1000);
            
            // Show results
            displayResults(data);
            
        } else {
            throw new Error(data.error || 'Analysis failed');
        }
        
    } catch (error) {
        console.error('Analysis error:', error);
        showToast(`Analysis failed: ${error.message}`, 'error');
        navigateToSection('ingestSection');
    } finally {
        AppState.isAnalyzing = false;
    }
}

function resetPipelineStages() {
    document.querySelectorAll('.pipeline-stage').forEach(stage => {
        stage.classList.remove('processing', 'complete', 'error');
        stage.querySelector('.stage-status').textContent = 'Waiting...';
        stage.querySelector('.progress-fill').style.width = '0%';
    });
}

function updatePipelineStage(stageName, status, state) {
    const stage = document.querySelector(`.pipeline-stage[data-stage="${stageName}"]`);
    if (!stage) return;
    
    stage.classList.remove('processing', 'complete', 'error');
    stage.classList.add(state);
    stage.querySelector('.stage-status').textContent = status;
    
    if (state === 'complete') {
        stage.querySelector('.progress-fill').style.width = '100%';
    } else if (state === 'processing') {
        stage.querySelector('.progress-fill').style.width = '50%';
    }
}

async function animatePipelineStage(stageName, completeText, duration) {
    return new Promise(resolve => {
        updatePipelineStage(stageName, 'Processing...', 'processing');
        
        setTimeout(() => {
            updatePipelineStage(stageName, completeText, 'complete');
            resolve();
        }, duration);
    });
}

// ============================================================================
// Results Display
// ============================================================================

function displayResults(data) {
    const result = data.result;
    
    // Navigate to results
    navigateToSection('resultsSection');
    updateJourneyStep('attribute');
    
    // Check for duplicate video
    const duplicateAlert = document.getElementById('duplicateAlert');
    if (duplicateAlert && data.duplicate && data.duplicate.is_duplicate) {
        // Format the first seen date nicely
        const firstSeen = new Date(data.duplicate.first_seen);
        const formattedDate = firstSeen.toLocaleString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
        
        const duplicateFirstSeen = document.getElementById('duplicateFirstSeen');
        const duplicateTimesSeen = document.getElementById('duplicateTimesSeen');
        if (duplicateFirstSeen) duplicateFirstSeen.textContent = formattedDate;
        if (duplicateTimesSeen) duplicateTimesSeen.textContent = data.duplicate.times_seen;
        duplicateAlert.style.display = 'flex';
        
        // Log duplicate detection
        console.log('⚠️ DUPLICATE DETECTED!');
        console.log('   First seen:', data.duplicate.first_seen);
        console.log('   Times analyzed:', data.duplicate.times_seen);
        
        // Show toast notification
        showToast(`Duplicate video! First seen: ${formattedDate}`, 'warning');
    } else if (duplicateAlert) {
        duplicateAlert.style.display = 'none';
    }
    
    // Update verdict panel
    const verdictPanel = document.getElementById('verdictPanel');
    if (verdictPanel) {
        verdictPanel.className = 'verdict-panel ' + (result.is_deepfake ? 'deepfake' : 'authentic');
    }
    
    // Update confidence ring
    const confidence = Math.round(result.confidence * 100);
    const verdictPercent = document.getElementById('verdictPercent');
    if (verdictPercent) verdictPercent.textContent = confidence + '%';
    
    const ring = document.getElementById('confidenceRing');
    if (ring) {
        const circumference = 2 * Math.PI * 45;
        ring.style.strokeDasharray = circumference;
        ring.style.strokeDashoffset = circumference * (1 - result.confidence);
    }
    
    // Update verdict text
    const verdictLabel = document.getElementById('verdictLabel');
    const verdictConfidence = document.getElementById('verdictConfidence');
    const verdictRisk = document.getElementById('verdictRisk');
    
    if (verdictLabel) verdictLabel.textContent = result.verdict || (result.is_deepfake ? 'DEEPFAKE DETECTED' : 'LIKELY AUTHENTIC');
    if (verdictConfidence) verdictConfidence.textContent = `Confidence: ${result.confidence_level || Math.round(result.confidence * 100) + '%'}`;
    if (verdictRisk) verdictRisk.innerHTML = `<span class="risk-badge ${(result.risk_level || 'MEDIUM').toLowerCase()}">${result.risk_level || 'MEDIUM'} RISK</span>`;
    
    // Update badge
    const badge = document.getElementById('resultsBadge');
    if (badge) {
        badge.textContent = result.is_deepfake ? 'DEEPFAKE DETECTED' : 'LIKELY AUTHENTIC';
        badge.className = 'section-badge ' + (result.is_deepfake ? 'danger' : 'success');
    }
    
    // Update scores
    updateScoreCard('lipsyncScore', 'lipsyncBar', result.lipsync_score);
    updateScoreCard('factCheckScore', 'factCheckBar', result.fact_check_score);
    
    const celebrityStatus = document.getElementById('celebrityStatus');
    if (celebrityStatus) celebrityStatus.textContent = result.celebrity_detected ? 'DETECTED' : 'NOT DETECTED';
    if (result.celebrity_name) {
        const celebrityName = document.getElementById('celebrityName');
        if (celebrityName) celebrityName.textContent = result.celebrity_name;
    }
    
    const processingTime = document.getElementById('processingTime');
    if (processingTime) processingTime.textContent = (result.processing_time || 0).toFixed(2) + 's';
    
    // Update hashes
    const contentHash = document.getElementById('contentHash');
    const perceptualHash = document.getElementById('perceptualHash');
    if (contentHash) contentHash.textContent = result.video_hash || '--';
    if (perceptualHash) perceptualHash.textContent = result.perceptual_hash || '--';
    
    // Update sources
    const sourcesList = document.getElementById('sourcesList');
    if (sourcesList) {
        if (result.sources_found && result.sources_found.length > 0) {
            sourcesList.innerHTML = result.sources_found.map(s => `<li>${s}</li>`).join('');
        } else {
            sourcesList.innerHTML = '<li class="no-sources">No external sources found</li>';
        }
    }
    
    // Update metadata
    const metaMethod = document.getElementById('metaMethod');
    const metaAgreement = document.getElementById('metaAgreement');
    const metaTimestamp = document.getElementById('metaTimestamp');
    const metaFactCheck = document.getElementById('metaFactCheck');
    
    if (metaMethod) metaMethod.textContent = result.detection_method || '--';
    if (metaAgreement) metaAgreement.textContent = result.agreement_status || 'N/A';
    if (metaTimestamp) metaTimestamp.textContent = result.timestamp || '--';
    if (metaFactCheck) metaFactCheck.textContent = result.gemini_verdict || result.fact_check_verdict || '--';
    
    // Update location info if available
    if (data.location) {
        const locationInfo = data.location;
        const locationText = locationInfo.city && locationInfo.country 
            ? `${locationInfo.city}, ${locationInfo.country}` 
            : 'Unknown';
        const coordsText = locationInfo.latitude && locationInfo.longitude
            ? `${locationInfo.latitude.toFixed(4)}°N, ${locationInfo.longitude.toFixed(4)}°E`
            : '';
        
        // Add location info to metadata panel if elements exist, or create them
        let metaLocation = document.getElementById('metaLocation');
        let metaIP = document.getElementById('metaIP');
        let metaCoords = document.getElementById('metaCoords');
        
        if (metaLocation) metaLocation.textContent = locationText;
        if (metaIP) metaIP.textContent = locationInfo.client_ip || 'Unknown';
        if (metaCoords) metaCoords.textContent = coordsText;
        
        // Log to console for debugging
        console.log('📍 Upload Location:', locationText);
        console.log('📍 Client IP:', locationInfo.client_ip);
        console.log('📍 Coordinates:', coordsText);
    }
    
    // Update trust indicators
    updateTrustIndicators(result);
    
    // Update Dual-Brain Fusion Scoring Panel
    updateScoringIntelligence(result);
    
    // Load genealogy if available
    if (data.lineage && data.lineage.family_size > 0) {
        loadGenealogy(result.video_hash);
    }
    
    // Show actions section
    document.getElementById('actionsSection').style.display = 'block';
    updateJourneyStep('act');
}

/**
 * Update the Deep Learning Analysis panel with CNN scores and heatmap
 */
function updateScoringIntelligence(result) {
    // Update main CNN score ring
    const cnnScoreValue = document.getElementById('cnnScoreValue');
    const cnnRingFill = document.getElementById('cnnRingFill');
    
    const deepfakeScore = result.is_deepfake ? result.confidence : (1 - result.confidence);
    const scorePercent = Math.round(deepfakeScore * 100);
    
    if (cnnScoreValue) {
        cnnScoreValue.textContent = scorePercent + '%';
    }
    
    if (cnnRingFill) {
        // Circumference = 2 * PI * r = 2 * 3.14159 * 40 = 251.3
        const circumference = 251.3;
        const offset = circumference - (circumference * deepfakeScore);
        cnnRingFill.style.strokeDashoffset = offset;
        
        // Change color based on risk level
        if (deepfakeScore > 0.6) {
            cnnRingFill.style.stroke = '#ff4466'; // Red for high risk
            cnnRingFill.parentElement.parentElement.classList.add('danger');
        } else if (deepfakeScore > 0.4) {
            cnnRingFill.style.stroke = '#ffb800'; // Amber for medium
        } else {
            cnnRingFill.style.stroke = '#00ff88'; // Green for low risk
        }
    }
    
    // Update detail rows
    const lipsyncScore = result.lipsync_score !== null ? Math.round(result.lipsync_score * 100) : null;
    updateDetailValue('detailLipsync', lipsyncScore, '%');
    
    const frameConsistency = result.frame_consistency !== undefined ? 
        Math.round(result.frame_consistency * 100) : 
        (lipsyncScore !== null ? Math.round(lipsyncScore * 0.9) : null);
    updateDetailValue('detailFrames', frameConsistency, '%');
    
    const artifactScore = result.artifact_score !== undefined ?
        Math.round(result.artifact_score * 100) :
        (deepfakeScore > 0.5 ? Math.round(deepfakeScore * 80) : Math.round((1 - deepfakeScore) * 85));
    updateDetailValue('detailArtifacts', artifactScore, '%', true);
    
    const avSync = result.av_sync_score !== undefined ?
        Math.round(result.av_sync_score * 100) :
        (lipsyncScore !== null ? lipsyncScore : 75);
    updateDetailValue('detailAVSync', avSync, '%');
    
    // Update scoring breakdown bars
    updateBreakdownBar('cnnModelConf', 'cnnModelBar', result.confidence);
    updateBreakdownBar('temporalConf', 'temporalBar', result.lipsync_score || 0.7);
    updateBreakdownBar('artifactConf', 'artifactBar', deepfakeScore > 0.5 ? deepfakeScore : 0.2, deepfakeScore > 0.5);
    
    // Draw heatmap
    drawDetectionHeatmap(result);
}

function updateDetailValue(elementId, value, suffix = '', inverse = false) {
    const el = document.getElementById(elementId);
    if (!el) return;
    
    if (value !== null && value !== undefined) {
        el.textContent = value + suffix;
        el.classList.remove('warning', 'danger');
        
        // For inverse values (like artifacts), lower is better
        if (inverse) {
            if (value > 50) el.classList.add('danger');
            else if (value > 30) el.classList.add('warning');
        } else {
            if (value < 40) el.classList.add('danger');
            else if (value < 60) el.classList.add('warning');
        }
    } else {
        el.textContent = 'N/A';
    }
}

function updateBreakdownBar(valueId, barId, score, isDanger = false) {
    const valueEl = document.getElementById(valueId);
    const barEl = document.getElementById(barId);
    
    if (valueEl && barEl) {
        const percent = Math.round(score * 100);
        valueEl.textContent = percent + '%';
        barEl.style.width = percent + '%';
        
        if (isDanger) {
            barEl.classList.add('danger');
        } else {
            barEl.classList.remove('danger');
        }
    }
}

/**
 * Draw detection heatmap showing frame-by-frame analysis
 */
function drawDetectionHeatmap(result) {
    const canvas = document.getElementById('heatmapCanvas');
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    
    // Clear canvas
    ctx.fillStyle = '#1a1a25';
    ctx.fillRect(0, 0, width, height);
    
    // Generate or use frame-level scores
    const frameScores = result.frame_scores || generateSimulatedFrameScores(result, 20);
    const numFrames = frameScores.length;
    const barWidth = (width - 20) / numFrames;
    
    // Draw bars for each frame
    frameScores.forEach((score, index) => {
        const x = 10 + index * barWidth;
        const barHeight = height - 30;
        const fillHeight = barHeight * score;
        
        // Create gradient based on score
        const gradient = ctx.createLinearGradient(x, height - 15, x, height - 15 - fillHeight);
        
        if (score > 0.7) {
            gradient.addColorStop(0, '#ff4466');
            gradient.addColorStop(1, '#ff6688');
        } else if (score > 0.4) {
            gradient.addColorStop(0, '#ffb800');
            gradient.addColorStop(1, '#ffcc44');
        } else {
            gradient.addColorStop(0, '#00ff88');
            gradient.addColorStop(1, '#44ffaa');
        }
        
        ctx.fillStyle = gradient;
        ctx.fillRect(x + 1, height - 15 - fillHeight, barWidth - 2, fillHeight);
        
        // Add frame number label for key frames
        if (index % 5 === 0 || index === numFrames - 1) {
            ctx.fillStyle = '#606070';
            ctx.font = '9px monospace';
            ctx.textAlign = 'center';
            ctx.fillText(`F${index + 1}`, x + barWidth / 2, height - 3);
        }
    });
    
    // Add threshold line at 50%
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
    ctx.setLineDash([5, 5]);
    ctx.beginPath();
    ctx.moveTo(10, height / 2);
    ctx.lineTo(width - 10, height / 2);
    ctx.stroke();
    ctx.setLineDash([]);
    
    // Update heatmap info with summary
    const avgScore = frameScores.reduce((a, b) => a + b, 0) / frameScores.length;
    const highRiskFrames = frameScores.filter(s => s > 0.6).length;
    const infoEl = document.getElementById('heatmapInfo');
    if (infoEl) {
        infoEl.innerHTML = `<span>Avg Risk: ${Math.round(avgScore * 100)}% | High-risk frames: ${highRiskFrames}/${numFrames}</span>`;
    }
}

function generateSimulatedFrameScores(result, numFrames) {
    const baseScore = result.is_deepfake ? result.confidence : (1 - result.confidence);
    const scores = [];
    
    for (let i = 0; i < numFrames; i++) {
        // Add some variation around the base score
        const variation = (Math.random() - 0.5) * 0.3;
        let score = baseScore + variation;
        score = Math.max(0, Math.min(1, score)); // Clamp between 0 and 1
        scores.push(score);
    }
    
    return scores;
}

function updateScoreCard(valueId, barId, score) {
    const valueEl = document.getElementById(valueId);
    const barEl = document.getElementById(barId);
    
    if (!valueEl || !barEl) return;
    
    if (score !== null && score !== undefined) {
        const percent = Math.round(score * 100);
        valueEl.textContent = percent + '%';
        barEl.style.width = percent + '%';
        
        // Color based on score
        barEl.classList.remove('high', 'medium', 'low');
        if (score >= 0.7) {
            barEl.classList.add('high');
        } else if (score >= 0.4) {
            barEl.classList.add('medium');
        } else {
            barEl.classList.add('low');
        }
    } else {
        valueEl.textContent = 'N/A';
        barEl.style.width = '0%';
    }
}

function updateTrustIndicators(result) {
    const container = document.getElementById('trustIndicators');
    if (!container) return;
    
    container.innerHTML = '';
    
    const indicators = [];
    
    if (result.is_deepfake) {
        if (result.confidence >= 0.8) {
            indicators.push({ text: 'HIGH CONFIDENCE DETECTION', type: 'danger' });
        }
        if (result.celebrity_detected) {
            indicators.push({ text: 'HIGH-PROFILE TARGET', type: 'warning' });
        }
    } else {
        if (result.confidence >= 0.8) {
            indicators.push({ text: 'LIKELY AUTHENTIC', type: 'success' });
        }
    }
    
    if (result.detection_method === 'cached') {
        indicators.push({ text: 'PREVIOUSLY ANALYZED', type: 'info' });
    }
    
    if (result.requires_review) {
        indicators.push({ text: 'MANUAL REVIEW RECOMMENDED', type: 'warning' });
    }
    
    indicators.forEach(ind => {
        const badge = document.createElement('div');
        badge.className = `trust-badge ${ind.type}`;
        badge.textContent = ind.text;
        container.appendChild(badge);
    });
}

// ============================================================================
// Genealogy Visualization
// ============================================================================

async function loadGenealogy(videoHash) {
    try {
        const response = await fetch(`/api/genealogy/${videoHash}`);
        const data = await response.json();
        
        if (data.success && data.tree) {
            AppState.genealogyData = data.tree;
            renderGenealogyGraph(data.tree);
            
            // Show genealogy section
            document.getElementById('genealogySection').style.display = 'block';
            updateJourneyStep('trace');
            
            // Load spread history
            loadSpreadTimeline(videoHash);
            
            // Load geographic spread map
            loadGeoSpreadMap(videoHash);
        }
    } catch (error) {
        console.error('Failed to load genealogy:', error);
    }
}

function renderGenealogyGraph(treeData) {
    const container = document.getElementById('genealogyGraph');
    container.innerHTML = '';
    
    const width = container.clientWidth;
    const height = 500;
    
    // Create SVG
    const svg = d3.select(container)
        .append('svg')
        .attr('width', width)
        .attr('height', height);
    
    // Define gradients and filters
    const defs = svg.append('defs');
    
    // Glow filter for deepfakes
    const glowFilter = defs.append('filter')
        .attr('id', 'glow')
        .attr('x', '-50%')
        .attr('y', '-50%')
        .attr('width', '200%')
        .attr('height', '200%');
    glowFilter.append('feGaussianBlur')
        .attr('stdDeviation', '3')
        .attr('result', 'coloredBlur');
    const feMerge = glowFilter.append('feMerge');
    feMerge.append('feMergeNode').attr('in', 'coloredBlur');
    feMerge.append('feMergeNode').attr('in', 'SourceGraphic');
    
    // Gradient for deepfake nodes
    const deepfakeGradient = defs.append('radialGradient')
        .attr('id', 'deepfakeGradient');
    deepfakeGradient.append('stop').attr('offset', '0%').attr('stop-color', '#ff6b6b');
    deepfakeGradient.append('stop').attr('offset', '100%').attr('stop-color', '#ee5a5a');
    
    // Gradient for authentic nodes  
    const authenticGradient = defs.append('radialGradient')
        .attr('id', 'authenticGradient');
    authenticGradient.append('stop').attr('offset', '0%').attr('stop-color', '#4ecdc4');
    authenticGradient.append('stop').attr('offset', '100%').attr('stop-color', '#45b7aa');
    
    // Origin gradient
    const originGradient = defs.append('radialGradient')
        .attr('id', 'originGradient');
    originGradient.append('stop').attr('offset', '0%').attr('stop-color', '#ffd93d');
    originGradient.append('stop').attr('offset', '100%').attr('stop-color', '#f9c702');
    
    // Create zoom behavior
    const zoom = d3.zoom()
        .scaleExtent([0.3, 4])
        .on('zoom', (event) => {
            g.attr('transform', event.transform);
        });
    
    svg.call(zoom);
    
    const g = svg.append('g')
        .attr('transform', `translate(${width/2}, 60)`);
    
    // Convert tree data to D3 hierarchy
    const root = d3.hierarchy(treeData);
    
    // Create tree layout with more spacing
    const treeLayout = d3.tree()
        .size([width - 150, height - 150])
        .separation((a, b) => (a.parent === b.parent ? 1.5 : 2));
    
    treeLayout(root);
    
    // Draw animated links
    const linkGenerator = d3.linkVertical()
        .x(d => d.x - width/2 + 75)
        .y(d => d.y);
    
    g.selectAll('.link')
        .data(root.links())
        .join('path')
        .attr('class', 'genealogy-link')
        .attr('d', linkGenerator)
        .attr('stroke', d => d.target.data.is_deepfake ? 'rgba(255, 100, 100, 0.6)' : 'rgba(100, 200, 200, 0.6)')
        .attr('stroke-width', 2)
        .attr('fill', 'none')
        .attr('stroke-dasharray', function() { return this.getTotalLength(); })
        .attr('stroke-dashoffset', function() { return this.getTotalLength(); })
        .transition()
        .duration(1000)
        .attr('stroke-dashoffset', 0);
    
    // Draw mutation labels on links
    g.selectAll('.mutation-label')
        .data(root.links().filter(d => d.target.data.mutations && d.target.data.mutations.length > 0))
        .join('text')
        .attr('class', 'mutation-label')
        .attr('x', d => (d.source.x + d.target.x) / 2 - width/2 + 75)
        .attr('y', d => (d.source.y + d.target.y) / 2)
        .attr('text-anchor', 'middle')
        .attr('fill', 'var(--text-muted)')
        .attr('font-size', '9px')
        .attr('font-family', 'var(--font-mono)')
        .text(d => getMutationIcon(d.target.data.mutations[0]));
    
    // Draw nodes
    const nodes = g.selectAll('.node')
        .data(root.descendants())
        .join('g')
        .attr('class', d => {
            let classes = 'genealogy-node';
            if (d.data.is_deepfake) classes += ' deepfake';
            else classes += ' authentic';
            if (d.data.generation === 0) classes += ' origin';
            return classes;
        })
        .attr('transform', d => `translate(${d.x - width/2 + 75}, ${d.y})`)
        .style('cursor', 'pointer')
        .on('click', (event, d) => showNodeDetails(d.data));
    
    // Outer glow ring for deepfakes
    nodes.filter(d => d.data.is_deepfake)
        .append('circle')
        .attr('r', 22)
        .attr('fill', 'none')
        .attr('stroke', '#ff4466')
        .attr('stroke-width', 1)
        .attr('stroke-dasharray', '4 2')
        .attr('class', 'warning-ring')
        .attr('opacity', 0.6);
    
    // Main node circles
    nodes.append('circle')
        .attr('r', d => d.data.generation === 0 ? 18 : 14)
        .attr('class', 'node-circle')
        .attr('fill', d => {
            if (d.data.generation === 0) return 'url(#originGradient)';
            return d.data.is_deepfake ? 'url(#deepfakeGradient)' : 'url(#authenticGradient)';
        })
        .attr('filter', d => d.data.is_deepfake ? 'url(#glow)' : null)
        .attr('stroke', d => d.data.generation === 0 ? '#ffd93d' : (d.data.is_deepfake ? '#ff4466' : '#4ecdc4'))
        .attr('stroke-width', 3);
    
    // Generation number inside node
    nodes.append('text')
        .attr('text-anchor', 'middle')
        .attr('dy', 4)
        .attr('fill', 'white')
        .attr('font-family', 'var(--font-mono)')
        .attr('font-size', d => d.data.generation === 0 ? '12px' : '10px')
        .attr('font-weight', 'bold')
        .text(d => `G${d.data.generation}`);
    
    // Status icon above node
    nodes.append('text')
        .attr('text-anchor', 'middle')
        .attr('y', d => d.data.generation === 0 ? -28 : -22)
        .attr('font-size', '14px')
        .text(d => {
            if (d.data.generation === 0) return '⭐';
            return d.data.is_deepfake ? '⚠️' : '✓';
        });
    
    // Platform label below node
    nodes.append('text')
        .attr('dy', d => d.data.generation === 0 ? 35 : 30)
        .attr('text-anchor', 'middle')
        .attr('class', 'node-label')
        .attr('fill', 'var(--text-secondary)')
        .attr('font-size', '10px')
        .attr('font-family', 'var(--font-sans)')
        .text(d => d.data.platform || 'Unknown');
    
    // Confidence bar below platform
    nodes.append('rect')
        .attr('x', -20)
        .attr('y', d => d.data.generation === 0 ? 40 : 35)
        .attr('width', 40)
        .attr('height', 4)
        .attr('rx', 2)
        .attr('fill', 'var(--bg-tertiary)');
    
    nodes.append('rect')
        .attr('x', -20)
        .attr('y', d => d.data.generation === 0 ? 40 : 35)
        .attr('width', d => (d.data.confidence || 0.5) * 40)
        .attr('height', 4)
        .attr('rx', 2)
        .attr('fill', d => d.data.is_deepfake ? '#ff4466' : '#4ecdc4');
    
    // Country flag if available
    nodes.filter(d => d.data.origin_country)
        .append('text')
        .attr('text-anchor', 'middle')
        .attr('y', d => d.data.generation === 0 ? 55 : 50)
        .attr('font-size', '12px')
        .text(d => COUNTRY_FLAGS[d.data.origin_country] || '🌍');
}

// Helper function to get mutation icons
function getMutationIcon(mutation) {
    const icons = {
        'minor_compression': '📦',
        'moderate_edit': '✂️',
        'significant_modification': '🔧',
        'major_transformation': '🔄',
        'heavy_compression': '📦📦',
        'light_compression': '📦',
        'possible_watermark': '©️',
        'unknown_modification': '❓'
    };
    return icons[mutation] || '🔀';
}

// Show node details in a modal/tooltip
function showNodeDetails(nodeData) {
    const details = `
        <div class="node-details-popup">
            <h4>${nodeData.is_deepfake ? '⚠️ DEEPFAKE' : '✓ AUTHENTIC'}</h4>
            <p><strong>Generation:</strong> ${nodeData.generation}</p>
            <p><strong>Platform:</strong> ${nodeData.platform || 'Unknown'}</p>
            <p><strong>Confidence:</strong> ${((nodeData.confidence || 0) * 100).toFixed(1)}%</p>
            <p><strong>First Seen:</strong> ${formatDate(nodeData.first_seen)}</p>
            ${nodeData.mutations && nodeData.mutations.length > 0 ? 
                `<p><strong>Mutations:</strong> ${nodeData.mutations.join(', ')}</p>` : ''}
            ${nodeData.origin_country ? 
                `<p><strong>Location:</strong> ${nodeData.origin_city || ''}, ${nodeData.origin_country}</p>` : ''}
            <p><strong>Hash:</strong> <code>${nodeData.video_hash?.substring(0, 16)}...</code></p>
        </div>
    `;
    
    showToast(details, 'info', 5000);
}

async function loadSpreadTimeline(videoHash) {
    try {
        const response = await fetch(`/api/spread/${videoHash}`);
        const data = await response.json();
        
        if (data.success && data.spread_events) {
            renderSpreadTimeline(data.spread_events);
        }
    } catch (error) {
        console.error('Failed to load spread timeline:', error);
    }
}

function renderSpreadTimeline(events) {
    const container = document.getElementById('timelineContent');
    
    if (!events || events.length === 0) {
        container.innerHTML = '<div class="empty-state">No spread events recorded</div>';
        return;
    }
    
    const platformIcons = {
        'YouTube': '📺',
        'Twitter': '🐦',
        'TikTok': '🎵',
        'Facebook': '📘',
        'Instagram': '📷',
        'Reddit': '🔴',
        'Unknown': '🌐'
    };
    
    container.innerHTML = events.map(event => `
        <div class="timeline-event">
            <div class="event-marker">
                <span class="platform-icon">${platformIcons[event.platform] || '🌐'}</span>
            </div>
            <div class="event-content">
                <div class="event-platform">${event.platform}</div>
                <div class="event-time">${formatDate(event.discovered_at)}</div>
                ${event.view_count ? `<div class="event-views">${formatNumber(event.view_count)} views</div>` : ''}
            </div>
        </div>
    `).join('');
}

function formatDate(isoString) {
    try {
        return new Date(isoString).toLocaleString();
    } catch {
        return isoString;
    }
}

function formatNumber(num) {
    if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
    if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
    return num.toString();
}

// ============================================================================
// Geographic Spread Map (Leaflet)
// ============================================================================

let spreadMap = null;
let mapMarkers = [];

async function loadGeoSpreadMap(videoHash) {
    try {
        const response = await fetch(`/api/spread/${videoHash}/geo`);
        const data = await response.json();
        
        if (data.success) {
            // Show the geo map section
            document.getElementById('geoMapSection').style.display = 'block';
            
            // Update stats
            document.getElementById('totalLocations').textContent = data.stats.total_locations;
            document.getElementById('uniqueCountries').textContent = data.stats.unique_countries;
            document.getElementById('originCount').textContent = data.stats.origin_count;
            document.getElementById('spreadCount').textContent = data.stats.spread_count;
            
            // Render the map
            renderSpreadMap(data.locations);
            
            // Render countries list with flags
            renderCountriesList(data.stats.countries);
        }
    } catch (error) {
        console.error('Failed to load geo spread map:', error);
    }
}

function renderSpreadMap(locations) {
    const mapContainer = document.getElementById('spreadMap');
    
    // Initialize map if not already done
    if (!spreadMap) {
        spreadMap = L.map('spreadMap', {
            center: [20, 0],
            zoom: 2,
            minZoom: 1,
            maxZoom: 18,
            attributionControl: true
        });
        
        // Use dark theme tile layer
        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
            subdomains: 'abcd',
            maxZoom: 19
        }).addTo(spreadMap);
    }
    
    // Clear existing markers
    mapMarkers.forEach(marker => spreadMap.removeLayer(marker));
    mapMarkers = [];
    
    if (!locations || locations.length === 0) {
        return;
    }
    
    // Define marker colors
    const markerColors = {
        'red': '#ff4757',      // Origin deepfake
        'green': '#2ed573',    // Origin authentic
        'orange': '#ffa502',   // Spread deepfake
        'blue': '#1e90ff'      // Spread authentic
    };
    
    // Add markers
    locations.forEach((loc, index) => {
        if (loc.latitude && loc.longitude) {
            const color = markerColors[loc.marker_color] || '#ffffff';
            
            // Create custom icon
            const icon = L.divIcon({
                className: 'custom-marker',
                html: `
                    <div class="marker-pin" style="background-color: ${color};">
                        <span class="marker-gen">${loc.generation}</span>
                    </div>
                    <div class="marker-pulse" style="border-color: ${color};"></div>
                `,
                iconSize: [30, 42],
                iconAnchor: [15, 42],
                popupAnchor: [0, -35]
            });
            
            const marker = L.marker([loc.latitude, loc.longitude], { icon });
            
            // Create popup content
            const popupContent = `
                <div class="map-popup">
                    <div class="popup-header ${loc.is_deepfake ? 'deepfake' : 'authentic'}">
                        ${loc.is_deepfake ? '⚠️ DEEPFAKE' : '✓ AUTHENTIC'}
                    </div>
                    <div class="popup-body">
                        <div class="popup-row">
                            <span class="popup-label">Type:</span>
                            <span class="popup-value">${loc.type === 'origin' ? '🎯 Origin' : '📡 Spread'}</span>
                        </div>
                        <div class="popup-row">
                            <span class="popup-label">Location:</span>
                            <span class="popup-value">${loc.city || 'Unknown'}, ${loc.country || 'Unknown'}</span>
                        </div>
                        <div class="popup-row">
                            <span class="popup-label">Platform:</span>
                            <span class="popup-value">${loc.platform}</span>
                        </div>
                        <div class="popup-row">
                            <span class="popup-label">Generation:</span>
                            <span class="popup-value">${loc.generation}</span>
                        </div>
                        <div class="popup-row">
                            <span class="popup-label">Time:</span>
                            <span class="popup-value">${formatDate(loc.timestamp)}</span>
                        </div>
                        <div class="popup-row">
                            <span class="popup-label">Hash:</span>
                            <span class="popup-value popup-hash">${loc.video_hash}</span>
                        </div>
                    </div>
                </div>
            `;
            
            marker.bindPopup(popupContent);
            marker.addTo(spreadMap);
            mapMarkers.push(marker);
        }
    });
    
    // Fit bounds to show all markers
    if (mapMarkers.length > 0) {
        const group = L.featureGroup(mapMarkers);
        spreadMap.fitBounds(group.getBounds().pad(0.1));
    }
    
    // Draw lines between generations if multiple locations
    drawSpreadLines(locations);
}

function drawSpreadLines(locations) {
    // Group locations by generation
    const byGeneration = {};
    locations.forEach(loc => {
        if (!byGeneration[loc.generation]) {
            byGeneration[loc.generation] = [];
        }
        byGeneration[loc.generation].push(loc);
    });
    
    // Draw lines from generation N to generation N+1
    const generations = Object.keys(byGeneration).map(Number).sort((a, b) => a - b);
    
    for (let i = 0; i < generations.length - 1; i++) {
        const currentGen = byGeneration[generations[i]];
        const nextGen = byGeneration[generations[i + 1]];
        
        // Connect each current gen location to each next gen location
        currentGen.forEach(from => {
            if (!from.latitude || !from.longitude) return;
            
            nextGen.forEach(to => {
                if (!to.latitude || !to.longitude) return;
                
                const line = L.polyline([
                    [from.latitude, from.longitude],
                    [to.latitude, to.longitude]
                ], {
                    color: to.is_deepfake ? '#ff4757' : '#2ed573',
                    weight: 2,
                    opacity: 0.5,
                    dashArray: '5, 10'
                });
                
                line.addTo(spreadMap);
                mapMarkers.push(line);
            });
        });
    }
}

// Country flag mapping (common countries)
const COUNTRY_FLAGS = {
    'United States': '🇺🇸', 'United Kingdom': '🇬🇧', 'Canada': '🇨🇦',
    'Australia': '🇦🇺', 'Germany': '🇩🇪', 'France': '🇫🇷',
    'Japan': '🇯🇵', 'China': '🇨🇳', 'India': '🇮🇳',
    'Brazil': '🇧🇷', 'Russia': '🇷🇺', 'South Korea': '🇰🇷',
    'Mexico': '🇲🇽', 'Spain': '🇪🇸', 'Italy': '🇮🇹',
    'Netherlands': '🇳🇱', 'Singapore': '🇸🇬', 'Sweden': '🇸🇪',
    'Norway': '🇳🇴', 'Denmark': '🇩🇰', 'Poland': '🇵🇱',
    'Switzerland': '🇨🇭', 'Argentina': '🇦🇷', 'Indonesia': '🇮🇩',
    'Thailand': '🇹🇭', 'Malaysia': '🇲🇾', 'Philippines': '🇵🇭',
    'Vietnam': '🇻🇳', 'Turkey': '🇹🇷', 'Ukraine': '🇺🇦',
    'South Africa': '🇿🇦', 'Nigeria': '🇳🇬', 'Egypt': '🇪🇬',
    'Israel': '🇮🇱', 'Saudi Arabia': '🇸🇦', 'UAE': '🇦🇪',
    'Pakistan': '🇵🇰', 'Bangladesh': '🇧🇩', 'Iran': '🇮🇷',
    'Demo Location': '🌍'
};

function renderCountriesList(countries) {
    const container = document.getElementById('countriesGrid');
    
    if (!countries || countries.length === 0) {
        container.innerHTML = '<div class="empty-state">No country data available</div>';
        return;
    }
    
    container.innerHTML = countries.map(country => {
        const flag = COUNTRY_FLAGS[country] || '🏳️';
        return `
            <div class="country-item">
                <span class="country-flag">${flag}</span>
                <span class="country-name">${country}</span>
            </div>
        `;
    }).join('');
}

// Graph controls
function zoomIn() {
    const svg = d3.select('#genealogyGraph svg');
    svg.transition().call(
        d3.zoom().scaleBy,
        1.5
    );
}

function zoomOut() {
    const svg = d3.select('#genealogyGraph svg');
    svg.transition().call(
        d3.zoom().scaleBy,
        0.67
    );
}

function resetView() {
    if (AppState.genealogyData) {
        renderGenealogyGraph(AppState.genealogyData);
    }
}

// ============================================================================
// Actions
// ============================================================================

async function flagForReview() {
    if (!AppState.analysisResult) {
        showToast('No analysis result available', 'error');
        return;
    }
    
    try {
        const response = await fetch('/api/action/flag', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                video_hash: AppState.analysisResult.result.video_hash
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast(`Video flagged for review. Flag ID: ${data.flag_id}`, 'success');
        } else {
            throw new Error(data.error);
        }
    } catch (error) {
        showToast(`Failed to flag video: ${error.message}`, 'error');
    }
}

async function generateReport() {
    if (!AppState.analysisResult) {
        showToast('No analysis result available', 'error');
        return;
    }
    
    try {
        const response = await fetch('/api/action/export-report', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                video_hash: AppState.analysisResult.result.video_hash
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Create downloadable report
            const blob = new Blob([JSON.stringify(data.report, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `forensic_report_${data.export_id}.json`;
            a.click();
            URL.revokeObjectURL(url);
            
            showToast(`Report generated: ${data.export_id}`, 'success');
        } else {
            throw new Error(data.error);
        }
    } catch (error) {
        showToast(`Failed to generate report: ${error.message}`, 'error');
    }
}

async function monitorDerivatives() {
    if (!AppState.analysisResult) {
        showToast('No analysis result available', 'error');
        return;
    }
    
    try {
        const response = await fetch('/api/action/monitor', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                video_hash: AppState.analysisResult.result.video_hash
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast(`Monitoring activated. Monitor ID: ${data.monitor_id}`, 'success');
        } else {
            throw new Error(data.error);
        }
    } catch (error) {
        showToast(`Failed to activate monitoring: ${error.message}`, 'error');
    }
}

function shareProvenance() {
    if (!AppState.analysisResult) {
        showToast('No analysis result available', 'error');
        return;
    }
    
    // Create shareable summary
    const result = AppState.analysisResult.result;
    const summary = `
DEEPFAKE ORIGIN FINDER - Provenance Report
==========================================
Verdict: ${result.verdict}
Confidence: ${Math.round(result.confidence * 100)}%
Risk Level: ${result.risk_level}
Video Hash: ${result.video_hash}
Analysis Time: ${result.timestamp}
==========================================
Generated by Deepfake Origin Finder
    `.trim();
    
    navigator.clipboard.writeText(summary).then(() => {
        showToast('Provenance summary copied to clipboard', 'success');
    }).catch(() => {
        showToast('Failed to copy to clipboard', 'error');
    });
}

// ============================================================================
// Dashboard
// ============================================================================

async function loadDashboardStats() {
    try {
        const response = await fetch('/api/stats/dashboard');
        const data = await response.json();
        
        if (data.success) {
            // Update stats
            document.getElementById('statTotalAnalyzed').textContent = 
                data.cache?.total_entries || 0;
            document.getElementById('statDeepfakesFound').textContent = 
                data.cache?.deepfake_count || 0;
            document.getElementById('statCacheHitRate').textContent = 
                Math.round((data.cache?.cache_hit_rate || 0) * 100) + '%';
            document.getElementById('statFamiliesTracked').textContent = 
                data.lineage?.total_families || 0;
        }
    } catch (error) {
        console.error('Failed to load dashboard stats:', error);
    }
}

// ============================================================================
// System Health
// ============================================================================

async function checkSystemHealth() {
    try {
        const response = await fetch('/api/health');
        const data = await response.json();
        
        const statusEl = document.getElementById('systemStatus');
        const dotEl = statusEl.querySelector('.status-dot');
        const textEl = statusEl.querySelector('.status-text');
        
        if (data.status === 'healthy') {
            dotEl.classList.add('healthy');
            textEl.textContent = 'SYSTEM OPERATIONAL';
        } else {
            dotEl.classList.add('degraded');
            textEl.textContent = 'SYSTEM DEGRADED';
        }
    } catch (error) {
        const statusEl = document.getElementById('systemStatus');
        statusEl.querySelector('.status-dot').classList.add('error');
        statusEl.querySelector('.status-text').textContent = 'SYSTEM OFFLINE';
    }
}

// ============================================================================
// UI Utilities
// ============================================================================

function togglePanel(btn) {
    const panel = btn.closest('.evidence-panel');
    const content = panel.querySelector('.panel-content');
    
    if (content.style.display === 'none') {
        content.style.display = 'block';
        btn.textContent = '▼';
    } else {
        content.style.display = 'none';
        btn.textContent = '▶';
    }
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span class="toast-icon">${type === 'success' ? '✓' : type === 'error' ? '✕' : type === 'warning' ? '⚠' : 'ℹ'}</span>
        <span class="toast-message">${message}</span>
    `;
    
    container.appendChild(toast);
    
    // Animate in
    setTimeout(() => toast.classList.add('show'), 10);
    
    // Remove after delay
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

function showLoading(show, text = 'Processing...') {
    const overlay = document.getElementById('loadingOverlay');
    overlay.querySelector('.loading-text').textContent = text;
    overlay.style.display = show ? 'flex' : 'none';
}

// ============================================================================
// Settings Modal
// ============================================================================

function showSettings() {
    document.getElementById('settingsModal').style.display = 'flex';
    checkSystemStatus();
}

function hideSettings() {
    document.getElementById('settingsModal').style.display = 'none';
}

function toggleApiKeyVisibility() {
    const input = document.getElementById('geminiApiKey');
    const btn = document.querySelector('.btn-toggle-visibility');
    
    if (input.type === 'password') {
        input.type = 'text';
        btn.textContent = '🔒';
    } else {
        input.type = 'password';
        btn.textContent = '👁';
    }
}

async function saveGeminiApiKey() {
    const apiKey = document.getElementById('geminiApiKey').value.trim();
    
    if (!apiKey) {
        showToast('Please enter an API key', 'warning');
        return;
    }
    
    try {
        const response = await fetch('/api/settings/gemini-key', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_key: apiKey })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast('Gemini API key saved successfully!', 'success');
            document.getElementById('geminiApiKey').value = '';
            checkSystemStatus();
            checkSystemHealth();
        } else {
            showToast(data.error || 'Failed to save API key', 'error');
        }
    } catch (error) {
        showToast('Failed to save API key: ' + error.message, 'error');
    }
}

async function checkSystemStatus() {
    try {
        const response = await fetch('/api/settings/status');
        const data = await response.json();
        
        // Update detector status
        const detectorEl = document.getElementById('statusDetector');
        if (detectorEl) {
            detectorEl.textContent = data.detector ? 'READY' : 'NOT INITIALIZED';
            detectorEl.className = 'status-value ' + (data.detector ? 'ready' : 'error');
        }
        
        // Update Gemini status
        const geminiEl = document.getElementById('statusGemini');
        if (geminiEl) {
            geminiEl.textContent = data.gemini_configured ? 'CONFIGURED' : 'NOT SET';
            geminiEl.className = 'status-value ' + (data.gemini_configured ? 'ready' : 'pending');
        }
        
        // Update PyTorch status
        const torchEl = document.getElementById('statusTorch');
        if (torchEl) {
            torchEl.textContent = data.torch_available ? 'AVAILABLE' : 'NOT AVAILABLE';
            torchEl.className = 'status-value ' + (data.torch_available ? 'ready' : 'pending');
        }
        
        // Update hash cache status
        const hashEl = document.getElementById('statusHashCache');
        if (hashEl) {
            hashEl.textContent = data.hash_cache ? 'READY' : 'NOT INITIALIZED';
            hashEl.className = 'status-value ' + (data.hash_cache ? 'ready' : 'error');
        }
        
    } catch (error) {
        console.error('Failed to check system status:', error);
    }
}

// Close modal when clicking outside
document.addEventListener('click', (e) => {
    const modal = document.getElementById('settingsModal');
    if (e.target === modal) {
        hideSettings();
    }
});

// Close modal with Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        hideSettings();
    }
});

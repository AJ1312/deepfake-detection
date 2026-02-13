/**
 * Host Dashboard — JavaScript
 * WebSocket integration + UI updates
 */

// Connect WebSocket
const socket = io ? io() : null;

if (socket) {
    socket.on('connect', () => {
        document.getElementById('status-dot').classList.add('online');
        document.getElementById('status-text').textContent = 'Online';
        socket.emit('subscribe', { room: 'detection' });
        socket.emit('subscribe', { room: 'alerts' });
        socket.emit('subscribe', { room: 'network' });
    });

    socket.on('disconnect', () => {
        document.getElementById('status-dot').classList.remove('online');
        document.getElementById('status-text').textContent = 'Disconnected';
    });

    // Detection events
    socket.on('detection_started', data => {
        addFeedItem('live-feed', `Analyzing: ${data.filename}`, 'info');
    });

    socket.on('detection_progress', data => {
        const pct = Math.round(data.progress * 100);
        const fill = document.getElementById('progress-fill');
        if (fill) fill.style.width = pct + '%';
        const text = document.getElementById('progress-text');
        if (text) text.textContent = `${data.stage} (${pct}%)`;
    });

    socket.on('detection_complete', data => {
        const r = data.result || {};
        const cls = r.is_deepfake ? 'deepfake' : 'authentic';
        const label = r.is_deepfake ? '⚠️ DEEPFAKE' : '✅ AUTHENTIC';
        addFeedItem('live-feed', `${label} — confidence: ${((r.confidence || 0) * 100).toFixed(1)}%`, cls);
        refreshStats();
    });

    // Alert events
    socket.on('new_alert', data => {
        const alert = data.alert || {};
        addFeedItem('alerts-feed', `🔔 ${alert.alert_type || 'Alert'}: ${alert.message || ''}`, 'alert');
    });

    // Network events
    socket.on('peer_joined', data => {
        const p = data.peer || {};
        addFeedItem('live-feed', `Peer joined: ${p.node_id}`, 'info');
        refreshPeers();
    });

    socket.on('peer_left', data => {
        const p = data.peer || {};
        addFeedItem('live-feed', `Peer left: ${p.node_id}`, 'info');
        refreshPeers();
    });
}

// Feed management
function addFeedItem(containerId, message, cls) {
    const container = document.getElementById(containerId);
    if (!container) return;

    // Remove empty placeholder
    const empty = container.querySelector('.feed-empty');
    if (empty) empty.remove();

    const item = document.createElement('div');
    item.className = 'feed-item ' + (cls || '');
    item.innerHTML = `
        <span>${message}</span>
        <small>${new Date().toLocaleTimeString()}</small>
    `;
    container.insertBefore(item, container.firstChild);

    // Keep max 50 items
    while (container.children.length > 50) {
        container.removeChild(container.lastChild);
    }
}

// Upload handling
const uploadZone = document.getElementById('upload-zone');
const videoInput = document.getElementById('video-input');
const analyzeBtn = document.getElementById('analyze-btn');
const form = document.getElementById('upload-form');

if (uploadZone) {
    uploadZone.addEventListener('dragover', e => { e.preventDefault(); uploadZone.classList.add('dragover'); });
    uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('dragover'));
    uploadZone.addEventListener('drop', e => {
        e.preventDefault();
        uploadZone.classList.remove('dragover');
        if (e.dataTransfer.files.length) {
            videoInput.files = e.dataTransfer.files;
            analyzeBtn.disabled = false;
        }
    });
}

if (videoInput) {
    videoInput.addEventListener('change', () => { analyzeBtn.disabled = !videoInput.files.length; });
}

if (form) {
    form.addEventListener('submit', async e => {
        e.preventDefault();
        const file = videoInput.files[0];
        if (!file) return;

        analyzeBtn.disabled = true;
        document.getElementById('upload-progress').style.display = 'block';
        document.getElementById('progress-fill').style.width = '20%';
        document.getElementById('progress-text').textContent = 'Uploading...';

        const formData = new FormData();
        formData.append('video', file);

        try {
            document.getElementById('progress-text').textContent = 'Analyzing...';
            document.getElementById('progress-fill').style.width = '40%';

            const resp = await fetch('/api/analyze', { method: 'POST', body: formData });
            const result = await resp.json();

            document.getElementById('progress-fill').style.width = '100%';
            document.getElementById('progress-text').textContent = 'Done!';
            showResult(result);
        } catch (err) {
            document.getElementById('progress-text').textContent = 'Error: ' + err.message;
            analyzeBtn.disabled = false;
        }
    });
}

function showResult(r) {
    const panel = document.getElementById('result-panel');
    if (!panel) return;
    panel.style.display = 'block';

    const verdict = document.getElementById('result-verdict');
    if (r.error) {
        verdict.className = 'verdict error';
        verdict.textContent = 'Error: ' + r.error;
        return;
    }

    verdict.className = r.is_deepfake ? 'verdict deepfake' : 'verdict authentic';
    verdict.textContent = r.is_deepfake ? '⚠️ DEEPFAKE DETECTED' : '✅ AUTHENTIC VIDEO';

    document.getElementById('r-confidence').textContent = ((r.confidence || 0) * 100).toFixed(1) + '%';
    document.getElementById('r-lipsync').textContent = ((r.lipsync_score || 0) * 100).toFixed(1) + '%';
    document.getElementById('r-factcheck').textContent = r.fact_check_score != null 
        ? ((r.fact_check_score * 100).toFixed(1) + '%') : 'N/A';
    document.getElementById('r-tx').textContent = r.blockchain_tx || 'N/A';
    document.getElementById('r-time').textContent = (r.processing_time || 0).toFixed(2) + 's';
}

// Periodic stat refresh
async function refreshStats() {
    try {
        const resp = await fetch('/api/stats');
        const data = await resp.json();
        document.getElementById('stat-analyzed').textContent = data.stats?.videos_analyzed || 0;
        document.getElementById('stat-deepfakes').textContent = data.stats?.deepfakes_found || 0;
        document.getElementById('stat-blockchain').textContent = data.stats?.blockchain_writes || 0;
        if (data.peers) {
            document.getElementById('stat-peers').textContent = data.peers.length;
        }
    } catch (e) {}
}

async function refreshPeers() {
    try {
        const resp = await fetch('/api/network/peers');
        const data = await resp.json();
        const tbody = document.getElementById('peers-body');
        if (!tbody) return;

        if (!data.peers || !data.peers.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty">No peers connected</td></tr>';
            return;
        }

        tbody.innerHTML = data.peers.map(p => `
            <tr>
                <td>${p.node_id}</td>
                <td>${p.role}</td>
                <td>${p.address}:${p.port}</td>
                <td>${p.latency_ms.toFixed(1)}ms</td>
                <td><span class="status-dot online"></span> Online</td>
            </tr>
        `).join('');
    } catch (e) {}
}

// Auto-refresh
setInterval(refreshStats, 10000);
setInterval(refreshPeers, 15000);
refreshStats();
refreshPeers();

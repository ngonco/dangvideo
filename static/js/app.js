// State
let appState = {
  videos: [],
  config: {},
  stats: {},
  ws: null
};

// DOM Elements
const tabBtns = document.querySelectorAll('.tab-btn');
const tabViews = document.querySelectorAll('.tab-view');
const videoGrid = document.getElementById('videoGridContainer');
const terminalBody = document.getElementById('terminalBody');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  setupTabs();
  setupWebSocket();
  loadStats();
  loadVideos();
  loadConfig();
  loadSystemVersion();
  setupEventListeners();

  setInterval(() => {
    loadStats();
  }, 15000);
});

// Tab Switching
function setupTabs() {
  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.dataset.tab;
      tabBtns.forEach(b => b.classList.remove('active'));
      tabViews.forEach(v => v.classList.remove('active'));
      
      btn.classList.add('active');
      const viewEl = document.getElementById(`tab-${target}`);
      if (viewEl) viewEl.classList.add('active');
    });
  });
}

// WebSocket Live Logs
function setupWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/logs`;

  appState.ws = new WebSocket(wsUrl);

  appState.ws.onmessage = (event) => {
    try {
      const log = JSON.parse(event.data);
      appendLogLine(log);
    } catch (e) {
      console.error(e);
    }
  };

  appState.ws.onclose = () => {
    setTimeout(setupWebSocket, 3000);
  };
}

function appendLogLine(log) {
  if (!terminalBody) return;
  const line = document.createElement('div');
  line.className = `log-line ${log.level || 'INFO'}`;
  line.innerHTML = `
    <span class="log-time">[${log.time || ''}]</span>
    <span class="log-cat">[${log.category || 'SYSTEM'}]</span>
    <span class="log-msg">${escapeHtml(log.message || '')}</span>
  `;
  terminalBody.appendChild(line);
  terminalBody.scrollTop = terminalBody.scrollHeight;
}

// Load Stats
async function loadStats() {
  try {
    const res = await fetch('/api/stats');
    const data = await res.json();
    appState.stats = data;

    document.getElementById('statTotalVideos').innerText = data.total_videos || 0;
    document.getElementById('statPostsToday').innerText = `${data.posts_today || 0} / ${data.max_posts_per_day || 3}`;
    document.getElementById('statTotalSuccess').innerText = data.total_posts_success || 0;
    
    const autoStatusEl = document.getElementById('statAutoStatus');
    const autoModeText = document.getElementById('autoModeText');
    const autoModeIcon = document.getElementById('autoModeIcon');
    const botBadgeText = document.getElementById('botStatusText');
    const botBadge = document.getElementById('botStatusBadge');

    if (data.auto_mode) {
      autoStatusEl.innerText = 'Đang Bật';
      autoStatusEl.style.color = 'var(--success)';
      autoModeText.innerText = 'Lịch Tự Động: BẬT';
      autoModeIcon.innerText = '▶️';
    } else {
      autoStatusEl.innerText = 'Đang Tắt';
      autoStatusEl.style.color = 'var(--text-muted)';
      autoModeText.innerText = 'Lịch Tự Động: TẮT';
      autoModeIcon.innerText = '⏸️';
    }

    if (data.is_busy) {
      botBadgeText.innerText = 'Đang xử lý tác vụ...';
      botBadge.style.borderColor = 'var(--primary)';
    } else {
      botBadgeText.innerText = 'Sẵn sàng';
      botBadge.style.borderColor = 'var(--border-color)';
    }

  } catch (err) {
    console.error('Lỗi khi tải stats:', err);
  }
}

// Load Videos
async function loadVideos() {
  try {
    const res = await fetch('/api/videos');
    const data = await res.json();
    appState.videos = data.videos || [];
    renderVideos(appState.videos);
  } catch (err) {
    console.error('Lỗi khi tải danh sách video:', err);
  }
}

function renderVideos(videos) {
  if (!videoGrid) return;
  videoGrid.innerHTML = '';

  if (videos.length === 0) {
    videoGrid.innerHTML = `
      <div class="empty-state" style="grid-column: 1 / -1;">
        <div class="empty-state-icon">📭</div>
        <h3>Chưa có video nào trong hệ thống</h3>
        <p>Bấm nút <strong>"Quét HatBuiNho"</strong> hoặc <strong>"Test Tải Video Mới Nhất"</strong> để tải video về máy!</p>
      </div>
    `;
    return;
  }

  videos.forEach(v => {
    const filename = v.file_path ? v.file_path.split(/[\\/]/).pop() : '';
    const mediaUrl = filename ? `/media/${filename}` : '';
    
    const statuses = {};
    if (v.platform_statuses) {
      v.platform_statuses.split(',').forEach(item => {
        const [plat, stat] = item.split(':');
        if (plat) statuses[plat] = stat;
      });
    }

    const titleToShow = v.suggested_title || v.title || 'Video không tên';
    const isCleaned = v.status === 'cleaned' || !v.file_path;
    const hasPosts = v.post_attempts_count > 0 || Object.keys(statuses).length > 0;

    const card = document.createElement('div');
    card.className = 'video-card';
    card.innerHTML = `
      <div class="video-player-box">
        ${mediaUrl ? `
          <video controls preload="metadata" src="${mediaUrl}"></video>
        ` : `
          <div style="color: var(--text-dim); text-align: center; padding: 1rem;">
            ${isCleaned ? '🧹 File video đã được dọn dẹp sau 2 ngày' : 'Chưa có file preview'}
          </div>
        `}
      </div>
      <div class="video-card-body">
        <div class="video-title" title="${escapeHtml(titleToShow)}">
          ${escapeHtml(titleToShow)}
        </div>
        ${v.hashtags ? `<div class="video-hashtags">${escapeHtml(v.hashtags)}</div>` : ''}
        
        <div class="video-script-preview">
          ${escapeHtml(v.raw_script || 'Không có kịch bản gốc')}
        </div>

        <div class="video-meta-row">
          <span>🕒 ${v.created_date_str || v.downloaded_at || ''}</span>
          <div class="platform-badges">
            <span class="p-badge ${statuses.youtube === 'success' ? 'success' : (statuses.youtube === 'failed' ? 'failed' : '')}" title="YouTube">YT</span>
            <span class="p-badge ${statuses.tiktok === 'success' ? 'success' : (statuses.tiktok === 'failed' ? 'failed' : '')}" title="TikTok">TT</span>
            <span class="p-badge ${statuses.facebook === 'success' ? 'success' : (statuses.facebook === 'failed' ? 'failed' : '')}" title="Facebook">FB</span>
            <span class="p-badge ${statuses.instagram === 'success' ? 'success' : (statuses.instagram === 'failed' ? 'failed' : '')}" title="Instagram">IG</span>
          </div>
        </div>

        <div class="video-actions" style="display: flex; flex-direction: column; gap: 8px;">
          <div style="display: flex; gap: 8px;">
            ${!isCleaned ? `
              <button class="btn btn-primary btn-sm" style="flex: 1;" onclick="openPostModal(${v.id}, '${escapeHtml(titleToShow)}')">
                🚀 Đăng Ngay
              </button>
            ` : `
              <button class="btn btn-outline btn-sm" style="flex: 1; opacity: 0.6;" disabled>
                ✅ Đã Dọn Dẹp
              </button>
            `}
            
            ${hasPosts ? `
              <button class="btn btn-outline btn-sm" style="flex: 1; border-color: var(--primary); color: var(--primary);" onclick="openLinksModal(${v.id})">
                🔗 Xem Link Đã Đăng
              </button>
            ` : ''}
          </div>
        </div>
      </div>
    `;
    videoGrid.appendChild(card);
  });
}

// Load Config
async function loadConfig() {
  try {
    const res = await fetch('/api/config');
    const cfg = await res.json();
    appState.config = cfg;

    const plats = cfg.platforms || {};
    document.getElementById('cfgYtEnabled').checked = plats.youtube?.enabled ?? true;
    document.getElementById('cfgTtEnabled').checked = plats.tiktok?.enabled ?? true;
    document.getElementById('cfgFbEnabled').checked = plats.facebook?.enabled ?? true;
    document.getElementById('cfgIgEnabled').checked = plats.instagram?.enabled ?? true;

    const sched = cfg.schedule || {};
    document.getElementById('cfgMaxPosts').value = sched.max_posts_per_day || 3;
    document.getElementById('cfgTimeSlots').value = (sched.post_time_slots || ["08:00", "11:30", "19:30"]).join(', ');
    document.getElementById('cfgScanInterval').value = sched.scan_interval_minutes || 60;

    const cleanup = cfg.cleanup || {};
    document.getElementById('cfgAutoCleanup').checked = cleanup.auto_cleanup ?? true;
    document.getElementById('cfgRetentionDays').value = cleanup.retention_days ?? 2;

    const customCap = cfg.custom_caption || {};
    document.getElementById('cfgPrefixText').value = customCap.prefix_text || '';
    document.getElementById('cfgAppendText').value = customCap.append_text || '';

    const hat = cfg.hatbuinho || {};
    document.getElementById('cfgHatUser').value = hat.username || 'cun';
    document.getElementById('cfgHatPass').value = hat.password || '123';

  } catch (err) {
    console.error('Lỗi khi tải cấu hình:', err);
  }
}

// Save Config
async function saveConfig() {
  const timeSlotsRaw = document.getElementById('cfgTimeSlots').value;
  const timeSlots = timeSlotsRaw.split(',').map(s => s.trim()).filter(s => s.length > 0);

  const payload = {
    platforms: {
      youtube: { ...appState.config.platforms?.youtube, enabled: document.getElementById('cfgYtEnabled').checked },
      tiktok: { ...appState.config.platforms?.tiktok, enabled: document.getElementById('cfgTtEnabled').checked },
      facebook: { ...appState.config.platforms?.facebook, enabled: document.getElementById('cfgFbEnabled').checked },
      instagram: { ...appState.config.platforms?.instagram, enabled: document.getElementById('cfgIgEnabled').checked }
    },
    schedule: {
      ...appState.config.schedule,
      max_posts_per_day: parseInt(document.getElementById('cfgMaxPosts').value) || 3,
      post_time_slots: timeSlots,
      scan_interval_minutes: parseInt(document.getElementById('cfgScanInterval').value) || 60
    },
    cleanup: {
      auto_cleanup: document.getElementById('cfgAutoCleanup').checked,
      retention_days: parseInt(document.getElementById('cfgRetentionDays').value) || 2
    },
    custom_caption: {
      prefix_text: document.getElementById('cfgPrefixText').value,
      append_text: document.getElementById('cfgAppendText').value
    },
    hatbuinho: {
      ...appState.config.hatbuinho,
      username: document.getElementById('cfgHatUser').value,
      password: document.getElementById('cfgHatPass').value
    }
  };

  try {
    const res = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const result = await res.json();
    if (result.success) {
      alert('Đã lưu cấu hình thành công!');
      loadConfig();
      loadStats();
    }
  } catch (err) {
    alert('Lỗi khi lưu cấu hình: ' + err.message);
  }
}

// Event Listeners
function setupEventListeners() {
  document.getElementById('btnQuickScan').addEventListener('click', () => triggerScan(false));
  document.getElementById('btnScanCustom').addEventListener('click', () => triggerScan(false));
  document.getElementById('btnTestDownloadLatest').addEventListener('click', () => triggerScan(true));
  document.getElementById('btnRefreshVideos').addEventListener('click', loadVideos);
  document.getElementById('btnSaveConfig').addEventListener('click', saveConfig);
  document.getElementById('btnToggleAuto').addEventListener('click', toggleAutoMode);
  document.getElementById('btnClearLogs').addEventListener('click', () => {
    terminalBody.innerHTML = '';
  });
  document.getElementById('btnManualCleanup').addEventListener('click', triggerManualCleanup);

  // System Update Buttons
  const btnHeaderUpdate = document.getElementById('btnHeaderUpdate');
  if (btnHeaderUpdate) btnHeaderUpdate.addEventListener('click', triggerSystemUpdate);
  const btnSystemUpdate = document.getElementById('btnSystemUpdate');
  if (btnSystemUpdate) btnSystemUpdate.addEventListener('click', triggerSystemUpdate);

  // AutoStart Switch Listener
  const autoStartToggle = document.getElementById('cfgAutoStart');
  if (autoStartToggle) {
    autoStartToggle.addEventListener('change', (e) => {
      handleAutoStartToggle(e.target.checked);
    });
  }

  document.getElementById('btnClosePostModal').addEventListener('click', closePostModal);
  document.getElementById('btnCancelPostModal').addEventListener('click', closePostModal);
  document.getElementById('btnConfirmPost').addEventListener('click', executePostModal);

  document.getElementById('btnCloseLinksModal').addEventListener('click', closeLinksModal);
  document.getElementById('btnCloseLinksModalBtn').addEventListener('click', closeLinksModal);
}

// Load System Version & AutoStart Status
async function loadSystemVersion() {
  try {
    const res = await fetch('/api/system/version');
    const data = await res.json();
    const verEl = document.getElementById('systemVersionText');
    const dateEl = document.getElementById('systemCommitDate');
    if (verEl) {
      verEl.innerText = `Phiên bản: ${data.commit || 'v1.0.0'}`;
    }
    if (dateEl && data.date) {
      dateEl.innerText = `(${data.date})`;
    }
  } catch (e) {
    console.error('Không thể tải phiên bản hệ thống:', e);
  }

  // Load AutoStart status
  try {
    const res = await fetch('/api/system/autostart');
    const data = await res.json();
    const autoStartToggle = document.getElementById('cfgAutoStart');
    if (autoStartToggle) {
      autoStartToggle.checked = !!data.enabled;
    }
  } catch (e) {
    console.error('Không thể tải trạng thái autostart:', e);
  }
}

// Toggle AutoStart
async function handleAutoStartToggle(enabled) {
  try {
    const res = await fetch('/api/system/autostart', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled })
    });
    const data = await res.json();
    if (res.ok) {
      const msg = data.enabled 
        ? '✅ ĐÃ BẬT TỰ ĐỘNG KHỞI ĐỘNG CÙNG WINDOWS!\n\nMỗi khi bạn mở máy tính, phần mềm sẽ tự động chạy ngầm để đảm bảo kịp giờ đăng video.' 
        : '🛑 ĐÃ TẮT TỰ ĐỘNG KHỞI ĐỘNG CÙNG WINDOWS.';
      alert(msg);
    }
  } catch (e) {
    alert('Lỗi khi thiết lập autostart: ' + e.message);
  }
}

// Trigger System Update from GitHub
async function triggerSystemUpdate() {
  if (!confirm('Bạn có muốn kiểm tra và cập nhật mã nguồn mới nhất từ kho lưu trữ GitHub (origin/main) không?')) {
    return;
  }

  const btnHeader = document.getElementById('btnHeaderUpdate');
  const btnSettings = document.getElementById('btnSystemUpdate');
  if (btnHeader) btnHeader.innerText = '⏳ Đang tải...';
  if (btnSettings) btnSettings.innerText = '⏳ Đang cập nhật từ GitHub...';

  try {
    const res = await fetch('/api/system/update', { method: 'POST' });
    const data = await res.json();
    if (res.ok && data.success) {
      alert(`✅ CẬP NHẬT THÀNH CÔNG!\n\n${data.message}`);
      loadSystemVersion();
      loadConfig();
    } else {
      alert(`❌ LỖI KHI CẬP NHẬT:\n\n${data.error || data.detail || 'Không thể kéo mã nguồn từ GitHub.'}`);
    }
  } catch (e) {
    alert('Lỗi mạng khi cập nhật: ' + e.message);
  } finally {
    if (btnHeader) btnHeader.innerHTML = '<span>🔄</span> Cập Nhật';
    if (btnSettings) btnSettings.innerHTML = '<span>🔄</span> Kiểm Tra & Cập Nhật Mã Nguồn Ngay';
  }
}

// Trigger Scan
async function triggerScan(forceLatest = false) {
  try {
    const res = await fetch('/api/action/scan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ force_latest: forceLatest })
    });
    const data = await res.json();
    if (res.ok) {
      const modeText = forceLatest ? 'Chế độ TEST: Đang ép tải video mới nhất...' : 'Đang quét các video Chưa tải xuống...';
      alert(modeText + ' Bạn có thể xem tiến trình tại tab "Nhật Ký Realtime"!');
      document.querySelector('.tab-btn[data-tab="logs"]').click();
    } else {
      alert(data.detail || 'Lỗi khi kích hoạt quét.');
    }
  } catch (e) {
    alert('Lỗi mạng: ' + e.message);
  }
}

// Trigger Manual Cleanup
async function triggerManualCleanup() {
  const days = document.getElementById('cfgRetentionDays').value || 2;
  if (!confirm(`Bạn có chắc muốn dọn dẹp các tệp video .mp4 đã đăng cũ hơn ${days} ngày không? (Dữ liệu bài đăng trong lịch sử vẫn được giữ nguyên)`)) {
    return;
  }

  try {
    const res = await fetch('/api/action/cleanup', { method: 'POST' });
    const data = await res.json();
    if (res.ok) {
      const r = data.results || {};
      alert(`Dọn dẹp hoàn tất!\n- Đã xóa: ${r.deleted_count || 0} tệp video\n- Giải phóng: ${r.freed_mb || 0} MB`);
      loadVideos();
      loadStats();
    }
  } catch (e) {
    alert('Lỗi khi dọn dẹp: ' + e.message);
  }
}

// Toggle Auto
async function toggleAutoMode() {
  try {
    const res = await fetch('/api/action/toggle-scheduler', { method: 'POST' });
    const data = await res.json();
    loadStats();
  } catch (e) {
    console.error(e);
  }
}

// Open Login Browser
async function openLoginUrl(url) {
  try {
    await fetch('/api/action/open-login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url })
    });
    alert('Đang mở trình duyệt Chrome. Bạn hãy đăng nhập tài khoản vào cửa sổ vừa mở nhé!');
  } catch (e) {
    alert('Lỗi: ' + e.message);
  }
}

// Post Modal Logic
function openPostModal(videoId, title) {
  document.getElementById('modalVideoId').value = videoId;
  document.getElementById('modalVideoTitleInput').value = title;
  document.getElementById('postModal').classList.add('open');
}

function closePostModal() {
  document.getElementById('postModal').classList.remove('open');
}

async function executePostModal() {
  const videoId = parseInt(document.getElementById('modalVideoId').value);
  const targets = [];
  if (document.getElementById('postModalYt').checked) targets.push('youtube');
  if (document.getElementById('postModalTt').checked) targets.push('tiktok');
  if (document.getElementById('postModalFb').checked) targets.push('facebook');
  if (document.getElementById('postModalIg').checked) targets.push('instagram');

  if (targets.length === 0) {
    alert('Vui lòng chọn ít nhất 1 nền tảng để đăng!');
    return;
  }

  closePostModal();

  try {
    const res = await fetch('/api/action/post', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ video_id: videoId, target_platforms: targets })
    });
    const data = await res.json();
    if (res.ok) {
      alert('Đã gửi yêu cầu đăng video. Hệ thống đang tiến hành mở trình duyệt để upload...');
      document.querySelector('.tab-btn[data-tab="logs"]').click();
    } else {
      alert(data.detail || 'Lỗi khi đăng bài.');
    }
  } catch (e) {
    alert('Lỗi mạng: ' + e.message);
  }
}

// Links Modal Logic
async function openLinksModal(videoId) {
  const modalBody = document.getElementById('linksModalBody');
  modalBody.innerHTML = '<div style="text-align: center; padding: 2rem; color: var(--text-muted);">Đang tải thông tin liên kết bài đăng...</div>';
  document.getElementById('linksModal').classList.add('open');

  try {
    const res = await fetch(`/api/videos/${videoId}/history`);
    const data = await res.json();
    const video = data.video || {};
    const posts = data.posts || [];

    const platIcons = {
      youtube: '▶️ YouTube Shorts',
      tiktok: '🎵 TikTok',
      facebook: '📘 Facebook Reels',
      instagram: '📸 Instagram Reels'
    };

    let html = `
      <div style="margin-bottom: 1.2rem; padding-bottom: 0.8rem; border-bottom: 1px solid var(--border-color);">
        <h4 style="font-size: 1rem; color: #fff; margin-bottom: 4px;">${escapeHtml(video.suggested_title || video.title || 'Video')}</h4>
        <small style="color: var(--text-muted);">Hashtags: ${escapeHtml(video.hashtags || '')}</small>
      </div>
    `;

    if (posts.length === 0) {
      html += `
        <div style="text-align: center; padding: 1.5rem; color: var(--text-muted);">
          Chưa có bài đăng nào được thực hiện cho video này.
        </div>
      `;
    } else {
      html += '<div style="display: flex; flex-direction: column; gap: 12px;">';
      posts.forEach(p => {
        const platName = platIcons[p.platform] || p.platform.toUpperCase();
        const isSuccess = p.status === 'success';
        const postUrl = p.post_url || '';

        html += `
          <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: 12px 14px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
              <span style="font-weight: 600; font-size: 0.95rem;">${platName}</span>
              <span style="font-size: 0.75rem; padding: 3px 8px; border-radius: 12px; font-weight: 600; background: ${isSuccess ? 'rgba(34,197,94,0.15); color: #4ade80;' : 'rgba(239,68,68,0.15); color: #f87171;'}">
                ${isSuccess ? '✅ Thành công' : '❌ Thất bại'}
              </span>
            </div>
            
            ${isSuccess && postUrl ? `
              <div style="display: flex; align-items: center; gap: 8px; background: rgba(0,0,0,0.2); padding: 8px 10px; border-radius: 6px; font-size: 0.85rem;">
                <a href="${escapeHtml(postUrl)}" target="_blank" style="color: var(--primary); text-decoration: none; word-break: break-all; flex: 1;">
                  🔗 ${escapeHtml(postUrl)}
                </a>
                <button class="btn btn-outline btn-sm" style="padding: 3px 8px; font-size: 0.75rem;" onclick="copyToClipboard('${escapeHtml(postUrl)}')">
                  📋 Copy
                </button>
              </div>
            ` : (isSuccess ? `
              <div style="font-size: 0.85rem; color: var(--success);">
                Đã đăng thành công lên kênh của bạn.
              </div>
            ` : `
              <div style="font-size: 0.85rem; color: #f87171;">
                Lỗi: ${escapeHtml(p.error_message || 'Không xác định')}
              </div>
            `)}

            <div style="font-size: 0.75rem; color: var(--text-dim); margin-top: 6px;">
              🕒 Thời gian: ${escapeHtml(p.posted_at || '')}
            </div>
          </div>
        `;
      });
      html += '</div>';
    }

    modalBody.innerHTML = html;

  } catch (e) {
    modalBody.innerHTML = `<div style="color: red; text-align: center;">Lỗi khi tải lịch sử: ${escapeHtml(e.message)}</div>`;
  }
}

function closeLinksModal() {
  document.getElementById('linksModal').classList.remove('open');
}

function copyToClipboard(text) {
  navigator.clipboard.writeText(text).then(() => {
    alert('Đã sao chép liên kết vào bộ nhớ tạm:\n' + text);
  }).catch(() => {
    prompt('Sao chép liên kết:', text);
  });
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

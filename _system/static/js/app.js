// ==========================================================================
// TỰ ĐỘNG ĐĂNG VIDEO — CLIENT SCRIPT (PHONG CÁCH MỘC & ĐƠN GIẢN)
// ==========================================================================

let isAutoMode = true;
let isMuteAudio = true;
let isShowBrowser = false;
let currentBrowserConfig = { headless: true, mute_audio: true, user_data_dir: "browser_profiles/default" };
let currentTimeSlots = ["08:00", "11:30", "19:30"];
let socket = null;
let userManuallyToggledLogin = false;

document.addEventListener('DOMContentLoaded', () => {
    initApp();
});

async function initApp() {
    setupEventListeners();
    connectWebSocket();
    await fetchSystemVersion();
    await fetchConfigAndState();
    await fetchQueueSummary();
    await fetchAccountsStatus();
    await fetchHistory();
    await fetchAutostartStatus();

    // Tự động kiểm tra lại trạng thái tài khoản khi quay lại tab
    window.addEventListener('focus', () => {
        fetchAccountsStatus();
        fetchQueueSummary();
    });

    // Tự động làm mới lịch sử và hàng đợi mỗi 30s
    setInterval(() => {
        fetchHistory();
        fetchAccountsStatus();
        fetchQueueSummary();
    }, 30000);
}

// --------------------------------------------------------------------------
// 1. CÁC SỰ KIỆN NÚT BẤM CHÍNH
// --------------------------------------------------------------------------
function setupEventListeners() {
    // Nút 1: Bật / Tắt tự động
    const btnToggleAuto = document.getElementById('btnToggleAuto');
    if (btnToggleAuto) {
        btnToggleAuto.addEventListener('click', toggleScheduler);
    }

    // Nút 2: Đăng hàng loạt theo lịch (Đa ngày)
    const btnBatchQueue = document.getElementById('btnBatchQueue');
    if (btnBatchQueue) {
        btnBatchQueue.addEventListener('click', runBatchQueueDownload);
    }

    // Nút 3: Đăng 1 Video Ngay
    const btnPostNow = document.getElementById('btnPostNow');
    if (btnPostNow) {
        btnPostNow.addEventListener('click', runWorkflowNow);
    }

    const btnMuteAudio = document.getElementById('btnMuteAudio');
    if (btnMuteAudio) {
        btnMuteAudio.addEventListener('click', toggleMuteAudio);
    }

    const btnShowBrowser = document.getElementById('btnShowBrowser');
    if (btnShowBrowser) {
        btnShowBrowser.addEventListener('click', toggleShowBrowser);
    }

    // Nút Thêm Mốc Giờ Hẹn Đăng
    const btnAddSlot = document.getElementById('btnAddSlot');
    if (btnAddSlot) {
        btnAddSlot.addEventListener('click', addTimeSlot);
    }

    // Accordion Đăng Nhập Tài Khoản
    const btnToggleLogin = document.getElementById('btnToggleLogin');
    if (btnToggleLogin) {
        btnToggleLogin.addEventListener('click', () => {
            userManuallyToggledLogin = true;
            toggleLoginAccordion();
        });
    }

    // Nút Lưu tài khoản HatBuiNho
    const btnSaveHbn = document.getElementById('btnSaveHbn');
    if (btnSaveHbn) {
        btnSaveHbn.addEventListener('click', saveHatBuiNhoConfig);
    }

    // Accordion Tùy Chỉnh Nâng Cao
    const btnToggleAdvanced = document.getElementById('btnToggleAdvanced');
    if (btnToggleAdvanced) {
        btnToggleAdvanced.addEventListener('click', toggleAdvancedAccordion);
    }

    // Công tắc Khởi động cùng Windows
    const chkAutostart = document.getElementById('chkAutostart');
    if (chkAutostart) {
        chkAutostart.addEventListener('change', onAutostartChanged);
    }

    // Nút Dọn dẹp video cũ
    const btnManualCleanup = document.getElementById('btnManualCleanup');
    if (btnManualCleanup) {
        btnManualCleanup.addEventListener('click', manualCleanup);
    }

    // Nút Gửi Thử Email Báo Cáo
    const btnSendTestEmail = document.getElementById('btnSendTestEmail');
    if (btnSendTestEmail) {
        btnSendTestEmail.addEventListener('click', sendTestEmail);
    }

    // Nút Cập nhật phần mềm
    const btnCheckUpdate = document.getElementById('btnCheckUpdate');
    if (btnCheckUpdate) {
        btnCheckUpdate.addEventListener('click', performUpdate);
    }

    // Nút Xóa logs
    const btnClearLogs = document.getElementById('btnClearLogs');
    if (btnClearLogs) {
        btnClearLogs.addEventListener('click', () => {
            document.getElementById('logsTerminal').innerHTML = '<div class="log-line log-info">[HỆ THỐNG] Đã xóa lịch sử nhật ký hiển thị.</div>';
        });
    }
}

// --------------------------------------------------------------------------
// 2. HERO CONTROL & KHUNG HẸN GIỜ ĐĂNG VIDEO
// --------------------------------------------------------------------------
async function fetchConfigAndState() {
    try {
        const res = await fetch('/api/config');
        const data = await res.json();
        const cfg = (data && data.config && data.config.schedule) ? data.config : data;
        if (cfg) {
            isAutoMode = cfg.schedule?.auto_mode !== false;
            updateHeroUI(isAutoMode);

            if (cfg.schedule?.post_time_slots) {
                currentTimeSlots = cfg.schedule.post_time_slots;
                renderTimeSlots();
            }

            if (cfg.browser) {
                currentBrowserConfig = {
                    headless: cfg.browser.headless !== false,
                    mute_audio: cfg.browser.mute_audio !== false,
                    user_data_dir: cfg.browser.user_data_dir || "browser_profiles/default"
                };
            }
            isMuteAudio = currentBrowserConfig.mute_audio !== false;
            isShowBrowser = currentBrowserConfig.headless === false;
            updateMuteUI(isMuteAudio);
            updateShowBrowserUI(isShowBrowser);

            // Điền form HatBuiNho
            if (cfg.hatbuinho) {
                document.getElementById('hbnUsername').value = cfg.hatbuinho.username || '';
                document.getElementById('hbnPassword').value = cfg.hatbuinho.password || '';
            }
        }
    } catch (e) {
        console.error('Lỗi nạp cấu hình:', e);
    }
}

function updateHeroUI(autoRunning) {
    isAutoMode = autoRunning;
    const heroBox = document.getElementById('heroStatusBox');
    const heroIcon = document.getElementById('heroStatusIcon');
    const heroTitle = document.getElementById('heroStatusTitle');
    const heroDesc = document.getElementById('heroStatusDesc');

    const btnToggle = document.getElementById('btnToggleAuto');
    const btnIcon = document.getElementById('btnToggleIcon');
    const btnMain = document.getElementById('btnToggleMainText');
    const btnSub = document.getElementById('btnToggleSubText');

    if (autoRunning) {
        heroBox.classList.remove('paused');
        heroIcon.innerText = '🟢';
        heroTitle.innerText = 'HỆ THỐNG ĐANG TỰ ĐỘNG ĐĂNG VIDEO';
        heroDesc.innerText = 'Đang tự động chạy ngầm theo các khung giờ hẹn bên dưới. Khi bật laptop là máy tự chạy.';

        btnToggle.classList.remove('is-paused');
        btnIcon.innerText = '⏸️';
        btnMain.innerText = 'BẬT / TẮT TỰ ĐỘNG';
        btnSub.innerText = 'Đăng tự động mỗi ngày 1 lần (Đang BẬT)';
    } else {
        heroBox.classList.add('paused');
        heroIcon.innerText = '⚪';
        heroTitle.innerText = 'HỆ THỐNG ĐANG TẠM DỪNG';
        heroDesc.innerText = 'Chế độ tự động đăng đang tắt. Bấm nút bên dưới để bật tự động chạy.';

        btnToggle.classList.add('is-paused');
        btnIcon.innerText = '▶️';
        btnMain.innerText = 'BẬT / TẮT TỰ ĐỘNG';
        btnSub.innerText = 'Đăng tự động mỗi ngày 1 lần (Đang TẮT)';
    }
}

function updateMuteUI(muted) {
    isMuteAudio = muted !== false;
    const btn = document.getElementById('btnMuteAudio');
    const icon = document.getElementById('btnMuteIcon');
    const main = document.getElementById('btnMuteMainText');
    const sub = document.getElementById('btnMuteSubText');
    if (!btn) return;

    if (isMuteAudio) {
        btn.classList.remove('is-unmuted');
        if (icon) icon.innerText = '🔇';
        if (main) main.innerText = 'TẮT TIẾNG TRÌNH DUYỆT';
        if (sub) sub.innerText = 'Đang BẬT — mọi cửa sổ Playwright im lặng';
    } else {
        btn.classList.add('is-unmuted');
        if (icon) icon.innerText = '🔊';
        if (main) main.innerText = 'TẮT TIẾNG TRÌNH DUYỆT';
        if (sub) sub.innerText = 'Đang TẮT — trình duyệt có tiếng';
    }
}

function applyBrowserConfig(browser) {
    currentBrowserConfig = {
        headless: browser.headless !== false,
        mute_audio: browser.mute_audio !== false,
        user_data_dir: browser.user_data_dir || "browser_profiles/default"
    };
    isMuteAudio = currentBrowserConfig.mute_audio !== false;
    isShowBrowser = currentBrowserConfig.headless === false;
    updateMuteUI(isMuteAudio);
    updateShowBrowserUI(isShowBrowser);
}

function updateShowBrowserUI(shown) {
    isShowBrowser = shown === true;
    const btn = document.getElementById('btnShowBrowser');
    const icon = document.getElementById('btnShowBrowserIcon');
    const main = document.getElementById('btnShowBrowserMainText');
    const sub = document.getElementById('btnShowBrowserSubText');
    if (!btn) return;

    if (isShowBrowser) {
        btn.classList.add('is-shown');
        if (icon) icon.innerText = '👁️';
        if (main) main.innerText = 'HIỂN THỊ QUÁ TRÌNH ĐĂNG';
        if (sub) sub.innerText = 'Đang BẬT — mở cửa sổ để xem từng bước';
    } else {
        btn.classList.remove('is-shown');
        if (icon) icon.innerText = '🙈';
        if (main) main.innerText = 'HIỂN THỊ QUÁ TRÌNH ĐĂNG';
        if (sub) sub.innerText = 'Đang TẮT — đăng ẩn, không mở cửa sổ';
    }
}

async function saveBrowserConfig(partial, successMessage) {
    currentBrowserConfig = {
        headless: currentBrowserConfig.headless !== false,
        mute_audio: currentBrowserConfig.mute_audio !== false,
        user_data_dir: currentBrowserConfig.user_data_dir || "browser_profiles/default",
        ...partial
    };
    try {
        const res = await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ browser: currentBrowserConfig })
        });
        const data = await res.json();
        if (data.success) {
            if (data.config && data.config.browser) {
                applyBrowserConfig(data.config.browser);
            } else {
                applyBrowserConfig(currentBrowserConfig);
            }
            if (successMessage) showToast(successMessage, 'success');
            return true;
        }
        showToast('❌ Không lưu được cấu hình trình duyệt.', 'error');
        return false;
    } catch (e) {
        showToast('❌ Không lưu được cấu hình trình duyệt.', 'error');
        return false;
    }
}

async function toggleMuteAudio() {
    const nextMuted = !isMuteAudio;
    await saveBrowserConfig(
        { mute_audio: nextMuted },
        nextMuted
            ? '🔇 Đã tắt tiếng trình duyệt Playwright (đăng nhập, tải, đăng).'
            : '🔊 Đã bật tiếng trình duyệt Playwright.'
    );
}

async function toggleShowBrowser() {
    const nextShown = !isShowBrowser;
    await saveBrowserConfig(
        { headless: !nextShown },
        nextShown
            ? '👁️ Đã bật hiện cửa sổ khi tải và đăng video.'
            : '🙈 Đã ẩn cửa sổ đăng video (chạy ẩn). Nút đăng nhập vẫn mở cửa sổ.'
    );
}

async function toggleScheduler() {
    try {
        const res = await fetch('/api/action/toggle-scheduler', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            updateHeroUI(data.auto_mode);
            showToast(data.auto_mode ? '🟢 Đã BẬT chế độ tự động đăng video theo hẹn giờ!' : '⏸️ Đã TẠM DỪNG chế độ tự động!');
        }
    } catch (e) {
        showToast('❌ Có lỗi khi bật/tắt tự động.', 'error');
    }
}

function renderTimeSlots() {
    const container = document.getElementById('timeSlotsHeroList');
    if (!container) return;

    if (!currentTimeSlots || currentTimeSlots.length === 0) {
        container.innerHTML = '<p style="color: var(--text-muted); font-style: italic; padding: 6px 0;">Chưa có mốc giờ nào. Hãy chọn giờ và bấm nút Thêm Mốc Giờ ở dưới!</p>';
        return;
    }

    container.innerHTML = currentTimeSlots.map(slot => {
        const [h, m] = slot.split(':');
        const hourNum = parseInt(h, 10);
        const icon = hourNum < 11 ? '🌅' : (hourNum < 18 ? '☀️' : '🌙');
        const period = hourNum < 11 ? 'Sáng' : (hourNum < 18 ? 'Trưa/Chiều' : 'Tối');
        return `
            <div class="slot-chip-hero">
                <span>${icon} <b>${slot}</b> (${period})</span>
                <button class="btn-delete-slot" onclick="deleteTimeSlot('${slot}')" title="Xóa mốc giờ ${slot}">✕</button>
            </div>
        `;
    }).join('');
}

async function addTimeSlot() {
    const input = document.getElementById('inputNewSlot');
    const slot = input ? input.value.trim() : '';
    if (!slot || !slot.includes(':')) {
        showToast('⚠️ Vui lòng chọn mốc giờ hợp lệ!', 'warn');
        return;
    }

    if (currentTimeSlots.includes(slot)) {
        showToast(`⚠️ Mốc giờ ${slot} đã có trong danh sách rồi!`, 'warn');
        return;
    }

    const updated = [...currentTimeSlots, slot].sort();
    await saveTimeSlots(updated, `⏰ Đã thêm mốc giờ hẹn đăng: ${slot}!`);
}

async function deleteTimeSlot(slot) {
    if (currentTimeSlots.length <= 1) {
        showToast('⚠️ Cần giữ lại ít nhất 1 khung giờ đăng video trong ngày!', 'warn');
        return;
    }

    const updated = currentTimeSlots.filter(s => s !== slot);
    await saveTimeSlots(updated, `🗑️ Đã xóa mốc giờ ${slot}!`);
}

async function saveTimeSlots(slots, successMsg) {
    try {
        const res = await fetch('/api/schedule/timeslots', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ time_slots: slots })
        });
        const data = await res.json();
        if (data.success) {
            currentTimeSlots = data.time_slots;
            renderTimeSlots();
            showToast(successMsg || '⏰ Đã cập nhật khung giờ hẹn đăng!', 'success');
            await fetchQueueSummary();
        }
    } catch (e) {
        showToast('❌ Lỗi khi lưu khung giờ.', 'error');
    }
}

async function fetchQueueSummary() {
    try {
        const res = await fetch('/api/queue/summary');
        const data = await res.json();
        const textElem = document.getElementById('queueSummaryText');
        if (textElem && data.success && data.queue) {
            const { total_pending, estimated_days } = data.queue;
            if (total_pending > 0) {
                textElem.innerHTML = `<b style="color: var(--tea-green); font-size: 15px;">${total_pending} video</b> đang chờ trong kho (Dự kiến tự động đăng trong <b style="color: var(--warm-orange);">${estimated_days} ngày</b> tới theo các mốc giờ)`;
            } else {
                textElem.innerHTML = `Kho đang trống (0 video). Hệ thống sẽ tự động quét tải video 'Chưa tải xuống' cũ nhất khi đến giờ hẹn.`;
            }
        }
    } catch (e) {
        console.error('Lỗi đọc tóm tắt hàng đợi:', e);
    }
}

async function runBatchQueueDownload() {
    const btn = document.getElementById('btnBatchQueue');
    const progressBox = document.getElementById('workflowProgressBox');
    const progressTitle = document.getElementById('progressTitle');
    const progressPercent = document.getElementById('progressPercent');
    const progressBarFill = document.getElementById('progressBarFill');
    const progressStepDetail = document.getElementById('progressStepDetail');

    if (btn) {
        btn.disabled = true;
        btn.style.opacity = '0.7';
    }
    progressBox.style.display = 'block';
    progressPercent.innerText = '20%';
    progressBarFill.style.width = '20%';
    progressTitle.innerText = '📦 Đang quét & tải toàn bộ video từ HatBuiNho...';
    progressStepDetail.innerText = 'Hệ thống đang mở trình duyệt và gom tất cả video chưa tải vào kho...';

    showToast('📦 Đang quét & tải toàn bộ video vào Kho Hàng Đợi...', 'info');

    try {
        const res = await fetch('/api/action/batch-download-queue', { method: 'POST' });
        const data = await res.json();

        if (data.success) {
            progressPercent.innerText = '100%';
            progressBarFill.style.width = '100%';
            progressTitle.innerText = '✅ Hoàn tất gom video vào kho!';
            progressStepDetail.innerText = data.message || `Đã tải về ${data.downloaded_count || 0} video mới vào kho hàng đợi.`;
            showToast(`🎉 ${data.message || 'Đã gom video thành công!'}`, 'success');
            await fetchQueueSummary();
        } else {
            progressTitle.innerText = '⚠️ Thông báo quét video:';
            progressStepDetail.innerText = data.error || data.message || 'Không tải được video.';
            showToast(data.error || 'Chưa tải được video.', 'warn');
        }
    } catch (e) {
        progressTitle.innerText = '❌ Có sự cố khi tải hàng loạt';
        progressStepDetail.innerText = e.message;
        showToast('❌ Sự cố kết nối máy chủ.', 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.style.opacity = '1';
        }
        setTimeout(() => {
            progressBox.style.display = 'none';
        }, 10000);
    }
}

// --------------------------------------------------------------------------
// 3. ĐĂNG 1 VIDEO NGAY BÂY GIỜ (RUN WORKFLOW)
// --------------------------------------------------------------------------
async function runWorkflowNow() {
    const btn = document.getElementById('btnPostNow');
    const progressBox = document.getElementById('workflowProgressBox');
    const progressTitle = document.getElementById('progressTitle');
    const progressPercent = document.getElementById('progressPercent');
    const progressBarFill = document.getElementById('progressBarFill');
    const progressStepDetail = document.getElementById('progressStepDetail');

    btn.disabled = true;
    btn.style.opacity = '0.7';
    progressBox.style.display = 'block';
    progressPercent.innerText = '15%';
    progressBarFill.style.width = '15%';
    progressTitle.innerText = '⏳ Đang quét và tải video từ HatBuiNho...';
    progressStepDetail.innerText = 'Ưu tiên video Chưa tải xuống; hết thì lấy video mới nhất...';

    showToast('⚡ Bắt đầu tiến trình tải & đăng 1 video...', 'info');

    try {
        const res = await fetch('/api/action/run-workflow', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: 'normal' })
        });
        const data = await res.json();
        
        if (data.success) {
            progressPercent.innerText = '100%';
            progressBarFill.style.width = '100%';
            progressTitle.innerText = '✅ Hoàn tất đăng video!';
            progressStepDetail.innerText = data.message || 'Đã phân phối đăng video thành công lên các kênh.';
            showToast('🎉 Đăng video thành công!', 'success');
            await fetchHistory();
        } else {
            progressTitle.innerText = '⚠️ Thông báo từ hệ thống:';
            progressStepDetail.innerText = data.message || data.error || 'Có thông tin cần kiểm tra.';
            showToast(data.message || 'Chưa đăng được video.', 'warn');
        }
    } catch (e) {
        progressTitle.innerText = '❌ Có sự cố khi đăng video';
        progressStepDetail.innerText = e.message;
        showToast('❌ Sự cố kết nối máy chủ.', 'error');
    } finally {
        btn.disabled = false;
        btn.style.opacity = '1';
        setTimeout(() => {
            progressBox.style.display = 'none';
        }, 10000);
    }
}

// --------------------------------------------------------------------------
// 4. ACCORDION ĐĂNG NHẬP TÀI KHOẢN & KIỂM TRA TRẠNG THÁI
// --------------------------------------------------------------------------
function toggleLoginAccordion() {
    const content = document.getElementById('loginAccordionContent');
    const arrow = document.getElementById('accordionLoginArrow');
    if (!content) return;

    if (content.style.display === 'none') {
        content.style.display = 'block';
        if (arrow) arrow.classList.add('rotated');
    } else {
        content.style.display = 'none';
        if (arrow) arrow.classList.remove('rotated');
    }
}

async function fetchAccountsStatus() {
    try {
        const res = await fetch('/api/accounts/status');
        const data = await res.json();
        if (data.success && data.statuses) {
            updateAccountBadge('statusHatBuiNho', data.statuses.hatbuinho, 'Đã Cấu Hình', 'Chưa Cấu Hình');
            updateAccountBadge('statusYouTube', data.statuses.youtube, 'Đã Đăng Nhập', 'Chưa Đăng Nhập');
            updateAccountBadge('statusTikTok', data.statuses.tiktok, 'Đã Đăng Nhập', 'Chưa Đăng Nhập');
            updateAccountBadge('statusFacebook', data.statuses.facebook, 'Đã Đăng Nhập', 'Chưa Đăng Nhập');
            updateAccountBadge('statusInstagram', data.statuses.instagram, 'Đã Đăng Nhập', 'Chưa Đăng Nhập');

            // Tính số lượng kênh đã kết nối
            const total = 5;
            let connected = 0;
            if (data.statuses.hatbuinho) connected++;
            if (data.statuses.youtube) connected++;
            if (data.statuses.tiktok) connected++;
            if (data.statuses.facebook) connected++;
            if (data.statuses.instagram) connected++;

            const badgeSummary = document.getElementById('badgeAccountSummary');
            const loginSub = document.getElementById('loginAccordionSub');
            const loginContent = document.getElementById('loginAccordionContent');
            const arrow = document.getElementById('accordionLoginArrow');

            if (badgeSummary) {
                if (connected === total) {
                    badgeSummary.innerText = `🟢 Đã kết nối đủ 5/5 kênh`;
                    badgeSummary.style.background = 'var(--tea-green-light)';
                    badgeSummary.style.color = 'var(--tea-green)';
                    badgeSummary.style.borderColor = 'var(--tea-green-border)';
                    if (loginSub) loginSub.innerText = 'Tất cả tài khoản đã sẵn sàng tự động đăng video.';
                    
                    // Tự động thu gọn nếu user chưa can thiệp thủ công
                    if (!userManuallyToggledLogin && loginContent) {
                        loginContent.style.display = 'none';
                        if (arrow) arrow.classList.remove('rotated');
                    }
                } else {
                    badgeSummary.innerText = `⚠️ Đã kết nối ${connected}/5 kênh`;
                    badgeSummary.style.background = '#FFF8E1';
                    badgeSummary.style.color = '#F57F17';
                    badgeSummary.style.borderColor = '#FFE082';
                    if (loginSub) loginSub.innerText = '👉 Có kênh chưa đăng nhập. Bấm vào đây để đăng nhập tài khoản!';
                    
                    // Tự động mở rộng nếu còn thiếu kênh
                    if (!userManuallyToggledLogin && loginContent) {
                        loginContent.style.display = 'block';
                        if (arrow) arrow.classList.add('rotated');
                    }
                }
            }
        }
    } catch (e) {
        console.error('Lỗi đọc trạng thái tài khoản:', e);
    }
}

function updateAccountBadge(elemId, isConnected, connectedText, pendingText) {
    const elem = document.getElementById(elemId);
    if (!elem) return;
    if (isConnected) {
        elem.className = 'account-status-badge badge-connected';
        elem.innerText = `🟢 ${connectedText}`;
    } else {
        elem.className = 'account-status-badge badge-pending';
        elem.innerText = `⚪ ${pendingText}`;
    }
}

async function openLoginBrowser(platform) {
    const names = {
        'hatbuinho': 'HatBuiNho.com',
        'youtube': 'YouTube Studio',
        'tiktok': 'TikTok Creator',
        'facebook': 'Facebook',
        'instagram': 'Instagram'
    };
    const pName = names[platform] || platform.toUpperCase();
    showToast(`🌐 Đang mở trình duyệt để bạn đăng nhập ${pName}...`, 'info');

    try {
        const res = await fetch(`/api/browser/open-login/${platform}`, { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            showToast(`👉 Hãy đăng nhập ${pName} trên cửa sổ vừa mở, sau đó đóng lại là xong!`, 'success');
        }
    } catch (e) {
        showToast('❌ Không thể mở trình duyệt.', 'error');
    }
}

async function saveHatBuiNhoConfig() {
    const u = document.getElementById('hbnUsername').value.trim();
    const p = document.getElementById('hbnPassword').value.trim();
    try {
        const res = await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                hatbuinho: { username: u, password: p, auto_login: true, url: "https://hatbuinho.com/" }
            })
        });
        const data = await res.json();
        if (data.success) {
            showToast('💾 Đã lưu tài khoản HatBuiNho thành công!', 'success');
            await fetchAccountsStatus();
        }
    } catch (e) {
        showToast('❌ Lỗi khi lưu tài khoản.', 'error');
    }
}

// --------------------------------------------------------------------------
// 5. DANH SÁCH CÁC VIDEO ĐÃ ĐĂNG
// --------------------------------------------------------------------------
async function fetchHistory() {
    try {
        const res = await fetch('/api/history');
        const data = await res.json();
        const tbody = document.getElementById('historyTableBody');
        if (!tbody) return;
        
        if (!data.history || data.history.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="empty-table-msg">Chưa có video nào trong kho hoặc đã đăng. Bấm nút <b>"Bấm Đăng 1 Video Ngay"</b> ở trên để thử nghiệm!</td></tr>';
            return;
        }

        const platformsList = ["youtube", "tiktok", "facebook", "instagram"];
        const platformNames = {
            "youtube": "YouTube",
            "tiktok": "TikTok",
            "facebook": "Facebook",
            "instagram": "Instagram"
        };
        const platformIcons = {
            "youtube": "▶️",
            "tiktok": "🎵",
            "facebook": "📘",
            "instagram": "📸"
        };

        const rowsHtml = data.history.map((v, index) => {
            const rawTitle = v.suggested_title || v.title || `Video #${v.id || (index + 1)}`;
            const isPosted = v.status === 'posted';
            const isQueue = v.status === 'downloaded';

            const statusTag = isPosted 
                ? '<span class="tag-video-status tag-posted">✅ Đã xuất bản</span>' 
                : (isQueue ? '<span class="tag-video-status tag-downloaded">📦 Trong kho chờ đăng</span>' : '');

            const platforms = v.platforms || {};
            const linksHtml = platformsList.map(plat => {
                const p = platforms[plat];
                const pName = platformNames[plat];
                const pIcon = platformIcons[plat];

                if (!p) {
                    return `<span class="btn-view-post badge-pending">⚪ ${pName} (Chờ)</span>`;
                }

                if (p.status === 'success') {
                    if (p.post_url && p.post_url.startsWith('http')) {
                        return `<a href="${p.post_url}" target="_blank" class="btn-view-post link-${plat}">${pIcon} ${pName} ↗</a>`;
                    } else {
                        return `<span class="btn-view-post link-${plat}">🟢 ${pName} (Đã đăng)</span>`;
                    }
                } else {
                    return `<span class="btn-view-post badge-failed" title="Chi tiết lỗi: ${escapeHtml(p.error_message || 'Thất bại')}">❌ ${pName} (Lỗi)</span>`;
                }
            }).join(' ');

            return `
                <tr>
                    <td><b>#${index + 1}</b></td>
                    <td class="video-title-text">
                        <div style="font-size: 15px; font-weight: 700; color: var(--text-main);">${escapeHtml(rawTitle)}</div>
                        <div style="margin-top: 4px;">${statusTag}</div>
                    </td>
                    <td class="video-time-text">${escapeHtml(v.time || 'Mới đây')}</td>
                    <td><div class="platform-links-group">${linksHtml}</div></td>
                </tr>
            `;
        }).join('');

        tbody.innerHTML = rowsHtml;
    } catch (e) {
        console.error('Lỗi tải lịch sử:', e);
    }
}

// --------------------------------------------------------------------------
// 6. ACCORDION CÀI ĐẶT NÂNG CAO
// --------------------------------------------------------------------------
function toggleAdvancedAccordion() {
    const content = document.getElementById('advancedContent');
    const arrow = document.getElementById('accordionAdvancedArrow');
    if (!content) return;

    if (content.style.display === 'none' || content.style.display === '') {
        content.style.display = 'block';
        if (arrow) arrow.classList.add('rotated');
    } else {
        content.style.display = 'none';
        if (arrow) arrow.classList.remove('rotated');
    }
}

async function fetchAutostartStatus() {
    try {
        const res = await fetch('/api/system/autostart');
        const data = await res.json();
        const chk = document.getElementById('chkAutostart');
        const lbl = document.getElementById('lblAutostart');
        if (chk && lbl) {
            chk.checked = !!data.enabled;
            lbl.innerText = data.enabled ? 'Đang BẬT tự khởi động' : 'Đang TẮT';
        }
    } catch (e) {
        console.error('Lỗi autostart:', e);
    }
}

async function onAutostartChanged(e) {
    const enabled = e.target.checked;
    const lbl = document.getElementById('lblAutostart');
    lbl.innerText = 'Đang lưu...';
    try {
        const res = await fetch('/api/system/autostart', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled })
        });
        const data = await res.json();
        lbl.innerText = data.enabled ? 'Đang BẬT tự khởi động' : 'Đang TẮT';
        showToast(data.enabled ? '🚀 Đã BẬT tự khởi động cùng Windows!' : 'Đã TẮT tự khởi động!', 'info');
    } catch (err) {
        showToast('❌ Lỗi cài đặt autostart.', 'error');
    }
}

async function manualCleanup() {
    showToast('🧹 Đang quét dọn dẹp các file video cũ hơn 2 ngày...', 'info');
    try {
        const res = await fetch('/api/action/cleanup-old-videos', { method: 'POST' });
        const data = await res.json();
        showToast(data.message || '✅ Đã dọn dẹp xong video cũ!', 'success');
    } catch (e) {
        showToast('❌ Lỗi khi dọn dẹp.', 'error');
    }
}

async function sendTestEmail() {
    const btn = document.getElementById('btnSendTestEmail');
    if (btn) {
        btn.disabled = true;
        btn.innerText = '⏳ Đang gửi...';
    }
    showToast('📧 Đang gửi email kiểm thử tới thv.vinh@gmail.com...', 'info');
    try {
        const res = await fetch('/api/action/send-test-email', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            showToast('✅ Đã gửi email kiểm thử thành công tới thv.vinh@gmail.com!', 'success');
        } else {
            showToast(data.error || '❌ Không thể gửi email.', 'error');
        }
    } catch (e) {
        showToast('❌ Lỗi kết nối máy chủ.', 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerText = '📧 Gửi Thử Email Báo Cáo';
        }
    }
}

async function performUpdate() {
    const btn = document.getElementById('btnCheckUpdate');
    btn.disabled = true;
    btn.innerText = '⏳ Đang kiểm tra...';
    showToast('🔄 Đang kết nối GitHub kiểm tra cập nhật...', 'info');
    try {
        const res = await fetch('/api/system/update', { method: 'POST' });
        const data = await res.json();
        showToast(data.message || 'Hoàn tất kiểm tra cập nhật.', 'success');
        await fetchSystemVersion();
    } catch (e) {
        showToast('❌ Không thể cập nhật từ GitHub.', 'error');
    } finally {
        btn.disabled = false;
        btn.innerText = '🔄 Kiểm Tra & Cập Nhật';
    }
}

async function fetchSystemVersion() {
    try {
        const res = await fetch('/api/system/version');
        const data = await res.json();
        const tag = document.getElementById('appVersion');
        if (tag) {
            tag.innerText = `Bản ${data.version || data.commit || '1.2.0'}`;
        }
    } catch (e) {}
}

// --------------------------------------------------------------------------
// 7. WEBSOCKET NHẬT KÝ REALTIME
// --------------------------------------------------------------------------
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/logs`;
    
    socket = new WebSocket(wsUrl);
    
    socket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            appendLogLine(data);
        } catch (e) {}
    };

    socket.onclose = () => {
        setTimeout(connectWebSocket, 3000);
    };
}

function appendLogLine(log) {
    const terminal = document.getElementById('logsTerminal');
    if (!terminal) return;

    const div = document.createElement('div');
    const lvl = (log.level || 'INFO').toLowerCase();
    div.className = `log-line log-${lvl}`;
    div.innerText = `[${log.time || ''}] [${log.category || 'SYSTEM'}] ${log.message || ''}`;
    terminal.appendChild(div);
    terminal.scrollTop = terminal.scrollHeight;
}

// --------------------------------------------------------------------------
// 8. TOAST NOTIFICATION & HELPER
// --------------------------------------------------------------------------
let toastTimeout = null;
function showToast(message, type = 'info') {
    const toast = document.getElementById('toastBox');
    const toastMsg = document.getElementById('toastMessage');
    const toastIcon = document.getElementById('toastIcon');
    if (!toast) return;

    toastIcon.innerText = type === 'success' ? '🌿' :
                          type === 'warn' ? '⚠️' :
                          type === 'error' ? '❌' : '🌱';
    toastMsg.innerText = message;

    toast.classList.add('show');
    clearTimeout(toastTimeout);
    toastTimeout = setTimeout(() => {
        toast.classList.remove('show');
    }, 4500);
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/[&<>'"]/g, 
        tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag)
    );
}

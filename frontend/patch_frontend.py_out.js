const originalFetch = window.fetch;
window.fetch = function() {
    let [resource, config] = arguments;
    if (!config) config = {};
    if (!config.headers) config.headers = {};
    if (config.headers instanceof Headers) {
        config.headers.append('X-Requested-With', 'XMLHttpRequest');
        config.headers.append('X-Tunnel-Skip-AntiPhishing-Page', 'true');
    } else {
        config.headers['X-Requested-With'] = 'XMLHttpRequest';
        config.headers['X-Tunnel-Skip-AntiPhishing-Page'] = 'true';
    }
    return originalFetch(resource, config);
};
// --- STATE ---
const savedToken = sessionStorage.getItem('ramiel_token');
const savedUser = (() => {
    try {
        return JSON.parse(sessionStorage.getItem('ramiel_user') || 'null');
    } catch {
        return null;
    }
})();

let authToken = savedToken || null;
let authUser = savedUser || null;
let isFirstMessage = true;

let currentSessionId = null;
let isFirstMessage = true;
let chatTree = {};
let activeLeafId = null;

window.switchSibling = function(targetId) {
    let leaf = targetId;
    while (chatTree[leaf] && chatTree[leaf].children && chatTree[leaf].children.length > 0) {
        leaf = chatTree[leaf].children[chatTree[leaf].children.length - 1];
    }
    activeLeafId = leaf;
    renderChatPath(activeLeafId);
};

window.renderChatPath = function(leafId) {
    chatBox.innerHTML = '';
    lastMessageDate = null;
    if (!leafId) return;
    
    let path = [];
    let curr = leafId;
    while (curr && chatTree[curr]) {
        path.push(chatTree[curr]);
        curr = chatTree[curr].parent_id;
    }
    path.reverse();
    
    path.forEach(msg => {
        let siblings = [];
        if (msg.parent_id && chatTree[msg.parent_id]) {
            siblings = chatTree[msg.parent_id].children.map(id => chatTree[id]);
        } else {
            siblings = Object.values(chatTree).filter(m => !m.parent_id);
        }
        let currentIndex = siblings.findIndex(m => m.id === msg.id) + 1;
        let totalSiblings = siblings.length;
        
        let siblingNav = null;
        if (totalSiblings > 1) {
            siblingNav = { current: currentIndex, total: totalSiblings, siblings: siblings, msgId: msg.id };
        }
        
        appendMessage(msg.role, msg.content, msg.source, '', msg.id, msg.raw_content, msg.created_at, msg.attachments || [], siblingNav);
    });
    chatBox.scrollTop = chatBox.scrollHeight;
};


const chatBox       = document.getElementById('chat-box');
const userInput     = document.getElementById('user-input');
const sendBtn       = document.getElementById('send-btn');


// --- SIDEBAR ---
const sidebar         = document.getElementById('sidebar');
const sidebarOverlay  = document.getElementById('sidebar-overlay');
const toggleOpen      = document.getElementById('sidebar-toggle-open');
const toggleClose     = document.getElementById('sidebar-toggle-close');
const newChatBtn      = document.getElementById('new-chat-btn');

function openSidebar() {
    sidebar.classList.add('open');
    sidebarOverlay.classList.add('show');
}
function closeSidebar() {
    sidebar.classList.remove('open');
    sidebarOverlay.classList.remove('show');
}

toggleOpen.addEventListener('click', openSidebar);
toggleClose.addEventListener('click', closeSidebar);
sidebarOverlay.addEventListener('click', closeSidebar);

newChatBtn.addEventListener('click', () => {
    currentSessionId = null;
    closeEditPopup();
    document.querySelectorAll('.history-item').forEach(el => el.classList.remove('active'));
    chatBox.innerHTML = '';
    lastMessageDate = null;
    const hero = document.createElement('div');
    hero.id = 'hero';
    hero.className = 'hero';
    hero.innerHTML = `<h2 class="hero-title"><span class="gradient-text">RAMIEL</span></h2>
                      <p class="hero-subtitle">${quotes[Math.floor(Math.random() * quotes.length)]}</p>`;
    chatBox.appendChild(hero);
    document.getElementById('main-container').classList.add('initial-state');
    userInput.placeholder = 'Ask Ramiel...';
    isFirstMessage = true;
    closeSidebar();
});


// --- ACCOUNT BUTTON & POPUP ---
const accountBtn    = document.getElementById('account-btn');
const accountPopup  = document.getElementById('account-popup');
const popupLoggedOut = document.getElementById('popup-logged-out');
const popupLoggedIn  = document.getElementById('popup-logged-in');
const popupUsername  = document.getElementById('popup-username');
const profileModalOverlay = document.getElementById('profile-modal-overlay');
const profileStatus = document.getElementById('profile-status');
const btnMyProfile = document.getElementById('btn-my-profile');
const btnSaveProfile = document.getElementById('btn-save-profile');

function updateAccountUI() {
    const btnName = document.getElementById('account-name');
    const authScreen = document.getElementById('auth-screen');
    const mainContainer = document.getElementById('main-container');
    
    if (authUser) {
        if (btnName) btnName.textContent = authUser.username;
        accountBtn.classList.add('has-name');
        
        document.getElementById('btn-logout').classList.remove('hidden');

        if (authUser.role === 'admin' || authUser.role === 'dev') {
            const btnDev = document.getElementById('btn-dev-settings');
            btnDev.classList.remove('hidden');
            btnDev.textContent = 'Admin Settings';
        } else {
            document.getElementById('btn-dev-settings').classList.add('hidden');
        }
        
        if (authScreen) authScreen.style.display = 'none';
        if (mainContainer) mainContainer.style.display = 'flex';
        toggleOpen.classList.remove('hidden');
    } else {
        if (btnName) btnName.textContent = '';
        accountBtn.classList.remove('has-name');
        
        document.getElementById('btn-dev-settings').classList.add('hidden');
        document.getElementById('btn-logout').classList.add('hidden');

        
        if (authScreen) authScreen.style.display = 'flex';
        if (mainContainer) mainContainer.style.display = 'none';
        toggleOpen.classList.add('hidden');
        showForm(formLogin);
    }
}

accountBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    accountPopup.classList.toggle('hidden');
    updateAccountUI();
});

document.addEventListener('click', (e) => {
    if (!accountPopup.contains(e.target) && !accountBtn.contains(e.target)) {
        accountPopup.classList.add('hidden');
    }
});


// --- AUTH MODAL ---
const formLogin      = document.getElementById('form-login');
const formForgotPw   = document.getElementById('form-forgot-pw');
let loginChallengeId = null;
let loginOtpTimer = null;

function completeLogin(data) {
    authToken = data.token;
    authUser = { id: data.id, username: data.username, role: data.role };
    sessionStorage.setItem('ramiel_token', authToken);
    sessionStorage.setItem('ramiel_user', JSON.stringify(authUser));
    updateAccountUI();
    loadSessions();
}

function startOtpCountdown(button, seconds) {
    clearInterval(loginOtpTimer);
    let remaining = Math.max(0, Number(seconds) || 0);
    const updateButton = () => {
        button.disabled = remaining > 0;
        button.classList.toggle('cooldown', remaining > 0);
        button.textContent = remaining > 0 ? remaining : 'Send OTP';
    };
    updateButton();
    if (remaining > 0) {
        loginOtpTimer = setInterval(() => {
            remaining -= 1;
            updateButton();
            if (remaining <= 0) clearInterval(loginOtpTimer);
        }, 1000);
    }
}

function showForm(form) {
    formLogin.classList.add('hidden');
    formForgotPw.classList.add('hidden');
    form.classList.remove('hidden');
    accountPopup.classList.add('hidden');
    clearErrors();
    clearInputs();
}
function clearErrors() {
    document.getElementById('login-error').classList.add('hidden');
    document.getElementById('login-otp-error').classList.add('hidden');
    document.getElementById('forgot-success').style.display = 'none';
}
function clearInputs() {
    clearInterval(loginOtpTimer);
    loginChallengeId = null;
    document.getElementById('login-credentials').classList.remove('hidden');
    document.getElementById('login-otp-step').classList.add('hidden');
    document.getElementById('login-otp').value = '';
    startOtpCountdown(document.getElementById('btn-resend-login-otp'), 0);
    document.getElementById('login-username').value = '';
    document.getElementById('login-password').value = '';
    document.getElementById('forgot-email').value = '';
    
    document.getElementById('login-password').type = 'password';
    const eyeIconSVG = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="eye-icon"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
    document.querySelectorAll('.password-toggle').forEach(el => el.innerHTML = eyeIconSVG);
}

document.getElementById('switch-to-login-from-forgot').addEventListener('click', () => showForm(formLogin));
document.getElementById('btn-forgot-pw').addEventListener('click', () => showForm(formForgotPw));

if (btnMyProfile) {
    btnMyProfile.addEventListener('click', async () => {
        if (!authToken) return;
        accountPopup.classList.add('hidden');
        try {
            const res = await fetch('/api/profile', {
                headers: { 'Authorization': 'Bearer ' + authToken }
            });
            const data = await res.json();
            if (!res.ok) {
                showProfileStatus(data.error || 'Unable to load profile.', true);
                return;
            }
            fillProfileForm(data);
            if (profileModalOverlay) profileModalOverlay.classList.remove('hidden');
        } catch (e) {
            showProfileStatus('Cannot load profile right now.', true);
        }
    });
}

const btnCloseProfile = document.getElementById('btn-close-profile');
if (btnCloseProfile) btnCloseProfile.addEventListener('click', closeProfileModal);
if (profileModalOverlay) {
    profileModalOverlay.addEventListener('click', (e) => {
        if (e.target === profileModalOverlay) closeProfileModal();
    });
}

function showProfileStatus(message, isError = false) {
    if (!profileStatus) return;
    profileStatus.textContent = message;
    profileStatus.classList.toggle('hidden', !message);
    profileStatus.classList.toggle('modal-error', true);
    if (isError) {
        profileStatus.style.background = 'rgba(255,0,0,0.08)';
        profileStatus.style.color = 'var(--accent)';
    } else {
        profileStatus.style.background = 'rgba(76, 175, 80, 0.08)';
        profileStatus.style.color = '#4caf50';
    }
}

function closeProfileModal() {
    if (profileModalOverlay) profileModalOverlay.classList.add('hidden');
    if (profileStatus) {
        profileStatus.classList.add('hidden');
        profileStatus.textContent = '';
    }
}

function fillProfileForm(data) {
    document.getElementById('profile-username').value = data.username || '';
    document.getElementById('profile-email').value = data.email || '';
    document.getElementById('profile-first-name').value = data.first_name || '';
    document.getElementById('profile-last-name').value = data.last_name || '';
    document.getElementById('profile-phone').value = data.phone || '';
    document.getElementById('profile-current-password').value = '';
    document.getElementById('profile-new-password').value = '';
    document.getElementById('profile-confirm-password').value = '';
}

async function saveProfile() {
    const payload = {
        username: document.getElementById('profile-username').value.trim(),
        first_name: document.getElementById('profile-first-name').value.trim(),
        last_name: document.getElementById('profile-last-name').value.trim(),
        phone: document.getElementById('profile-phone').value.trim(),
    };
    const currentPassword = document.getElementById('profile-current-password').value;
    const newPassword = document.getElementById('profile-new-password').value;
    const confirmPassword = document.getElementById('profile-confirm-password').value;
    if (currentPassword || newPassword || confirmPassword) {
        if (!currentPassword || !newPassword || !confirmPassword) {
            showProfileStatus('Enter your current password, new password, and repeat the new password.', true);
            return;
        }
        if (newPassword !== confirmPassword) {
            showProfileStatus('New passwords do not match.', true);
            return;
        }
        if (!/^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[\W_]).{8,}$/.test(newPassword)) {
            showProfileStatus('Password must be 8+ characters with uppercase, lowercase, number, and symbol.', true);
            return;
        }
        payload.current_password = currentPassword;
        payload.new_password = newPassword;
        payload.confirm_password = confirmPassword;
        
        if (!confirm("Are you sure you want to change your password?")) {
            return;
        }
    }

    try {
        const res = await fetch('/api/profile', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + authToken },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) {
            showProfileStatus(data.error || 'Profile update failed.', true);
            return;
        }
        if (data.username && data.username !== authUser.username) {
            authUser.username = data.username;
            sessionStorage.setItem('ramiel_user', JSON.stringify(authUser));
            updateAccountUI();
        }
        if (payload.new_password) {
            alert('Password has changed successfully.');
            showProfileStatus('Password has changed successfully.', false);
        } else {
            showProfileStatus('Profile saved successfully.', false);
        }
        setTimeout(closeProfileModal, 800);
    } catch (e) {
        showProfileStatus('Unable to save profile right now.', true);
    }
}

if (btnSaveProfile) btnSaveProfile.addEventListener('click', saveProfile);

const profileNewPw = document.getElementById('profile-new-password');
if (profileNewPw) {
    profileNewPw.addEventListener('input', () => {
        const password = profileNewPw.value;
        const rulesEl = document.getElementById('profile-password-rules');
        if (password.length > 0) {
            rulesEl.classList.remove('hidden');
        } else {
            rulesEl.classList.add('hidden');
        }
        
        const checks = {
            'prof-rule-pw-len': password.length >= 8,
            'prof-rule-pw-case': /[a-z]/.test(password) && /[A-Z]/.test(password),
            'prof-rule-pw-num': /\d/.test(password),
            'prof-rule-pw-sym': /[\W_]/.test(password),
        };
        Object.entries(checks).forEach(([id, isValid]) => {
            const rule = document.getElementById(id);
            if (!rule) return;
            const icon = rule.querySelector('.rule-icon');
            rule.classList.toggle('valid', password.length > 0 && isValid);
            rule.classList.toggle('invalid', password.length > 0 && !isValid);
            icon.textContent = password.length === 0 ? '○' : isValid ? '✓' : '×';
        });
    });
}

document.getElementById('btn-send-forgot').addEventListener('click', async () => {
    const email = document.getElementById('forgot-email').value.trim();
    const status = document.getElementById('forgot-success');
    const linkEl = document.getElementById('forgot-reset-link');
    if (!email) {
        document.getElementById('forgot-email').classList.add('input-error');
        document.getElementById('forgot-email').addEventListener('input', function() {
            this.classList.remove('input-error');
        }, { once: true });
        return;
    }

    linkEl.classList.add('hidden');
    linkEl.innerHTML = '';
    status.style.display = 'none';

    try {
        const res = await fetch('/api/auth/password-reset/request', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Unable to submit the reset request.');
        status.textContent = data.message;
        status.style.color = '#4caf50';
        status.style.display = 'block';
        if (data.reset_url) {
            const a = document.createElement('a');
            a.href = data.reset_url;
            a.textContent = window.location.origin + data.reset_url;
            a.style.cssText = 'color:var(--accent); text-decoration:underline; cursor:pointer;';
            linkEl.innerHTML = 'Reset link: ';
            linkEl.appendChild(a);
            linkEl.classList.remove('hidden');
        }
    } catch (error) {
        status.textContent = error.message;
        status.style.color = 'var(--accent)';
        status.style.display = 'block';
    }
});


// --- FORM ENTER NAVIGATION ---
document.getElementById('login-username').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); document.getElementById('login-password').focus(); }
});
document.getElementById('login-password').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); document.getElementById('btn-login').click(); }
});
document.getElementById('login-otp').addEventListener('input', (event) => {
    event.target.value = event.target.value.replace(/\D/g, '').slice(0, 6);
});
document.getElementById('login-otp').addEventListener('keydown', (event) => {
    if (event.key === 'Enter') { event.preventDefault(); document.getElementById('btn-verify-login-otp').click(); }
});

// LOGIN
document.getElementById('btn-login').addEventListener('click', async () => {
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;
    const errEl = document.getElementById('login-error');
    if (!username || !password) { showError(errEl, 'Please enter username and password.'); return; }
    const button = document.getElementById('btn-login');
    button.disabled = true;
    try {
        const res = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        const data = await res.json();
        if (!res.ok) { showError(errEl, data.error || 'Login failed.'); return; }
        if (!data.otp_required) {
            completeLogin(data);
            return;
        }
        loginChallengeId = data.challenge_id;
        document.getElementById('login-credentials').classList.add('hidden');
        document.getElementById('login-otp-step').classList.remove('hidden');
        document.getElementById('login-otp-note').textContent = data.sent
            ? 'A verification code was sent to your account email.'
            : 'A code was sent recently. Wait before requesting another one.';
        showOtpPlain(data.otp_plain);
        startOtpCountdown(document.getElementById('btn-resend-login-otp'), data.cooldown_seconds);
        document.getElementById('login-otp').focus();
    } catch(e) {
        showError(errEl, 'Cannot connect to server.');
    } finally {
        button.disabled = false;
    }
});

function showOtpPlain(otp) {
    const el = document.getElementById('login-otp-plain');
    if (otp) {
        el.textContent = `OTP: ${otp}`;
        el.classList.remove('hidden');
    } else {
        el.classList.add('hidden');
        el.textContent = '';
    }
}

document.getElementById('btn-resend-login-otp').addEventListener('click', async () => {
    if (!loginChallengeId) return;
    const errorElement = document.getElementById('login-otp-error');
    errorElement.classList.add('hidden');
    const button = document.getElementById('btn-resend-login-otp');
    button.disabled = true;
    try {
        const response = await fetch('/api/auth/login/resend-otp', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ challenge_id: loginChallengeId })
        });
        const data = await response.json();
        if (!response.ok) {
            if (response.status === 404) {
                clearInputs();
                showError(document.getElementById('login-error'), data.error || 'Sign in again to request a new code.');
                return;
            }
            throw new Error(data.error || 'Unable to resend the code.');
        }
        document.getElementById('login-otp-note').textContent = data.sent
            ? 'A new verification code was sent to your account email.'
            : 'Please wait before requesting another code.';
        showOtpPlain(data.otp_plain);
        startOtpCountdown(button, data.cooldown_seconds);
    } catch (error) {
        showError(errorElement, error.message || 'Cannot connect to server.');
        button.disabled = false;
    }
});

document.getElementById('btn-verify-login-otp').addEventListener('click', async () => {
    const otp = document.getElementById('login-otp').value.trim();
    const errorElement = document.getElementById('login-otp-error');
    if (!/^\d{6}$/.test(otp)) { showError(errorElement, 'Enter the 6-digit verification code.'); return; }
    const button = document.getElementById('btn-verify-login-otp');
    button.disabled = true;
    try {
        const response = await fetch('/api/auth/login/verify-otp', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ challenge_id: loginChallengeId, otp })
        });
        const data = await response.json();
        if (!response.ok) { showError(errorElement, data.error || 'Code verification failed.'); return; }
        completeLogin(data);
    } catch {
        showError(errorElement, 'Cannot connect to server.');
    } finally {
        button.disabled = false;
    }
});

function resetAuthState() {
    authToken = null; authUser = null;
    sessionStorage.removeItem('ramiel_token');
    sessionStorage.removeItem('ramiel_user');
    localStorage.removeItem('ramiel_token');
    localStorage.removeItem('ramiel_user');
    accountPopup.classList.add('hidden');
    updateAccountUI();
    document.getElementById('chat-history-list').innerHTML = '';
}

// LOGOUT
document.getElementById('btn-logout').addEventListener('click', () => {
    resetAuthState();
    clearInputs();
    closeSidebar();
    newChatBtn.click();
});



// --- CHAT SESSIONS (SIDEBAR HISTORY) ---
let activeEditPopup = null;

function closeEditPopup() {
    const existing = document.getElementById('history-edit-popup');
    if (existing) existing.remove();
    activeEditPopup = null;
}

function showEditPopup(e, sessionId, itemEl) {
    closeEditPopup();
    const popup = document.createElement('div');
    popup.className = 'history-edit-popup';
    popup.id = 'history-edit-popup';

    const btnRename = document.createElement('button');
    btnRename.textContent = 'Rename';
    btnRename.onclick = () => { closeEditPopup(); startRename(itemEl, sessionId); };

    const btnDelete = document.createElement('button');
    btnDelete.textContent = 'Delete';
    btnDelete.className = 'danger';
    btnDelete.onclick = () => { closeEditPopup(); deleteSession(sessionId, itemEl); };

    popup.appendChild(btnRename);
    popup.appendChild(btnDelete);
    document.body.appendChild(popup);
    activeEditPopup = popup;

    const rect = e.currentTarget.getBoundingClientRect();
    const popupW = 130;
    let left = rect.left;
    if (left + popupW > window.innerWidth) left = window.innerWidth - popupW - 8;
    popup.style.top = `${rect.bottom + 4}px`;
    popup.style.left = `${left}px`;

    setTimeout(() => {
        document.addEventListener('click', closeEditPopup, { once: true });
    }, 0);
}

function startRename(itemEl, sessionId) {
    const label = itemEl.querySelector('.history-label');
    const currentTitle = label.textContent;

    const input = document.createElement('input');
    input.className = 'history-rename-input';
    input.value = currentTitle;
    label.replaceWith(input);
    input.focus();
    input.select();

    let saved = false;
    const doRename = async () => {
        if (saved) return;
        saved = true;
        const newTitle = input.value.trim() || currentTitle;
        const newLabel = document.createElement('span');
        newLabel.className = 'history-label';
        newLabel.textContent = newTitle;
        input.replaceWith(newLabel);
        if (newTitle !== currentTitle) {
            try {
                await fetch(`/api/sessions/${sessionId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + authToken },
                    body: JSON.stringify({ title: newTitle })
                });
            } catch(err) { console.error('Rename failed', err); }
        }
    };

    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); doRename(); }
        if (e.key === 'Escape') {
            saved = true;
            const origLabel = document.createElement('span');
            origLabel.className = 'history-label';
            origLabel.textContent = currentTitle;
            input.replaceWith(origLabel);
        }
    });
    input.addEventListener('blur', doRename);
}

async function deleteSession(sessionId, itemEl) {
    if (!confirm('Are you sure you want to delete this chat?')) return;
    try {
        const res = await fetch(`/api/sessions/${sessionId}`, {
            method: 'DELETE',
            headers: { 'Authorization': 'Bearer ' + authToken }
        });
        if (res.ok) {
            itemEl.remove();
            if (currentSessionId === sessionId) {
                currentSessionId = null;
                newChatBtn.click();
            }
            const list = document.getElementById('chat-history-list');
            if (!list.querySelector('.history-item')) {
                list.innerHTML = '<div style="color: var(--L50); font-size: 0.8rem; padding: 10px;">No history yet</div>';
            }
        }
    } catch(err) { console.error('Delete failed', err); }
}

function createSessionItem(session) {
    const item = document.createElement('div');
    item.className = 'history-item';
    item.dataset.sessionId = session.id;

    const label = document.createElement('span');
    label.className = 'history-label';
    label.textContent = session.title || 'New Chat';
    item.appendChild(label);

    const editBtn = document.createElement('button');
    editBtn.className = 'history-edit-btn';
    editBtn.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>`;
    editBtn.title = 'Edit';
    editBtn.addEventListener('click', (e) => { e.stopPropagation(); showEditPopup(e, session.id, item); });
    item.appendChild(editBtn);

    item.addEventListener('click', (e) => {
        if (e.target.closest('.history-edit-btn')) return;
        closeEditPopup();
        loadSessionMessages(session.id, item);
    });

    return item;
}

function refreshSessionInSidebar(sessionId, newTitle) {
    const list = document.getElementById('chat-history-list');

    // Find and remove existing item
    const existing = list.querySelector(`[data-session-id="${sessionId}"]`);
    let title = newTitle;
    if (existing) {
        if (!title) title = existing.querySelector('.history-label').textContent;
        existing.remove();
    } else if (!title) {
        title = `chat_${sessionId}`;
    }

    // Remove "No history" placeholder
    const placeholder = list.querySelector('div[style]');
    if (placeholder && !placeholder.dataset.sessionId) placeholder.remove();

    // Create and insert at top
    const item = createSessionItem({ id: sessionId, title });
    list.querySelectorAll('.history-item').forEach(el => el.classList.remove('active'));
    item.classList.add('active');
    list.insertBefore(item, list.firstChild);
}

async function loadSessions() {
    if (!authToken) return;
    try {
        const res = await fetch('/api/sessions', {
            headers: { 'Authorization': 'Bearer ' + authToken }
        });
        const data = await res.json();
        const list = document.getElementById('chat-history-list');
        list.innerHTML = '';
        if (data.length === 0) {
            list.innerHTML = '<div style="color: var(--L50); font-size: 0.8rem; padding: 10px;">No history yet</div>';
            return;
        }
        data.forEach(session => list.appendChild(createSessionItem(session)));
    } catch (e) {
        console.error('Failed to load sessions', e);
    }
}

async function loadSessionMessages(sessionId, itemElement) {
    if (!authToken) return;
    currentSessionId = sessionId;
    document.querySelectorAll('.history-item').forEach(el => el.classList.remove('active'));
    if (itemElement) itemElement.classList.add('active');

    try {
        const res = await fetch(`/api/sessions/${sessionId}/messages`, {
            headers: { 'Authorization': 'Bearer ' + authToken }
        });
        const messages = await res.json();
        
        // Clear chat area
        chatBox.innerHTML = '';
        const mainContainer = document.getElementById('main-container');
        const hero = document.getElementById('hero');
        if (hero) hero.classList.add('hidden');
        mainContainer.classList.remove('initial-state');
        userInput.placeholder = '';
        isFirstMessage = false;

        if (messages.error) {
            appendMessage('system', 'Error loading chat: ' + messages.error);
            return;
        }

        lastMessageDate = null;
        messages.forEach(msg => {
            appendMessage(msg.role, msg.content, msg.source, '', msg.id, msg.raw_content, msg.created_at);
        });

        chatBox.scrollTop = chatBox.scrollHeight;
        if (window.innerWidth <= 768) closeSidebar();

    } catch (e) {
        console.error('Failed to load messages', e);
    }
}

function togglePassword(inputId, iconSpan) {
    const input = document.getElementById(inputId);
    if (input.type === 'password') {
        input.type = 'text';
        iconSpan.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';
    } else {
        input.type = 'password';
        iconSpan.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
    }
}

function showError(el, msg) { el.textContent = msg; el.classList.remove('hidden'); }


// --- TYPING DOM ANIMATION ---
async function typeDOM(sourceNode, targetNode, speed = 15) {
    for (let child of Array.from(sourceNode.childNodes)) {
        if (child.nodeType === Node.TEXT_NODE) {
            const text = child.nodeValue;
            if (text.trim() === '') { targetNode.appendChild(document.createTextNode(text)); continue; }
            for (let i = 0; i < text.length; i += 4) {
                const span = document.createElement('span');
                span.textContent = text.substring(i, i + 4);
                span.className = 'type-chunk';
                targetNode.appendChild(span);
                chatBox.scrollTop = chatBox.scrollHeight;
                await new Promise(r => setTimeout(r, speed));
            }
        } else if (child.nodeType === Node.ELEMENT_NODE) {
            if (child.classList && (child.classList.contains('table-outer-flex') || child.classList.contains('markdown-table-scroll'))) {
                targetNode.appendChild(child.cloneNode(true));
                chatBox.scrollTop = chatBox.scrollHeight;
                await new Promise(r => setTimeout(r, 100));
            } else {
                const newEl = document.createElement(child.tagName);
                Array.from(child.attributes).forEach(a => newEl.setAttribute(a.name, a.value));
                targetNode.appendChild(newEl);
                await typeDOM(child, newEl, speed);
            }
        }
    }
}


function wrapMarkdownTables(root) {
    root.querySelectorAll('table:not(.data-table):not(.numbers-table)').forEach(table => {
        if (table.closest('.markdown-table-scroll, .table-scroll-wrapper, .table-outer-flex')) return;
        const wrapper = document.createElement('div');
        wrapper.className = 'markdown-table-scroll';
        wrapper.tabIndex = 0;
        wrapper.setAttribute('role', 'region');
        wrapper.setAttribute('aria-label', 'Scrollable response table');
        table.parentNode.insertBefore(wrapper, table);
        wrapper.appendChild(table);
    });
}


// --- MESSAGES ---
let lastMessageDate = null;

function formatDateDivider(dateStr) {
    const d = new Date(dateStr);
    const now = new Date();
    const diffDays = Math.floor((now - d) / (1000 * 60 * 60 * 24));
    if (diffDays === 0 && d.getDate() === now.getDate()) return 'Today';
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) {
        const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
        return days[d.getDay()];
    }
    return String(d.getDate()).padStart(2, '0') + '/' + String(d.getMonth() + 1).padStart(2, '0') + '/' + d.getFullYear();
}

function formatTime(dateStr) {
    const d = new Date(dateStr);
    let h = d.getHours();
    let m = d.getMinutes();
    return h.toString().padStart(2, '0') + ':' + m.toString().padStart(2, '0');
}

async function appendMessage(sender, text, source = '', export_file = '', msgId = null, rawContent = '', createdAt = '', attachments = [], siblingNav = null) {
    if (!createdAt) createdAt = new Date().toISOString();
    const dStr = createdAt.split('T')[0];
    
    if (lastMessageDate !== dStr) {
        lastMessageDate = dStr;
        const dateDiv = document.createElement('div');
        dateDiv.style.textAlign = 'center';
        dateDiv.style.margin = '10px 0';
        dateDiv.style.fontSize = '0.75rem';
        dateDiv.style.color = 'var(--L50)';
        dateDiv.style.fontWeight = '500';
        dateDiv.textContent = formatDateDivider(createdAt);
        chatBox.appendChild(dateDiv);
    }

    const msgDiv = document.createElement('div');
    msgDiv.classList.add('message', sender === 'user' ? 'user-msg' : 'system-msg');
    if (msgId) msgDiv.dataset.id = msgId;


    if (sender === 'user' && attachments && attachments.length > 0) {
        const attContainer = document.createElement('div');
        attContainer.style.display = 'flex';
        attContainer.style.gap = '10px';
        attContainer.style.marginBottom = '6px';
        attContainer.style.overflowX = 'auto';
        attContainer.style.paddingBottom = '4px';
        attContainer.classList.add('attachment-preview-area-scroll');
        
        attachments.forEach(file => {
            const wrapper = document.createElement('div');
            wrapper.style.minWidth = '60px';
            wrapper.style.maxWidth = '120px';
            wrapper.style.height = '60px';
            wrapper.style.borderRadius = '8px';
            wrapper.style.overflow = 'hidden';
            wrapper.style.border = '1px solid var(--L20)';
            wrapper.style.backgroundColor = 'var(--L10)';
            wrapper.style.display = 'flex';
            wrapper.style.alignItems = 'center';
            wrapper.style.justifyContent = 'center';
            wrapper.title = file.name;
            
            if (file.mime_type && file.mime_type.startsWith('image/')) {
                const img = document.createElement('img');
                img.src = 'data:' + file.mime_type + ';base64,' + file.data;
                img.style.width = '100%';
                img.style.height = '100%';
                img.style.objectFit = 'cover';
                wrapper.appendChild(img);
            } else {
                const icon = document.createElement('div');
                icon.style.fontSize = '24px';
                icon.textContent = '📄';
                wrapper.appendChild(icon);
            }
            attContainer.appendChild(wrapper);
        });
        msgDiv.appendChild(attContainer);
    }
    const bubble = document.createElement('div');
    bubble.classList.add('bubble');
    if (text) msgDiv.appendChild(bubble);
    else bubble.style.display = 'none';
    chatBox.appendChild(msgDiv);

    if (siblingNav && siblingNav.total > 1) {
        const navDiv = document.createElement('div');
        navDiv.style.display = 'flex';
        navDiv.style.alignItems = 'center';
        navDiv.style.gap = '8px';
        navDiv.style.marginTop = '8px';
        navDiv.style.fontSize = '0.8rem';
        navDiv.style.color = 'var(--L50)';
        
        const prevBtn = document.createElement('button');
        prevBtn.innerHTML = '❮';
        prevBtn.style.background = 'none';
        prevBtn.style.border = 'none';
        prevBtn.style.color = siblingNav.current > 1 ? 'var(--foreground)' : 'var(--L20)';
        prevBtn.style.cursor = siblingNav.current > 1 ? 'pointer' : 'default';
        if (siblingNav.current > 1) {
            prevBtn.onclick = () => switchSibling(siblingNav.siblings[siblingNav.current - 2].id);
        }
        
        const span = document.createElement('span');
        span.textContent = `${siblingNav.current}/${siblingNav.total}`;
        span.style.color = 'var(--foreground)';
        
        const nextBtn = document.createElement('button');
        nextBtn.innerHTML = '❯';
        nextBtn.style.background = 'none';
        nextBtn.style.border = 'none';
        nextBtn.style.color = siblingNav.current < siblingNav.total ? 'var(--foreground)' : 'var(--L20)';
        nextBtn.style.cursor = siblingNav.current < siblingNav.total ? 'pointer' : 'default';
        if (siblingNav.current < siblingNav.total) {
            nextBtn.onclick = () => switchSibling(siblingNav.siblings[siblingNav.current].id);
        }
        
        navDiv.appendChild(prevBtn);
        navDiv.appendChild(span);
        navDiv.appendChild(nextBtn);
        msgDiv.appendChild(navDiv);
    }


    if (sender === 'system') {
        const temp = document.createElement('div');
        temp.innerHTML = text;
        wrapMarkdownTables(temp);
        
        const tables = temp.querySelectorAll('table.data-table');
        tables.forEach(tbl => {
            if (tbl.classList.contains('numbers-table')) return;
            const outerFlex = document.createElement('div');
            outerFlex.className = 'table-outer-flex';
            outerFlex.style.display = 'flex';
            outerFlex.style.alignItems = 'flex-start';
            const wrapper = document.createElement('div');
            wrapper.className = 'table-scroll-wrapper';
            tbl.parentNode.insertBefore(outerFlex, tbl);
            const headers = tbl.querySelectorAll('thead th');
            const centerCols = [];
            headers.forEach((th, idx) => {
                const t = th.textContent.toLowerCase().trim();
                if (t === 'no.' || t === 'row' || t === 'id') { centerCols.push(idx); th.style.textAlign = 'center'; }
            });
            if (centerCols.length > 0) {
                tbl.querySelectorAll('tbody tr').forEach(tr => {
                    const tds = tr.querySelectorAll('td');
                    centerCols.forEach(idx => { if (tds[idx]) tds[idx].style.textAlign = 'center'; });
                });
            }
            outerFlex.appendChild(wrapper);
            wrapper.appendChild(tbl);
        });
        
        if (msgId) {
            bubble.innerHTML = temp.innerHTML;
        } else {
            await typeDOM(temp, bubble, 20);
        }
        
        if (source && Array.isArray(source) && source.length > 0) {
            const srcDiv = document.createElement('div');
            srcDiv.style.marginTop = '10px';
            srcDiv.style.display = 'flex';
            srcDiv.style.gap = '8px';
            srcDiv.style.flexWrap = 'wrap';
            source.forEach(s => {
                const a = document.createElement('a');
                a.href = s.uri;
                a.target = '_blank';
                a.textContent = s.title || new URL(s.uri).hostname;
                a.style.fontSize = '0.75rem';
                a.style.padding = '4px 8px';
                a.style.background = 'var(--L90)';
                a.style.border = '1px solid var(--L80)';
                a.style.borderRadius = '12px';
                a.style.textDecoration = 'none';
                a.style.color = 'var(--L30)';
                a.style.display = 'inline-flex';
                a.style.alignItems = 'center';
                srcDiv.appendChild(a);
            });
            bubble.appendChild(srcDiv);
        }

        const actionsDiv = document.createElement('div');
        actionsDiv.style.display = 'flex';
        actionsDiv.style.gap = '10px';
        actionsDiv.style.marginTop = '8px';
        
        const copyBtn = document.createElement('button');
        copyBtn.innerHTML = '<svg width=\"14\" height=\"14\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\"><rect x=\"9\" y=\"9\" width=\"13\" height=\"13\" rx=\"2\" ry=\"2\"></rect><path d=\"M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1\"></path></svg>';
        copyBtn.style.background = 'none'; copyBtn.style.border = 'none'; copyBtn.style.color = 'var(--L50)'; copyBtn.style.cursor = 'pointer';
        copyBtn.onclick = () => { navigator.clipboard.writeText(bubble.innerText); copyBtn.style.color = 'var(--accent)'; setTimeout(()=>copyBtn.style.color='var(--L50)', 1000); };
        actionsDiv.appendChild(copyBtn);
        
        msgDiv.appendChild(actionsDiv);
    } else {
        bubble.textContent = text;
        const timeSpan = document.createElement('span');
        timeSpan.textContent = formatTime(createdAt);
        timeSpan.style.fontSize = '0.65rem';
        timeSpan.style.color = 'rgba(255,255,255,0.7)';
        timeSpan.style.marginLeft = '12px';
        timeSpan.style.float = 'right';
        timeSpan.style.marginTop = '6px';
        bubble.appendChild(timeSpan);
        
        const actionsDiv = document.createElement('div');
        actionsDiv.style.display = 'flex';
        actionsDiv.style.justifyContent = 'flex-end';
        actionsDiv.style.gap = '10px';
        actionsDiv.style.marginTop = '4px';
        
        const copyBtn = document.createElement('button');
        copyBtn.innerHTML = '<svg width=\"14\" height=\"14\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\"><rect x=\"9\" y=\"9\" width=\"13\" height=\"13\" rx=\"2\" ry=\"2\"></rect><path d=\"M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1\"></path></svg>';
        copyBtn.style.background = 'none'; copyBtn.style.border = 'none'; copyBtn.style.color = 'var(--L50)'; copyBtn.style.cursor = 'pointer';
        copyBtn.onclick = () => { navigator.clipboard.writeText(text); copyBtn.style.color = 'var(--accent)'; setTimeout(()=>copyBtn.style.color='var(--L50)', 1000); };
        
        const editBtn = document.createElement('button');
        editBtn.innerHTML = '<svg width=\"14\" height=\"14\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\"><path d=\"M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7\"></path><path d=\"M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z\"></path></svg>';
        editBtn.style.background = 'none'; editBtn.style.border = 'none'; editBtn.style.color = 'var(--L50)'; editBtn.style.cursor = 'pointer';
        editBtn.onclick = () => {
            const raw = rawContent || text;
            bubble.innerHTML = '';
            
            const editArea = document.createElement('textarea');
            editArea.style.width = '100%';
            editArea.style.minHeight = '60px';
            editArea.style.background = 'transparent';
            editArea.style.border = 'none';
            editArea.style.color = 'var(--foreground)';
            editArea.style.outline = 'none';
            editArea.style.resize = 'none';
            editArea.style.fontFamily = 'inherit';
            editArea.style.fontSize = 'inherit';
            editArea.value = raw;
            
            const btnGroup = document.createElement('div');
            btnGroup.style.display = 'flex';
            btnGroup.style.gap = '8px';
            btnGroup.style.marginTop = '8px';
            
            const cancelBtn = document.createElement('button');
            cancelBtn.textContent = 'Cancel';
            cancelBtn.style.padding = '4px 12px';
            cancelBtn.style.borderRadius = '16px';
            cancelBtn.style.border = '1px solid var(--L50)';
            cancelBtn.style.background = 'transparent';
            cancelBtn.style.color = 'var(--L50)';
            cancelBtn.style.cursor = 'pointer';
            cancelBtn.onclick = () => renderChatPath(activeLeafId);
            
            const saveBtn = document.createElement('button');
            saveBtn.textContent = 'Save & Submit';
            saveBtn.style.padding = '4px 12px';
            saveBtn.style.borderRadius = '16px';
            saveBtn.style.border = 'none';
            saveBtn.style.background = 'var(--primary)';
            saveBtn.style.color = 'var(--background)';
            saveBtn.style.cursor = 'pointer';
            saveBtn.onclick = () => {
                const newText = editArea.value.trim();
                if (newText && newText !== raw) {
                    userInput.dataset.editId = msgId;
                    userInput.value = newText;
                    sendMessage();
                } else {
                    renderChatPath(activeLeafId);
                }
            };
            
            editArea.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    saveBtn.click();
                }
            });
            
            btnGroup.appendChild(cancelBtn);
            btnGroup.appendChild(saveBtn);
            bubble.appendChild(editArea);
            bubble.appendChild(btnGroup);
            editArea.focus();
            
            actionsDiv.style.display = 'none';
        };
        
        const regenBtn = document.createElement('button');
        regenBtn.innerHTML = '<svg width=\"14\" height=\"14\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\"><path d=\"M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.92-10.26l5.58 5.69\"/></svg>';
        regenBtn.style.background = 'none'; regenBtn.style.border = 'none'; regenBtn.style.color = 'var(--L50)'; regenBtn.style.cursor = 'pointer';
        regenBtn.onclick = () => { userInput.value = text; userInput.dataset.editId = msgId; userInput.dataset.regen = '1'; sendBtn.click(); };
        
        actionsDiv.appendChild(editBtn);
        actionsDiv.appendChild(regenBtn);
        actionsDiv.appendChild(copyBtn);
        
        msgDiv.appendChild(actionsDiv);
    }
    chatBox.scrollTop = chatBox.scrollHeight;
}


function showTyping() {
    const msgDiv = document.createElement('div');
    msgDiv.id = 'typing'; msgDiv.classList.add('message', 'system-msg');
    const bubble = document.createElement('div');
    bubble.classList.add('bubble', 'typing-indicator');
    bubble.innerHTML = '<span></span><span></span><span></span>';
    msgDiv.appendChild(bubble); chatBox.appendChild(msgDiv);

    if (siblingNav && siblingNav.total > 1) {
        const navDiv = document.createElement('div');
        navDiv.style.display = 'flex';
        navDiv.style.alignItems = 'center';
        navDiv.style.gap = '8px';
        navDiv.style.marginTop = '8px';
        navDiv.style.fontSize = '0.8rem';
        navDiv.style.color = 'var(--L50)';
        
        const prevBtn = document.createElement('button');
        prevBtn.innerHTML = '❮';
        prevBtn.style.background = 'none';
        prevBtn.style.border = 'none';
        prevBtn.style.color = siblingNav.current > 1 ? 'var(--foreground)' : 'var(--L20)';
        prevBtn.style.cursor = siblingNav.current > 1 ? 'pointer' : 'default';
        if (siblingNav.current > 1) {
            prevBtn.onclick = () => switchSibling(siblingNav.siblings[siblingNav.current - 2].id);
        }
        
        const span = document.createElement('span');
        span.textContent = `${siblingNav.current}/${siblingNav.total}`;
        span.style.color = 'var(--foreground)';
        
        const nextBtn = document.createElement('button');
        nextBtn.innerHTML = '❯';
        nextBtn.style.background = 'none';
        nextBtn.style.border = 'none';
        nextBtn.style.color = siblingNav.current < siblingNav.total ? 'var(--foreground)' : 'var(--L20)';
        nextBtn.style.cursor = siblingNav.current < siblingNav.total ? 'pointer' : 'default';
        if (siblingNav.current < siblingNav.total) {
            nextBtn.onclick = () => switchSibling(siblingNav.siblings[siblingNav.current].id);
        }
        
        navDiv.appendChild(prevBtn);
        navDiv.appendChild(span);
        navDiv.appendChild(nextBtn);
        msgDiv.appendChild(navDiv);
    }

    chatBox.scrollTop = chatBox.scrollHeight;
}
function hideTyping() { const t = document.getElementById('typing'); if (t) t.remove(); }


// --- SEND MESSAGE ---
async function sendMessage() {
    const text = userInput.value.trim();
    if (!text && typeof selectedChatFiles !== 'undefined' && selectedChatFiles.length === 0) return;

    if (!authToken) {
        showForm(formLogin);
        return;
    }

    if (isFirstMessage) {
        const hero = document.getElementById('hero');
        const mainContainer = document.getElementById('main-container');
        if (hero) hero.classList.add('fade-out');
        mainContainer.classList.remove('initial-state');
        setTimeout(() => {
            if (hero) hero.classList.add('hidden');
        }, 500);
        userInput.placeholder = '';
        isFirstMessage = false;
    }

    const base64Files = typeof selectedChatFiles !== 'undefined' ? [...selectedChatFiles] : [];
    if (typeof selectedChatFiles !== 'undefined') {
        selectedChatFiles = [];
        updateAttachmentsUI();
    }
    
    userInput.value = '';
    userInput.style.height = 'auto';

    const editId = userInput.dataset.editId ? parseInt(userInput.dataset.editId) : null;
    delete userInput.dataset.editId;
    
    let currentParent = activeLeafId;
    if (editId && chatTree[editId]) {
        currentParent = chatTree[editId].parent_id;
    }
    
    const tempId = 'temp_' + Date.now();
    chatTree[tempId] = { id: tempId, role: 'user', content: text, raw_content: text, parent_id: currentParent, children: [], created_at: new Date().toISOString() };
    if (currentParent && chatTree[currentParent]) {
        chatTree[currentParent].children.push(tempId);
    }
    activeLeafId = tempId;
    renderChatPath(activeLeafId);
    showTyping();

    try {
        const reqBody = {
            message: text,
            role: "user",
            session_id: currentSessionId,
            parent_id: currentParent,
            edit_message_id: editId,
            files: base64Files
        };

        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + authToken
            },
            body: JSON.stringify(reqBody)
        });

        const data = await res.json();
        hideTyping();

        if (data.session_id) {
            currentSessionId = data.session_id;
            refreshSessionInSidebar(data.session_id, data.session_title || null);
        }

        if (data.user_msg_id) {
            chatTree[data.user_msg_id] = chatTree[tempId];
            chatTree[data.user_msg_id].id = data.user_msg_id;
            delete chatTree[tempId];
            if (currentParent && chatTree[currentParent]) {
                let pChildren = chatTree[currentParent].children;
                let idx = pChildren.indexOf(tempId);
                if (idx !== -1) pChildren[idx] = data.user_msg_id;
            }
            activeLeafId = data.user_msg_id;
        }

        if (data.ai_msg_id) {
            chatTree[data.ai_msg_id] = { 
                id: data.ai_msg_id, 
                role: 'system', 
                content: data.answer, 
                raw_content: data.raw_answer || data.answer, 
                parent_id: activeLeafId, 
                children: [],
                created_at: data.created_at || new Date().toISOString()
            };
            chatTree[activeLeafId].children.push(data.ai_msg_id);
            activeLeafId = data.ai_msg_id;
        } else if (data.answer) {
             // Fallback for errors
             const errId = 'err_' + Date.now();
             chatTree[errId] = { id: errId, role: 'system', content: data.answer, parent_id: activeLeafId, children: [], created_at: new Date().toISOString() };
             chatTree[activeLeafId].children.push(errId);
             activeLeafId = errId;
        }
        
        renderChatPath(activeLeafId);
        
        if (!currentSessionId && !editId) {
if (!currentSessionId && !editId) {
        try {
            const initRes = await fetch('/api/chat/init', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + authToken },
                body: JSON.stringify({ message: text })
            });
            if (initRes.ok) {
                const initData = await initRes.json();
                currentSessionId = initData.session_id;
                reqBody.session_id = currentSessionId;
                if (typeof loadHistory === 'function') loadHistory();
            }
        } catch (e) { console.error(e); }
    }

    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + authToken
            },
            body: JSON.stringify(reqBody)
        });

        if (res.status === 401) {
            hideTyping();
            authToken = null; authUser = null;
            sessionStorage.removeItem('ramiel_token');
            sessionStorage.removeItem('ramiel_user');
            appendMessage('system', 'Session expired, please log in again.');
            showForm(formLogin);
            return;
        }

        const data = await res.json();
        hideTyping();

        if (data.session_id) {
            currentSessionId = data.session_id;
            refreshSessionInSidebar(data.session_id, data.session_title || null);
        }

        if (data.user_msg_id) {
            const userMsgs = chatBox.querySelectorAll('.user-msg');
            if (userMsgs.length > 0) {
                userMsgs[userMsgs.length - 1].dataset.id = data.user_msg_id;
            }
        }

        if (editId) {
            window.activeAlternative = {
                lockEditId: editId,
                stagedUser: text,
                stagedAi: data.answer
            };
        }

        appendMessage('system', data.answer, data.source, data.export_file, data.ai_msg_id, data.raw_answer, data.created_at);
    } catch {
        hideTyping();
        appendMessage('system', 'Error: Cannot connect to server.');
    }
}

sendBtn.addEventListener('click', sendMessage);


// --- SLASH COMMANDS ---
const availableCommands = ['/exit'];
const slashContainer = document.getElementById('slash-commands');
let slashIndex = -1;

function updateSlashSelection(items) {
    items.forEach(item => item.classList.remove('active'));
    if (slashIndex >= 0 && slashIndex < items.length) {
        items[slashIndex].classList.add('active');
        items[slashIndex].scrollIntoView({ block: 'nearest' });
    }
}

userInput.addEventListener('input', () => {
    const text = userInput.value;
    if (text.startsWith('/')) {
        const matches = availableCommands.filter(cmd => cmd.startsWith(text.toLowerCase()));
        if (matches.length > 0) {
            slashContainer.classList.remove('hidden');
            slashContainer.innerHTML = '';
            matches.slice(0, 4).forEach(cmd => {
                const item = document.createElement('div');
                item.className = 'slash-item';
                item.textContent = cmd.substring(1);
                item.dataset.cmd = cmd;
                item.onclick = () => { userInput.value = cmd; slashContainer.classList.add('hidden'); userInput.focus(); };
                slashContainer.appendChild(item);
            });
            slashIndex = -1;
        } else { slashContainer.classList.add('hidden'); }
    } else { slashContainer.classList.add('hidden'); }
});

userInput.addEventListener('keydown', (e) => {
    if (!slashContainer.classList.contains('hidden')) {
        const items = slashContainer.querySelectorAll('.slash-item');
        if (e.key === 'ArrowDown') { e.preventDefault(); slashIndex = (slashIndex + 1) % items.length; updateSlashSelection(items); }
        else if (e.key === 'ArrowUp') { e.preventDefault(); slashIndex = (slashIndex - 1 + items.length) % items.length; updateSlashSelection(items); }
        else if (e.key === 'Enter' || e.key === 'Tab') {
            const target = slashIndex >= 0 ? items[slashIndex] : items[0];
            if (target) { e.preventDefault(); userInput.value = target.dataset.cmd; slashContainer.classList.add('hidden'); }
            else if (e.key === 'Enter') { e.preventDefault(); slashContainer.classList.add('hidden'); sendMessage(); }
        } else if (e.key === 'Escape') { slashContainer.classList.add('hidden'); }
    } else {
        if (e.key === 'Enter') { e.preventDefault(); sendMessage(); }
    }
});


// --- GRADIENT TITLE MOUSE TRACKING ---
document.addEventListener('mousemove', (e) => {
    const heroTitle = document.querySelector('.gradient-text');
    if (heroTitle) {
        const rect = heroTitle.getBoundingClientRect();
        heroTitle.style.setProperty('--x', `${e.clientX - rect.left}px`);
        heroTitle.style.setProperty('--y', `${e.clientY - rect.top}px`);
    }
});


// --- THEME SWITCHER ---
const themeBtns   = document.querySelectorAll('.theme-btn');
const themeSlider = document.getElementById('theme-slider');
let originalCSS = '';

async function initThemeSwitcher() {
    if (!themeBtns.length) return;
    try { const res = await fetch('styles.css?v=' + Date.now()); originalCSS = await res.text(); } catch {}
    const savedTheme = localStorage.getItem('ramiel_theme');
    if (['dark', 'ash', 'light'].includes(savedTheme)) {
        themeBtns.forEach(btn => btn.classList.toggle('active', btn.getAttribute('data-theme') === savedTheme));
        applyAlgorithmicTheme(savedTheme);
    }
    const activeBtn = document.querySelector('.theme-btn.active');
    if (activeBtn) { themeSlider.style.width = activeBtn.offsetWidth + 'px'; themeSlider.style.transform = `translateX(${activeBtn.offsetLeft}px)`; }
    themeBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            themeBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            themeSlider.style.width = btn.offsetWidth + 'px';
            themeSlider.style.transform = `translateX(${btn.offsetLeft - 4}px)`;
            applyAlgorithmicTheme(btn.getAttribute('data-theme'));
        });
    });
}

function applyAlgorithmicTheme(theme) {
    if (!['dark', 'ash', 'light'].includes(theme)) return;
    localStorage.setItem('ramiel_theme', theme);
    let dynamicStyle = document.getElementById('dynamic-theme');
    if (!dynamicStyle) { dynamicStyle = document.createElement('style'); dynamicStyle.id = 'dynamic-theme'; document.head.appendChild(dynamicStyle); }
    if (theme === 'dark') { dynamicStyle.textContent = ''; return; }
    const hslRegex = /--L[a-zA-Z0-9]+:\s*hsl\(\s*(\d+),\s*([\d.]+)%,\s*([\d.]+)%\)/g;
    dynamicStyle.textContent = originalCSS.replace(hslRegex, (match, h, s, l) => {
        l = parseFloat(l); const varName = match.split(':')[0];
        if (theme === 'light') return `${varName}: hsl(${h}, ${s}%, ${100 - l}%)`;
        if (theme === 'ash') { s = parseFloat(s); let newL = Math.min(100, l * 2); if (l === 0) newL = 30; return `${varName}: hsl(${h}, ${s}%, ${newL}%)`; }
        return match;
    });
}

window.addEventListener('load', initThemeSwitcher);


// --- QUOTES ---
const quotes = [
    '"I came. I saw. I forgot what I was doing."',
    '"I opened my phone to check the time and forgot why."',
    '"I\'m not always sarcastic. Sometimes I\'m sleeping."',
    '"Working hard or hardly working? Hard while working."',
    '"When nothing goes right, go left."',
    '"I May Not Have a Brain, Gentlemen, But I Have an Idea"',
    '"Every 60 Seconds in Africa a Minute Passes"',
    '"Why don\'t scientists trust atoms? Because they make up everything!"'
];

window.addEventListener('DOMContentLoaded', () => {
    const quoteEl = document.getElementById('random-quote');
    if (quoteEl) quoteEl.textContent = quotes[Math.floor(Math.random() * quotes.length)];
    updateAccountUI();
    if (authToken) {
        loadSessions();
    }
});
// ATTACHMENT UI LOGIC
const btnAttach = document.getElementById('btn-attach');
const fileUpload = document.getElementById('chat-file-upload');
const previewArea = document.getElementById('attachment-preview-area');
let selectedChatFiles = [];

if (btnAttach && fileUpload) {
    btnAttach.addEventListener('click', () => {
        fileUpload.click();
    });

    fileUpload.addEventListener('change', (e) => {
        if (e.target.files && e.target.files.length > 0) {
            Array.from(e.target.files).forEach(file => {
                selectedChatFiles.push(file);
            });
            renderPreviews();
        }
        fileUpload.value = '';
    });
}

// Global paste listener for images/files
document.addEventListener('paste', (e) => {
    const items = e.clipboardData?.items;
    if (items) {
        let hasFiles = false;
        Array.from(items).forEach(item => {
            if (item.kind === 'file') {
                const file = item.getAsFile();
                if (file) {
                    selectedChatFiles.push(file);
                    hasFiles = true;
                }
            }
        });
        if (hasFiles) {
            e.preventDefault();
            renderPreviews();
        }
    }
});

// Global drag and drop listeners
document.body.addEventListener('dragover', (e) => {
    e.preventDefault();
});

document.body.addEventListener('dragleave', (e) => {
    e.preventDefault();
});

document.body.addEventListener('drop', (e) => {
    e.preventDefault();
    if (e.dataTransfer?.files && e.dataTransfer.files.length > 0) {
        Array.from(e.dataTransfer.files).forEach(file => {
            selectedChatFiles.push(file);
        });
        renderPreviews();
    }
});

function renderPreviews() {
    if (!previewArea) return;
    if (selectedChatFiles.length === 0) {
        previewArea.classList.add('hidden');
        previewArea.innerHTML = '';
        return;
    }
    previewArea.classList.remove('hidden');
    previewArea.innerHTML = '';

    selectedChatFiles.forEach((file, index) => {
        const item = document.createElement('div');
        item.className = 'file-preview-item';

        const nameLabel = document.createElement('div');
        nameLabel.className = 'file-preview-name';
        nameLabel.textContent = file.name;
        
        const removeBtn = document.createElement('button');
        removeBtn.className = 'remove-file-btn';
        removeBtn.innerHTML = 'x';
        removeBtn.onclick = () => {
            selectedChatFiles.splice(index, 1);
            renderPreviews();
        };

        if (file.type.startsWith('image/')) {
            const img = document.createElement('img');
            img.className = 'file-preview-img';
            img.src = URL.createObjectURL(file);
            item.appendChild(img);
        } else {
            const svgIcon = document.createElement('div');
            svgIcon.innerHTML = `<svg class="file-preview-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>`;
            item.appendChild(svgIcon.firstChild);
        }
        
        item.appendChild(nameLabel);
        item.appendChild(removeBtn);
        previewArea.appendChild(item);
    });
}

// Duplicate dropZone events removed to avoid double attachments




import re

with open('d:/njovi/Documents/Workspace/Projects/Vistakom/RAMIEL_AI/frontend/script.js', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add globals
if 'let chatTree = {};' not in content:
    globals_injection = """
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
"""
    content = content.replace("let currentSessionId = null;", globals_injection)


# 2. Patch loadSessionMessages
def replace_block(text, start_str, end_str, new_block):
    start = text.find(start_str)
    if start == -1: return text
    end = text.find(end_str, start)
    if end == -1: return text
    return text[:start] + new_block + text[end:]

loadSession_new = """async function loadSessionMessages(sessionId, itemElement) {
    if (!authToken) return;
    currentSessionId = sessionId;
    document.querySelectorAll('.history-item').forEach(el => el.classList.remove('active'));
    if (itemElement) itemElement.classList.add('active');

    try {
        const res = await fetch(`/api/sessions/${sessionId}/messages`, {
            headers: { 'Authorization': 'Bearer ' + authToken }
        });
        const messages = await res.json();
        
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
        chatTree = {};
        messages.forEach(msg => {
            chatTree[msg.id] = { ...msg, children: [] };
        });
        
        let leaf = null;
        messages.forEach(msg => {
            if (msg.parent_id && chatTree[msg.parent_id]) {
                chatTree[msg.parent_id].children.push(msg.id);
            }
            leaf = msg.id; // defaults to the last inserted
        });
        
        activeLeafId = leaf;
        renderChatPath(activeLeafId);
        
        if (window.innerWidth <= 768) closeSidebar();

"""
content = replace_block(content, "async function loadSessionMessages(sessionId, itemElement) {", "    } catch (error) {", loadSession_new)

# 3. Patch appendMessage signature
content = content.replace(
    "async function appendMessage(sender, text, source = '', export_file = '', msgId = null, rawContent = '', createdAt = '', attachments = []) {",
    "async function appendMessage(sender, text, source = '', export_file = '', msgId = null, rawContent = '', createdAt = '', attachments = [], siblingNav = null) {"
)

# 4. Patch Edit Button in appendMessage
edit_btn_old = """        editBtn.onclick = () => { userInput.value = text; userInput.focus(); userInput.dataset.editId = msgId; };"""
edit_btn_new = """        editBtn.onclick = () => {
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
        };"""
content = content.replace(edit_btn_old, edit_btn_new)

# 5. Patch Sibling Nav Append
sibling_nav_injection = """
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
"""
content = content.replace("chatBox.appendChild(msgDiv);", "chatBox.appendChild(msgDiv);\n" + sibling_nav_injection)

# 6. Patch sendMessage
sendMessage_old_start = "async function sendMessage() {"
sendMessage_old_end = "if (!currentSessionId && !editId) {"
sendMessage_new = """async function sendMessage() {
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
"""
content = replace_block(content, sendMessage_old_start, "if (!currentSessionId && !editId) {", sendMessage_new)

with open('d:/njovi/Documents/Workspace/Projects/Vistakom/RAMIEL_AI/frontend/patch_frontend.py_out.js', 'w', encoding='utf-8') as f:
    f.write(content)


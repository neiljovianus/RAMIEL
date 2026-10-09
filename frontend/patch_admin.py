import re

with open('d:/njovi/Documents/Workspace/Projects/Vistakom/RAMIEL_AI/frontend/admin.html', 'r', encoding='utf-8') as f:
    c = f.read()

start_sig = "document.getElementById('btn-admin-send-reset-link').addEventListener('click', async () => {"
end_sig = "});"

start_idx = c.find(start_sig)
if start_idx != -1:
    end_idx = c.find(end_sig, start_idx) + len(end_sig)
    
    new_logic = """
        let currentResetUrl = "";
        
        document.getElementById('btn-admin-get-reset-link').addEventListener('click', async () => {
            const btn = document.getElementById('btn-admin-get-reset-link');
            btn.disabled = true;
            try {
                const res = await sendAdminRequest(`/api/dev/users/${managedUserId}/send-reset`, 'POST');
                if (res.url) {
                    currentResetUrl = new URL(res.url, location.origin).href;
                    document.getElementById('btn-admin-copy-reset-link').style.display = 'inline-block';
                    btn.textContent = 'Get Link (New)';
                } else {
                    alert(res.message || 'Password reset link generated.');
                }
            } catch (error) {
                alert(error.message);
            } finally {
                btn.disabled = false;
            }
        });

        document.getElementById('btn-admin-copy-reset-link').addEventListener('click', () => {
            if (currentResetUrl) {
                navigator.clipboard.writeText(currentResetUrl);
                const btn = document.getElementById('btn-admin-copy-reset-link');
                const oldText = btn.textContent;
                btn.textContent = 'Copied!';
                setTimeout(() => btn.textContent = 'Copy Link', 2000);
            }
        });
"""
    c = c[:start_idx] + new_logic.strip() + c[end_idx:]
    with open('d:/njovi/Documents/Workspace/Projects/Vistakom/RAMIEL_AI/frontend/admin.html', 'w', encoding='utf-8') as f:
        f.write(c)
    print("Patched admin.html logic successfully.")
else:
    print("Could not find start signature.")


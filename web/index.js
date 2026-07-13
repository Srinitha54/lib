// API Configuration
const API_URL = 'http://localhost:8000/api';

// Selectors
const chatMessages = document.getElementById('chat-messages');
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const btnSend = document.getElementById('btn-send');
const typingIndicator = document.getElementById('typing-indicator');
const btnResetSession = document.getElementById('btn-reset-session');
const btnSeedDb = document.getElementById('btn-seed-db');
const btnRefresh = document.getElementById('btn-refresh');
const activeModeBadge = document.getElementById('active-mode-badge');
const toast = document.getElementById('toast');

// Table Bodies
const booksTableBody = document.getElementById('books-table-body');
const membersTableBody = document.getElementById('members-table-body');
const reservationsTableBody = document.getElementById('reservations-table-body');

// State variables
let currentMode = 'sequential';
let isSending = false;

// Initialize Page
document.addEventListener('DOMContentLoaded', () => {
    setupTabListeners();
    setupModeSelector();
    setupSamplePromptChips();
    
    // Initial fetch of database tables
    refreshDatabaseViews();

    // Form submission listener
    chatForm.addEventListener('submit', handleChatSubmit);

    // Sidebar button listeners
    btnResetSession.addEventListener('click', handleSessionReset);
    btnSeedDb.addEventListener('click', handleDatabaseSeed);
    btnRefresh.addEventListener('click', () => {
        refreshDatabaseViews();
        showToast('Database views refreshed!');
    });
});

// Setup UI Tab Panel toggling
function setupTabListeners() {
    const tabButtons = document.querySelectorAll('.tab-btn');
    tabButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            // Remove active classes
            tabButtons.forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
            
            // Add active classes to current selection
            btn.classList.add('active');
            const targetId = btn.getAttribute('data-tab');
            document.getElementById(targetId).classList.add('active');
        });
    });
}

// Setup radio button workflow mode toggles
function setupModeSelector() {
    const radioButtons = document.querySelectorAll('input[name="agent-mode"]');
    radioButtons.forEach(radio => {
        radio.addEventListener('change', (e) => {
            currentMode = e.target.value;
            // Update UI badge
            activeModeBadge.textContent = `${currentMode.charAt(0).toUpperCase() + currentMode.slice(1)} Mode`;
            showToast(`Switched execution mode to ${currentMode.toUpperCase()}`);
        });
    });
}

// Setup clicking on pre-defined sample prompt chips
function setupSamplePromptChips() {
    // Event delegation for dynamically added chips or initial chips
    document.addEventListener('click', (e) => {
        if (e.target.classList.contains('prompt-chip')) {
            const promptText = e.target.getAttribute('data-prompt');
            chatInput.value = promptText;
            chatInput.focus();
            
            // Automatically submit
            handleChatSubmit(new Event('submit'));
        }
    });
}

// Fetch and reload all lists from the DynamoDB API
function refreshDatabaseViews() {
    fetchBooks();
    fetchMembers();
    fetchReservations();
}

// Toast Notifications
function showToast(message, isError = false) {
    toast.textContent = message;
    if (isError) {
        toast.style.borderLeftColor = '#ef4444';
    } else {
        toast.style.borderLeftColor = '#3b82f6';
    }
    toast.classList.add('show');
    
    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

// --- API FETCH FUNCTIONS ---

async function fetchBooks() {
    try {
        const res = await fetch(`${API_URL}/books`);
        if (!res.ok) throw new Error('Failed to fetch books');
        const books = await res.json();
        
        if (books.length === 0) {
            booksTableBody.innerHTML = `<tr><td colspan="5" class="loading-cell">No books found in DynamoDB. Try seeding.</td></tr>`;
            return;
        }

        booksTableBody.innerHTML = books.map(book => {
            const statusClass = book.status.toUpperCase() === 'AVAILABLE' ? 'pill-available' : 'pill-reserved';
            return `
                <tr>
                    <td><strong>${book.book_id}</strong></td>
                    <td>${book.title}</td>
                    <td>${book.author}</td>
                    <td>${book.genre || 'N/A'}</td>
                    <td><span class="pill ${statusClass}">${book.status}</span></td>
                </tr>
            `;
        }).join('');
    } catch (err) {
        booksTableBody.innerHTML = `<tr><td colspan="5" class="loading-cell" style="color:#ef4444;">Error: ${err.message}</td></tr>`;
    }
}

async function fetchMembers() {
    try {
        const res = await fetch(`${API_URL}/members`);
        if (!res.ok) throw new Error('Failed to fetch members');
        const members = await res.json();
        
        if (members.length === 0) {
            membersTableBody.innerHTML = `<tr><td colspan="5" class="loading-cell">No members found in DynamoDB. Try seeding.</td></tr>`;
            return;
        }

        membersTableBody.innerHTML = members.map(member => {
            const tierClass = member.tier.toLowerCase() === 'premium' ? 'pill-premium' : 'pill-standard';
            return `
                <tr>
                    <td><strong>${member.member_id}</strong></td>
                    <td>${member.name}</td>
                    <td><span class="pill ${tierClass}">${member.tier.toUpperCase()}</span></td>
                    <td>${member.expiry_date}</td>
                    <td>${member.active_reservations}</td>
                </tr>
            `;
        }).join('');
    } catch (err) {
        membersTableBody.innerHTML = `<tr><td colspan="5" class="loading-cell" style="color:#ef4444;">Error: ${err.message}</td></tr>`;
    }
}

async function fetchReservations() {
    try {
        const res = await fetch(`${API_URL}/reservations`);
        if (!res.ok) throw new Error('Failed to fetch reservations');
        const reservations = await res.json();
        
        if (reservations.length === 0) {
            reservationsTableBody.innerHTML = `<tr><td colspan="6" class="loading-cell">No active reservations recorded.</td></tr>`;
            return;
        }

        reservationsTableBody.innerHTML = reservations.map(resv => {
            return `
                <tr>
                    <td><strong>${resv.reservation_id}</strong></td>
                    <td>${resv.member_id}</td>
                    <td>${resv.book_id}</td>
                    <td>${resv.reservation_date}</td>
                    <td>${resv.due_date}</td>
                    <td><span class="pill pill-reserved">${resv.status}</span></td>
                </tr>
            `;
        }).join('');
    } catch (err) {
        reservationsTableBody.innerHTML = `<tr><td colspan="6" class="loading-cell" style="color:#ef4444;">Error: ${err.message}</td></tr>`;
    }
}

// --- ACTION HANDLERS ---

async function handleChatSubmit(e) {
    e.preventDefault();
    const prompt = chatInput.value.trim();
    if (!prompt || isSending) return;

    // Append user message bubble to chat window
    appendMessage(prompt, 'user-message');
    chatInput.value = '';
    
    // Lock inputs
    isSending = true;
    chatInput.disabled = true;
    btnSend.disabled = true;
    typingIndicator.style.display = 'flex';
    chatMessages.scrollTop = chatMessages.scrollHeight;

    try {
        const res = await fetch(`${API_URL}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt, mode: currentMode })
        });
        
        const data = await res.json();
        
        if (!res.ok) {
            throw new Error(data.error || 'Server error occurred');
        }

        // Append agent response bubble to chat
        appendMessage(data.response, 'agent-message');
        
        // Auto-refresh the DynamoDB views to update catalog changes immediately
        refreshDatabaseViews();
    } catch (err) {
        appendMessage(`[System Error] ${err.message}. Please verify the backend server is running and AWS model access is configured correctly.`, 'agent-message');
        showToast('Agent invocation failed', true);
    } finally {
        // Unlock inputs
        isSending = false;
        chatInput.disabled = false;
        btnSend.disabled = false;
        typingIndicator.style.display = 'none';
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
}

async function handleSessionReset() {
    if (isSending) return;
    try {
        const res = await fetch(`${API_URL}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reset: true })
        });
        
        if (res.ok) {
            // Clear message list except system welcome
            chatMessages.innerHTML = `
                <div class="message system-message">
                    <div class="message-content">
                        Chat session was successfully reset. Specialist agents have been re-instantiated.
                        <div class="sample-prompts">
                            <span class="prompt-chip" data-prompt="I want to reserve book BOOK-2001. My member ID is MEM-1001.">Reserve BOOK-2001 for MEM-1001</span>
                            <span class="prompt-chip" data-prompt="Check available books.">List Available Books</span>
                            <span class="prompt-chip" data-prompt="I want to cancel my reservation for book BOOK-2006. Member is MEM-1001.">Cancel BOOK-2006 for MEM-1001</span>
                        </div>
                    </div>
                </div>
            `;
            showToast('Chat history and agent sessions reset!');
        } else {
            showToast('Failed to reset session', true);
        }
    } catch (err) {
        showToast('Error resetting session', true);
    }
}

async function handleDatabaseSeed() {
    if (isSending) return;
    if (!confirm('Are you sure you want to delete current reservation changes and re-seed all DynamoDB tables to default sample data?')) {
        return;
    }

    btnSeedDb.disabled = true;
    const oldText = btnSeedDb.innerHTML;
    btnSeedDb.innerHTML = `<span class="icon">⏳</span> Seeding...`;
    showToast('Deleting and recreating DynamoDB tables...');

    try {
        const res = await fetch(`${API_URL}/seed`, { method: 'POST' });
        const data = await res.json();
        
        if (res.ok && data.success) {
            showToast('DynamoDB Tables seeded successfully!');
            refreshDatabaseViews();
            
            // Clear chat since database state changed
            handleSessionReset();
        } else {
            throw new Error(data.error || 'Failed to seed tables');
        }
    } catch (err) {
        alert(`Error seeding database:\n${err.message}`);
        showToast('Database seeding failed', true);
    } finally {
        btnSeedDb.disabled = false;
        btnSeedDb.innerHTML = oldText;
    }
}

// Append a message bubble to the chat logs
function appendMessage(text, className) {
    const msgDiv = document.createElement('div');
    msgDiv.classList.add('message', className);
    
    // Format text: convert newlines to line breaks and format Markdown-style summaries
    let formattedText = escapeHTML(text)
        .replace(/\n/g, '<br>')
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
        .replace(/`([^`]+)`/g, '<code>$1</code>');

    msgDiv.innerHTML = `<div class="message-content">${formattedText}</div>`;
    chatMessages.appendChild(msgDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Simple HTML escaping to prevent XSS
function escapeHTML(str) {
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

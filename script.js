const API_BASE = "http://localhost:5000";
let sessionId = "session_" + Date.now();

const homeView    = document.getElementById("home-view");
const chatView    = document.getElementById("chat-view");
const mainInput   = document.getElementById("main-input");
const chatInput   = document.getElementById("chat-input");
const chatMessages= document.getElementById("chat-messages");
const homeSubmit  = document.getElementById("home-submit");
const chatSubmit  = document.getElementById("chat-submit");
const backBtn     = document.getElementById("back-btn");
const clearBtn    = document.getElementById("clear-btn");

// ── Suggestion category data ──────────────────────────────
const categories = {
  recruiting: [
    "Monitor job postings at target companies",
    "Build interactive talent market map",
    "Benchmark salary for a role"
  ],
  organise: [
    "Create a weekly schedule for me",
    "Help me prioritise my tasks today",
    "Draft a morning routine plan"
  ],
  monitor: [
    "Summarise the latest AI news",
    "Track competitor product updates",
    "Alert me to market changes"
  ],
  prototype: [
    "Design a REST API for a todo app",
    "Create a landing page wireframe",
    "Build a simple Python script template"
  ]
};

// ── Switch Views ──────────────────────────────────────────
function showChat() {
  homeView.classList.add("hidden");
  chatView.classList.remove("hidden");
  chatInput.focus();
}

function showHome() {
  chatView.classList.add("hidden");
  homeView.classList.remove("hidden");
  mainInput.focus();
}

// ── Render message bubbles ────────────────────────────────
function appendMessage(role, text, sources = []) {
  const wrapper = document.createElement("div");
  wrapper.className = `message ${role}`;

  const label = document.createElement("div");
  label.className = "message-label";
  label.textContent = role === "user" ? "You" : "trendDesk AI";

  const bubble = document.createElement("div");
  bubble.className = "message-bubble";

  if (sources && sources.length > 0 && role === "assistant") {
    const sourcesDiv = document.createElement("div");
    sourcesDiv.className = "sources-container";
    sourcesDiv.style.marginBottom = "12px";
    sourcesDiv.innerHTML = `<strong>🔍 Sources Searched:</strong>`;
    
    const ul = document.createElement("ul");
    ul.style.listStyleType = "none";
    ul.style.paddingLeft = "0";
    ul.style.marginTop = "6px";
    
    sources.forEach(url => {
      const li = document.createElement("li");
      li.style.marginBottom = "4px";
      try {
        const urlObj = new URL(url);
        let siteName = urlObj.hostname.replace("www.", "");
        // Capitalize for display, e.g., vogue.in -> Vogue.in (or we could just uppercase first letter)
        siteName = siteName.split('.').map(part => part.charAt(0).toUpperCase() + part.slice(1)).join(' ');
        if (siteName.endsWith(" Com") || siteName.endsWith(" In") || siteName.endsWith(" Org")) {
            siteName = siteName.substring(0, siteName.lastIndexOf(" "));
        }
        
        let displayUrl = urlObj.hostname + urlObj.pathname;
        if (displayUrl.length > 35) {
            displayUrl = displayUrl.substring(0, 35) + "...";
        }
        
        li.innerHTML = `• ${siteName} &mdash; <a href="${url}" target="_blank" style="color: #1a73e8; text-decoration: none;">${displayUrl}</a>`;
      } catch (e) {
        li.innerHTML = `• <a href="${url}" target="_blank" style="color: #1a73e8; text-decoration: none;">${url}</a>`;
      }
      ul.appendChild(li);
    });
    
    sourcesDiv.appendChild(ul);
    bubble.appendChild(sourcesDiv);
    
    const ansLabel = document.createElement("div");
    ansLabel.innerHTML = `<strong>💡 Answer:</strong>`;
    ansLabel.style.marginBottom = "6px";
    bubble.appendChild(ansLabel);
    
    const textDiv = document.createElement("div");
    textDiv.textContent = text;
    bubble.appendChild(textDiv);
  } else {
    bubble.textContent = text;
  }

  wrapper.appendChild(label);
  wrapper.appendChild(bubble);
  chatMessages.appendChild(wrapper);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return bubble;
}

function showTyping() {
  const wrapper = document.createElement("div");
  wrapper.className = "message assistant";
  wrapper.id = "typing-wrapper";

  const label = document.createElement("div");
  label.className = "message-label";
  label.textContent = "trendDesk AI";

  const indicator = document.createElement("div");
  indicator.className = "typing-indicator";
  indicator.innerHTML = `<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>`;

  wrapper.appendChild(label);
  wrapper.appendChild(indicator);
  chatMessages.appendChild(wrapper);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function removeTyping() {
  const el = document.getElementById("typing-wrapper");
  if (el) el.remove();
}

// ── Send message to Flask backend ────────────────────────
async function sendMessage(text) {
  if (!text.trim()) return;

  showChat();
  appendMessage("user", text);
  showTyping();

  try {
    const homePersona = document.getElementById("home-persona");
    const homeLang = document.getElementById("home-lang");

    const res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ 
          message: text, 
          session_id: sessionId,
          persona: homePersona ? homePersona.value : "Assistant",
          language: homeLang ? homeLang.value : "English"
      })
    });

    const data = await res.json();
    removeTyping();

    if (data.error) {
      appendMessage("assistant", `⚠️ Error: ${data.error}`);
    } else {
      appendMessage("assistant", data.reply, data.sources);
    }
  } catch (err) {
    removeTyping();
    appendMessage("assistant", "⚠️ Could not reach the server. Make sure the Flask backend is running on port 5000.");
  }
}

// ── Event Listeners ───────────────────────────────────────

// Home submit button
homeSubmit.addEventListener("click", () => {
  const text = mainInput.value.trim();
  mainInput.value = "";
  sendMessage(text);
});

// Home enter key
mainInput.addEventListener("keypress", (e) => {
  if (e.key === "Enter") {
    const text = mainInput.value.trim();
    mainInput.value = "";
    sendMessage(text);
  }
});

// Chat submit button
chatSubmit.addEventListener("click", () => {
  const text = chatInput.value.trim();
  chatInput.value = "";
  sendMessage(text);
});

// Chat enter key
chatInput.addEventListener("keypress", (e) => {
  if (e.key === "Enter") {
    const text = chatInput.value.trim();
    chatInput.value = "";
    sendMessage(text);
  }
});

// Back to home
backBtn.addEventListener("click", showHome);

// Clear chat
clearBtn.addEventListener("click", async () => {
  chatMessages.innerHTML = "";
  await fetch(`${API_BASE}/api/clear`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId })
  });
  sessionId = "session_" + Date.now(); // fresh session
});

// Tag selection
document.querySelectorAll(".tag").forEach(tag => {
  tag.addEventListener("click", () => {
    document.querySelectorAll(".tag").forEach(t => t.classList.remove("active"));
    tag.classList.add("active");

    const cat = tag.dataset.category;
    const items = categories[cat] || [];
    const list = document.getElementById("suggestion-list");
    list.innerHTML = items.map(i =>
      `<div class="suggestion-item" data-prompt="${i}">${i}</div>`
    ).join("");

    // Re-attach click listeners
    list.querySelectorAll(".suggestion-item").forEach(item => {
      item.addEventListener("click", () => sendMessage(item.dataset.prompt));
    });
  });
});

// Suggestion item clicks (initial render)
document.querySelectorAll(".suggestion-item").forEach(item => {
  item.addEventListener("click", () => sendMessage(item.dataset.prompt));
});

// ── PDF Upload Logic ──────────────────────────────────────
const pdfUpload = document.getElementById("pdf-upload");
const homeAttachBtn = document.getElementById("home-attach-btn");
const chatAttachBtn = document.getElementById("chat-attach-btn");
const homeUploadStatus = document.getElementById("home-upload-status");
const chatUploadStatus = document.getElementById("chat-upload-status");

if (homeAttachBtn) homeAttachBtn.addEventListener("click", (e) => { e.preventDefault(); pdfUpload.click(); });
if (chatAttachBtn) chatAttachBtn.addEventListener("click", (e) => { e.preventDefault(); pdfUpload.click(); });

if (pdfUpload) {
  pdfUpload.addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    if (homeUploadStatus) {
      homeUploadStatus.textContent = "Uploading...";
      homeUploadStatus.classList.remove("hidden");
    }
    if (chatUploadStatus) {
      chatUploadStatus.textContent = "Uploading...";
      chatUploadStatus.classList.remove("hidden");
    }

    const formData = new FormData();
    formData.append("file", file);
    formData.append("session_id", sessionId);

    try {
      const res = await fetch(`${API_BASE}/api/upload`, {
        method: "POST",
        body: formData
      });
      
      const data = await res.json();
      if (data.error) {
        alert("Upload failed: " + data.error);
        if (homeUploadStatus) homeUploadStatus.classList.add("hidden");
        if (chatUploadStatus) chatUploadStatus.classList.add("hidden");
      } else {
        if (homeUploadStatus) homeUploadStatus.textContent = file.name;
        if (chatUploadStatus) chatUploadStatus.textContent = file.name;
      }
    } catch (err) {
      alert("Upload failed: Server error");
      if (homeUploadStatus) homeUploadStatus.classList.add("hidden");
      if (chatUploadStatus) chatUploadStatus.classList.add("hidden");
    }
    
    pdfUpload.value = '';
  });
}

// Clear UI status on clear button
if (clearBtn) {
  clearBtn.addEventListener("click", () => {
      if (homeUploadStatus) {
        homeUploadStatus.classList.add("hidden");
        homeUploadStatus.textContent = "";
      }
      if (chatUploadStatus) {
        chatUploadStatus.classList.add("hidden");
        chatUploadStatus.textContent = "";
      }
  });
}

// ── Dropdown Sync Logic ──────────────────────────────────
const homePersona = document.getElementById("home-persona");
const chatPersona = document.getElementById("chat-persona");
const homeLang = document.getElementById("home-lang");
const chatLang = document.getElementById("chat-lang");

if (homePersona && chatPersona) {
    homePersona.addEventListener("change", () => chatPersona.value = homePersona.value);
    chatPersona.addEventListener("change", () => homePersona.value = chatPersona.value);
}
if (homeLang && chatLang) {
    homeLang.addEventListener("change", () => chatLang.value = homeLang.value);
    chatLang.addEventListener("change", () => homeLang.value = chatLang.value);
}

// ── Mic logic ─────────────────────────────────────────────
const homeMic = document.getElementById("home-mic");
const chatMic = document.getElementById("chat-mic");
let recognition;
if ('webkitSpeechRecognition' in window) {
    recognition = new webkitSpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'en-US'; // Default, could be linked to lang selector
    
    recognition.onresult = function(event) {
        const transcript = event.results[0][0].transcript;
        if (homeView.classList.contains("hidden")) {
            chatInput.value = transcript;
            chatSubmit.click();
        } else {
            mainInput.value = transcript;
            homeSubmit.click();
        }
    };
    recognition.onerror = function(event) {
        console.error("Speech error", event);
        alert("Speech recognition error: " + event.error);
    };
    
    if (homeMic) homeMic.addEventListener("click", () => {
        recognition.lang = homeLang.value === "Spanish" ? "es-ES" : (homeLang.value === "French" ? "fr-FR" : "en-US");
        recognition.start()
    });
    if (chatMic) chatMic.addEventListener("click", () => {
        recognition.lang = chatLang.value === "Spanish" ? "es-ES" : (chatLang.value === "French" ? "fr-FR" : "en-US");
        recognition.start()
    });
} else {
    const noMic = () => alert("Microphone API not supported in this browser.");
    if (homeMic) homeMic.addEventListener("click", noMic);
    if (chatMic) chatMic.addEventListener("click", noMic);
}

// ── Export PDF logic ──────────────────────────────────────
const exportBtn = document.getElementById("export-btn");
if (exportBtn) {
    exportBtn.addEventListener("click", () => {
        const { jsPDF } = window.jspdf;
        const doc = new jsPDF();
        let yPos = 10;
        const msgs = document.querySelectorAll('.message');
        
        doc.setFontSize(16);
        doc.text("Chat Export", 10, yPos);
        yPos += 10;
        doc.setFontSize(12);

        msgs.forEach(msg => {
            const role = msg.classList.contains("user") ? "You:" : "trendDesk AI:";
            // Strip the hardcoded role label from text
            const textContent = msg.textContent.substring(role.length).trim();
            const lines = doc.splitTextToSize(textContent, 180);
            
            doc.setFont(undefined, 'bold');
            doc.text(role, 10, yPos);
            yPos += 7;
            
            doc.setFont(undefined, 'normal');
            doc.text(lines, 10, yPos);
            yPos += (lines.length * 7) + 5;
            
            if (yPos > 280) {
                doc.addPage();
                yPos = 10;
            }
        });
        
        doc.save("chat-export.pdf");
    });
}

// ── Share button logic ────────────────────────────────────
const shareBtn = document.getElementById("share-btn");
if (shareBtn) {
    shareBtn.addEventListener("click", () => {
        const shareUrl = window.location.origin + window.location.pathname + "?session=" + sessionId;
        navigator.clipboard.writeText(shareUrl).then(() => {
            alert("Share link copied to clipboard!");
        });
    });
}

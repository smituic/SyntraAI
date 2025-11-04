// chat.js

// 1. Generate or load a session_id for this user
let session_id = localStorage.getItem("chat_session_id");
if (!session_id) {
    session_id = "sess_" + Date.now() + "_" + Math.floor(Math.random() * 1000);
    localStorage.setItem("chat_session_id", session_id);
}

// 2. Hardcode restaurant_key for this page
const restaurant_key = "dominos_pizza"; // replace per restaurant page

const chatMessages = document.getElementById("chat-messages");
const inputBox = document.getElementById("user-message");
const sendBtn = document.getElementById("send-btn");

const chatBubble = document.getElementById("chat-bubble");
const chatOverlay = document.getElementById("chat-overlay");
const closeChat = document.getElementById("close-chat");

// Show chat window
chatBubble.addEventListener("click", () => {
  chatOverlay.classList.remove("hidden");
});

// Close chat window
closeChat.addEventListener("click", () => {
  chatOverlay.classList.add("hidden");
});


// 3. Handle sending a message
async function sendMessage() {
    const msg = inputBox.value.trim();
    if (!msg) return;

    // display user message
    appendMessage(msg, "user");
    inputBox.value = "";

    // get geolocation (optional)
    let lat = null, lon = null;
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(pos => {
            lat = pos.coords.latitude;
            lon = pos.coords.longitude;
            sendToServer(msg, lat, lon);
        }, err => {
            sendToServer(msg, null, null);
        });
    } else {
        sendToServer(msg, null, null);
    }
}

// 4. Send message to FastAPI /ask
async function sendToServer(msg, lat, lon) {
    try {
        const response = await fetch("/ask", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                message: msg,
                restaurant: restaurant_key,
                mode: "order",
                session_id: session_id,
                latitude: lat,
                longitude: lon
            })
        });
        const data = await response.json();
        appendMessage(data.response, "bot");
    } catch (e) {
        appendMessage("Error: Could not reach server", "bot");
    }
}

// 5. Helper to append messages
function appendMessage(msg, role) {
    const div = document.createElement("div");
    div.className = "message " + role;
    div.textContent = msg;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// 6. Event listeners
sendBtn.addEventListener("click", sendMessage);
inputBox.addEventListener("keydown", e => { if(e.key === "Enter") sendMessage(); });


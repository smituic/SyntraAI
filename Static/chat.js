// chat.js

// 1. Generate or load a session_id for this user
let session_id = localStorage.getItem("chat_session_id");
if (!session_id) {
    session_id = "sess_" + Date.now() + "_" + Math.floor(Math.random() * 1000);
    localStorage.setItem("chat_session_id", session_id);
}

// 2. Hardcode restaurant_key for this page
// const scriptTag = document.currentScript;
// const restaurant_key = scriptTag.getAttribute("data-restaurant");
const restaurant_key = "dominos_pizza";


const chatMessages = document.getElementById("chat-messages");
const inputBox = document.getElementById("user-message");
const sendBtn = document.getElementById("send-btn");



const chatBubble = document.getElementById("chat-bubble");
const chatOverlay = document.getElementById("chat-overlay");
const chatBox = document.getElementById("chat-box");
const closeChat = document.getElementById("close-chat");

// ✅ At start — only bubble visible
window.addEventListener("DOMContentLoaded", () => {
  chatOverlay.classList.remove("active");
  chatOverlay.style.display = "none";
  chatBubble.style.display = "flex";
});

// 🗨️ When user clicks bubble → show chat, hide bubble
chatBubble.addEventListener("click", (e) => {
  e.stopPropagation();
  chatBubble.style.display = "none";
  chatOverlay.style.display = "flex";
  setTimeout(() => chatOverlay.classList.add("active"), 10);
});

// ❌ Close button → hide chat, show bubble
closeChat.addEventListener("click", (e) => {
  e.stopPropagation();
  chatOverlay.classList.remove("active");
  setTimeout(() => {
    chatOverlay.style.display = "none";
    chatBubble.style.display = "flex";
  }, 300);
});

// 🖱 Click anywhere outside chat → hide chat, show bubble
document.addEventListener("click", (e) => {
  if (!chatBox.contains(e.target) && !chatBubble.contains(e.target)) {
    chatOverlay.classList.remove("active");
    setTimeout(() => {
      chatOverlay.style.display = "none";
      chatBubble.style.display = "flex";
    }, 300);
  }
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
      let botReply = data.response;

      // ---------------- JSON Extraction -----------------
      const start = botReply.indexOf("---ORDER_JSON_START---");
      const end = botReply.indexOf("---ORDER_JSON_END---");

      let cleanText = botReply;
      let orderJson = null;

      if (start !== -1 && end !== -1) {
          const jsonString = botReply.substring(
              start + "---ORDER_JSON_START---".length,
              end
          ).trim();

          try {
              orderJson = JSON.parse(jsonString);
          } catch (err) {
              console.error("JSON parse error:", err);
          }

          cleanText = botReply.replace(
              botReply.substring(start, end + "---ORDER_JSON_END---".length),
              ""
          ).trim();
      }

      // ---- Show only clean text ----
      appendMessage(cleanText, "bot");

      // ---- If JSON exists ----
      if (orderJson) {
          renderOrderSummary(orderJson.order);
      }

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

function renderOrderSummary(order) {
  const div = document.createElement("div");
  div.className = "order-summary-card";

  div.innerHTML = `
      <h3>Order Confirmed ✔️</h3>
      <p><strong>Name:</strong> ${order.customer_name}</p>
      <p><strong>Pickup/Delivery:</strong> ${order.pickup_or_delivery}</p>

      <h4>Items:</h4>
      <ul>
          ${order.items.map(i => `
              <li>${i.qty} × ${i.name} — $${i.price}</li>
          `).join("")}
      </ul>

      <h4>Total: $${order.total}</h4>
  `;

  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

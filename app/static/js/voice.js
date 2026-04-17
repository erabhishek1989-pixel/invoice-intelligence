const chatBox = document.getElementById("chat-box");
const questionInput = document.getElementById("question-input");
const sendBtn = document.getElementById("send-btn");
const micBtn = document.getElementById("mic-btn");

function appendMessage(role, text) {
  const div = document.createElement("div");
  div.className = `chat-message ${role}`;
  div.innerHTML = `<span class="bubble">${text}</span>`;
  chatBox.appendChild(div);
  chatBox.scrollTop = chatBox.scrollHeight;
}

function speak(text) {
  if (!window.speechSynthesis) return;
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "en-IN";
  utterance.rate = 0.9;
  window.speechSynthesis.speak(utterance);
}

async function sendQuery(question, wasVoice = false) {
  if (!question.trim()) return;
  appendMessage("user", question);
  questionInput.value = "";

  try {
    const res = await fetch("/api/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, was_voice: wasVoice }),
    });
    const data = await res.json();
    const answer = data.answer || data.error || "No response.";
    appendMessage("assistant", answer);
    if (wasVoice) speak(answer);
  } catch {
    appendMessage("assistant", "Network error. Please try again.");
  }
}

sendBtn.addEventListener("click", () => {
  sendQuery(questionInput.value.trim());
});

questionInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendQuery(questionInput.value.trim());
});

// Voice input — Chrome/Edge only
if ("webkitSpeechRecognition" in window || "SpeechRecognition" in window) {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const recognition = new SpeechRecognition();
  recognition.lang = "en-IN";
  recognition.continuous = false;
  recognition.interimResults = false;

  recognition.onresult = (e) => {
    const text = e.results[0][0].transcript;
    questionInput.value = text;
    sendQuery(text, true);
  };

  recognition.onstart = () => micBtn.classList.add("listening");
  recognition.onend = () => micBtn.classList.remove("listening");
  recognition.onerror = () => micBtn.classList.remove("listening");

  micBtn.addEventListener("click", () => recognition.start());
} else {
  micBtn.disabled = true;
  micBtn.title = "Voice input requires Chrome or Edge";
}

const messageList = document.querySelector("#messageList");
const messageForm = document.querySelector("#messageForm");
const messageInput = document.querySelector("#messageInput");
const sendButton = document.querySelector("#sendButton");
const webhookSecret = document.querySelector("#webhookSecret");
const conversationIdLabel = document.querySelector("#conversationId");
const healthBadge = document.querySelector("#healthBadge");
const healthText = document.querySelector("#healthText");
const debugButton = document.querySelector("#toggleDebugButton");
const loadingTemplate = document.querySelector("#loadingTemplate");
const welcomeMessage = document.querySelector(".welcome-message").cloneNode(true);

let conversationId = createId("conversation");
let messageSequence = 0;
let debugVisible = true;
let sending = false;

function createId(prefix) {
  const suffix = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${suffix}`;
}

function createElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function currentTime() {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date());
}

function scrollToBottom() {
  messageList.scrollTop = messageList.scrollHeight;
}

function resetConversation() {
  conversationId = createId("conversation");
  messageSequence = 0;
  messageList.replaceChildren(welcomeMessage.cloneNode(true));
  conversationIdLabel.textContent = conversationId;
  messageInput.value = "";
  resizeComposer();
  messageInput.focus();
}

function appendUserMessage(text) {
  const row = createElement("article", "message-row user-message");
  const avatar = createElement("div", "avatar", "ME");
  const content = createElement("div", "message-content");
  const meta = createElement("div", "message-meta");
  meta.append(createElement("strong", "", "测试用户"), createElement("span", "", currentTime()));
  const bubble = createElement("div", "bubble", text);
  content.append(meta, bubble);
  row.append(avatar, content);
  messageList.append(row);
  scrollToBottom();
}

function appendLoading() {
  const loading = loadingTemplate.content.firstElementChild.cloneNode(true);
  loading.dataset.loading = "true";
  messageList.append(loading);
  scrollToBottom();
  return loading;
}

function appendStatus(content, response) {
  const status = createElement("div", "response-status");
  const decision = createElement(
    "span",
    `decision-badge ${response.decision}`,
    response.decision === "answered" ? "已回答" : response.decision === "handoff" ? "已转人工" : "安全降级",
  );
  status.append(decision);
  for (const tag of response.risk_tags ?? []) {
    status.append(createElement("span", "channel-badge", tag));
  }
  content.append(status);

  if (response.handoff_reason) {
    content.append(createElement("div", "reason-box", `转人工原因：${response.handoff_reason}`));
  }
}

function appendDebugDetails(content, response) {
  const details = createElement("div", "debug-details");
  details.hidden = !debugVisible;

  const traceBlock = createElement("section", "debug-block");
  const traceTitle = createElement("div", "debug-title");
  traceTitle.append(
    createElement("span", "", "LangGraph Trace"),
    createElement("span", "", `${(response.graph_trace ?? []).length} nodes`),
  );
  const traceList = createElement("ol", "trace-list");
  for (const node of response.graph_trace ?? []) {
    traceList.append(createElement("li", "", node));
  }
  traceBlock.append(traceTitle, traceList);
  details.append(traceBlock);

  const citationBlock = createElement("section", "debug-block");
  const citationTitle = createElement("div", "debug-title");
  const citations = response.citations ?? [];
  citationTitle.append(
    createElement("span", "", "Knowledge Citations"),
    createElement("span", "", `${citations.length} hits`),
  );
  citationBlock.append(citationTitle);

  if (citations.length === 0) {
    citationBlock.append(createElement("p", "message-meta", "本次未使用知识文档"));
  } else {
    const list = createElement("div", "citation-list");
    citations.forEach((citation, index) => {
      const card = createElement("article", "citation-card");
      card.append(createElement("strong", "", `${index + 1}. ${citation.title}`));
      const meta = createElement("div", "citation-meta");
      meta.append(
        createElement("span", "citation-category", citation.category ?? "general"),
        createElement("span", "", `score ${Number(citation.score).toFixed(3)}`),
      );
      if (citation.source_sheet) {
        meta.append(createElement("span", "", `${citation.source_sheet}!${citation.source_row ?? "?"}`));
      }
      for (const channel of citation.retrieval_channels ?? []) {
        meta.append(createElement("span", "channel-badge", channel));
      }
      card.append(meta);
      list.append(card);
    });
    citationBlock.append(list);
  }
  details.append(citationBlock);
  content.append(details);
}

function appendAssistantMessage(response) {
  const row = createElement("article", "message-row assistant-message");
  const avatar = createElement("div", "avatar", "S1");
  const content = createElement("div", "message-content");
  const meta = createElement("div", "message-meta");
  meta.append(createElement("strong", "", "SounderOne Agent"), createElement("span", "", currentTime()));
  content.append(meta, createElement("div", "bubble", response.text));
  appendStatus(content, response);
  appendDebugDetails(content, response);
  row.append(avatar, content);
  messageList.append(row);
  scrollToBottom();
}

function appendError(error) {
  const row = createElement("article", "message-row assistant-message");
  const avatar = createElement("div", "avatar", "!");
  const content = createElement("div", "message-content");
  const meta = createElement("div", "message-meta");
  meta.append(createElement("strong", "", "请求失败"), createElement("span", "", currentTime()));
  content.append(meta, createElement("div", "bubble error-bubble", error));
  row.append(avatar, content);
  messageList.append(row);
  scrollToBottom();
}

async function sendMessage(text) {
  const normalized = text.trim();
  if (!normalized || sending) return;

  sending = true;
  messageSequence += 1;
  appendUserMessage(normalized);
  const loading = appendLoading();
  messageInput.value = "";
  resizeComposer();
  sendButton.disabled = true;

  try {
    const response = await fetch("/v1/webhooks/simulator", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Webhook-Secret": webhookSecret.value,
      },
      body: JSON.stringify({
        message_id: `${conversationId}-message-${messageSequence}`,
        conversation_id: conversationId,
        user_id: "browser-tester",
        text: normalized,
        metadata: { source: "agent-lab" },
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail ?? `HTTP ${response.status}`);
    }
    appendAssistantMessage(payload);
  } catch (error) {
    appendError(error instanceof Error ? error.message : String(error));
  } finally {
    loading.remove();
    sending = false;
    sendButton.disabled = false;
    messageInput.focus();
    scrollToBottom();
  }
}

function resizeComposer() {
  messageInput.style.height = "auto";
  messageInput.style.height = `${Math.min(messageInput.scrollHeight, 140)}px`;
}

async function checkHealth() {
  try {
    const response = await fetch("/health");
    if (!response.ok) throw new Error("offline");
    const health = await response.json();
    healthBadge.className = "health-badge is-online";
    healthText.textContent = `服务正常 · ${health.active_knowledge_documents} 条知识`;
  } catch {
    healthBadge.className = "health-badge is-offline";
    healthText.textContent = "服务不可用";
  }
}

messageForm.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage(messageInput.value);
});

messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    messageForm.requestSubmit();
  }
});

messageInput.addEventListener("input", resizeComposer);

document.querySelectorAll(".scenario-card").forEach((button) => {
  button.addEventListener("click", () => sendMessage(button.dataset.message ?? ""));
});

document.querySelector("#newConversationButton").addEventListener("click", resetConversation);

document.querySelector("#toggleSecretButton").addEventListener("click", (event) => {
  const revealing = webhookSecret.type === "password";
  webhookSecret.type = revealing ? "text" : "password";
  event.currentTarget.textContent = revealing ? "隐藏" : "显示";
});

debugButton.addEventListener("click", () => {
  debugVisible = !debugVisible;
  debugButton.setAttribute("aria-pressed", String(debugVisible));
  debugButton.textContent = debugVisible ? "隐藏调试信息" : "显示调试信息";
  document.querySelectorAll(".debug-details").forEach((details) => {
    details.hidden = !debugVisible;
  });
});

resetConversation();
checkHealth();

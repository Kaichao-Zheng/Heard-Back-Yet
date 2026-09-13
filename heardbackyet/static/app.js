(() => {
  "use strict";

  const runtimeConfig = window.__HEARDBACKYET_CONFIG__ || {};
  const apiBaseUrl = typeof runtimeConfig.apiBaseUrl === "string"
    ? runtimeConfig.apiBaseUrl.trim().replace(/\/+$/, "")
    : "";

  function apiUrl(path) {
    return `${apiBaseUrl}${path}`;
  }

  const API_URL = apiUrl("/api/v1/responses");
  const READINESS_URL = apiUrl("/ready");
  const WEIXIN_LOGIN_URL = apiUrl("/api/v1/weixin/login-sessions");
  const CONVERSATION_STORAGE_KEY = "heardbackyet.conversation_id";
  const SAMPLE_SCROLL_SPEED = 0.04;
  const SAMPLE_SCROLL_RESUME_DELAY = 500;
  const sampleQueries = [
    "最近有什么消息吗",
    "九月投递了哪些",
    "哪些岗位要求AWS",
    "亚马逊是怎么推进的",
    "平安那边有消息吗",
  ];

  const outcomeAliases = {
    resolved: "答案已找到",
    direct_answer: "直接回答",
    needs_clarification: "需补充信息",
    requires_decomposition: "需拆分问题",
    unsupported: "暂不支持"
  };

  const initialMessage = {
    role: "assistant",
    answer: "Hi，这里是 Kai 的\"投了么\"求职百问灵。\n你可以问我 求职进度、最近投递、邮件往来、岗位要求 等应聘动态。\n------\n注意：频繁扫码换绑可能触发微信防滥用导致无回复。\n详见：https://github.com/Tencent/openclaw-weixin/issues/278",
    badge: "欢迎语",
    sources: []
  };

  const state = {
    messages: [initialMessage],
    loading: false,
    introHidden: false
  };

  function createConversationId() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    return `web-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  function loadConversationId() {
    try {
      const existing = window.sessionStorage.getItem(CONVERSATION_STORAGE_KEY);
      if (existing) return existing;
      const created = createConversationId();
      window.sessionStorage.setItem(CONVERSATION_STORAGE_KEY, created);
      return created;
    } catch (_error) {
      return createConversationId();
    }
  }

  const conversationId = loadConversationId();

  const elements = {
    conversation: document.getElementById("conversation"),
    messageList: document.getElementById("messageList"),
    form: document.getElementById("queryForm"),
    input: document.getElementById("queryInput"),
    send: document.getElementById("sendButton"),
    sampleList: document.querySelector(".sample-list"),
    weixinEntry: document.getElementById("weixinEntry")
  };
  const weixinEntryLabel = elements.weixinEntry.textContent;
  let weixinFeedbackTimer = null;
  let sampleScrollLastTime = null;
  let sampleScrollPosition = null;
  let sampleScrollPausedUntil = 0;
  let sampleScrollInteracting = false;
  const sampleSets = [];

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function cleanInlineMarkup(text) {
    return text.replace(/\*\*/g, "").replace(/`/g, "");
  }

  function sourceFilename(sourcePath) {
    if (typeof sourcePath !== "string" || sourcePath.trim().length === 0) {
      return "未提供文件名";
    }
    const segments = sourcePath.replace(/\\/g, "/").split("/").filter(Boolean);
    return segments[segments.length - 1] || "未提供文件名";
  }

  function sourceName(source) {
    if (source.source_path) return sourceFilename(source.source_path);
    const references = [];
    const emailId = source.email_id
      ?? source.latest_status_email_id
      ?? source.pointed_email_id
      ?? (source.source_type === "email" ? source.source_id : null);
    const jobDescriptionId = source.latest_jd_id
      ?? (source.source_type === "job_description" ? source.source_id : null);
    if (emailId != null) references.push(`邮件 #${emailId}`);
    if (jobDescriptionId != null) references.push(`职位描述 #${jobDescriptionId}`);
    if (source.provenance_id != null) references.push(`证据记录 #${source.provenance_id}`);
    return references.join(" · ") || "未提供来源详情";
  }

  function initializeSampleQueries() {
    const track = element("div", "sample-track");
    [true, false, true].forEach((isDuplicate) => {
      const set = element("div", "sample-set");
      if (isDuplicate) set.setAttribute("aria-hidden", "true");
      sampleQueries.forEach((query) => {
        const button = element("button", "sample-query", query);
        button.type = "button";
        button.dataset.query = query;
        if (isDuplicate) button.tabIndex = -1;
        set.appendChild(button);
      });
      track.appendChild(set);
      sampleSets.push(set);
    });
    elements.sampleList.appendChild(track);
  }

  function animateSampleQueries(timestamp) {
    const cycleWidth = sampleSets.length > 1
      ? sampleSets[1].offsetLeft - sampleSets[0].offsetLeft
      : 0;
    const maxScrollLeft = elements.sampleList.scrollWidth - elements.sampleList.clientWidth;
    const resetAt = Math.min(cycleWidth * 2, maxScrollLeft);
    const elapsed = sampleScrollLastTime === null
      ? 0
      : Math.min(timestamp - sampleScrollLastTime, 50);
    sampleScrollLastTime = timestamp;

    if (sampleScrollPosition === null || sampleScrollInteracting || timestamp < sampleScrollPausedUntil) {
      sampleScrollPosition = elements.sampleList.scrollLeft;
    }

    if (cycleWidth > 0 && resetAt > cycleWidth + 1 && sampleScrollPosition >= resetAt - 0.5) {
      sampleScrollPosition -= cycleWidth;
    } else if (cycleWidth > 0 && sampleScrollPosition <= 0.5) {
      sampleScrollPosition += cycleWidth;
    }

    if (!sampleScrollInteracting && timestamp >= sampleScrollPausedUntil && maxScrollLeft > 1) {
      sampleScrollPosition += elapsed * SAMPLE_SCROLL_SPEED;
    }
    elements.sampleList.scrollLeft = sampleScrollPosition;

    window.requestAnimationFrame(animateSampleQueries);
  }

  function appendFormattedText(container, text) {
    const lines = String(text || "").split(/\r?\n/);
    let list = null;
    let listType = null;

    function closeList() {
      list = null;
      listType = null;
    }

    lines.forEach((rawLine) => {
      const line = rawLine.trim();
      if (!line) {
        closeList();
        return;
      }

      const headingMatch = line.match(/^#{1,3}\s+(.+)$/);
      const unorderedMatch = line.match(/^[-*]\s+(.+)$/);
      const orderedMatch = line.match(/^(\d+)[.)]\s+(.+)$/);

      if (headingMatch) {
        closeList();
        container.appendChild(element("h3", "", cleanInlineMarkup(headingMatch[1])));
        return;
      }

      if (unorderedMatch || orderedMatch) {
        const nextType = unorderedMatch ? "ul" : "ol";
        if (!list || listType !== nextType) {
          list = document.createElement(nextType);
          listType = nextType;
          container.appendChild(list);
        }
        const item = element("li", "", cleanInlineMarkup(unorderedMatch ? unorderedMatch[1] : orderedMatch[2]));
        if (orderedMatch) item.value = Number(orderedMatch[1]);
        list.appendChild(item);
        return;
      }

      closeList();
      container.appendChild(element("p", "", cleanInlineMarkup(line)));
    });
  }

  function renderSources(sources) {
    if (!Array.isArray(sources) || sources.length === 0) return null;

    const details = element("details", "sources");
    const summary = element("summary", "", "查看来源");
    const list = element("ol", "source-list");

    details.addEventListener("toggle", () => {
      summary.textContent = details.open ? "隐藏来源" : "查看来源";
      requestAnimationFrame(maybeHideIntro);
    });

    sources.forEach((source) => {
      const item = element("li", "source-item");
      const topline = element("div", "source-topline");
      const hasEmail = source.email_id != null || source.latest_status_email_id != null || source.pointed_email_id != null;
      const hasJobDescription = source.latest_jd_id != null || source.jd_source_url;
      const typeLabel = source.source_type === "email" ? "原始邮件" : source.source_type === "job_description" ? "职位描述" : hasEmail ? "原始邮件" : hasJobDescription ? "职位描述" : "来源";
      topline.appendChild(element("span", "source-kind", typeLabel));
      if (source.source_id !== undefined && source.source_id !== null) {
        topline.appendChild(element("span", "source-id", `#${source.source_id}`));
      }
      item.appendChild(topline);

      const detail = element("div", "source-detail");
      const name = element("div", "source-name", sourceName(source));
      if (source.source_path) name.title = source.source_path;
      detail.appendChild(name);

      const sourceUrl = source.source_url || source.jd_source_url;
      if (typeof sourceUrl === "string" && /^https?:\/\//i.test(sourceUrl)) {
        const link = element("a", "source-link", "打开职位详情");
        link.href = sourceUrl;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        detail.appendChild(link);
      }
      item.appendChild(detail);
      list.appendChild(item);
    });

    details.append(summary, list);
    return details;
  }

  function renderMessage(message) {
    const classes = ["message", message.role];
    if (message.role === "assistant") {
      classes.push("response");
    }
    if (message.error) classes.push("error");
    const article = element("article", classes.join(" "));
    if (message.role === "assistant") {
      const meta = element("div", "message-meta");
      meta.appendChild(element("span", "", "HeardBackYet"));
      const badge = message.badge || (message.outcome ? outcomeAliases[message.outcome] || message.outcome : null);
      if (badge) meta.appendChild(element("span", "outcome", badge));
      article.appendChild(meta);
    }

    const body = element("div", "message-body");
    appendFormattedText(body, message.answer);
    article.appendChild(body);

    const sources = renderSources(message.sources);
    if (sources) article.appendChild(sources);
    return article;
  }

  function maybeHideIntro() {
    const hasUserQuery = state.messages.length > 1;
    if (state.introHidden || state.loading || !hasUserQuery) return;
    if (elements.conversation.scrollHeight <= elements.conversation.clientHeight + 1) return;

    state.introHidden = true;
    document.body.classList.add("intro-hidden");
  }

  function render() {
    document.body.classList.toggle("intro-hidden", state.introHidden);
    elements.messageList.replaceChildren();
    state.messages.forEach((message) => elements.messageList.appendChild(renderMessage(message)));

    if (state.loading) {
      const loading = element("article", "message assistant response");
      const meta = element("div", "message-meta", "HeardBackYet · 正在检索");
      const dots = element("div", "typing");
      dots.setAttribute("aria-label", "正在生成回答");
      dots.append(element("span"), element("span"), element("span"));
      loading.append(meta, dots);
      elements.messageList.appendChild(loading);
    }

    elements.send.disabled = state.loading || elements.input.value.trim().length === 0;
    requestAnimationFrame(() => {
      maybeHideIntro();
      elements.conversation.scrollTop = elements.conversation.scrollHeight;
    });
  }

  function autosizeInput() {
    elements.input.style.height = "auto";
    const requiredHeight = elements.input.scrollHeight;
    elements.input.style.height = `${Math.min(requiredHeight, 132)}px`;
    elements.input.style.overflowY = requiredHeight > 132 ? "auto" : "hidden";
    elements.send.disabled = state.loading || elements.input.value.trim().length === 0;
  }

  async function queryApi(query) {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 60000);
    try {
      const response = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_query: query, conversation_id: conversationId }),
        signal: controller.signal
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        const error = new Error(payload && payload.message ? payload.message : `HTTP ${response.status}`);
        error.code = payload && payload.code ? payload.code : "http_error";
        throw error;
      }
      return payload;
    } finally {
      window.clearTimeout(timeoutId);
    }
  }

  async function ensureDependenciesReady() {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 5000);
    try {
      const response = await fetch(READINESS_URL, {
        headers: { "Accept": "application/json" },
        signal: controller.signal
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        const error = new Error(payload && payload.message ? payload.message : `HTTP ${response.status}`);
        error.code = payload && payload.code ? payload.code : "readiness_unavailable";
        throw error;
      }
    } catch (error) {
      if (error && error.code) throw error;
      const readinessError = new Error("Dependency readiness check failed.");
      readinessError.code = error && error.name === "AbortError" ? "readiness_timeout" : "readiness_unreachable";
      throw readinessError;
    } finally {
      window.clearTimeout(timeoutId);
    }
  }

  function publicErrorMessage(error) {
    if (error && error.code === "dependencies_unavailable") return "数据库未就绪，请先启动 Docker（PostgreSQL）后重试。";
    if (error && error.code === "readiness_timeout") return "数据库状态检查超时，请确认 Docker（PostgreSQL）已启动。";
    if (error && error.code === "readiness_unreachable") return "无法连接后端服务，请确认 FastAPI 已启动后重试。";
    if (error && error.name === "AbortError") return "本次查询超过 60 秒。请确认本地模型状态后重试。";
    if (error && error.code === "validation_error") return "问题格式无效，请修改后重试。";
    if (error && error.code === "response_unavailable") return "当前无法生成回答，请稍后重试。";
    return "无法连接查询服务，请确认后端服务可用后重试。";
  }

  async function submitQuery(rawQuery) {
    const query = rawQuery.trim();
    if (!query || state.loading) return;

    state.messages.push({ role: "user", answer: query, sources: [] });
    state.loading = true;
    elements.input.value = "";
    autosizeInput();
    render();

    try {
      await ensureDependenciesReady();
      const response = await queryApi(query);
      state.messages.push({
        role: "assistant",
        answer: response.answer || "服务没有返回可显示回答。",
        outcome: response.outcome,
        sources: Array.isArray(response.sources) ? response.sources : []
      });
    } catch (error) {
      state.messages.push({
        role: "assistant",
        answer: publicErrorMessage(error),
        error: true,
        sources: []
      });
    } finally {
      state.loading = false;
      render();
      elements.input.focus();
    }
  }

  elements.form.addEventListener("submit", (event) => {
    event.preventDefault();
    submitQuery(elements.input.value);
  });

  elements.input.addEventListener("input", autosizeInput);
  elements.input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      elements.form.requestSubmit();
    }
  });

  elements.sampleList.addEventListener("pointerdown", (event) => {
    if (event.pointerType === "touch" || event.pointerType === "pen") {
      sampleScrollInteracting = true;
    }
  });

  function pauseSampleAutoScroll(delay) {
    sampleScrollPausedUntil = window.performance.now() + delay;
  }

  function resumeSampleAutoScroll() {
    sampleScrollInteracting = false;
    pauseSampleAutoScroll(SAMPLE_SCROLL_RESUME_DELAY);
  }

  elements.sampleList.addEventListener("pointerup", resumeSampleAutoScroll);
  elements.sampleList.addEventListener("pointercancel", resumeSampleAutoScroll);
  elements.sampleList.addEventListener("wheel", (event) => {
    const scrollDistance = Math.abs(event.deltaX) > Math.abs(event.deltaY)
      ? event.deltaX
      : event.deltaY;
    if (scrollDistance === 0) return;
    event.preventDefault();
    elements.sampleList.scrollLeft -= scrollDistance;
    sampleScrollPosition = elements.sampleList.scrollLeft;
    pauseSampleAutoScroll(SAMPLE_SCROLL_RESUME_DELAY);
  }, { passive: false });

  elements.sampleList.addEventListener("click", (event) => {
    const button = event.target.closest(".sample-query");
    if (button) submitQuery(button.dataset.query || "");
  });

  async function startWeixinLogin() {
    if (elements.weixinEntry.disabled) return;
    if (weixinFeedbackTimer !== null) {
      window.clearTimeout(weixinFeedbackTimer);
      weixinFeedbackTimer = null;
    }
    elements.weixinEntry.disabled = true;
    elements.weixinEntry.textContent = "正在打开微信…";
    try {
      const response = await fetch(WEIXIN_LOGIN_URL, {
        method: "POST",
        headers: { Accept: "application/json" }
      });
      if (response.status === 429) throw new Error("busy");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      if (!payload.qrcode_url) throw new Error("missing-url");
      window.location.assign(payload.qrcode_url);
    } catch (error) {
      elements.weixinEntry.disabled = false;
      elements.weixinEntry.textContent = error.message === "busy"
        ? "授权请求较多，请稍后重试"
        : "暂时无法打开，请重试";
      weixinFeedbackTimer = window.setTimeout(() => {
        elements.weixinEntry.textContent = weixinEntryLabel;
        weixinFeedbackTimer = null;
      }, 2400);
    }
  }

  elements.weixinEntry.addEventListener("click", startWeixinLogin);

  window.addEventListener("resize", () => requestAnimationFrame(maybeHideIntro));

  initializeSampleQueries();
  window.requestAnimationFrame(animateSampleQueries);
  render();
  autosizeInput();
})();

(() => {
  "use strict";

  const API_URL = "/api/v1/responses";
  const sampleQueries = [
    "哪些岗位要求AWS",
    "平安那边有消息吗",
    "亚马逊是怎么推进的"
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
    answer: "Hi，这里是 Kai 的\"投了么\"求职百问灵。\n你可以问我 求职进度、最近投递、邮件往来、岗位要求 等应聘动态。",
    badge: "欢迎语",
    sources: []
  };

  const state = {
    messages: [initialMessage],
    loading: false,
    introHidden: false
  };

  const elements = {
    conversation: document.getElementById("conversation"),
    messageList: document.getElementById("messageList"),
    form: document.getElementById("queryForm"),
    input: document.getElementById("queryInput"),
    send: document.getElementById("sendButton"),
    sample: document.querySelector(".sample-query")
  };

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
    const emailId = source.email_id ?? source.latest_status_email_id ?? source.pointed_email_id;
    if (emailId != null) references.push(`邮件 #${emailId}`);
    if (source.latest_jd_id != null) references.push(`职位描述 #${source.latest_jd_id}`);
    if (source.provenance_id != null) references.push(`证据记录 #${source.provenance_id}`);
    return references.join(" · ") || "未提供来源详情";
  }

  function initializeSampleQuery() {
    const query = sampleQueries[Math.floor(Math.random() * sampleQueries.length)];
    elements.sample.dataset.query = query;
    elements.sample.textContent = `问问看：${query}`;
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
    const hasUserQuery = state.messages.length > 1;
    document.body.classList.toggle("has-query", hasUserQuery);
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
    const timeoutId = window.setTimeout(() => controller.abort(), 120000);
    try {
      const response = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_query: query }),
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

  function publicErrorMessage(error) {
    if (error && error.name === "AbortError") return "本次查询超过 120 秒。请确认本地模型状态后重试。";
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

  elements.sample.addEventListener("click", () => submitQuery(elements.sample.dataset.query || ""));

  window.addEventListener("resize", () => requestAnimationFrame(maybeHideIntro));

  initializeSampleQuery();
  render();
  autosizeInput();
})();

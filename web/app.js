"use strict";

const DEMO_TEXT = `雨敲在旧车站的玻璃顶上。林夏抱紧书包，望向站台尽头。

“你真的要一个人去北城？”陈默低声问。

林夏笑了笑：“总得有人把信送到。”

“可外面在下暴雨！”陈默喊道。

长椅旁的老爷爷抬起头，缓慢地说道：“年轻人，怕的从来不是雨，是不知道为什么出发。”

一个小男孩从售票窗后探出脑袋，兴奋地叫道：“火车来啦！”

远处传来汽笛声。林夏转过身，眼睛亮了起来。

“等我回来。”林夏轻声说。`;

const labels = {
  gender: {
    female: "女性呈现",
    male: "男性呈现",
    neutral: "中性",
    unknown: "未知",
  },
  age: {
    child: "儿童",
    teen: "少年 / 少女",
    adult: "成年",
    elder: "老年",
    unknown: "未知",
  },
  emotion: {
    neutral: "平静",
    questioning: "疑问",
    excited: "激动",
    happy: "愉快",
    sad: "悲伤",
    angry: "愤怒",
  },
};

const state = {
  config: null,
  analysis: null,
  isSpeaking: false,
};

const elements = {};

document.addEventListener("DOMContentLoaded", async () => {
  for (const id of [
    "systemStatus",
    "sourceText",
    "characterCounter",
    "analyzerMode",
    "loadDemoButton",
    "analyzeButton",
    "messageBox",
    "resultSection",
    "analysisSummary",
    "warningList",
    "characterGrid",
    "scriptTimeline",
    "playButton",
    "stopButton",
    "providerNotice",
    "demoRenderButton",
    "dashscopeRenderButton",
    "audioResult",
    "resultAudio",
    "audioMeta",
    "downloadLink",
  ]) {
    elements[id] = document.getElementById(id);
  }

  elements.sourceText.addEventListener("input", updateCounter);
  elements.loadDemoButton.addEventListener("click", loadDemo);
  elements.analyzeButton.addEventListener("click", analyzeText);
  elements.playButton.addEventListener("click", startBrowserPreview);
  elements.stopButton.addEventListener("click", stopBrowserPreview);
  elements.demoRenderButton.addEventListener("click", () => renderAudio("demo"));
  elements.dashscopeRenderButton.addEventListener("click", () =>
    renderAudio("dashscope"),
  );
  window.addEventListener("beforeunload", stopBrowserPreview);

  await loadConfig();
  updateCounter();
});

async function loadConfig() {
  try {
    state.config = await requestJson("/api/config");
    elements.systemStatus.classList.add("ready");
    elements.systemStatus.lastChild.textContent = " 服务正常";
    const qwenReady = state.config.analyzers.qwen.ready;
    const qwenOption = elements.analyzerMode.querySelector('option[value="qwen"]');
    if (!qwenReady) {
      qwenOption.textContent = "千问增强 · 未配置时自动降级";
    }
    const dashscopeReady = state.config.providers.dashscope.ready;
    elements.dashscopeRenderButton.disabled = !dashscopeReady;
    elements.providerNotice.textContent = dashscopeReady
      ? "百炼已连接：真实合成会按字符消耗供应商额度，提交前会再次确认。"
      : "百炼尚未配置：浏览器多人试听与离线拼接检测仍可完整运行。";
  } catch (error) {
    elements.systemStatus.lastChild.textContent = " 服务未连接";
    showMessage(error.message);
  }
}

function loadDemo() {
  elements.sourceText.value = DEMO_TEXT;
  updateCounter();
  elements.sourceText.focus();
  showMessage("已载入原创演示片段，可直接点击“开始选角”。", true);
}

function updateCounter() {
  const count = [...elements.sourceText.value].length;
  const max = state.config?.limits?.analyze_characters ?? 50000;
  elements.characterCounter.textContent = `${count.toLocaleString()} / ${max.toLocaleString()} 字`;
}

async function analyzeText() {
  const text = elements.sourceText.value.trim();
  if (!text) {
    showMessage("请先粘贴小说文本，或者载入演示文本。");
    return;
  }
  setBusy(elements.analyzeButton, true, "正在拆解角色…");
  hideMessage();
  stopBrowserPreview();
  try {
    state.analysis = await requestJson("/api/analyze", {
      method: "POST",
      body: JSON.stringify({
        text,
        mode: elements.analyzerMode.value,
      }),
    });
    renderAnalysis();
    elements.resultSection.hidden = false;
    elements.resultSection.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    showMessage(error.message);
  } finally {
    setBusy(elements.analyzeButton, false, "开始选角");
  }
}

function renderAnalysis() {
  const summary = state.analysis.summary;
  elements.analysisSummary.textContent =
    `识别到 ${summary.character_count} 位人物、${summary.dialogue_count} 句对话，` +
    `当前由 ${state.analysis.analyzer} 生成。请先确认黄色与红色项目。`;

  const warnings = state.analysis.warnings || [];
  elements.warningList.hidden = warnings.length === 0;
  elements.warningList.innerHTML = warnings
    .map((warning) => `<div>△ ${escapeHtml(warning)}</div>`)
    .join("");

  renderCharacters();
  renderTimeline();
  elements.audioResult.hidden = true;
}

function renderCharacters() {
  elements.characterGrid.innerHTML = "";
  for (const character of state.analysis.characters) {
    const card = document.createElement("article");
    card.className = `character-card ${character.id === "narrator" ? "narrator" : ""}`;
    const confidenceClass = confidenceLevel(character.confidence);
    const traits = (character.traits || [])
      .map((trait) => `<span class="trait">${escapeHtml(trait)}</span>`)
      .join("");
    const evidence = (character.evidence || [])[0] || "等待更多文本证据";
    card.innerHTML = `
      <div class="character-head">
        <span class="avatar">${escapeHtml(character.name.slice(0, 1))}</span>
        <div>
          <input class="character-name" type="text" value="${escapeAttribute(character.name)}"
            ${character.id === "narrator" ? "readonly" : ""} aria-label="角色名" />
          <span class="character-confidence">
            <i class="confidence-dot confidence-${confidenceClass}"></i>
            ${(character.confidence * 100).toFixed(0)}% 识别置信度
          </span>
        </div>
      </div>
      <div class="character-fields">
        <label class="field-label">性别呈现
          ${buildSelect(labels.gender, character.gender, "gender-select")}
        </label>
        <label class="field-label">年龄段
          ${buildSelect(labels.age, character.age_group, "age-select")}
        </label>
        <label class="field-label voice-field">配音声线
          ${buildVoiceSelect(character.voice_id)}
        </label>
      </div>
      <div class="trait-list">${traits}</div>
      <p class="evidence">“${escapeHtml(evidence)}”</p>
    `;
    const nameInput = card.querySelector(".character-name");
    const avatar = card.querySelector(".avatar");
    nameInput.addEventListener("change", () => {
      const value = nameInput.value.trim() || character.name;
      character.name = value;
      nameInput.value = value;
      avatar.textContent = value.slice(0, 1);
      renderTimeline();
    });
    card.querySelector(".gender-select").addEventListener("change", (event) => {
      character.gender = event.target.value;
    });
    card.querySelector(".age-select").addEventListener("change", (event) => {
      character.age_group = event.target.value;
    });
    card.querySelector(".voice-select").addEventListener("change", (event) => {
      character.voice_id = event.target.value;
    });
    elements.characterGrid.appendChild(card);
  }
}

function renderTimeline() {
  elements.scriptTimeline.innerHTML = "";
  const characterOptions = state.analysis.characters
    .map(
      (character) =>
        `<option value="${escapeAttribute(character.id)}">${escapeHtml(character.name)}</option>`,
    )
    .join("");
  for (const [index, segment] of state.analysis.segments.entries()) {
    const row = document.createElement("div");
    row.className = "script-row";
    const confidenceClass = confidenceLevel(segment.confidence);
    row.innerHTML = `
      <span class="segment-index">${String(index + 1).padStart(2, "0")}</span>
      <select class="script-speaker" aria-label="第 ${index + 1} 段说话人">
        ${characterOptions}
      </select>
      <div class="script-text">${escapeHtml(segment.text)}</div>
      <div class="segment-meta">
        <span class="emotion-tag">${escapeHtml(labels.emotion[segment.emotion] || segment.emotion)}</span>
        <i class="confidence-dot confidence-${confidenceClass}" title="${(
          segment.confidence * 100
        ).toFixed(0)}% 置信度"></i>
      </div>
    `;
    const select = row.querySelector(".script-speaker");
    select.value = segment.speaker_id;
    select.addEventListener("change", () => {
      segment.speaker_id = select.value;
      segment.confidence = 1;
      row.querySelector(".confidence-dot").className =
        "confidence-dot confidence-high";
      row.querySelector(".confidence-dot").title = "人工确认";
    });
    elements.scriptTimeline.appendChild(row);
  }
}

function buildSelect(options, selected, className) {
  const values = Object.entries(options)
    .map(
      ([value, label]) =>
        `<option value="${value}" ${value === selected ? "selected" : ""}>${label}</option>`,
    )
    .join("");
  return `<select class="${className}">${values}</select>`;
}

function buildVoiceSelect(selected) {
  const options = state.config.voices
    .map(
      (voice) =>
        `<option value="${escapeAttribute(voice.id)}" ${
          voice.id === selected ? "selected" : ""
        }>${escapeHtml(voice.label)} · ${escapeHtml(voice.description)}</option>`,
    )
    .join("");
  return `<select class="voice-select">${options}</select>`;
}

function confidenceLevel(confidence) {
  if (confidence >= 0.8) return "high";
  if (confidence >= 0.5) return "medium";
  return "low";
}

async function startBrowserPreview() {
  if (!state.analysis || !("speechSynthesis" in window)) {
    showMessage("当前浏览器不支持 Web Speech 试听，请使用 Chrome 或 Safari。");
    return;
  }
  stopBrowserPreview();
  state.isSpeaking = true;
  elements.playButton.disabled = true;
  const characters = new Map(
    state.analysis.characters.map((character) => [character.id, character]),
  );
  const voicePresets = new Map(
    state.config.voices.map((voice) => [voice.id, voice]),
  );
  const browserVoices = await waitForBrowserVoices();
  const chineseVoices = browserVoices.filter((voice) =>
    voice.lang.toLowerCase().startsWith("zh"),
  );
  let index = 0;

  const speakNext = () => {
    if (!state.isSpeaking || index >= state.analysis.segments.length) {
      stopBrowserPreview();
      return;
    }
    const segment = state.analysis.segments[index++];
    const character = characters.get(segment.speaker_id);
    const preset = voicePresets.get(character?.voice_id);
    const utterance = new SpeechSynthesisUtterance(segment.text);
    utterance.lang = "zh-CN";
    utterance.rate = preset?.browser_rate || 1;
    utterance.pitch = preset?.browser_pitch || 1;
    if (chineseVoices.length) {
      const hash = [...(character?.voice_id || "")].reduce(
        (total, value) => total + value.charCodeAt(0),
        0,
      );
      utterance.voice = chineseVoices[hash % chineseVoices.length];
    }
    utterance.onend = () => window.setTimeout(speakNext, 140);
    utterance.onerror = () => window.setTimeout(speakNext, 80);
    window.speechSynthesis.speak(utterance);
  };
  speakNext();
}

function stopBrowserPreview() {
  state.isSpeaking = false;
  if ("speechSynthesis" in window) {
    window.speechSynthesis.cancel();
  }
  if (elements.playButton) {
    elements.playButton.disabled = false;
  }
}

function waitForBrowserVoices() {
  const existing = window.speechSynthesis.getVoices();
  if (existing.length) return Promise.resolve(existing);
  return new Promise((resolve) => {
    const timeout = window.setTimeout(
      () => resolve(window.speechSynthesis.getVoices()),
      800,
    );
    window.speechSynthesis.addEventListener(
      "voiceschanged",
      () => {
        window.clearTimeout(timeout);
        resolve(window.speechSynthesis.getVoices());
      },
      { once: true },
    );
  });
}

async function renderAudio(provider) {
  if (!state.analysis) return;
  if (
    provider === "dashscope" &&
    !window.confirm(
      "真实合成会把本段文本发送到阿里云百炼，并按供应商规则消耗额度。确认继续吗？",
    )
  ) {
    return;
  }
  const button =
    provider === "dashscope"
      ? elements.dashscopeRenderButton
      : elements.demoRenderButton;
  setBusy(button, true, provider === "dashscope" ? "正在真实合成…" : "正在拼接…");
  hideMessage();
  try {
    const plan = await requestJson("/api/render/plan", {
      method: "POST",
      body: JSON.stringify({ analysis: state.analysis, provider }),
    });
    const result = await requestJson("/api/render", {
      method: "POST",
      body: JSON.stringify({
        analysis: state.analysis,
        provider,
        confirm_cost: provider === "dashscope",
      }),
    });
    elements.audioResult.hidden = false;
    elements.resultAudio.src = result.audio_url;
    elements.downloadLink.href = result.audio_url;
    elements.audioMeta.textContent =
      `${result.segment_count} 个片段 · ${result.total_characters} 字 · ` +
      `${provider === "demo" ? "离线诊断音" : "百炼真实语音"}；${plan.note}`;
    elements.audioResult.scrollIntoView({ behavior: "smooth", block: "center" });
    if (provider === "dashscope") {
      elements.resultAudio.play().catch(() => {});
    }
  } catch (error) {
    showMessage(error.message);
  } finally {
    setBusy(
      button,
      false,
      provider === "dashscope" ? "百炼真实合成" : "生成离线链路检测音",
    );
  }
}

async function requestJson(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new Error(`服务返回了无法解析的内容（HTTP ${response.status}）`);
  }
  if (!response.ok) {
    throw new Error(payload.message || `请求失败（HTTP ${response.status}）`);
  }
  return payload;
}

function setBusy(button, busy, label) {
  button.disabled = busy;
  const span = button.querySelector("span");
  if (span) span.textContent = label;
  else button.textContent = label;
}

function showMessage(message, success = false) {
  elements.messageBox.hidden = false;
  elements.messageBox.classList.toggle("success", success);
  elements.messageBox.textContent = message;
}

function hideMessage() {
  elements.messageBox.hidden = true;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttribute(value) {
  return escapeHtml(value);
}


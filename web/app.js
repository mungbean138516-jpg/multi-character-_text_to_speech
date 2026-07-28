"use strict";

const DRAFT_KEY = "voxcast.project.v2";
const DRAFT_VERSION = 3;
const MAX_TEXT_FILE_BYTES = 2_000_000;

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
  analysisSourceText: "",
  analysisStale: false,
  isSpeaking: false,
  isRendering: false,
  lastProvider: "demo",
  speechSession: 0,
  activeSegmentIndex: null,
  pronunciationSegmentIndex: null,
  sourceFile: null,
  draftTimer: null,
  planTimer: null,
};

const elements = {};

document.addEventListener("DOMContentLoaded", async () => {
  for (const id of [
    "systemStatus",
    "sourceText",
    "characterCounter",
    "analyzerMode",
    "loadDemoButton",
    "importFileButton",
    "fileInput",
    "fileMeta",
    "draftStatus",
    "clearDraftButton",
    "analyzeButton",
    "messageBox",
    "resultSection",
    "analysisSummary",
    "warningList",
    "characterGrid",
    "pronunciationPanel",
    "addPronunciationButton",
    "pronunciationForm",
    "pronunciationSource",
    "pronunciationReading",
    "pronunciationHint",
    "cancelPronunciationButton",
    "pronunciationList",
    "scriptTimeline",
    "playButton",
    "stopButton",
    "previewSpeed",
    "nowPlaying",
    "providerNotice",
    "outputFormat",
    "renderPlan",
    "refreshPlanButton",
    "demoRenderButton",
    "dashscopeRenderButton",
    "retryRenderButton",
    "audioResult",
    "audioTitle",
    "resultAudio",
    "audioMeta",
    "downloadLink",
    "wavDownloadLink",
  ]) {
    elements[id] = document.getElementById(id);
  }

  elements.sourceText.addEventListener("input", handleSourceChanged);
  elements.analyzerMode.addEventListener("change", scheduleDraftSave);
  elements.sourceText.addEventListener("dragover", handleTextDragOver);
  elements.sourceText.addEventListener("dragleave", handleTextDragLeave);
  elements.sourceText.addEventListener("drop", handleTextDrop);
  elements.loadDemoButton.addEventListener("click", loadDemo);
  elements.importFileButton.addEventListener("click", () =>
    elements.fileInput.click(),
  );
  elements.fileInput.addEventListener("change", () => {
    const [file] = elements.fileInput.files;
    if (file) importTextFile(file);
    elements.fileInput.value = "";
  });
  elements.clearDraftButton.addEventListener("click", clearSavedDraft);
  elements.analyzeButton.addEventListener("click", analyzeText);
  elements.playButton.addEventListener("click", () => startBrowserPreview(0));
  elements.stopButton.addEventListener("click", () => stopBrowserPreview());
  elements.previewSpeed.addEventListener("change", () => {
    scheduleDraftSave();
    if (state.isSpeaking && state.activeSegmentIndex !== null) {
      startBrowserPreview(state.activeSegmentIndex);
    }
  });
  elements.addPronunciationButton.addEventListener("click", () =>
    openPronunciationEditor(),
  );
  elements.cancelPronunciationButton.addEventListener(
    "click",
    closePronunciationEditor,
  );
  elements.pronunciationForm.addEventListener(
    "submit",
    savePronunciation,
  );
  elements.outputFormat.addEventListener("change", () => {
    scheduleDraftSave();
    scheduleRenderPlan();
  });
  elements.refreshPlanButton.addEventListener("click", () =>
    refreshRenderPlan(state.lastProvider, true),
  );
  elements.demoRenderButton.addEventListener("click", () => renderAudio("demo"));
  elements.dashscopeRenderButton.addEventListener("click", () =>
    renderAudio("dashscope"),
  );
  elements.retryRenderButton.addEventListener("click", () =>
    renderAudio(state.lastProvider, true),
  );
  window.addEventListener("beforeunload", stopBrowserPreview);

  await loadConfig();
  restoreDraft();
  updateCounter();
  updateActionAvailability();
});

async function loadConfig() {
  try {
    state.config = await requestJson("/api/config");
    elements.systemStatus.classList.add("ready");
    elements.systemStatus.lastChild.textContent = " 服务正常";

    const qwenOption = elements.analyzerMode.querySelector('option[value="qwen"]');
    if (!state.config.analyzers.qwen.ready) {
      qwenOption.textContent = "千问增强 · 未配置时自动降级";
    }

    const mp3Option = elements.outputFormat.querySelector('option[value="mp3"]');
    if (!state.config.formats?.mp3?.ready) {
      mp3Option.disabled = true;
      mp3Option.textContent = "MP3 · 服务器未安装 ffmpeg";
      if (elements.outputFormat.value === "mp3") {
        elements.outputFormat.value = "wav";
      }
    }
    state.lastProvider = state.config.providers?.dashscope?.ready
      ? "dashscope"
      : "demo";
    updateProviderNotice();
  } catch (error) {
    elements.systemStatus.lastChild.textContent = " 服务未连接";
    showMessage(error.message);
  }
}

function updateProviderNotice() {
  const dashscopeReady = Boolean(state.config?.providers?.dashscope?.ready);
  elements.providerNotice.textContent = dashscopeReady
    ? "高品质语音服务已就绪，生成前会先显示预计内容和费用。"
    : "高品质语音服务尚未连接；现在仍可免费完成多人试听和全部纠错。";
  const label = elements.dashscopeRenderButton.querySelector("span");
  if (label) {
    label.textContent = dashscopeReady ? "开始生成" : "高品质语音待连接";
  }
}

function loadDemo() {
  resetAnalysis();
  state.sourceFile = {
    name: "原创演示文本",
    encoding: "内置 UTF-8",
  };
  elements.sourceText.value = DEMO_TEXT;
  elements.fileMeta.textContent = "原创演示文本 · 内置 UTF-8";
  handleSourceChanged();
  elements.sourceText.focus();
  showMessage("已载入原创演示片段，可直接点击“自动识别角色”。", true);
}

function handleTextDragOver(event) {
  event.preventDefault();
  elements.sourceText.classList.add("drop-active");
}

function handleTextDragLeave() {
  elements.sourceText.classList.remove("drop-active");
}

function handleTextDrop(event) {
  event.preventDefault();
  elements.sourceText.classList.remove("drop-active");
  const [file] = event.dataTransfer.files;
  if (!file) return;
  importTextFile(file);
}

async function importTextFile(file) {
  hideMessage();
  if (
    !file.name.toLowerCase().endsWith(".txt") &&
    file.type &&
    file.type !== "text/plain"
  ) {
    showMessage("当前只支持 TXT 文本文件。");
    return;
  }
  if (file.size > MAX_TEXT_FILE_BYTES) {
    showMessage("TXT 文件过大；Alpha 版单个文件最多 2 MB。");
    return;
  }
  try {
    const decoded = decodeTextBytes(await file.arrayBuffer());
    const max = state.config?.limits?.analyze_characters ?? 50000;
    const count = [...decoded.text].length;
    if (count > max) {
      throw new Error(
        `文件有 ${count.toLocaleString()} 字，当前单次最多分析 ${max.toLocaleString()} 字。`,
      );
    }
    resetAnalysis();
    state.sourceFile = { name: file.name, encoding: decoded.encoding };
    elements.sourceText.value = decoded.text;
    elements.fileMeta.textContent =
      `${file.name} · ${decoded.encoding} · ${count.toLocaleString()} 字`;
    handleSourceChanged();
    showMessage(`已按 ${decoded.encoding} 导入 ${file.name}。`, true);
  } catch (error) {
    showMessage(error.message);
  }
}

function decodeTextBytes(arrayBuffer) {
  const bytes = new Uint8Array(arrayBuffer);
  const startsWith = (...values) =>
    values.every((value, index) => bytes[index] === value);
  const decode = (encoding, offset, label) => {
    const text = new TextDecoder(encoding, { fatal: true }).decode(
      bytes.slice(offset),
    );
    const controlCount = [...text].filter((character) => {
      const code = character.charCodeAt(0);
      return code < 32 && !["\n", "\r", "\t"].includes(character);
    }).length;
    if (text.length && controlCount / text.length >= 0.01) {
      throw new Error("文件包含过多控制字符，可能不是小说文本。");
    }
    return {
      text: text.replace(/\r\n?/g, "\n"),
      encoding: label,
    };
  };

  if (startsWith(0xef, 0xbb, 0xbf)) {
    return decode("utf-8", 3, "UTF-8 BOM");
  }
  if (startsWith(0xff, 0xfe)) {
    return decode("utf-16le", 2, "UTF-16 LE");
  }
  if (startsWith(0xfe, 0xff)) {
    return decode("utf-16be", 2, "UTF-16 BE");
  }

  for (const [encoding, label] of [
    ["utf-8", "UTF-8"],
    ["gb18030", "GB18030"],
  ]) {
    try {
      return decode(encoding, 0, label);
    } catch {
      // Try the next supported encoding.
    }
  }
  throw new Error("无法识别 TXT 编码；请转换为 UTF-8、UTF-16 或 GB18030。");
}

function handleSourceChanged() {
  updateCounter();
  const current = elements.sourceText.value.trim();
  if (state.analysis) {
    state.analysisStale = current !== state.analysisSourceText;
    renderAnalysisSummary();
  }
  scheduleDraftSave();
  updateActionAvailability();
}

function updateCounter() {
  const count = [...elements.sourceText.value].length;
  const max = state.config?.limits?.analyze_characters ?? 50000;
  elements.characterCounter.textContent =
    `${count.toLocaleString()} / ${max.toLocaleString()} 字`;
  elements.characterCounter.classList.toggle("over-limit", count > max);
}

function resetAnalysis() {
  stopBrowserPreview();
  state.analysis = null;
  state.analysisSourceText = "";
  state.analysisStale = false;
  elements.resultSection.hidden = true;
  elements.audioResult.hidden = true;
  elements.retryRenderButton.hidden = true;
  elements.renderPlan.textContent =
    "完成角色识别后，这里会显示预计生成内容。";
  closePronunciationEditor();
  updateActionAvailability();
}

async function analyzeText() {
  const text = elements.sourceText.value.trim();
  if (!text) {
    showMessage("请先粘贴小说文本、导入 TXT，或者载入演示文本。");
    return;
  }
  const max = state.config?.limits?.analyze_characters ?? 50000;
  if ([...text].length > max) {
    showMessage(`当前单次最多分析 ${max.toLocaleString()} 字。`);
    return;
  }

  setBusy(elements.analyzeButton, true, "正在识别角色…");
  hideMessage();
  stopBrowserPreview();
  try {
    state.analysis = normalizeAnalysis(
      await requestJson("/api/analyze", {
        method: "POST",
        body: JSON.stringify({
          text,
          mode: elements.analyzerMode.value,
        }),
      }),
    );
    state.analysisSourceText = text;
    state.analysisStale = false;
    renderAnalysis();
    elements.resultSection.hidden = false;
    scheduleDraftSave();
    scheduleRenderPlan(state.lastProvider);
    elements.resultSection.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    showMessage(error.message);
  } finally {
    setBusy(elements.analyzeButton, false, "自动识别角色");
    updateActionAvailability();
  }
}

function normalizeAnalysis(analysis) {
  analysis.characters = (analysis.characters || []).map((character) => ({
    aliases: [],
    locked: false,
    ...character,
  }));
  analysis.segments = (analysis.segments || []).map((segment) => ({
    locked: false,
    ...segment,
  }));
  analysis.warnings = analysis.warnings || [];
  analysis.pronunciations = analysis.pronunciations || {};
  recomputeSummary(analysis);
  return analysis;
}

function recomputeSummary(analysis = state.analysis) {
  if (!analysis) return;
  analysis.summary = {
    character_count: Math.max(0, analysis.characters.length - 1),
    segment_count: analysis.segments.length,
    dialogue_count: analysis.segments.filter(
      (segment) => segment.kind === "dialogue",
    ).length,
    characters_to_render: analysis.segments.reduce(
      (total, segment) => total + [...segment.text].length,
      0,
    ),
  };
}

function renderAnalysis() {
  recomputeSummary();
  renderAnalysisSummary();

  const warnings = state.analysis.warnings || [];
  elements.warningList.hidden = warnings.length === 0;
  elements.warningList.innerHTML = warnings
    .map((warning) => `<div>△ ${escapeHtml(warning)}</div>`)
    .join("");

  renderCharacters();
  renderPronunciations();
  renderTimeline();
  elements.audioResult.hidden = true;
  elements.retryRenderButton.hidden = true;
  updateActionAvailability();
}

function renderAnalysisSummary() {
  if (!state.analysis) return;
  const summary = state.analysis.summary;
  const prefix = state.analysisStale
    ? "原文已变更，请重新分析后再试听或生成。"
    : `识别到 ${summary.character_count} 位人物和 ${summary.dialogue_count} 句对话。`;
  const suffix = state.analysisStale
    ? ""
    : " 先试听；不合适的角色和声音都可以直接更换。";
  elements.analysisSummary.textContent = `${prefix}${suffix}`;
  elements.analysisSummary.classList.toggle("stale", state.analysisStale);
}

function renderCharacters() {
  elements.characterGrid.innerHTML = "";
  for (const character of state.analysis.characters) {
    const card = document.createElement("article");
    card.className =
      `character-card ${character.id === "narrator" ? "narrator" : ""}`;
    const confidenceClass = confidenceLevel(character.confidence);
    const traits = (character.traits || [])
      .map((trait) => `<span class="trait">${escapeHtml(trait)}</span>`)
      .join("");
    const judgment =
      character.id === "narrator"
        ? "叙述者 · 沉稳清晰"
        : [
            labels.age[character.age_group],
            labels.gender[character.gender],
            (character.traits || [])[0],
          ]
            .filter(Boolean)
            .join(" · ");
    const evidence = (character.evidence || [])[0] || "等待更多文本证据";
    const mergeTargets = state.analysis.characters
      .filter(
        (candidate) =>
          candidate.id !== "narrator" && candidate.id !== character.id,
      )
      .map(
        (candidate) =>
          `<option value="${escapeAttribute(candidate.id)}">${escapeHtml(candidate.name)}</option>`,
      )
      .join("");

    card.innerHTML = `
      <div class="character-head">
        <span class="avatar">${escapeHtml(character.name.slice(0, 1))}</span>
        <div>
          <input class="character-name" type="text" value="${escapeAttribute(character.name)}"
            ${character.id === "narrator" ? "readonly" : ""} aria-label="角色名" />
          <span class="character-judgment">
            <i class="confidence-dot confidence-${confidenceClass}"></i>
            ${escapeHtml(judgment || "人物特质待确认")}
            <b class="locked-badge" ${character.locked ? "" : "hidden"}>人工锁定</b>
          </span>
        </div>
      </div>
      <div class="voice-picker">
        <label class="field-label voice-field">默认声音
          ${buildVoiceSelect(character.voice_id)}
        </label>
        <button class="mini-button voice-preview-button" type="button">▶ 试听</button>
      </div>
      <details class="character-details">
        <summary>角色信息与别名</summary>
        <div class="character-fields">
          <label class="field-label">性别呈现
            ${buildSelect(labels.gender, character.gender, "gender-select")}
          </label>
          <label class="field-label">年龄段
            ${buildSelect(labels.age, character.age_group, "age-select")}
          </label>
          <label class="field-label alias-field">角色别名
            <input class="alias-input" type="text"
              value="${escapeAttribute((character.aliases || []).join("，"))}"
              ${character.id === "narrator" ? "readonly" : ""}
              placeholder="例如：陈伯，老陈" />
          </label>
        </div>
        <div class="trait-list">${traits}</div>
        <p class="evidence">判断依据：“${escapeHtml(evidence)}”</p>
        ${
          character.id === "narrator"
            ? ""
            : `<div class="merge-controls">
                <select class="merge-target" aria-label="合并目标" ${mergeTargets ? "" : "disabled"}>
                  ${mergeTargets || '<option value="">暂无其他角色</option>'}
                </select>
                <button class="mini-button merge-button" type="button" ${mergeTargets ? "" : "disabled"}>
                  其实是同一个人
                </button>
              </div>`
        }
      </details>
    `;

    const lockCharacter = () => {
      character.locked = true;
      card.querySelector(".locked-badge").hidden = false;
      scheduleDraftSave();
      scheduleRenderPlan();
    };
    const nameInput = card.querySelector(".character-name");
    const avatar = card.querySelector(".avatar");
    nameInput.addEventListener("change", () => {
      const oldName = character.name;
      const value = nameInput.value.trim() || oldName;
      character.name = value;
      if (oldName !== value && oldName !== "旁白") {
        character.aliases = uniqueValues([...(character.aliases || []), oldName])
          .filter((alias) => alias !== value);
      }
      nameInput.value = value;
      avatar.textContent = value.slice(0, 1);
      lockCharacter();
      renderTimeline();
    });
    card.querySelector(".gender-select").addEventListener("change", (event) => {
      character.gender = event.target.value;
      lockCharacter();
    });
    card.querySelector(".age-select").addEventListener("change", (event) => {
      character.age_group = event.target.value;
      lockCharacter();
    });
    card.querySelector(".voice-select").addEventListener("change", (event) => {
      character.voice_id = event.target.value;
      lockCharacter();
    });
    card
      .querySelector(".voice-preview-button")
      .addEventListener("click", () => previewCharacterVoice(character.id));
    if (character.id !== "narrator") {
      card.querySelector(".alias-input").addEventListener("change", (event) => {
        character.aliases = uniqueValues(
          event.target.value
            .split(/[,，、]/)
            .map((value) => value.trim())
            .filter((value) => value && value !== character.name),
        );
        event.target.value = character.aliases.join("，");
        lockCharacter();
      });
    }

    const mergeButton = card.querySelector(".merge-button");
    if (mergeButton) {
      mergeButton.addEventListener("click", () => {
        const targetId = card.querySelector(".merge-target").value;
        if (targetId) mergeCharacter(character.id, targetId);
      });
    }
    elements.characterGrid.appendChild(card);
  }
}

function mergeCharacter(sourceId, targetId) {
  const source = state.analysis.characters.find(
    (character) => character.id === sourceId,
  );
  const target = state.analysis.characters.find(
    (character) => character.id === targetId,
  );
  if (!source || !target || source.id === "narrator" || source.id === target.id) {
    return;
  }
  if (
    !window.confirm(
      `把“${source.name}”并入“${target.name}”？相关台词会全部改为“${target.name}”。`,
    )
  ) {
    return;
  }

  target.aliases = uniqueValues([
    ...(target.aliases || []),
    source.name,
    ...(source.aliases || []),
  ]).filter((alias) => alias !== target.name);
  target.traits = uniqueValues([
    ...(target.traits || []),
    ...(source.traits || []),
  ]).slice(0, 6);
  target.evidence = uniqueValues([
    ...(target.evidence || []),
    ...(source.evidence || []),
  ]).slice(0, 6);
  target.confidence = Math.max(target.confidence, source.confidence);
  target.locked = true;

  for (const segment of state.analysis.segments) {
    if (segment.speaker_id === source.id) {
      segment.speaker_id = target.id;
      segment.confidence = 1;
      segment.locked = true;
    }
  }
  state.analysis.characters = state.analysis.characters.filter(
    (character) => character.id !== source.id,
  );
  recomputeSummary();
  renderAnalysis();
  scheduleDraftSave();
  scheduleRenderPlan();
  showMessage(`已把“${source.name}”作为“${target.name}”的别名并完成台词迁移。`, true);
}

function renderPronunciations() {
  if (!state.analysis) return;
  const entries = Object.entries(state.analysis.pronunciations || {});
  if (!entries.length) {
    elements.pronunciationList.innerHTML =
      '<span class="pronunciation-empty">还没有发音纠正。也可以先在下方选中文字，再点“这个字读错了”。</span>';
    return;
  }
  elements.pronunciationList.innerHTML = entries
    .map(
      ([source, reading]) => `
        <span class="pronunciation-chip">
          <b>${escapeHtml(source)}</b><i>→</i>${escapeHtml(reading)}
          <button type="button" data-source="${escapeAttribute(source)}" aria-label="删除 ${escapeAttribute(source)} 的发音纠正">×</button>
        </span>
      `,
    )
    .join("");
  for (const button of elements.pronunciationList.querySelectorAll("button")) {
    button.addEventListener("click", () => {
      delete state.analysis.pronunciations[button.dataset.source];
      renderPronunciations();
      scheduleDraftSave();
      scheduleRenderPlan();
      showMessage("已删除这条全书发音规则。", true);
    });
  }
}

function openPronunciationEditor(segmentIndex = null, selectedText = "") {
  state.pronunciationSegmentIndex = segmentIndex;
  elements.pronunciationForm.hidden = false;
  elements.pronunciationSource.value = selectedText.trim().slice(0, 32);
  elements.pronunciationReading.value = "";
  elements.pronunciationHint.textContent =
    segmentIndex === null
      ? "保存后会应用到这本书的所有句子，原文显示不变。"
      : `正在纠正第 ${segmentIndex + 1} 句；保存后同一个词在全书都会照着读。`;
  elements.pronunciationSource.focus();
}

function closePronunciationEditor() {
  state.pronunciationSegmentIndex = null;
  if (!elements.pronunciationForm) return;
  elements.pronunciationForm.hidden = true;
  elements.pronunciationForm.reset();
}

function savePronunciation(event) {
  event.preventDefault();
  if (!state.analysis) return;
  const source = elements.pronunciationSource.value.trim();
  const reading = elements.pronunciationReading.value.trim();
  if (!source || !reading) {
    showMessage("请同时填写原文里的字词和希望朗读的写法。");
    return;
  }
  if (source === reading) {
    showMessage("两种写法相同，不需要保存发音纠正。");
    return;
  }
  if (
    !(source in state.analysis.pronunciations) &&
    Object.keys(state.analysis.pronunciations).length >= 100
  ) {
    showMessage("这本书最多保存 100 条发音规则，请先删除不再需要的规则。");
    return;
  }
  state.analysis.pronunciations[source] = reading;
  closePronunciationEditor();
  renderPronunciations();
  scheduleDraftSave();
  scheduleRenderPlan();
  showMessage(`已记住：“${source}”在全书读成“${reading}”。`, true);
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
    row.dataset.segmentIndex = String(index);
    row.classList.toggle("is-playing", state.activeSegmentIndex === index);
    const confidenceClass = confidenceLevel(segment.confidence);
    row.innerHTML = `
      <span class="segment-index">${String(index + 1).padStart(2, "0")}</span>
      <div class="script-row-body">
        <div class="script-row-head">
          <label class="speaker-field">
            <span>说话人</span>
            <select class="script-speaker" aria-label="第 ${index + 1} 句说话人">
              ${characterOptions}
            </select>
          </label>
          <div class="segment-meta">
            <label>
              <span>语气</span>
              ${buildSelect(labels.emotion, segment.emotion, "emotion-select")}
            </label>
            <i class="confidence-dot confidence-${confidenceClass}" title="${(
              segment.confidence * 100
            ).toFixed(0)}% 识别把握"></i>
            <b class="locked-badge" ${segment.locked ? "" : "hidden"}>已确认</b>
          </div>
        </div>
        <textarea class="script-text-input" rows="1"
          aria-label="第 ${index + 1} 句文本">${escapeHtml(segment.text)}</textarea>
        <div class="sentence-actions">
          <button class="sentence-button start-preview-button" type="button">▶ 从这里听</button>
          <button class="sentence-button wrong-speaker-button" type="button">角色错了</button>
          <button class="sentence-button pronunciation-button" type="button">这个字读错了</button>
          <button class="sentence-button segment-render-button" type="button">重做这句</button>
        </div>
      </div>
    `;
    const select = row.querySelector(".script-speaker");
    const textInput = row.querySelector(".script-text-input");
    const emotionSelect = row.querySelector(".emotion-select");
    const lockedBadge = row.querySelector(".locked-badge");
    select.value = segment.speaker_id;
    emotionSelect.value = segment.emotion;

    const lockSegment = () => {
      segment.locked = true;
      segment.confidence = 1;
      lockedBadge.hidden = false;
      const dot = row.querySelector(".confidence-dot");
      dot.className = "confidence-dot confidence-high";
      dot.title = "人工确认";
      scheduleDraftSave();
      scheduleRenderPlan();
    };
    select.addEventListener("change", () => {
      segment.speaker_id = select.value;
      row.classList.remove("needs-attention");
      lockSegment();
    });
    textInput.addEventListener("input", () => {
      segment.text = textInput.value.trim();
      autoResizeTextarea(textInput);
      recomputeSummary();
      lockSegment();
    });
    textInput.addEventListener("blur", () => {
      textInput.value = segment.text;
    });
    emotionSelect.addEventListener("change", () => {
      segment.emotion = emotionSelect.value;
      lockSegment();
    });
    row
      .querySelector(".start-preview-button")
      .addEventListener("click", () => startBrowserPreview(index));
    row
      .querySelector(".wrong-speaker-button")
      .addEventListener("click", () => {
        select.focus();
        row.classList.add("needs-attention");
        showMessage("请选择正确的说话人；保存后只需重做这一句。", true);
      });
    row
      .querySelector(".pronunciation-button")
      .addEventListener("click", () => {
        const selected = textInput.value.slice(
          textInput.selectionStart,
          textInput.selectionEnd,
        );
        openPronunciationEditor(index, selected);
        elements.pronunciationPanel.scrollIntoView({
          behavior: "smooth",
          block: "center",
        });
      });
    row
      .querySelector(".segment-render-button")
      .addEventListener("click", () => renderSingleSegment(index));
    elements.scriptTimeline.appendChild(row);
    autoResizeTextarea(textInput);
  }
  updateActionAvailability();
}

function autoResizeTextarea(textarea) {
  textarea.style.height = "auto";
  textarea.style.height = `${Math.min(180, textarea.scrollHeight)}px`;
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

function previewCharacterVoice(characterId) {
  const index = state.analysis.segments.findIndex(
    (segment) => segment.speaker_id === characterId,
  );
  if (index < 0) {
    showMessage("这个角色目前没有台词可供试听。");
    return;
  }
  startBrowserPreview(index, index + 1);
}

function applyPronunciationsToText(text) {
  const entries = Object.entries(state.analysis?.pronunciations || {}).sort(
    ([first], [second]) => second.length - first.length,
  );
  if (!entries.length) return text;
  const readings = Object.fromEntries(entries);
  const pattern = entries
    .map(([source]) => source.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .join("|");
  return text.replace(new RegExp(pattern, "gu"), (source) => readings[source]);
}

function setActiveSegment(index) {
  state.activeSegmentIndex = index;
  for (const row of elements.scriptTimeline.querySelectorAll(".script-row")) {
    row.classList.toggle(
      "is-playing",
      Number(row.dataset.segmentIndex) === index,
    );
  }
  const segment = state.analysis.segments[index];
  const character = state.analysis.characters.find(
    (candidate) => candidate.id === segment?.speaker_id,
  );
  if (!segment) return;
  elements.nowPlaying.innerHTML = `
    <span class="now-playing-dot"></span>
    <b>正在播放 · ${escapeHtml(character?.name || "待确认角色")}</b>
    <small>${escapeHtml(segment.text.slice(0, 46))}${segment.text.length > 46 ? "…" : ""}</small>
  `;
}

async function startBrowserPreview(startIndex = 0, endIndex = null) {
  if (state.analysisStale) {
    showMessage("原文已经变更，请重新分析后再试听。");
    return;
  }
  if (!state.analysis || !("speechSynthesis" in window)) {
    showMessage("当前浏览器不支持 Web Speech 试听，请使用 Chrome 或 Safari。");
    return;
  }
  stopBrowserPreview();
  state.isSpeaking = true;
  const session = state.speechSession;
  updateActionAvailability();
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
  let index = Math.max(
    0,
    Math.min(startIndex, state.analysis.segments.length - 1),
  );
  const stopIndex =
    endIndex === null
      ? state.analysis.segments.length
      : Math.max(index + 1, Math.min(endIndex, state.analysis.segments.length));

  const speakNext = () => {
    if (!state.isSpeaking || session !== state.speechSession) {
      return;
    }
    if (index >= stopIndex) {
      stopBrowserPreview(true);
      return;
    }
    const segmentIndex = index++;
    const segment = state.analysis.segments[segmentIndex];
    const character = characters.get(segment.speaker_id);
    const preset = voicePresets.get(character?.voice_id);
    const utterance = new SpeechSynthesisUtterance(
      applyPronunciationsToText(segment.text),
    );
    setActiveSegment(segmentIndex);
    utterance.lang = "zh-CN";
    utterance.rate =
      (preset?.browser_rate || 1) * Number(elements.previewSpeed.value || 1);
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

function stopBrowserPreview(finished = false) {
  state.speechSession += 1;
  state.isSpeaking = false;
  state.activeSegmentIndex = null;
  if ("speechSynthesis" in window) {
    window.speechSynthesis.cancel();
  }
  if (elements.scriptTimeline) {
    for (const row of elements.scriptTimeline.querySelectorAll(".script-row")) {
      row.classList.remove("is-playing");
    }
  }
  if (elements.nowPlaying) {
    elements.nowPlaying.innerHTML = `
      <span class="now-playing-dot"></span>
      <b>${finished ? "本次试听已结束" : "尚未开始播放"}</b>
      <small>点击任意一句的“从这里听”也可以开始</small>
    `;
  }
  if (elements.playButton) updateActionAvailability();
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

function scheduleRenderPlan(provider = state.lastProvider) {
  window.clearTimeout(state.planTimer);
  state.planTimer = window.setTimeout(
    () => refreshRenderPlan(provider, false),
    500,
  );
}

async function refreshRenderPlan(provider = state.lastProvider, showErrors = false) {
  if (!state.analysis || state.analysisStale) return null;
  state.lastProvider = provider;
  if (showErrors) setBusy(elements.refreshPlanButton, true, "正在估算…");
  try {
    const plan = await requestJson("/api/render/plan", {
      method: "POST",
      body: JSON.stringify({ analysis: state.analysis, provider }),
    });
    applyRenderPlan(plan);
    return plan;
  } catch (error) {
    if (showErrors) showMessage(error.message);
    return null;
  } finally {
    if (showErrors) setBusy(elements.refreshPlanButton, false, "重新计算");
  }
}

function applyRenderPlan(plan) {
  const isHighQuality = plan.provider === "dashscope";
  const ready = isHighQuality ? Number(plan.cached_segments) : 0;
  const remaining = isHighQuality
    ? Number(plan.estimated_requests)
    : Number(plan.segments);
  const remainingCharacters = isHighQuality
    ? Number(plan.estimated_billable_characters)
    : Number(plan.billable_characters);
  const cost =
    !isHighQuality ||
    plan.estimated_cost_cny === null ||
    plan.estimated_cost_cny === undefined
      ? ""
      : `<span><strong>约 ¥${Number(plan.estimated_cost_cny).toFixed(4)}</strong> 预计费用</span>`;
  const note =
    isHighQuality
      ? remaining
        ? `已有 ${ready} 句准备好；实际费用以最终账单为准。`
        : "所有句子都已准备好，再次生成不会重复制作声音。"
      : "现在可以先免费试听；连接高品质语音服务后即可生成可下载成片。";
  elements.renderPlan.innerHTML = `
    <span><strong>${Number(plan.segments).toLocaleString()}</strong> 句朗读内容</span>
    <span><strong>${remainingCharacters.toLocaleString()}</strong> 字待生成</span>
    <span><strong>${ready.toLocaleString()}</strong> 句已准备</span>
    ${cost}
    <small>${escapeHtml(note)}</small>
  `;
}

function singleSegmentAnalysis(index) {
  return {
    ...state.analysis,
    segments: [state.analysis.segments[index]],
  };
}

async function renderSingleSegment(index) {
  if (!state.analysis || state.analysisStale) {
    showMessage("请先重新识别角色，再修改这句话。");
    return;
  }
  if (!state.config?.providers?.dashscope?.ready) {
    startBrowserPreview(index, index + 1);
    showMessage(
      "高品质语音服务尚未连接，已先用设备声音试听这句；连接后同一按钮会只重新生成这一句。",
      true,
    );
    return;
  }
  const segment = state.analysis.segments[index];
  const row = elements.scriptTimeline.querySelector(
    `.script-row[data-segment-index="${index}"]`,
  );
  const button = row?.querySelector(".segment-render-button");
  if (!segment?.text.trim() || !button) return;

  state.isRendering = true;
  updateActionAvailability();
  setBusy(button, true, "正在重做…");
  hideMessage();
  try {
    const analysis = singleSegmentAnalysis(index);
    const plan = await requestJson("/api/render/plan", {
      method: "POST",
      body: JSON.stringify({ analysis, provider: "dashscope" }),
    });
    if (Number(plan.estimated_requests) > 0) {
      const cost =
        plan.estimated_cost_cny === null ||
        plan.estimated_cost_cny === undefined
          ? "当前未显示单价"
          : `预计约 ¥${Number(plan.estimated_cost_cny).toFixed(4)}`;
      if (
        !window.confirm(
          `只重新生成第 ${index + 1} 句，共约 ` +
            `${plan.estimated_billable_characters} 个字，${cost}。确认继续吗？`,
        )
      ) {
        return;
      }
    }
    const result = await requestJson("/api/render/segment", {
      method: "POST",
      body: JSON.stringify({
        analysis: state.analysis,
        segment_id: segment.id,
        provider: "dashscope",
        confirm_cost: true,
      }),
    });
    if (result.status !== "completed" || !result.audio_url) {
      throw new Error("这句话暂时没有生成成功，请稍后再试。");
    }
    const character = state.analysis.characters.find(
      (candidate) => candidate.id === segment.speaker_id,
    );
    elements.audioResult.hidden = false;
    elements.resultAudio.src = result.audio_url;
    elements.downloadLink.href = result.audio_url;
    elements.downloadLink.textContent = "下载本句 WAV ↓";
    elements.wavDownloadLink.hidden = true;
    elements.audioTitle.textContent =
      `${character?.name || "待确认角色"} · 第 ${index + 1} 句已重做`;
    elements.audioMeta.textContent =
      result.cache_hits > 0
        ? "直接使用了已准备好的版本"
        : "只生成了这一句；下次生成全书时会直接复用";
    elements.resultAudio.play().catch(() => {});
    elements.audioResult.scrollIntoView({ behavior: "smooth", block: "center" });
    showMessage("这句话已重新生成，其他句子没有重复处理。", true);
    scheduleRenderPlan("dashscope");
  } catch (error) {
    showMessage(error.message);
  } finally {
    state.isRendering = false;
    setBusy(button, false, "重做这句");
    updateActionAvailability();
  }
}

async function renderAudio(provider, isRetry = false) {
  if (!state.analysis) return;
  if (state.analysisStale) {
    showMessage("原文已经变更，请重新分析后再生成。");
    return;
  }
  const emptySegment = state.analysis.segments.find((segment) => !segment.text.trim());
  if (emptySegment) {
    showMessage(`${emptySegment.id} 的文本为空，请补充内容后再生成。`);
    return;
  }

  state.lastProvider = provider;
  state.isRendering = true;
  updateActionAvailability();
  hideMessage();
  const activeButton =
    provider === "dashscope"
      ? elements.dashscopeRenderButton
      : elements.demoRenderButton;
  setBusy(
    activeButton,
    true,
    isRetry
      ? "正在继续未完成内容…"
      : provider === "dashscope"
        ? "正在生成多人朗读…"
        : "正在检查链路…",
  );

  try {
    const plan = await refreshRenderPlan(provider, false);
    if (!plan) throw new Error("暂时无法估算本次生成内容，请稍后重试。");
    if (provider === "dashscope") {
      const cost =
        plan.estimated_cost_cny === null ||
        plan.estimated_cost_cny === undefined
          ? "当前未配置单价"
          : `估算约 ¥${Number(plan.estimated_cost_cny).toFixed(4)}`;
      const confirmed = window.confirm(
        `将生成 ${plan.estimated_requests} 句新内容，` +
          `约 ${plan.estimated_billable_characters} 个字，${cost}。` +
          `实际费用以最终账单为准。确认继续吗？`,
      );
      if (!confirmed) return;
    }

    const result = await requestJson("/api/render", {
      method: "POST",
      body: JSON.stringify({
        analysis: state.analysis,
        provider,
        format: elements.outputFormat.value,
        confirm_cost: provider === "dashscope",
      }),
    });

    if (result.status === "partial") {
      elements.audioResult.hidden = true;
      elements.retryRenderButton.hidden = false;
      const failed = result.failed_segments
        .map((item) => item.segment_id)
        .join("、");
      showMessage(
        `${result.failed_segments.length} 句话暂未完成（${failed}）。` +
          `已经完成的内容会保留；点击“继续完成未生成的句子”即可。`,
      );
    } else {
      elements.retryRenderButton.hidden = true;
      elements.audioResult.hidden = false;
      elements.resultAudio.src = result.audio_url;
      elements.downloadLink.href = result.audio_url;
      elements.downloadLink.textContent =
        `下载 ${result.format.toUpperCase()} ↓`;
      elements.audioTitle.textContent =
        provider === "demo" ? "离线链路检查已完成" : "多人有声书已生成";
      elements.audioMeta.textContent =
        `${result.segment_count} 句 · ${result.total_characters} 字 · ` +
        `${result.cache_hits} 句直接复用 · ${result.synthesized_segments} 句新生成`;
      elements.wavDownloadLink.hidden =
        result.format !== "mp3" || !result.wav_url;
      if (!elements.wavDownloadLink.hidden) {
        elements.wavDownloadLink.href = result.wav_url;
      }
      elements.audioResult.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
      if (provider === "dashscope") {
        elements.resultAudio.play().catch(() => {});
      }
      showMessage(
        result.cache_hits
          ? `生成完成，其中 ${result.cache_hits} 句话无需重复处理。`
          : "生成完成。",
        true,
      );
    }
    scheduleRenderPlan(provider);
  } catch (error) {
    showMessage(error.message);
  } finally {
    state.isRendering = false;
    setBusy(
      activeButton,
      false,
      provider === "dashscope" ? "开始生成" : "运行离线链路检查",
    );
    updateActionAvailability();
  }
}

function updateActionAvailability() {
  if (!elements.playButton) return;
  const unavailable =
    !state.analysis || state.analysisStale || state.isRendering;
  elements.playButton.disabled = unavailable || state.isSpeaking;
  elements.stopButton.disabled = !state.isSpeaking;
  elements.previewSpeed.disabled = state.isRendering;
  elements.demoRenderButton.disabled = unavailable;
  elements.refreshPlanButton.disabled = unavailable;
  elements.dashscopeRenderButton.disabled =
    unavailable || !state.config?.providers?.dashscope?.ready;
  elements.addPronunciationButton.disabled =
    !state.analysis || state.isRendering;
  for (const button of elements.scriptTimeline.querySelectorAll(
    ".sentence-button",
  )) {
    button.disabled = unavailable || state.isSpeaking;
  }
  if (!elements.retryRenderButton.hidden) {
    elements.retryRenderButton.disabled = unavailable;
  }
}

function scheduleDraftSave() {
  window.clearTimeout(state.draftTimer);
  elements.draftStatus.textContent = "正在保存本机草稿…";
  state.draftTimer = window.setTimeout(saveDraft, 450);
}

function saveDraft() {
  const text = elements.sourceText.value;
  if (!text && !state.analysis) {
    window.localStorage.removeItem(DRAFT_KEY);
    elements.draftStatus.textContent = "本机草稿尚未保存";
    return;
  }
  const savedAt = new Date().toISOString();
  const project = {
    version: DRAFT_VERSION,
    source_text: text,
    source_file: state.sourceFile,
    analyzer_mode: elements.analyzerMode.value,
    output_format: elements.outputFormat.value,
    preview_speed: elements.previewSpeed.value,
    analysis_source_text: state.analysisSourceText,
    analysis: state.analysis,
    saved_at: savedAt,
  };
  try {
    window.localStorage.setItem(DRAFT_KEY, JSON.stringify(project));
    elements.draftStatus.textContent =
      `本机草稿已保存 ${new Date(savedAt).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      })}`;
  } catch {
    elements.draftStatus.textContent = "本机存储空间不足，草稿未保存";
  }
}

function restoreDraft() {
  const raw = window.localStorage.getItem(DRAFT_KEY);
  if (!raw) return;
  try {
    const project = JSON.parse(raw);
    if (!project || typeof project.source_text !== "string") return;
    elements.sourceText.value = project.source_text;
    state.sourceFile = project.source_file || null;
    if (state.sourceFile) {
      elements.fileMeta.textContent =
        `${state.sourceFile.name} · ${state.sourceFile.encoding}`;
    }
    if (
      project.analyzer_mode &&
      [...elements.analyzerMode.options].some(
        (option) => option.value === project.analyzer_mode,
      )
    ) {
      elements.analyzerMode.value = project.analyzer_mode;
    }
    if (
      project.output_format &&
      [...elements.outputFormat.options].some(
        (option) =>
          option.value === project.output_format && !option.disabled,
      )
    ) {
      elements.outputFormat.value = project.output_format;
    }
    if (
      project.preview_speed &&
      [...elements.previewSpeed.options].some(
        (option) => option.value === project.preview_speed,
      )
    ) {
      elements.previewSpeed.value = project.preview_speed;
    }
    if (project.analysis) {
      state.analysis = normalizeAnalysis(project.analysis);
      state.analysisSourceText = project.analysis_source_text || "";
      state.analysisStale =
        elements.sourceText.value.trim() !== state.analysisSourceText;
      renderAnalysis();
      elements.resultSection.hidden = false;
      scheduleRenderPlan();
    }
    const saved = project.saved_at ? new Date(project.saved_at) : null;
    elements.draftStatus.textContent =
      saved && !Number.isNaN(saved.valueOf())
        ? `已恢复 ${saved.toLocaleString()} 的本机草稿`
        : "已恢复本机草稿";
    showMessage("已恢复上次保存在这台浏览器中的项目草稿。", true);
  } catch {
    window.localStorage.removeItem(DRAFT_KEY);
  }
}

function clearSavedDraft() {
  window.localStorage.removeItem(DRAFT_KEY);
  elements.draftStatus.textContent = "保存副本已删除；当前页面内容仍保留";
  showMessage("已删除这台浏览器中的保存副本，当前页面内容没有变化。", true);
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

function uniqueValues(values) {
  return [...new Set(values.filter(Boolean))];
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

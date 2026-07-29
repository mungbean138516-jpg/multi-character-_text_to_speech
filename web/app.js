"use strict";

const DRAFT_KEY = "voxcast.project.v2";
const DRAFT_VERSION = 5;
const DRAFT_DATABASE = "voxcast-local-projects";
const DRAFT_STORE = "drafts";
const DRAFT_RECORD = "active";
const BOOK_SCHEMA = "voxcast-book-project";
const BOOK_VERSION = 1;
const MAX_TEXT_FILE_BYTES = 2_000_000;
const MAX_PROJECT_FILE_BYTES = 12_000_000;
const ACTIVE_RENDER_JOB_STATUSES = new Set([
  "queued",
  "running",
  "pausing",
]);

const DEMO_TEXT = `雨敲在旧车站的玻璃顶上。林夏抱紧书包，望向站台尽头。

“你真的要一个人去北城？”陈默低声问。

林夏笑了笑：“总得有人把信送到。”

“可外面在下暴雨！”陈默喊道。

长椅旁的老奶奶抬起头，平静地说道：“年轻人，怕的从来不是雨，是不知道为什么出发。”

一个小女孩从售票窗后探出脑袋，兴奋地叫道：“火车来啦！”

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
  lastProvider: null,
  speechSession: 0,
  activeSegmentIndex: null,
  pronunciationSegmentIndex: null,
  sourceFile: null,
  draftTimer: null,
  planTimer: null,
  renderPollTimer: null,
  renderJob: null,
  renderJobIds: {},
  progressiveIndex: -1,
  progressiveJobId: null,
  waitingForProgressiveSegment: false,
  book: null,
  characterRegistry: emptyCharacterRegistry(),
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
    "bookPanel",
    "bookTitle",
    "bookAuthor",
    "chapterSelect",
    "previousChapterButton",
    "nextChapterButton",
    "chapterProgress",
    "registryCount",
    "importProjectButton",
    "projectFileInput",
    "exportProjectButton",
    "fileMeta",
    "draftStatus",
    "clearDraftButton",
    "analyzeButton",
    "messageBox",
    "resultSection",
    "analysisSummary",
    "warningList",
    "characterGrid",
    "consistencyButton",
    "directorButton",
    "consistencyResults",
    "resetEmotionButton",
    "emotionCurve",
    "emotionEditor",
    "voiceSamples",
    "compareVoicesButton",
    "voiceSimilarityResults",
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
    "localRenderButton",
    "dashscopeRenderButton",
    "renderJobPanel",
    "renderJobStatus",
    "renderProgress",
    "renderProgressLabel",
    "playableCount",
    "progressiveAudio",
    "playReadyButton",
    "pauseJobButton",
    "resumeJobButton",
    "progressiveNowPlaying",
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
    if (file) importSourceFile(file);
    elements.fileInput.value = "";
  });
  elements.importProjectButton.addEventListener("click", () =>
    elements.projectFileInput.click(),
  );
  elements.projectFileInput.addEventListener("change", () => {
    const [file] = elements.projectFileInput.files;
    if (file) importProjectFile(file);
    elements.projectFileInput.value = "";
  });
  elements.exportProjectButton.addEventListener("click", exportProjectFile);
  elements.chapterSelect.addEventListener("change", () =>
    switchChapter(elements.chapterSelect.value),
  );
  elements.previousChapterButton.addEventListener("click", () =>
    moveChapter(-1),
  );
  elements.nextChapterButton.addEventListener("click", () => moveChapter(1));
  elements.clearDraftButton.addEventListener("click", clearSavedDraft);
  elements.analyzeButton.addEventListener("click", analyzeText);
  elements.consistencyButton.addEventListener("click", runConsistencyCheck);
  elements.directorButton.addEventListener("click", applyRuleDirector);
  elements.resetEmotionButton.addEventListener("click", resetEmotionCurve);
  elements.compareVoicesButton.addEventListener("click", compareVoiceSamples);
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
  elements.localRenderButton.addEventListener("click", () =>
    renderAudio("local"),
  );
  elements.dashscopeRenderButton.addEventListener("click", () =>
    renderAudio("dashscope"),
  );
  elements.playReadyButton.addEventListener("click", () =>
    startProgressivePlayback(0),
  );
  elements.progressiveAudio.addEventListener(
    "ended",
    playNextProgressiveSegment,
  );
  elements.pauseJobButton.addEventListener("click", pauseRenderJob);
  elements.resumeJobButton.addEventListener("click", resumeRenderJob);
  window.addEventListener("beforeunload", () => {
    window.clearTimeout(state.renderPollTimer);
    stopBrowserPreview();
  });

  await loadConfig();
  await restoreDraft();
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
      : state.config.providers?.local?.ready
        ? "local"
        : null;
    updateProviderNotice();
  } catch (error) {
    elements.systemStatus.lastChild.textContent = " 服务未连接";
    showMessage(error.message);
  }
}

function updateProviderNotice() {
  const dashscopeReady = Boolean(state.config?.providers?.dashscope?.ready);
  const localReady = Boolean(state.config?.providers?.local?.ready);
  elements.providerNotice.textContent = dashscopeReady
    ? localReady
      ? "高品质语音与 Mac 免费本地语音均已就绪，可任选一种生成。"
      : "高品质语音服务已就绪，生成前会先显示预计内容和费用。"
    : localReady
      ? "已启用 Mac 免费本地中文语音：生成的是实际朗读，不再是测试音。"
      : "现在可用设备声音自然试听；生成可下载音频需要 Mac 中文系统声音或 CosyVoice。";
  elements.localRenderButton.hidden = !localReady;
  const label = elements.dashscopeRenderButton.querySelector("span");
  if (label) {
    label.textContent = dashscopeReady ? "开始生成" : "高品质语音待连接";
  }
  elements.localRenderButton.classList.toggle("primary-button", !dashscopeReady);
  elements.localRenderButton.classList.toggle("secondary-button", dashscopeReady);
}

function loadDemo() {
  resetAllRenderJobs();
  state.book = null;
  state.characterRegistry = emptyCharacterRegistry();
  renderBookNavigation();
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
  importSourceFile(file);
}

function importSourceFile(file) {
  const lowerName = file.name.toLowerCase();
  if (
    lowerName.endsWith(".epub") ||
    file.type === "application/epub+zip"
  ) {
    importEpubFile(file);
    return;
  }
  if (lowerName.endsWith(".pdf") || lowerName.endsWith(".docx")) {
    importDocumentFile(file);
    return;
  }
  importTextFile(file);
}

async function importDocumentFile(file) {
  hideMessage();
  const maxBytes = state.config?.limits?.document_bytes ?? 20_000_000;
  if (file.size > maxBytes) {
    showMessage(`文档过大；当前最多 ${(maxBytes / 1_000_000).toFixed(0)} MB。`);
    return;
  }
  setBusy(elements.importFileButton, true, "正在提取正文…");
  try {
    const project = await requestJson("/api/import/document", {
      method: "POST",
      headers: {
        "Content-Type": "application/octet-stream",
        "X-VoxCast-Filename": encodeURIComponent(file.name),
      },
      body: await file.arrayBuffer(),
    });
    openBookProject(
      project,
      { name: file.name, encoding: file.name.toLowerCase().endsWith(".pdf") ? "PDF" : "DOCX" },
      `已导入《${project.title}》，整理出 ${project.chapters.length} 个章节。`,
    );
  } catch (error) {
    showMessage(error.message);
  } finally {
    setBusy(elements.importFileButton, false, "导入文档");
  }
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
    resetAllRenderJobs();
    state.book = null;
    state.characterRegistry = emptyCharacterRegistry();
    renderBookNavigation();
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

async function importEpubFile(file) {
  hideMessage();
  const maxBytes = state.config?.limits?.epub_bytes ?? 20_000_000;
  if (!file.name.toLowerCase().endsWith(".epub")) {
    showMessage("请选择扩展名为 .epub 的书籍文件。");
    return;
  }
  if (file.size > maxBytes) {
    showMessage(
      `EPUB 文件过大；当前最多 ${(maxBytes / 1_000_000).toFixed(0)} MB。`,
    );
    return;
  }
  setBusy(elements.importFileButton, true, "正在整理章节…");
  try {
    const project = await requestJson("/api/import/epub", {
      method: "POST",
      headers: {
        "Content-Type": "application/epub+zip",
        "X-VoxCast-Filename": encodeURIComponent(file.name),
      },
      body: await file.arrayBuffer(),
    });
    openBookProject(
      project,
      { name: file.name, encoding: "EPUB" },
      `已导入《${project.title}》，共 ${project.chapters.length} 个可朗读章节。`,
    );
  } catch (error) {
    showMessage(error.message);
  } finally {
    setBusy(elements.importFileButton, false, "导入 TXT / EPUB");
  }
}

async function importProjectFile(file) {
  hideMessage();
  if (file.size > MAX_PROJECT_FILE_BYTES) {
    showMessage("项目备份过大；当前最多 12 MB。");
    return;
  }
  setBusy(elements.importProjectButton, true, "正在打开…");
  try {
    const project = JSON.parse(await file.text());
    openBookProject(
      project,
      { name: file.name, encoding: "声场项目" },
      `已打开《${project.title || "未命名书籍"}》的项目备份。`,
    );
  } catch (error) {
    showMessage(
      error instanceof SyntaxError
        ? "项目文件不是有效的 JSON。"
        : error.message,
    );
  } finally {
    setBusy(elements.importProjectButton, false, "打开书籍项目");
  }
}

function openBookProject(project, sourceFile, successMessage) {
  const normalized = normalizeBookProject(project);
  resetAllRenderJobs();
  stopBrowserPreview();
  resetAnalysis();
  state.book = normalized;
  state.characterRegistry = normalizeCharacterRegistry(
    normalized.character_registry,
  );
  state.sourceFile = sourceFile || {
    name: normalized.source_name || `${normalized.title}.voxcast.json`,
    encoding: "声场项目",
  };
  loadChapter(normalized.selected_chapter_id, false);
  renderBookNavigation();
  scheduleDraftSave();
  const warning = normalized.warnings?.[0];
  showMessage(
    warning ? `${successMessage} ${warning}` : successMessage,
    true,
  );
}

function normalizeBookProject(project) {
  if (!project || project.schema !== BOOK_SCHEMA) {
    throw new Error("这不是声场书籍项目文件。");
  }
  if (Number(project.version) !== BOOK_VERSION) {
    throw new Error("暂不支持这个版本的声场项目文件。");
  }
  if (!Array.isArray(project.chapters) || !project.chapters.length) {
    throw new Error("项目里没有可朗读章节。");
  }
  if (project.chapters.length > 500) {
    throw new Error("项目章节过多；当前最多保存 500 章。");
  }
  const seen = new Set();
  let totalCharacters = 0;
  const chapters = project.chapters.map((chapter, index) => {
    if (!chapter || typeof chapter.text !== "string") {
      throw new Error(`第 ${index + 1} 章缺少正文。`);
    }
    const id = String(chapter.id || `chapter_${index + 1}`);
    if (seen.has(id)) throw new Error("项目包含重复的章节。");
    seen.add(id);
    const text = chapter.text.replace(/\r\n?/g, "\n").trim();
    if (!text) throw new Error(`第 ${index + 1} 章没有可朗读文字。`);
    if ([...text].length > 50_000) {
      throw new Error(`“${chapter.title || `第 ${index + 1} 章`}”过长，请重新导入原 EPUB。`);
    }
    totalCharacters += [...text].length;
    return {
      id,
      title: String(chapter.title || `第 ${index + 1} 章`).trim(),
      text,
      source_path: String(chapter.source_path || ""),
      analysis: chapter.analysis
        ? normalizeAnalysis(deepCopy(chapter.analysis))
        : null,
    };
  });
  if (totalCharacters > 5_000_000) {
    throw new Error("整本书超过 500 万字，暂不支持导入。");
  }
  const pronunciations = normalizePronunciations(project.pronunciations);
  for (const chapter of chapters) {
    if (chapter.analysis) {
      chapter.analysis.pronunciations = { ...pronunciations };
    }
  }
  const selected = seen.has(String(project.selected_chapter_id))
    ? String(project.selected_chapter_id)
    : chapters[0].id;
  return {
    schema: BOOK_SCHEMA,
    version: BOOK_VERSION,
    title: String(project.title || "未命名书籍").trim(),
    author: String(project.author || "").trim(),
    source_name: String(project.source_name || ""),
    source_type: String(project.source_type || "project"),
    selected_chapter_id: selected,
    chapters,
    character_registry: normalizeCharacterRegistry(
      project.character_registry,
    ),
    pronunciations,
    warnings: Array.isArray(project.warnings)
      ? project.warnings.map(String).filter(Boolean)
      : [],
  };
}

function normalizeCharacterRegistry(value) {
  const limit = Math.max(
    1,
    Math.min(
      10,
      Number(value?.primary_limit) ||
        state.config?.limits?.primary_characters ||
        10,
    ),
  );
  const normalizedCharacters = Array.isArray(value?.characters)
    ? value.characters
        .filter(
          (character) =>
            character &&
            typeof character.id === "string" &&
            typeof character.name === "string",
        )
        .map((character) => ({
          aliases: [],
          traits: [],
          evidence: [],
          locked: false,
          gender: "unknown",
          age_group: "unknown",
          voice_id: "",
          confidence: 0.5,
          ...deepCopy(character),
        }))
    : [];
  const characters = [];
  let primaryCount = 0;
  for (const character of normalizedCharacters) {
    if (!["narrator", "minor_characters"].includes(character.id)) {
      if (primaryCount >= limit) continue;
      primaryCount += 1;
    }
    if (!characters.some((item) => item.id === character.id)) {
      characters.push(character);
    }
  }
  return {
    characters,
    dialogue_counts:
      value?.dialogue_counts && typeof value.dialogue_counts === "object"
        ? { ...value.dialogue_counts }
        : {},
    minor_character_names: Array.isArray(value?.minor_character_names)
      ? [...new Set(value.minor_character_names.map(String).filter(Boolean))]
      : [],
    primary_limit: limit,
    primary_count: primaryCount,
  };
}

function emptyCharacterRegistry() {
  return {
    characters: [],
    dialogue_counts: {},
    minor_character_names: [],
    primary_limit: 10,
    primary_count: 0,
  };
}

function normalizePronunciations(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(
    Object.entries(value)
      .map(([source, reading]) => [String(source).trim(), String(reading).trim()])
      .filter(
        ([source, reading]) =>
          source &&
          reading &&
          source !== reading &&
          [...source].length <= 32 &&
          [...reading].length <= 64,
      )
      .slice(0, 100),
  );
}

function currentChapter() {
  if (!state.book) return null;
  return (
    state.book.chapters.find(
      (chapter) => chapter.id === state.book.selected_chapter_id,
    ) || null
  );
}

function renderContextKey() {
  return state.book
    ? `chapter:${state.book.selected_chapter_id}`
    : "standalone";
}

function normalizeRenderJobIds(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(
    Object.entries(value)
      .map(([key, jobId]) => [String(key), String(jobId)])
      .filter(
        ([key, jobId]) =>
          key.length <= 160 && /^[a-f0-9]{12}$/.test(jobId),
      )
      .slice(0, 500),
  );
}

function resetRenderJobView() {
  window.clearTimeout(state.renderPollTimer);
  state.renderPollTimer = null;
  state.renderJob = null;
  resetProgressivePlayer();
  if (elements.renderJobPanel) {
    elements.renderJobPanel.hidden = true;
    elements.renderJobPanel.removeAttribute("data-status");
  }
}

function resetAllRenderJobs() {
  state.renderJobIds = {};
  resetRenderJobView();
}

function saveCurrentChapter() {
  const chapter = currentChapter();
  if (!chapter) return;
  chapter.text = elements.sourceText.value;
  chapter.analysis =
    state.analysis && !state.analysisStale ? deepCopy(state.analysis) : null;
  if (state.analysis) {
    state.book.pronunciations = {
      ...state.analysis.pronunciations,
    };
  }
  state.book.character_registry = deepCopy(state.characterRegistry);
}

function loadChapter(chapterId, saveCurrent = true) {
  if (!state.book) return;
  if (saveCurrent) saveCurrentChapter();
  const chapter = state.book.chapters.find((item) => item.id === chapterId);
  if (!chapter) return;
  stopBrowserPreview();
  state.book.selected_chapter_id = chapter.id;
  elements.sourceText.value = chapter.text;
  elements.fileMeta.textContent =
    `${state.book.source_name || state.sourceFile?.name || "书籍项目"} · ${chapter.title} · ${[...chapter.text].length.toLocaleString()} 字`;
  resetAnalysis();
  if (chapter.analysis) {
    state.analysis = normalizeAnalysis(deepCopy(chapter.analysis));
    state.analysis.pronunciations = {
      ...state.book.pronunciations,
    };
    applyRegistryProfiles(state.analysis);
    state.analysisSourceText = chapter.text.trim();
    state.analysisStale = false;
    renderAnalysis();
    elements.resultSection.hidden = false;
    scheduleRenderPlan();
  }
  renderBookNavigation();
  updateCounter();
  updateActionAvailability();
  if (saveCurrent) scheduleDraftSave();
}

function switchChapter(chapterId) {
  if (state.isRendering) {
    showMessage("当前正在生成声音，请完成后再切换章节。");
    elements.chapterSelect.value = state.book.selected_chapter_id;
    return;
  }
  loadChapter(chapterId);
  void restoreRenderJobForCurrentContext();
  showMessage(`已切换到“${currentChapter().title}”。`, true);
}

function moveChapter(offset) {
  if (!state.book) return;
  const index = state.book.chapters.findIndex(
    (chapter) => chapter.id === state.book.selected_chapter_id,
  );
  const target = Math.max(
    0,
    Math.min(state.book.chapters.length - 1, index + offset),
  );
  if (target !== index) switchChapter(state.book.chapters[target].id);
}

function renderBookNavigation() {
  elements.bookPanel.hidden = !state.book;
  if (!state.book) return;
  const index = Math.max(
    0,
    state.book.chapters.findIndex(
      (chapter) => chapter.id === state.book.selected_chapter_id,
    ),
  );
  elements.bookTitle.textContent = state.book.title;
  elements.bookAuthor.textContent = state.book.author || "作者未知";
  elements.chapterSelect.innerHTML = "";
  for (const chapter of state.book.chapters) {
    const option = document.createElement("option");
    option.value = chapter.id;
    option.textContent = chapter.analysis
      ? `✓ ${chapter.title}`
      : chapter.title;
    elements.chapterSelect.appendChild(option);
  }
  elements.chapterSelect.value = state.book.selected_chapter_id;
  elements.chapterProgress.textContent =
    `${index + 1} / ${state.book.chapters.length}`;
  const primaryCount = state.characterRegistry.characters.filter(
    (character) =>
      !["narrator", "minor_characters"].includes(character.id),
  ).length;
  elements.registryCount.textContent =
    `主要角色 ${primaryCount} / ${state.characterRegistry.primary_limit}`;
  elements.previousChapterButton.disabled = index <= 0 || state.isRendering;
  elements.nextChapterButton.disabled =
    index >= state.book.chapters.length - 1 || state.isRendering;
  elements.chapterSelect.disabled = state.isRendering;
}

function applyRegistryProfiles(analysis) {
  const registryById = new Map(
    state.characterRegistry.characters.map((character) => [
      character.id,
      character,
    ]),
  );
  analysis.characters = analysis.characters.map((character) =>
    registryById.has(character.id)
      ? deepCopy(registryById.get(character.id))
      : character,
  );
  recomputeSummary(analysis);
}

function syncRegistryFromAnalysis(removedIds = []) {
  if (!state.analysis) return;
  const removed = new Set(removedIds);
  const byId = new Map(
    state.characterRegistry.characters
      .filter((character) => !removed.has(character.id))
      .map((character) => [character.id, character]),
  );
  for (const character of state.analysis.characters) {
    byId.set(character.id, deepCopy(character));
  }
  state.characterRegistry.characters = [...byId.values()];
  state.characterRegistry.primary_count =
    state.characterRegistry.characters.filter(
      (character) =>
        !["narrator", "minor_characters"].includes(character.id),
    ).length;
  if (state.book) {
    state.book.character_registry = deepCopy(state.characterRegistry);
    renderBookNavigation();
  }
}

function syncBookPronunciations() {
  if (!state.book || !state.analysis) return;
  state.book.pronunciations = { ...state.analysis.pronunciations };
  for (const chapter of state.book.chapters) {
    if (chapter.analysis) {
      chapter.analysis.pronunciations = { ...state.book.pronunciations };
    }
  }
}

function exportProjectFile() {
  hideMessage();
  const text = elements.sourceText.value.trim();
  if (!state.book && !text) {
    showMessage("请先粘贴或导入一本书，再下载项目备份。");
    return;
  }
  saveCurrentChapter();
  const project = state.book
    ? deepCopy(state.book)
    : {
        schema: BOOK_SCHEMA,
        version: BOOK_VERSION,
        title: (state.sourceFile?.name || "我的有声书").replace(/\.[^.]+$/, ""),
        author: "",
        source_name: state.sourceFile?.name || "",
        source_type: "txt",
        selected_chapter_id: "chapter_1",
        chapters: [
          {
            id: "chapter_1",
            title: "正文",
            text: elements.sourceText.value,
            source_path: "",
            analysis: state.analysis ? deepCopy(state.analysis) : null,
          },
        ],
        character_registry: deepCopy(state.characterRegistry),
        pronunciations: {
          ...(state.analysis?.pronunciations || {}),
        },
        warnings: [],
      };
  project.schema = BOOK_SCHEMA;
  project.version = BOOK_VERSION;
  project.character_registry = deepCopy(state.characterRegistry);
  const blob = new Blob([JSON.stringify(project, null, 2)], {
    type: "application/json;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  const safeTitle = String(project.title || "voxcast-book")
    .replace(/[\\/:*?"<>|]+/g, "-")
    .slice(0, 80);
  anchor.href = url;
  anchor.download = `${safeTitle}.voxcast.json`;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 500);
  showMessage("项目备份已下载；它包含章节、角色、纠错和发音记忆。", true);
}

function deepCopy(value) {
  return JSON.parse(JSON.stringify(value));
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
  const chapter = currentChapter();
  if (chapter) chapter.text = elements.sourceText.value;
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
  resetRenderJobView();
  state.analysis = null;
  state.analysisSourceText = "";
  state.analysisStale = false;
  elements.resultSection.hidden = true;
  elements.audioResult.hidden = true;
  elements.renderPlan.textContent =
    "完成角色识别后，这里会显示预计生成内容。";
  closePronunciationEditor();
  updateActionAvailability();
}

async function analyzeText() {
  const text = elements.sourceText.value.trim();
  if (!text) {
    showMessage("请先粘贴小说文本、导入 TXT / EPUB，或者载入演示文本。");
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
    const result = await requestJson("/api/analyze", {
        method: "POST",
        body: JSON.stringify({
          text,
          mode: elements.analyzerMode.value,
          character_registry: state.characterRegistry,
        }),
      });
    state.characterRegistry = normalizeCharacterRegistry(
      result.character_registry,
    );
    delete result.character_registry;
    state.analysis = normalizeAnalysis(result);
    state.analysis.pronunciations = {
      ...(state.book?.pronunciations || state.analysis.pronunciations),
    };
    state.analysisSourceText = text;
    state.analysisStale = false;
    syncRegistryFromAnalysis();
    saveCurrentChapter();
    renderBookNavigation();
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
  renderEmotionEditor();
  renderVoiceSamples();
  renderPronunciations();
  renderTimeline();
  elements.audioResult.hidden = true;
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
      syncRegistryFromAnalysis();
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

const EMOTION_AXES = {
  neutral: [0, 20, 50],
  happy: [70, 65, 60],
  sad: [-70, 30, 25],
  angry: [-60, 90, 75],
  excited: [45, 85, 65],
  questioning: [0, 40, 45],
  restrained_sadness: [-55, 35, 70],
  restrained: [-20, 25, 75],
};

async function runConsistencyCheck() {
  if (!state.book) {
    elements.consistencyResults.textContent = "当前是单篇文本；导入多章节书籍后才能执行全书扫描。";
    return;
  }
  saveCurrentChapter();
  const analyzed = state.book.chapters.filter((chapter) => chapter.analysis);
  if (analyzed.length < 2) {
    elements.consistencyResults.textContent = "至少需要先分析两个章节。";
    return;
  }
  setBusy(elements.consistencyButton, true, "扫描中…");
  try {
    const result = await requestJson("/api/consistency-check", {
      method: "POST",
      body: JSON.stringify({ chapters: analyzed }),
    });
    if (!result.issues.length) {
      elements.consistencyResults.innerHTML =
        `<div class="quality-ok">✓ 已检查 ${result.checked_chapters} 章、${result.checked_characters} 个角色，未发现特征漂移。</div>`;
      return;
    }
    elements.consistencyResults.innerHTML = result.issues.map((issue) => `
      <article class="quality-issue ${escapeAttribute(issue.severity)}">
        <strong>${escapeHtml(issue.message)}</strong>
        <span>${issue.variants.map((item) =>
          `${escapeHtml(item.value)}${item.chapters.length ? `（${item.chapters.map(escapeHtml).join("、")}）` : ""}`
        ).join(" ↔ ")}</span>
      </article>`).join("");
  } catch (error) {
    showMessage(error.message);
  } finally {
    setBusy(elements.consistencyButton, false, "扫描全书一致性");
  }
}

async function applyRuleDirector() {
  if (!state.analysis) return;
  setBusy(elements.directorButton, true, "计算建议…");
  try {
    const result = await requestJson("/api/direct", {
      method: "POST",
      body: JSON.stringify({ segments: state.analysis.segments }),
    });
    const byId = new Map(result.directions.map((item) => [item.segment_id, item]));
    for (const segment of state.analysis.segments) {
      const direction = byId.get(segment.id);
      if (!direction) continue;
      segment.direction = direction;
      segment.emotion = direction.emotion;
      segment.emotion_axes = {
        valence: direction.valence,
        arousal: direction.arousal,
        dominance: direction.dominance,
      };
    }
    renderTimeline();
    renderEmotionEditor();
    scheduleDraftSave();
    showMessage(`规则导演已为 ${result.directions.length} 个片段生成参数建议。`, true);
  } catch (error) {
    showMessage(error.message);
  } finally {
    setBusy(elements.directorButton, false, "应用规则导演");
  }
}

function resetEmotionCurve() {
  if (!state.analysis) return;
  for (const segment of state.analysis.segments) {
    const axes = EMOTION_AXES[segment.emotion] || EMOTION_AXES.neutral;
    segment.emotion_axes = { valence: axes[0], arousal: axes[1], dominance: axes[2] };
  }
  renderEmotionEditor();
  scheduleDraftSave();
}

function renderEmotionEditor() {
  if (!state.analysis) return;
  for (const segment of state.analysis.segments) {
    if (!segment.emotion_axes) {
      const axes = EMOTION_AXES[segment.emotion] || EMOTION_AXES.neutral;
      segment.emotion_axes = { valence: axes[0], arousal: axes[1], dominance: axes[2] };
    }
  }
  const shown = state.analysis.segments.slice(0, 30);
  elements.emotionEditor.innerHTML = shown.map((segment, index) => `
    <div class="emotion-row" data-index="${index}">
      <span title="${escapeAttribute(segment.text)}">${index + 1}. ${escapeHtml(segment.text.slice(0, 18))}</span>
      ${emotionSlider("valence", "效价", segment.emotion_axes.valence, -100, 100)}
      ${emotionSlider("arousal", "唤醒", segment.emotion_axes.arousal, 0, 100)}
      ${emotionSlider("dominance", "控制", segment.emotion_axes.dominance, 0, 100)}
    </div>`).join("");
  for (const input of elements.emotionEditor.querySelectorAll("input")) {
    input.addEventListener("input", () => {
      const index = Number(input.closest(".emotion-row").dataset.index);
      state.analysis.segments[index].emotion_axes[input.dataset.axis] = Number(input.value);
      input.nextElementSibling.textContent = input.value;
      drawEmotionCurve();
      scheduleDraftSave();
    });
  }
  drawEmotionCurve();
}

function emotionSlider(axis, label, value, min, max) {
  return `<label><small>${label}</small><input data-axis="${axis}" type="range" min="${min}" max="${max}" value="${value}"><output>${value}</output></label>`;
}

function drawEmotionCurve() {
  const segments = state.analysis?.segments?.slice(0, 30) || [];
  const colors = { valence: "#d65d45", arousal: "#d2a33b", dominance: "#427b75" };
  const paths = Object.keys(colors).map((axis) => {
    const points = segments.map((segment, index) => {
      const raw = segment.emotion_axes[axis];
      const normalized = axis === "valence" ? (raw + 100) / 200 : raw / 100;
      const x = segments.length < 2 ? 20 : 20 + index * 860 / (segments.length - 1);
      return `${x.toFixed(1)},${(190 - normalized * 160).toFixed(1)}`;
    }).join(" ");
    return `<polyline points="${points}" fill="none" stroke="${colors[axis]}" stroke-width="3"/>`;
  }).join("");
  elements.emotionCurve.innerHTML = `<path d="M20 30V190H880" fill="none" stroke="#d8d2c7"/>
    ${paths}<g class="curve-legend"><text x="25" y="20">效价</text><text x="85" y="20">唤醒</text><text x="145" y="20">控制感</text></g>`;
}

function renderVoiceSamples() {
  if (!state.analysis) return;
  elements.voiceSamples.innerHTML = state.analysis.characters
    .filter((character) => character.id !== "narrator")
    .map((character) => `<label><strong>${escapeHtml(character.name)}</strong>
      <input type="file" accept="audio/wav,audio/mpeg,audio/mp4,audio/x-m4a" data-character-id="${escapeAttribute(character.id)}">
    </label>`).join("");
}

async function compareVoiceSamples() {
  const inputs = [...elements.voiceSamples.querySelectorAll("input")].filter((input) => input.files[0]);
  if (inputs.length < 2) {
    showMessage("请至少为两个角色选择标准试听音频。");
    return;
  }
  setBusy(elements.compareVoicesButton, true, "提取声学向量…");
  try {
    const context = new AudioContext();
    const samples = [];
    for (const input of inputs) {
      const buffer = await context.decodeAudioData(await input.files[0].arrayBuffer());
      samples.push({
        id: input.dataset.characterId,
        name: state.analysis.characters.find((item) => item.id === input.dataset.characterId).name,
        vector: audioEmbedding(buffer),
      });
    }
    await context.close();
    const header = `<tr><th></th>${samples.map((item) => `<th>${escapeHtml(item.name)}</th>`).join("")}</tr>`;
    const conflicts = [];
    const rows = samples.map((left) => `<tr><th>${escapeHtml(left.name)}</th>${samples.map((right) => {
      const score = cosineSimilarity(left.vector, right.vector);
      if (score >= 0.82 && samples.indexOf(left) < samples.indexOf(right)) {
        conflicts.push({ left, right, score });
      }
      return `<td class="${score >= 0.82 && left !== right ? "too-similar" : ""}">${score.toFixed(2)}</td>`;
    }).join("")}</tr>`).join("");
    elements.voiceSimilarityResults.innerHTML =
      `<table class="similarity-matrix">${header}${rows}</table>
      ${conflicts.length ? renderVoiceReplacementChoices(conflicts) : '<div class="quality-ok">✓ 没有超过 0.82 的角色声音组合。</div>'}
      <small>标红表示相似度 ≥ 0.82。更换声音后，请重新生成并上传该角色的标准试听音频复测。该轻量声学向量用于预筛，正式制作建议复核试听。</small>`;
    bindVoiceReplacementChoices();
  } catch (error) {
    showMessage(`音频分析失败：${error.message}`);
  } finally {
    setBusy(elements.compareVoicesButton, false, "生成相似度矩阵");
  }
}

function renderVoiceReplacementChoices(conflicts) {
  return `<section class="voice-replacement-panel">
    <strong>发现 ${conflicts.length} 组声音过于相似，可直接更换：</strong>
    ${conflicts.map((conflict, index) => {
      const target = pickReplacementTarget(conflict.left.id, conflict.right.id);
      return `<div class="voice-replacement-row" data-conflict-index="${index}">
        <span><b>${escapeHtml(conflict.left.name)}</b> 与 <b>${escapeHtml(conflict.right.name)}</b>
          <em>${conflict.score.toFixed(2)}</em></span>
        <label>更换
          <select class="replacement-character">
            <option value="${escapeAttribute(conflict.left.id)}" ${target === conflict.left.id ? "selected" : ""}>${escapeHtml(conflict.left.name)}</option>
            <option value="${escapeAttribute(conflict.right.id)}" ${target === conflict.right.id ? "selected" : ""}>${escapeHtml(conflict.right.name)}</option>
          </select>
        </label>
        <label>新声音
          <select class="replacement-voice"></select>
        </label>
        <button class="mini-button replacement-preview" type="button">▶ 试听候选</button>
        <button class="secondary-button compact replacement-apply" type="button">应用更换</button>
      </div>`;
    }).join("")}
  </section>`;
}

function pickReplacementTarget(leftId, rightId) {
  const left = state.analysis.characters.find((item) => item.id === leftId);
  const right = state.analysis.characters.find((item) => item.id === rightId);
  if (left?.locked && !right?.locked) return rightId;
  if (right?.locked && !left?.locked) return leftId;
  return rightId;
}

function compatibleReplacementOptions(characterId) {
  const character = state.analysis.characters.find((item) => item.id === characterId);
  if (!character) return "";
  const used = new Set(
    state.analysis.characters
      .filter((item) => item.id !== characterId)
      .map((item) => item.voice_id),
  );
  const ranked = [...state.config.voices].sort((left, right) => {
    const score = (voice) =>
      (voice.gender === character.gender ? 4 : 0) +
      (voice.age_group === character.age_group ? 6 : 0) -
      (voice.id.startsWith("narrator") ? 3 : 0) -
      (used.has(voice.id) ? 8 : 0);
    return score(right) - score(left);
  });
  return ranked
    .filter((voice) => voice.id !== character.voice_id)
    .map((voice) => `<option value="${escapeAttribute(voice.id)}" ${used.has(voice.id) ? "disabled" : ""}>
      ${escapeHtml(voice.label)} · ${escapeHtml(voice.description)}${used.has(voice.id) ? "（已使用）" : ""}
    </option>`)
    .join("");
}

function bindVoiceReplacementChoices() {
  for (const row of elements.voiceSimilarityResults.querySelectorAll(".voice-replacement-row")) {
    const characterSelect = row.querySelector(".replacement-character");
    const voiceSelect = row.querySelector(".replacement-voice");
    const refreshOptions = () => {
      voiceSelect.innerHTML = compatibleReplacementOptions(characterSelect.value);
    };
    refreshOptions();
    characterSelect.addEventListener("change", refreshOptions);
    row.querySelector(".replacement-preview").addEventListener("click", () => {
      previewReplacementVoice(characterSelect.value, voiceSelect.value);
    });
    row.querySelector(".replacement-apply").addEventListener("click", () => {
      applyReplacementVoice(characterSelect.value, voiceSelect.value, row);
    });
  }
}

async function previewReplacementVoice(characterId, voiceId) {
  const character = state.analysis.characters.find((item) => item.id === characterId);
  if (!character || !voiceId) return;
  const previousVoice = character.voice_id;
  character.voice_id = voiceId;
  try {
    await previewCharacterVoice(characterId);
  } finally {
    character.voice_id = previousVoice;
  }
}

function applyReplacementVoice(characterId, voiceId, row) {
  const character = state.analysis.characters.find((item) => item.id === characterId);
  const voice = state.config.voices.find((item) => item.id === voiceId);
  if (!character || !voice) return;
  character.voice_id = voiceId;
  character.locked = true;
  syncRegistryFromAnalysis();
  if (state.book) {
    for (const chapter of state.book.chapters) {
      const profile = chapter.analysis?.characters?.find((item) => item.id === characterId);
      if (profile) {
        profile.voice_id = voiceId;
        profile.locked = true;
      }
    }
  }
  scheduleDraftSave();
  scheduleRenderPlan();
  renderCharacters();
  row.classList.add("replacement-applied");
  row.innerHTML = `<span>✓ 已把 <b>${escapeHtml(character.name)}</b> 更换为
    <b>${escapeHtml(voice.label)}</b>。请重新生成、上传试听音频并复测。</span>`;
  showMessage(`已更换“${character.name}”的声音，并同步到全书角色表。`, true);
}

function audioEmbedding(buffer) {
  const data = buffer.getChannelData(0);
  let rawPeak = 0;
  for (let i = 0; i < data.length; i++) {
    rawPeak = Math.max(rawPeak, Math.abs(data[i]));
  }
  const threshold = rawPeak * 0.02;
  let start = 0, end = data.length;
  while (start < end && Math.abs(data[start]) < threshold) start++;
  while (end > start && Math.abs(data[end - 1]) < threshold) end--;
  const bins = new Array(32).fill(0);
  let peak = 0;
  for (let i = start; i < end; i++) peak = Math.max(peak, Math.abs(data[i]));
  const stride = Math.max(1, Math.floor((end - start) / 8192));
  let previous = 0, zcr = 0, energy = 0, count = 0;
  for (let i = start; i < end; i += stride) {
    const value = data[i] / (peak || 1);
    energy += value * value;
    if ((value >= 0) !== (previous >= 0)) zcr++;
    bins[Math.min(31, Math.floor(Math.abs(value) * 32))]++;
    previous = value; count++;
  }
  const vector = bins.map((value) => value / Math.max(1, count));
  vector.push(Math.sqrt(energy / Math.max(1, count)), zcr / Math.max(1, count));
  return vector;
}

function cosineSimilarity(left, right) {
  const dot = left.reduce((sum, value, index) => sum + value * right[index], 0);
  const a = Math.sqrt(left.reduce((sum, value) => sum + value * value, 0));
  const b = Math.sqrt(right.reduce((sum, value) => sum + value * value, 0));
  return dot / (a * b || 1);
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
  if (state.book) {
    for (const chapter of state.book.chapters) {
      if (!chapter.analysis) continue;
      const chapterSource = chapter.analysis.characters?.find(
        (character) => character.id === source.id,
      );
      const chapterTarget = chapter.analysis.characters?.find(
        (character) => character.id === target.id,
      );
      if (chapterSource && chapterTarget) {
        chapterTarget.aliases = uniqueValues([
          ...(chapterTarget.aliases || []),
          chapterSource.name,
          ...(chapterSource.aliases || []),
        ]).filter((alias) => alias !== chapterTarget.name);
      }
      chapter.analysis.characters = (chapter.analysis.characters || []).filter(
        (character) => character.id !== source.id,
      );
      for (const segment of chapter.analysis.segments || []) {
        if (segment.speaker_id === source.id) {
          segment.speaker_id = target.id;
          segment.locked = true;
        }
      }
      recomputeSummary(chapter.analysis);
    }
  }
  if (state.characterRegistry.dialogue_counts[source.id]) {
    state.characterRegistry.dialogue_counts[target.id] =
      Number(state.characterRegistry.dialogue_counts[target.id] || 0) +
      Number(state.characterRegistry.dialogue_counts[source.id] || 0);
    delete state.characterRegistry.dialogue_counts[source.id];
  }
  syncRegistryFromAnalysis([source.id]);
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
      syncBookPronunciations();
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
  syncBookPronunciations();
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
          ${segment.direction ? `<span class="director-chip" title="${escapeAttribute(segment.direction.reasons.join("；"))}">导演：${segment.direction.pace}× · 能量 ${segment.direction.energy} · 停顿 ${segment.direction.pause_after_ms}ms</span>` : ""}
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
  return startBrowserPreview(index, index + 1);
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

const NATURAL_FEMALE_VOICE_HINTS = [
  "huihui",
  "meijia",
  "sinji",
  "tingting",
  "xiaohan",
  "xiaomeng",
  "xiaomo",
  "xiaorui",
  "xiaoshuang",
  "xiaoxiao",
  "xiaoyi",
  "xiaoyan",
  "yaoyao",
];
const NATURAL_MALE_VOICE_HINTS = [
  "kangkang",
  "limu",
  "yunjian",
  "yunjie",
  "yunfeng",
  "yunhao",
  "yunxi",
  "yunyang",
  "yunye",
  "yushu",
];
const NOVELTY_VOICE_HINTS = [
  "badnews",
  "bahh",
  "bells",
  "boing",
  "bubbles",
  "cellos",
  "eddy",
  "flo",
  "goodnews",
  "grandma",
  "grandpa",
  "organ",
  "rocko",
  "sandy",
  "shelley",
  "trinoids",
  "whisper",
  "wobble",
  "zarvox",
];

function compactVoiceName(voice) {
  return `${voice?.name || ""}${voice?.voiceURI || ""}`
    .toLocaleLowerCase()
    .replace(/[^a-z0-9]+/g, "");
}

function browserVoiceGroup(voice) {
  const name = compactVoiceName(voice);
  if (NOVELTY_VOICE_HINTS.some((hint) => name.includes(hint))) {
    return "novelty";
  }
  if (NATURAL_FEMALE_VOICE_HINTS.some((hint) => name.includes(hint))) {
    return "female";
  }
  if (NATURAL_MALE_VOICE_HINTS.some((hint) => name.includes(hint))) {
    return "male";
  }
  return "unknown";
}

function browserVoiceScore(voice, targetGender) {
  const language = String(voice.lang || "").replace("_", "-").toLowerCase();
  let score = language === "zh-cn" ? 60 : language.startsWith("zh") ? 35 : 0;
  const group = browserVoiceGroup(voice);
  if (group === "novelty") {
    score -= 120;
  } else if (group === targetGender) {
    score += 45;
  } else if (["female", "male"].includes(group)) {
    score -= 35;
  } else {
    score += 5;
  }
  if (voice.default) score += 3;
  return score;
}

function stableVoiceHash(value) {
  return [...String(value || "")].reduce(
    (total, character) => (total * 31 + character.charCodeAt(0)) >>> 0,
    0,
  );
}

function selectNaturalBrowserVoice(character, preset, voices) {
  if (!voices.length) return null;
  const targetGender = preset?.gender || character?.gender || "unknown";
  const ranked = voices
    .map((voice) => ({
      voice,
      score: browserVoiceScore(voice, targetGender),
    }))
    .sort(
      (left, right) =>
        right.score - left.score ||
        String(left.voice.name).localeCompare(String(right.voice.name)),
    );
  const bestScore = ranked[0].score;
  const naturalShortlist = ranked.filter(
    (item) =>
      item.score >= bestScore - 4 &&
      browserVoiceGroup(item.voice) !== "novelty",
  );
  const shortlist = naturalShortlist.length ? naturalShortlist : [ranked[0]];
  const key = character?.voice_id || character?.id || "narrator";
  return shortlist[stableVoiceHash(key) % shortlist.length].voice;
}

function clampNumber(value, minimum, maximum) {
  return Math.max(minimum, Math.min(maximum, Number(value)));
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
    const selectedVoice = selectNaturalBrowserVoice(
      character,
      preset,
      chineseVoices,
    );
    utterance.lang = selectedVoice?.lang || "zh-CN";
    const baseRate = clampNumber(preset?.browser_rate || 1, 0.88, 1.08);
    utterance.rate = clampNumber(
      baseRate * Number(elements.previewSpeed.value || 1),
      0.75,
      1.5,
    );
    utterance.pitch = clampNumber(preset?.browser_pitch || 1, 0.92, 1.1);
    utterance.volume = 1;
    if (selectedVoice) {
      utterance.voice = selectedVoice;
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
  if (!provider) {
    elements.renderPlan.textContent =
      "设备自然试听已经可用；安装 Mac 中文系统声音或连接 CosyVoice 后可生成下载文件。";
    return;
  }
  state.planTimer = window.setTimeout(
    () => refreshRenderPlan(provider, false),
    500,
  );
}

async function refreshRenderPlan(provider = state.lastProvider, showErrors = false) {
  if (!state.analysis || state.analysisStale) return null;
  if (!provider) {
    elements.renderPlan.textContent =
      "目前只有设备自然试听可用，尚未连接可导出的语音生成方式。";
    return null;
  }
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
  const isPaid = plan.provider === "dashscope";
  const isLocal = plan.provider === "local";
  const ready = Number(plan.cached_segments) || 0;
  const remaining = Number(plan.estimated_requests) || 0;
  const remainingCharacters =
    Number(plan.estimated_billable_characters) || 0;
  const cost =
    !isPaid ||
    plan.estimated_cost_cny === null ||
    plan.estimated_cost_cny === undefined
      ? ""
      : `<span><strong>约 ¥${Number(plan.estimated_cost_cny).toFixed(4)}</strong> 预计费用</span>`;
  const note = isLocal
    ? remaining
      ? `将使用 Mac 的真实中文系统声音；已有 ${ready} 句可直接复用。`
      : "所有句子都已经生成过，可直接复用并导出。"
    : remaining
      ? `已有 ${ready} 句准备好；实际费用以最终账单为准。`
      : "所有句子都已准备好，再次生成不会重复制作声音。";
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
  const provider = state.config?.providers?.dashscope?.ready
    ? "dashscope"
    : state.config?.providers?.local?.ready
      ? "local"
      : null;
  if (!provider) {
    startBrowserPreview(index, index + 1);
    showMessage(
      "已先用设备的自然中文声音试听这句；安装 Mac 中文系统声音或连接 CosyVoice 后，同一按钮会只重新生成这一句。",
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
      body: JSON.stringify({ analysis, provider }),
    });
    if (provider === "dashscope" && Number(plan.estimated_requests) > 0) {
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
        provider,
        confirm_cost: provider === "dashscope",
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
        : provider === "local"
          ? "使用 Mac 本地中文语音生成；下次生成全书时会直接复用"
          : "只生成了这一句；下次生成全书时会直接复用";
    elements.resultAudio.play().catch(() => {});
    elements.audioResult.scrollIntoView({ behavior: "smooth", block: "center" });
    showMessage("这句话已重新生成，其他句子没有重复处理。", true);
    scheduleRenderPlan(provider);
  } catch (error) {
    showMessage(error.message);
  } finally {
    state.isRendering = false;
    setBusy(button, false, "重做这句");
    updateActionAvailability();
  }
}

async function renderAudio(provider) {
  if (!state.analysis) return;
  if (state.analysisStale) {
    showMessage("原文已经变更，请重新分析后再生成。");
    return;
  }
  if (currentRenderJobIsActive()) {
    showMessage("这一章已经在后台生成，不需要重复提交。");
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
      : elements.localRenderButton;
  setBusy(
    activeButton,
    true,
    provider === "dashscope"
      ? "正在加入后台任务…"
      : "正在调用 Mac 中文语音…",
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

    const chapter = currentChapter();
    const contextKey = renderContextKey();
    const result = await requestJson("/api/render/jobs", {
      method: "POST",
      body: JSON.stringify({
        analysis: state.analysis,
        provider,
        format: elements.outputFormat.value,
        confirm_cost: provider === "dashscope",
        chapter_id: chapter?.id || "standalone",
        chapter_title: chapter?.title || "当前文本",
      }),
    });
    state.renderJobIds[contextKey] = result.job_id;
    applyRenderJob(result);
    await saveDraft();
    scheduleRenderJobPoll(result.job_id);
    if (ACTIVE_RENDER_JOB_STATUSES.has(result.status)) {
      showMessage(
        "已开始后台生成；第一批句子完成后就能播放，刷新页面也会接回进度。",
        true,
      );
    }
  } catch (error) {
    showMessage(error.message);
  } finally {
    state.isRendering = false;
    setBusy(
      activeButton,
      false,
      provider === "dashscope" ? "开始生成" : "免费生成（Mac）",
    );
    updateActionAvailability();
  }
}

function currentRenderJobIsActive() {
  const jobId = state.renderJobIds[renderContextKey()];
  return Boolean(
    jobId &&
      state.renderJob?.job_id === jobId &&
      ACTIVE_RENDER_JOB_STATUSES.has(state.renderJob.status),
  );
}

function renderJobStatusLabel(job) {
  const labelsByStatus = {
    queued: "等待后台开始",
    running: "正在逐句生成",
    pausing: "完成当前句后暂停",
    paused: "生成已暂停",
    partial: "部分句子需要重试",
    completed: "章节生成完成",
    failed: "生成遇到错误",
    interrupted: "服务器重启后任务已中断",
  };
  return labelsByStatus[job.status] || "正在更新任务";
}

function applyRenderJob(job) {
  const previousStatus =
    state.renderJob?.job_id === job.job_id ? state.renderJob.status : null;
  if (state.progressiveJobId && state.progressiveJobId !== job.job_id) {
    resetProgressivePlayer();
  }
  job.playable_segments = Array.isArray(job.playable_segments)
    ? job.playable_segments
    : [];
  job.failed_segments = Array.isArray(job.failed_segments)
    ? job.failed_segments
    : [];
  state.renderJob = job;
  if (
    (job.provider === "local" && state.config?.providers?.local?.ready) ||
    (job.provider === "dashscope" && state.config?.providers?.dashscope?.ready)
  ) {
    state.lastProvider = job.provider;
  }
  elements.renderJobPanel.hidden = false;
  elements.renderJobPanel.dataset.status = job.status;
  elements.renderJobStatus.textContent =
    `${job.chapter_title || "当前章节"} · ${renderJobStatusLabel(job)}`;
  elements.renderProgress.max = 100;
  elements.renderProgress.value = Math.max(
    0,
    Math.min(100, Number(job.progress_percent) || 0),
  );
  const completed = Number(job.completed_segments) || 0;
  const total = Number(job.total_segments) || 0;
  elements.renderProgressLabel.textContent = `${completed} / ${total} 句`;
  elements.playableCount.textContent = job.playable_segments.length
    ? `${job.playable_segments.length} 句现在可播放`
    : "正在准备第一句";
  elements.playReadyButton.disabled = job.playable_segments.length === 0;
  elements.progressiveAudio.hidden =
    state.progressiveJobId !== job.job_id ||
    job.playable_segments.length === 0;
  elements.pauseJobButton.hidden = !["queued", "running", "pausing"].includes(
    job.status,
  );
  elements.pauseJobButton.disabled = job.status === "pausing";
  elements.pauseJobButton.textContent =
    job.status === "pausing" ? "正在暂停…" : "暂停生成";
  elements.resumeJobButton.hidden =
    !["paused", "partial", "failed"].includes(job.status) ||
    job.resumable === false;

  if (
    state.progressiveJobId === job.job_id &&
    state.waitingForProgressiveSegment &&
    job.playable_segments.length > state.progressiveIndex + 1
  ) {
    startProgressivePlayback(state.progressiveIndex + 1);
  }

  if (job.status === "completed" && job.audio_url) {
    elements.audioResult.hidden = false;
    elements.resultAudio.src = job.audio_url;
    elements.downloadLink.href = job.audio_url;
    elements.downloadLink.textContent =
      `下载 ${String(job.format || "wav").toUpperCase()} ↓`;
    elements.audioTitle.textContent =
      job.provider === "local"
        ? "Mac 本地多人朗读已生成"
        : job.provider === "demo"
          ? "内部音频检查已完成"
          : "多人有声书已生成";
    elements.audioMeta.textContent =
      `${completed} 句 · 后台生成完成，可播放或下载完整章节`;
    elements.wavDownloadLink.hidden =
      job.format !== "mp3" || !job.wav_url;
    if (!elements.wavDownloadLink.hidden) {
      elements.wavDownloadLink.href = job.wav_url;
    }
  } else {
    elements.audioResult.hidden = true;
  }

  if (previousStatus !== job.status) {
    if (job.status === "completed") {
      showMessage("这一章已经全部生成完成。", true);
      scheduleRenderPlan(state.lastProvider);
    } else if (job.status === "paused") {
      showMessage("生成已暂停，已经完成的句子仍然可以播放。", true);
    } else if (job.status === "partial") {
      showMessage(
        `${job.failed_segments.length} 句话暂未完成；点击“继续生成”只会补缺失内容。`,
      );
    } else if (job.status === "failed") {
      showMessage(job.message || "生成失败，可以稍后继续。");
    } else if (job.status === "interrupted") {
      showMessage(job.message || "任务因服务器重启中断，请重新提交章节。");
    }
  }
  updateActionAvailability();
}

function scheduleRenderJobPoll(jobId, delay = 650) {
  window.clearTimeout(state.renderPollTimer);
  if (
    state.renderJobIds[renderContextKey()] !== jobId ||
    !ACTIVE_RENDER_JOB_STATUSES.has(state.renderJob?.status)
  ) {
    return;
  }
  state.renderPollTimer = window.setTimeout(
    () => void pollRenderJob(jobId),
    delay,
  );
}

async function pollRenderJob(jobId) {
  if (state.renderJobIds[renderContextKey()] !== jobId) return;
  try {
    const job = await requestJson(`/api/render/jobs/${jobId}`);
    if (state.renderJobIds[renderContextKey()] !== jobId) return;
    if (job.provider === "demo") {
      delete state.renderJobIds[renderContextKey()];
      resetRenderJobView();
      scheduleDraftSave();
      return;
    }
    applyRenderJob(job);
    scheduleRenderJobPoll(jobId);
  } catch (error) {
    if (state.renderJobIds[renderContextKey()] === jobId) {
      delete state.renderJobIds[renderContextKey()];
      resetRenderJobView();
      scheduleDraftSave();
      showMessage(error.message);
    }
  }
}

async function restoreRenderJobForCurrentContext() {
  const contextKey = renderContextKey();
  const jobId = state.renderJobIds[contextKey];
  resetRenderJobView();
  if (!jobId) return;
  try {
    const job = await requestJson(`/api/render/jobs/${jobId}`);
    if (state.renderJobIds[renderContextKey()] !== jobId) return;
    if (job.provider === "demo") {
      delete state.renderJobIds[contextKey];
      scheduleDraftSave();
      return;
    }
    applyRenderJob(job);
    scheduleRenderJobPoll(jobId, 300);
  } catch {
    if (state.renderJobIds[contextKey] === jobId) {
      delete state.renderJobIds[contextKey];
      scheduleDraftSave();
    }
  }
}

async function pauseRenderJob() {
  const jobId = state.renderJob?.job_id;
  if (!jobId) return;
  setBusy(elements.pauseJobButton, true, "正在请求暂停…");
  try {
    const job = await requestJson(`/api/render/jobs/${jobId}/pause`, {
      method: "POST",
      body: "{}",
    });
    applyRenderJob(job);
    scheduleRenderJobPoll(jobId, 250);
  } catch (error) {
    showMessage(error.message);
  } finally {
    if (state.renderJob?.status !== "pausing") {
      setBusy(elements.pauseJobButton, false, "暂停生成");
    }
  }
}

async function resumeRenderJob() {
  const jobId = state.renderJob?.job_id;
  if (!jobId) return;
  setBusy(elements.resumeJobButton, true, "正在继续…");
  try {
    const job = await requestJson(`/api/render/jobs/${jobId}/resume`, {
      method: "POST",
      body: "{}",
    });
    applyRenderJob(job);
    scheduleRenderJobPoll(jobId, 250);
  } catch (error) {
    showMessage(error.message);
  } finally {
    setBusy(elements.resumeJobButton, false, "继续生成");
  }
}

function resetProgressivePlayer() {
  state.progressiveIndex = -1;
  state.progressiveJobId = null;
  state.waitingForProgressiveSegment = false;
  elements.progressiveAudio.pause();
  elements.progressiveAudio.removeAttribute("src");
  elements.progressiveAudio.load();
  elements.progressiveAudio.hidden = true;
  elements.progressiveNowPlaying.textContent =
    "第一批句子完成后即可播放。";
}

function startProgressivePlayback(index = 0) {
  const segments = state.renderJob?.playable_segments || [];
  if (!segments.length) {
    showMessage("第一句还在生成，请稍等片刻。");
    return;
  }
  if (index >= segments.length) {
    state.waitingForProgressiveSegment = ACTIVE_RENDER_JOB_STATUSES.has(
      state.renderJob.status,
    );
    elements.progressiveNowPlaying.textContent =
      state.waitingForProgressiveSegment
        ? "已播放完当前内容，正在等待下一句…"
        : "已播放完这一章当前可用的内容。";
    return;
  }
  const segment = segments[index];
  state.progressiveIndex = index;
  state.progressiveJobId = state.renderJob.job_id;
  state.waitingForProgressiveSegment = false;
  if (
    elements.progressiveAudio.getAttribute("src") !== segment.audio_url
  ) {
    elements.progressiveAudio.src = segment.audio_url;
  }
  elements.progressiveAudio.hidden = false;
  elements.progressiveNowPlaying.textContent =
    `正在播放第 ${segment.index} 句 · ${segment.character_name || "待确认角色"}`;
  elements.progressiveAudio.play().catch(() => {
    elements.progressiveNowPlaying.textContent =
      `第 ${segment.index} 句已准备好，请点击播放器开始。`;
  });
}

function playNextProgressiveSegment() {
  startProgressivePlayback(state.progressiveIndex + 1);
}

function updateActionAvailability() {
  if (!elements.playButton) return;
  const unavailable =
    !state.analysis || state.analysisStale || state.isRendering;
  const activeRenderJob = currentRenderJobIsActive();
  elements.playButton.disabled = unavailable || state.isSpeaking;
  elements.stopButton.disabled = !state.isSpeaking;
  elements.previewSpeed.disabled = state.isRendering;
  elements.localRenderButton.disabled =
    unavailable ||
    activeRenderJob ||
    !state.config?.providers?.local?.ready;
  elements.refreshPlanButton.disabled = unavailable || !state.lastProvider;
  elements.dashscopeRenderButton.disabled =
    unavailable ||
    activeRenderJob ||
    !state.config?.providers?.dashscope?.ready;
  elements.addPronunciationButton.disabled =
    !state.analysis || state.isRendering;
  for (const button of elements.scriptTimeline.querySelectorAll(
    ".sentence-button",
  )) {
    button.disabled = unavailable || state.isSpeaking;
  }
  renderBookNavigation();
}

function scheduleDraftSave() {
  window.clearTimeout(state.draftTimer);
  elements.draftStatus.textContent = "正在保存本机草稿…";
  state.draftTimer = window.setTimeout(() => void saveDraft(), 450);
}

async function saveDraft() {
  const text = elements.sourceText.value;
  if (!text && !state.analysis && !state.book) {
    await deleteStoredDraft();
    elements.draftStatus.textContent = "本机草稿尚未保存";
    return;
  }
  saveCurrentChapter();
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
    book: state.book,
    character_registry: state.characterRegistry,
    render_job_ids: state.renderJobIds,
    saved_at: savedAt,
  };
  try {
    await writeDraftToDatabase(project);
    window.localStorage.removeItem(DRAFT_KEY);
    elements.draftStatus.textContent =
      `本机草稿已保存 ${new Date(savedAt).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      })}`;
  } catch {
    try {
      window.localStorage.setItem(DRAFT_KEY, JSON.stringify(project));
      elements.draftStatus.textContent = "已使用兼容模式保存本机草稿";
    } catch {
      elements.draftStatus.textContent = "本机存储空间不足，草稿未保存";
    }
  }
}

async function restoreDraft() {
  let project = null;
  try {
    project = await readDraftFromDatabase();
  } catch {
    // Older browsers continue with the localStorage fallback below.
  }
  if (!project) {
    const raw = window.localStorage.getItem(DRAFT_KEY);
    if (!raw) return;
    try {
      project = JSON.parse(raw);
    } catch {
      window.localStorage.removeItem(DRAFT_KEY);
      return;
    }
  }
  try {
    if (!project || typeof project.source_text !== "string") return;
    state.sourceFile = project.source_file || null;
    state.renderJobIds = normalizeRenderJobIds(project.render_job_ids);
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

    if (project.book) {
      state.book = normalizeBookProject(project.book);
      state.characterRegistry = normalizeCharacterRegistry(
        project.character_registry || state.book.character_registry,
      );
      state.book.character_registry = deepCopy(state.characterRegistry);
      loadChapter(state.book.selected_chapter_id, false);
    } else {
      state.book = null;
      state.characterRegistry = normalizeCharacterRegistry(
        project.character_registry,
      );
      elements.sourceText.value = project.source_text;
      if (state.sourceFile) {
        elements.fileMeta.textContent =
          `${state.sourceFile.name} · ${state.sourceFile.encoding}`;
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
      renderBookNavigation();
    }
    await restoreRenderJobForCurrentContext();
    const saved = project.saved_at ? new Date(project.saved_at) : null;
    elements.draftStatus.textContent =
      saved && !Number.isNaN(saved.valueOf())
        ? `已恢复 ${saved.toLocaleString()} 的本机草稿`
        : "已恢复本机草稿";
    showMessage("已恢复上次保存在这台浏览器中的项目草稿。", true);
  } catch {
    await deleteStoredDraft();
  }
}

async function clearSavedDraft() {
  await deleteStoredDraft();
  elements.draftStatus.textContent = "保存副本已删除；当前页面内容仍保留";
  showMessage("已删除这台浏览器中的保存副本，当前页面内容没有变化。", true);
}

async function requestJson(path, options = {}) {
  const { headers = {}, ...requestOptions } = options;
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...headers },
    ...requestOptions,
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

function openDraftDatabase() {
  return new Promise((resolve, reject) => {
    if (!("indexedDB" in window)) {
      reject(new Error("浏览器不支持 IndexedDB"));
      return;
    }
    const request = window.indexedDB.open(DRAFT_DATABASE, 1);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(DRAFT_STORE)) {
        request.result.createObjectStore(DRAFT_STORE);
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("本机存储不可用"));
  });
}

async function writeDraftToDatabase(project) {
  const database = await openDraftDatabase();
  try {
    await new Promise((resolve, reject) => {
      const transaction = database.transaction(DRAFT_STORE, "readwrite");
      transaction.objectStore(DRAFT_STORE).put(project, DRAFT_RECORD);
      transaction.oncomplete = () => resolve();
      transaction.onerror = () =>
        reject(transaction.error || new Error("保存草稿失败"));
      transaction.onabort = () =>
        reject(transaction.error || new Error("保存草稿已中止"));
    });
  } finally {
    database.close();
  }
}

async function readDraftFromDatabase() {
  const database = await openDraftDatabase();
  try {
    return await new Promise((resolve, reject) => {
      const transaction = database.transaction(DRAFT_STORE, "readonly");
      const request = transaction.objectStore(DRAFT_STORE).get(DRAFT_RECORD);
      request.onsuccess = () => resolve(request.result || null);
      request.onerror = () =>
        reject(request.error || new Error("读取草稿失败"));
    });
  } finally {
    database.close();
  }
}

async function deleteStoredDraft() {
  window.localStorage.removeItem(DRAFT_KEY);
  try {
    const database = await openDraftDatabase();
    try {
      await new Promise((resolve, reject) => {
        const transaction = database.transaction(DRAFT_STORE, "readwrite");
        transaction.objectStore(DRAFT_STORE).delete(DRAFT_RECORD);
        transaction.oncomplete = () => resolve();
        transaction.onerror = () =>
          reject(transaction.error || new Error("删除草稿失败"));
      });
    } finally {
      database.close();
    }
  } catch {
    // localStorage has already been cleared; IndexedDB may not exist.
  }
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

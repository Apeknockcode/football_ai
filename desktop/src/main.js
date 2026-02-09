/**
 * Football AI 桌面应用 - 简化版
 * 使用 Tauri 全局 API 调用后端。
 */
const invoke = window.__TAURI__?.core?.invoke;
if (typeof invoke !== "function") {
  console.error("Tauri API 不可用，请在桌面应用内运行。");
}

const STORAGE_KEY = "football_ai_project_root";

function el(id) {
  return document.getElementById(id);
}

function setLog(id, text, isError = false) {
  const log = el(id);
  if (!log) return;
  log.textContent = text || "";
  log.className = "log-inline" + (isError ? " error" : text ? " success" : "");
}

function setSettingsLog(text, isError = false) {
  const logEl = el("settingsLog");
  if (!logEl) return;
  logEl.textContent = text || "";
  logEl.className = "log log-result" + (isError ? " error" : text ? " success" : "");
}

function getProjectRoot() {
  const v = (el("projectRoot") && el("projectRoot").value.trim()) || (el("projectRootSettings") && el("projectRootSettings").value.trim());
  return v || null;
}

function setProjectRoot(value) {
  if (el("projectRoot")) el("projectRoot").value = value || "";
  if (el("projectRootSettings")) el("projectRootSettings").value = value || "";
}

async function suggestRoot() {
  try {
    const path = await invoke("get_project_root_suggestion");
    setProjectRoot(path || "");
    if (path) localStorage.setItem(STORAGE_KEY, path);
  } catch (e) {
    setSettingsLog("获取建议路径失败: " + e, true);
  }
}

function todayStr() {
  const d = new Date();
  return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
}

function readFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => {
      const dataUrl = r.result;
      const i = dataUrl.indexOf(",");
      resolve(i >= 0 ? dataUrl.slice(i + 1) : dataUrl);
    };
    r.onerror = () => reject(new Error("读取文件失败"));
    r.readAsDataURL(file);
  });
}

// ---------- 标签页切换 ----------
function initTabs() {
  const tabs = document.querySelectorAll(".tab");
  const panels = document.querySelectorAll(".panel");
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const id = tab.getAttribute("data-tab");
      tabs.forEach((t) => t.classList.remove("active"));
      panels.forEach((p) => {
        p.classList.toggle("active", p.id === "panel-" + id);
      });
      tab.classList.add("active");
      if (id === "results") loadPredictions();
      if (id === "predict") loadTodaysMatchesFromFile();
    });
  });
}

// ---------- 今日预测 ----------
async function runSaveAndOcr() {
  const dateInput = (el("predictDate").value || todayStr()).trim();
  const matchInput = el("matchListImage");
  const injuryInput = el("injuryImage");
  const matchFile = matchInput?.files?.[0];
  const injuryFile = injuryInput?.files?.[0];
  if (!matchFile && !injuryFile) {
    setLog("predictLog", "请至少选择一张图片", true);
    return;
  }
  setLog("predictLog", "保存图片中…");
  try {
    let matchB64 = null, injuryB64 = null;
    if (matchFile) matchB64 = await readFileAsBase64(matchFile);
    if (injuryFile) injuryB64 = await readFileAsBase64(injuryFile);
    const saveMsg = await invoke("save_prediction_images", {
      projectRoot: getProjectRoot(),
      date: dateInput,
      matchListBase64: matchB64,
      injuryBase64: injuryB64,
    });
    setLog("predictLog", saveMsg + "\n识别中（OCR）…");
    const ocrResult = await invoke("run_ocr_todays_images", {
      projectRoot: getProjectRoot(),
      date: dateInput,
    });
    const text = (ocrResult.stdout || "") + (ocrResult.stderr ? "\n" + ocrResult.stderr : "") + "\n退出码: " + ocrResult.code;
    setLog("predictLog", saveMsg + "\n\n--- OCR ---\n" + text, ocrResult.code !== 0);
    if (ocrResult.code !== 0 && ocrResult.stderr?.includes("easyocr")) {
      setLog("predictLog", saveMsg + "\n\n" + text + "\n\n提示: pip install easyocr", true);
    }
  } catch (e) {
    setLog("predictLog", "失败: " + e, true);
  }
}

const PRED_LEAGUE_OPTIONS = [
  { value: "EPL", text: "英超" },
  { value: "La_Liga", text: "西甲" },
  { value: "Bundesliga", text: "德甲" },
  { value: "Serie_A", text: "意甲" },
  { value: "Ligue_1", text: "法甲" },
  { value: "Combined", text: "合并" },
];

function createPredictMatchRow() {
  const tr = document.createElement("tr");
  tr.className = "predict-match-row";
  tr.innerHTML =
    '<td><input type="text" class="pred-home" placeholder="主队" /></td>' +
    '<td><input type="text" class="pred-away" placeholder="客队" /></td>' +
    '<td><input type="number" class="pred-round" placeholder="1" min="1" /></td>' +
    '<td><select class="pred-league" aria-label="联赛">' +
    PRED_LEAGUE_OPTIONS.map((o) => `<option value="${o.value}">${o.text}</option>`).join("") +
    "</select></td>" +
    '<td><input type="text" class="pred-handicap" placeholder="-1/0/+1" /></td>' +
    '<td><input type="text" class="pred-xg-home" placeholder="可选" /></td>' +
    '<td><input type="text" class="pred-xg-away" placeholder="可选" /></td>' +
    '<td><button type="button" class="btn-remove-row" title="删除该行">删除</button></td>';
  return tr;
}

function getPredictMatchRows() {
  const tbody = el("predictMatchesTbody");
  if (!tbody) return [];
  const rows = [];
  tbody.querySelectorAll(".predict-match-row").forEach((tr) => {
    const home = (tr.querySelector(".pred-home")?.value || "").trim();
    const away = (tr.querySelector(".pred-away")?.value || "").trim();
    const roundEl = tr.querySelector(".pred-round");
    const round = roundEl?.value ? parseInt(roundEl.value, 10) : 1;
    const league = (tr.querySelector(".pred-league")?.value || "EPL").trim();
    const handicap = (tr.querySelector(".pred-handicap")?.value || "").trim();
    const xgHome = (tr.querySelector(".pred-xg-home")?.value || "").trim();
    const xgAway = (tr.querySelector(".pred-xg-away")?.value || "").trim();
    rows.push({
      home_team: home,
      away_team: away,
      round: isNaN(round) ? 1 : round,
      league_id: league || "EPL",
      league_zh: "",
      handicap_note: handicap,
      xg_home: xgHome || undefined,
      xg_away: xgAway || undefined,
      match_id: "",
    });
  });
  return rows.filter((r) => r.home_team && r.away_team);
}

function initPredictTable() {
  const tbody = el("predictMatchesTbody");
  if (!tbody) return;
  el("btnPredictAddRow").addEventListener("click", () => {
    tbody.appendChild(createPredictMatchRow());
  });
  tbody.addEventListener("click", (e) => {
    if (e.target.classList.contains("btn-remove-row")) {
      const row = e.target.closest("tr");
      if (tbody.querySelectorAll(".predict-match-row").length > 1) row?.remove();
    }
  });
}

function fillPredictTableFromCSV(csvText) {
  const tbody = el("predictMatchesTbody");
  if (!tbody || !csvText?.trim()) return;
  const { headers, rows } = parseCSV(csvText);
  const h = headers.map((x) => (x || "").trim().toLowerCase());
  const idx = (name) => {
    const i = h.indexOf(name);
    return i >= 0 ? i : h.indexOf(name.replace("_", " "));
  };
  const homeIdx = h.indexOf("home_team") >= 0 ? h.indexOf("home_team") : idx("home");
  const awayIdx = h.indexOf("away_team") >= 0 ? h.indexOf("away_team") : idx("away");
  const roundIdx = h.indexOf("round") >= 0 ? h.indexOf("round") : -1;
  const leagueIdx = h.indexOf("league_id") >= 0 ? h.indexOf("league_id") : -1;
  const handicapIdx = h.indexOf("handicap_note") >= 0 ? h.indexOf("handicap_note") : -1;
  const xgHIdx = h.indexOf("xg_home") >= 0 ? h.indexOf("xg_home") : -1;
  const xgAIdx = h.indexOf("xg_away") >= 0 ? h.indexOf("xg_away") : -1;
  tbody.innerHTML = "";
  if (rows.length === 0) {
    tbody.appendChild(createPredictMatchRow());
    return;
  }
  rows.forEach((row) => {
    const tr = createPredictMatchRow();
    const v = (i) => (i >= 0 && row[i] !== undefined ? String(row[i]).trim() : "");
    if (tr.querySelector(".pred-home")) tr.querySelector(".pred-home").value = v(homeIdx);
    if (tr.querySelector(".pred-away")) tr.querySelector(".pred-away").value = v(awayIdx);
    const roundEl = tr.querySelector(".pred-round");
    if (roundEl && roundIdx >= 0) {
      const r = parseInt(row[roundIdx], 10);
      roundEl.value = isNaN(r) ? "" : r;
    }
    const leagueSel = tr.querySelector(".pred-league");
    if (leagueSel && leagueIdx >= 0) {
      const lid = v(leagueIdx);
      if (lid && leagueSel.querySelector(`option[value="${lid}"]`)) leagueSel.value = lid;
    }
    if (tr.querySelector(".pred-handicap")) tr.querySelector(".pred-handicap").value = v(handicapIdx);
    if (tr.querySelector(".pred-xg-home")) tr.querySelector(".pred-xg-home").value = v(xgHIdx);
    if (tr.querySelector(".pred-xg-away")) tr.querySelector(".pred-xg-away").value = v(xgAIdx);
    tbody.appendChild(tr);
  });
}

/// 仅从本地 data/<日期>/todays_matches.csv 读取并填充表格，不发起网络请求。无文件时保留空表并提示。
async function loadTodaysMatchesFromFile() {
  const dateInput = (el("predictDate").value || todayStr()).trim();
  const tbody = el("predictMatchesTbody");
  try {
    const csv = await invoke("read_todays_matches_csv", { projectRoot: getProjectRoot(), date: dateInput });
    if (csv?.trim()) {
      fillPredictTableFromCSV(csv);
      const rows = (csv.trim().split(/\r?\n/).length - 1) || 0;
      setLog("predictLog", `已加载本地赛程 (${dateInput})，共 ${rows} 场。`);
    } else {
      if (tbody) {
        tbody.innerHTML = "";
        tbody.appendChild(createPredictMatchRow());
      }
      setLog("predictLog", "该日期暂无赛程，点击「获取今日五大联赛」拉取。");
    }
  } catch (_) {
    if (tbody) {
      tbody.innerHTML = "";
      tbody.appendChild(createPredictMatchRow());
    }
    setLog("predictLog", "该日期暂无赛程，点击「获取今日五大联赛」拉取。");
  }
}

/// 从网络获取五大联赛赛程并覆盖 data/<日期>/todays_matches.csv，然后从本地重新加载并显示。
async function runFetchTodaysFixtures() {
  const dateInput = (el("predictDate").value || todayStr()).trim();
  setLog("predictLog", "正在获取五大联赛赛程…");
  try {
    const result = await invoke("fetch_todays_fixtures", {
      projectRoot: getProjectRoot(),
      date: dateInput,
    });
    const msg = (result.stdout || "") + (result.stderr ? "\n" + result.stderr : "") + (result.code !== 0 ? "\n退出码: " + result.code : "");
    setLog("predictLog", msg, result.code !== 0);
    if (result.code === 0) {
      const csv = await invoke("read_todays_matches_csv", { projectRoot: getProjectRoot(), date: dateInput });
      if (csv?.trim()) fillPredictTableFromCSV(csv);
    }
  } catch (e) {
    setLog("predictLog", "执行失败: " + e, true);
  }
}

async function runFetchOdds() {
  const dateInput = (el("predictDate").value || todayStr()).trim();
  setLog("predictLog", "正在拉取盘口（The Odds API）…");
  try {
    const result = await invoke("fetch_odds", {
      projectRoot: getProjectRoot(),
      date: dateInput,
    });
    const msg = (result.stdout || "") + (result.stderr ? "\n" + result.stderr : "") + (result.code !== 0 ? "\n退出码: " + result.code : "");
    setLog("predictLog", msg, result.code !== 0);
    if (result.code === 0) {
      const csv = await invoke("read_todays_matches_csv", { projectRoot: getProjectRoot(), date: dateInput });
      if (csv?.trim()) fillPredictTableFromCSV(csv);
    }
  } catch (e) {
    setLog("predictLog", "执行失败: " + e, true);
  }
}

async function runPredict() {
  const dateInput = el("predictDate").value || todayStr();
  const tableRows = getPredictMatchRows();
  setLog("predictLog", "运行中…");
  try {
    let result;
    if (tableRows.length > 0) {
      result = await invoke("run_predict_today_with_matches", {
        projectRoot: getProjectRoot(),
        date: dateInput,
        matches: tableRows,
        model: (el("predictModel") && el("predictModel").value) || "poisson",
      });
    } else {
      result = await invoke("run_predict_today", {
        projectRoot: getProjectRoot(),
        date: dateInput,
        model: (el("predictModel") && el("predictModel").value) || "poisson",
      });
    }
    setLog("predictLog", (result.stdout || "") + (result.stderr ? "\n" + result.stderr : "") + "\n退出码: " + result.code, result.code !== 0);
    if (result.code === 0) el("viewDate").value = dateInput;
  } catch (e) {
    setLog("predictLog", "执行失败: " + e, true);
  }
}

// ---------- 预测结果 ----------
/// 预测结果 CSV 表头英文 -> 中文显示名
const PREDICTION_HEADER_LABELS = {
  match_id: "序号",
  league_zh: "联赛",
  home: "主队",
  away: "客队",
  handicap_note: "让球",
  xg_home: "预期xG(主)",
  xg_away: "预期xG(客)",
  主胜: "主胜",
  平: "平",
  客胜: "客胜",
  最可能比分: "最可能比分",
  次可能比分: "次可能比分",
  第三可能比分: "第三可能比分",
  让胜: "让胜",
  让平: "让平",
  让负: "让负",
  "value_主胜": "value主胜",
  "value_平": "value平",
  "value_客胜": "value客胜",
};

function parseCSV(text) {
  const lines = text.trim().split(/\r?\n/);
  if (lines.length === 0) return { headers: [], rows: [] };
  const headers = lines[0].split(",").map((h) => h.trim());
  const rows = lines.slice(1).map((line) => {
    const values = [];
    let cur = "";
    let inQuoted = false;
    for (let i = 0; i < line.length; i++) {
      const c = line[i];
      if (c === '"') inQuoted = !inQuoted;
      else if ((c === "," && !inQuoted) || (c === "\n" && !inQuoted)) {
        values.push(cur.trim());
        cur = "";
      } else cur += c;
    }
    values.push(cur.trim());
    return values;
  });
  if (rows.length && rows[0].length !== headers.length) {
    return { headers, rows: lines.slice(1).map((l) => l.split(",").map((c) => c.trim())) };
  }
  return { headers, rows };
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

async function loadPredictions() {
  const dateInput = el("viewDate").value || todayStr();
  const wrap = el("predictionsTableWrap");
  wrap.innerHTML = "<span class='empty'>加载中…</span>";
  try {
    const csv = await invoke("read_predictions_csv", {
      projectRoot: getProjectRoot(),
      date: dateInput,
    });
    if (!csv?.trim()) {
      wrap.innerHTML = "<span class='empty'>该日期无预测结果</span>";
      return;
    }
    const { headers, rows } = parseCSV(csv);
    let html = "<table><thead><tr>";
    headers.forEach((h) => {
      const label = PREDICTION_HEADER_LABELS[h] || PREDICTION_HEADER_LABELS[h.trim()] || h;
      html += "<th>" + escapeHtml(label) + "</th>";
    });
    html += "</tr></thead><tbody>";
    rows.forEach((row) => {
      html += "<tr>";
      row.forEach((cell) => { html += "<td>" + escapeHtml(cell) + "</td>"; });
      html += "</tr>";
    });
    html += "</tbody></table>";
    wrap.innerHTML = html;
  } catch (e) {
    wrap.innerHTML = "<span class='empty'>加载失败: " + escapeHtml(String(e)) + "</span>";
  }
}

// ---------- 赛前报告（表格多场逐个生成） ----------
const PRE_LEAGUE_OPTIONS = [
  { value: "EPL", text: "英超" },
  { value: "La_Liga", text: "西甲" },
  { value: "Bundesliga", text: "德甲" },
  { value: "Serie_A", text: "意甲" },
  { value: "Ligue_1", text: "法甲" },
  { value: "Combined", text: "合并" },
];

function createPreMatchRow() {
  const tr = document.createElement("tr");
  tr.className = "pre-match-row";
  const season = new Date().getFullYear();
  tr.innerHTML =
    '<td><input type="text" class="pre-home" placeholder="主队" /></td>' +
    '<td><input type="text" class="pre-away" placeholder="客队" /></td>' +
    '<td><input type="number" class="pre-round" placeholder="轮次" min="1" /></td>' +
    '<td><select class="pre-league" aria-label="联赛">' +
    PRE_LEAGUE_OPTIONS.map((o) => `<option value="${o.value}">${o.text}</option>`).join("") +
    "</select></td>" +
    `<td><input type="number" class="pre-season" placeholder="赛季" min="2020" max="2030" value="${season}" /></td>` +
    '<td><button type="button" class="btn-remove-row" title="删除该行">删除</button></td>';
  return tr;
}

function getPreReportRows() {
  const tbody = el("preMatchesTbody");
  if (!tbody) return [];
  const rows = [];
  tbody.querySelectorAll(".pre-match-row").forEach((tr) => {
    const home = tr.querySelector(".pre-home")?.value?.trim() || "";
    const away = tr.querySelector(".pre-away")?.value?.trim() || "";
    const round = parseInt(tr.querySelector(".pre-round")?.value, 10);
    const league = tr.querySelector(".pre-league")?.value?.trim() || null;
    const seasonEl = tr.querySelector(".pre-season");
    const season = seasonEl?.value ? parseInt(seasonEl.value, 10) : null;
    if (home || away || round) rows.push({ home, away, round, league, season });
  });
  return rows.filter((r) => r.home && r.away && r.round);
}

async function runPreReport() {
  const rows = getPreReportRows();
  if (rows.length === 0) {
    setLog("preReportLog", "请在表格中填写至少一场比赛（主队、客队、轮次）", true);
    return;
  }
  const outEl = el("preReportOut");
  outEl.textContent = "";
  const parts = [];
  for (let i = 0; i < rows.length; i++) {
    const r = rows[i];
    setLog("preReportLog", `正在生成 ${i + 1}/${rows.length}：${r.home} vs ${r.away} …`);
    try {
      const result = await invoke("run_pre_report", {
        projectRoot: getProjectRoot(),
        home: r.home,
        away: r.away,
        round: r.round,
        league: r.league || null,
        season: r.season || null,
      });
      const text = result.stdout || result.stderr || "";
      parts.push(`======== ${r.home} vs ${r.away} ========\n${text}`);
    } catch (e) {
      parts.push(`======== ${r.home} vs ${r.away} ========\n失败: ${e}`);
    }
  }
  outEl.innerHTML = parts.map((block) => renderReportAsTables(block)).join("");
  setLog("preReportLog", `已生成 ${rows.length} 场赛前报告`);
}

/**
 * 解析单场报告文本：按【章节】拆成区块，每块内按行解析为 项目/内容（含 "：" 的行拆成两列）。
 */
function parseReportSections(text) {
  const sections = [];
  const lines = text.split(/\r?\n/);
  let currentTitle = "";
  let currentRows = [];

  function flush() {
    if (currentTitle || currentRows.length) {
      sections.push({ title: currentTitle, rows: currentRows });
      currentTitle = "";
      currentRows = [];
    }
  }

  for (const line of lines) {
    const headerMatch = line.match(/^【(.+?)】\s*$/);
    if (headerMatch) {
      flush();
      currentTitle = headerMatch[1];
      continue;
    }
    const t = line.trim();
    if (!t) continue;
    const colonIdx = t.indexOf("：");
    if (colonIdx >= 0) {
      currentRows.push({ key: t.slice(0, colonIdx), value: t.slice(colonIdx + 1).trim() });
    } else {
      currentRows.push({ key: "", value: t });
    }
  }
  flush();
  return sections;
}

/**
 * 将 "======== 主队 vs 客队 ========\n报告正文" 渲染为带标题的表格 HTML。
 */
function renderReportAsTables(block) {
  const match = block.match(/^========\s(.+?)\s========\s*\n?([\s\S]*)$/);
  const title = match ? match[1] : "赛前报告";
  const body = match ? match[2] : block;
  const sections = parseReportSections(body);
  let html = `<div class="report-match-block"><h4 class="report-match-title">${escapeHtml(title)}</h4>`;
  for (const sec of sections) {
    if (!sec.title && sec.rows.length === 0) continue;
    html += '<table class="report-section-table"><caption class="report-section-caption">' + escapeHtml(sec.title || "内容") + "</caption><tbody>";
    for (const r of sec.rows) {
      if (r.key) {
        html += "<tr><th scope=\"row\">" + escapeHtml(r.key) + "</th><td>" + escapeHtml(r.value) + "</td></tr>";
      } else {
        html += "<tr><td colspan=\"2\">" + escapeHtml(r.value) + "</td></tr>";
      }
    }
    html += "</tbody></table>";
  }
  html += "</div>";
  return html;
}

function initPreReportTable() {
  const tbody = el("preMatchesTbody");
  if (!tbody) return;
  el("btnPreAddRow").addEventListener("click", () => {
    tbody.appendChild(createPreMatchRow());
  });
  tbody.addEventListener("click", (e) => {
    if (e.target.classList.contains("btn-remove-row")) {
      const row = e.target.closest("tr");
      if (tbody.querySelectorAll(".pre-match-row").length > 1) row?.remove();
    }
  });
  const firstSeason = tbody.querySelector(".pre-season");
  if (firstSeason) firstSeason.value = String(new Date().getFullYear());
}

// ---------- 赛后报告 ----------

async function runPostReport() {
  const home = el("postHome").value.trim();
  const away = el("postAway").value.trim();
  const round = parseInt(el("postRound").value, 10);
  if (!home || !away || !round) {
    setLog("postReportLog", "请填写主队、客队和轮次", true);
    return;
  }
  setLog("postReportLog", "生成中…");
  try {
    const result = await invoke("run_post_report", {
      projectRoot: getProjectRoot(),
      home,
      away,
      round,
    });
    setLog("postReportLog", result.code !== 0 ? (result.stderr || result.stdout || "失败") : "生成成功");
    el("postReportOut").textContent = result.stdout || result.stderr || "";
  } catch (e) {
    setLog("postReportLog", "失败: " + e, true);
    el("postReportOut").textContent = "";
  }
}

// ---------- 设置 ----------
function fillYearSelect() {
  const sel = el("settingsYear");
  if (!sel) return;
  const thisYear = new Date().getFullYear();
  sel.innerHTML = "";
  for (let y = thisYear; y >= 2018; y--) {
    const opt = document.createElement("option");
    opt.value = String(y);
    opt.textContent = String(y);
    sel.appendChild(opt);
  }
  sel.value = String(thisYear);
}

async function runValidateData() {
  const mode = (el("settingsValidateMode") && el("settingsValidateMode").value) || "";
  const useRef = el("settingsValidateRef") && el("settingsValidateRef").checked;
  setSettingsLog("校验中…");
  try {
    const result = await invoke("run_validate_data", {
      projectRoot: getProjectRoot(),
      mode: mode || null,
      useRef: !!useRef,
    });
    const text = (result.stdout || "").trim() + (result.stderr ? "\n" + result.stderr.trim() : "") + "\n退出码: " + result.code;
    setSettingsLog(text || "(无输出)", result.code !== 0);
  } catch (e) {
    setSettingsLog("执行失败: " + e, true);
  }
}

async function runFetchFive() {
  const year = String(el("settingsYear").value || new Date().getFullYear()).trim();
  setSettingsLog("拉取五大联赛 " + year + " 中…");
  try {
    const result = await invoke("run_fetch_five_leagues", { projectRoot: getProjectRoot(), year });
    const text = (result.stdout || "").trim() + (result.stderr ? "\n" + result.stderr.trim() : "") + "\n退出码: " + result.code;
    setSettingsLog(text || "(无输出)", result.code !== 0);
  } catch (e) {
    setSettingsLog("执行失败: " + e, true);
  }
}

async function runMergeFive() {
  setSettingsLog("合并五大联赛中…");
  try {
    const result = await invoke("run_merge_five_leagues", { projectRoot: getProjectRoot() });
    const text = (result.stdout || "").trim() + (result.stderr ? "\n" + result.stderr.trim() : "") + "\n退出码: " + result.code;
    setSettingsLog(text || "(无输出)", result.code !== 0);
  } catch (e) {
    setSettingsLog("执行失败: " + e, true);
  }
}

async function runCalibrate() {
  const league = el("settingsLeague").value || "Combined";
  setSettingsLog("校准 " + league + " 中…");
  try {
    const result = await invoke("run_calibrate", { projectRoot: getProjectRoot(), league });
    const text = (result.stdout || "").trim() + (result.stderr ? "\n" + result.stderr.trim() : "") + "\n退出码: " + result.code;
    setSettingsLog(text || "(无输出)", result.code !== 0);
  } catch (e) {
    setSettingsLog("执行失败: " + e, true);
  }
}

async function runBacktest() {
  const league = el("settingsLeague").value || "Combined";
  setSettingsLog("回测 " + league + " 中…");
  try {
    const result = await invoke("run_backtest", { projectRoot: getProjectRoot(), league });
    const text = (result.stdout || "").trim() + (result.stderr ? "\n" + result.stderr.trim() : "") + "\n退出码: " + result.code;
    setSettingsLog(text || "(无输出)", result.code !== 0);
  } catch (e) {
    setSettingsLog("执行失败: " + e, true);
  }
}

async function openBrowserWindow() {
  const urlInput = el("browserUrl").value.trim();
  try {
    await invoke("open_browser_window", { url: urlInput || "https://understat.com/league/EPL/2025" });
  } catch (e) {
    setSettingsLog("打开浏览器失败: " + e, true);
  }
}

// ---------- 初始化 ----------
function bindEvents() {
  el("btnSuggestRoot").addEventListener("click", suggestRoot);
  el("btnSuggestRootSettings").addEventListener("click", suggestRoot);
  el("btnFetchFixtures").addEventListener("click", runFetchTodaysFixtures);
  el("btnFetchOdds").addEventListener("click", runFetchOdds);
  el("btnPredict").addEventListener("click", runPredict);
  el("btnSaveAndOcr").addEventListener("click", runSaveAndOcr);
  el("btnLoadPredictions").addEventListener("click", loadPredictions);
  initPreReportTable();
  initPredictTable();
  el("btnPreReport").addEventListener("click", runPreReport);
  el("btnPostReport").addEventListener("click", runPostReport);
  el("btnValidateData").addEventListener("click", runValidateData);
  el("btnCopySettingsLog").addEventListener("click", async () => {
    const logEl = el("settingsLog");
    if (!logEl || !logEl.textContent) return;
    try {
      await navigator.clipboard.writeText(logEl.textContent);
      setSettingsLog(logEl.textContent + "\n\n[已复制到剪贴板]", false);
    } catch (_) {
      setSettingsLog(logEl.textContent + "\n\n复制失败", true);
    }
  });
  el("btnFetchFive").addEventListener("click", runFetchFive);
  el("btnMergeFive").addEventListener("click", runMergeFive);
  el("btnCalibrate").addEventListener("click", runCalibrate);
  el("btnBacktest").addEventListener("click", runBacktest);
  el("btnOpenBrowser").addEventListener("click", openBrowserWindow);

  el("projectRoot").addEventListener("input", () => {
    const v = el("projectRoot").value;
    localStorage.setItem(STORAGE_KEY, v);
    if (el("projectRootSettings")) el("projectRootSettings").value = v;
  });
  el("projectRootSettings").addEventListener("input", () => {
    const v = el("projectRootSettings").value;
    localStorage.setItem(STORAGE_KEY, v);
    if (el("projectRoot")) el("projectRoot").value = v;
  });

  if (el("matchListImage")) {
    el("matchListImage").addEventListener("change", function () {
      el("matchListImageName").textContent = this.files?.[0]?.name || "";
    });
  }
  if (el("injuryImage")) {
    el("injuryImage").addEventListener("change", function () {
      el("injuryImageName").textContent = this.files?.[0]?.name || "";
    });
  }
}

async function init() {
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved) setProjectRoot(saved);

  initTabs();
  fillYearSelect();
  bindEvents();

  el("predictDate").value = todayStr();
  el("viewDate").value = todayStr();

  try {
    const path = await invoke("get_project_root_suggestion");
    if (path && !saved) setProjectRoot(path);
  } catch (_) {}
  // 默认显示「今日预测」页：若该日期已有本地赛程则直接加载显示，否则提示用户点击「获取今日五大联赛」
  loadTodaysMatchesFromFile();
  el("predictDate").addEventListener("change", loadTodaysMatchesFromFile);
}

init();

const state = {
  poles: [],
  cables: [],
  bom: [],
  bomByPole: {},
  structureAudit: null,
  selectedBomPole: "",
  validation: null,
  recommendations: [],
  qualityGate: null,
  gateUi: {
    overrideEnabled: false,
    overrideReason: "",
    lowConfReviewConfirmed: false,
  },
};

const APP_MODE = document.body?.dataset?.appMode || "programacao";
const SUPABASE_URL = "https://zhuwirlcnbxysbgdtses.supabase.co";
const SUPABASE_ANON_KEY =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpodXdpcmxjbmJ4eXNiZ2R0c2VzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA0NTI1MjAsImV4cCI6MjA5NjAyODUyMH0.RJ0yS7aWZLAhRGhuN26hwZ0eg3SEw99DbUmAIlzOp30";
let authClient = null;

const POLE_TYPES = [
  "Desconhecido",
  "C11/300",
  "C11/400",
  "C11/600",
  "C11/1000",
  "C12/300",
  "C12/400",
  "C12/600",
  "C12/1000",
  "DT11/300",
  "DT11/600",
  "DT12/300",
  "D11/300",
];
const TRAFO_OPTIONS = ["", "MONO-10kVA", "MONO-15kVA", "MONO-25kVA", "TRI-30kVA", "TRI-45kVA", "TRI-75kVA"];
const CHAVE_OPTIONS = ["", "FACA", "FUSIVEL", "SECCIONADORA"];
const CABLE_TYPES = ["BT", "MT"];
let structureHints = ["N1", "N2F", "N3F", "N4F", "B2F", "CE2", "CE4", "ET1BR", "ET1T", "ET4A", "S1", "S2", "S3"];
const CABLE_DESC_HINTS = ["MT 2X2AN", "MT 2X4ANA", "MT 3X2ANA(4ANA)", "BT 3X70+70", "BT 3X120+70"];

const els = {
  appVersionInfo: document.getElementById("appVersionInfo"),
  btnGoAsBuilt: document.getElementById("btnGoAsBuilt"),
  btnGoProgramacao: document.getElementById("btnGoProgramacao"),
  btnCheckUpdate: document.getElementById("btnCheckUpdate"),
  btnApplyUpdate: document.getElementById("btnApplyUpdate"),
  updateStatus: document.getElementById("updateStatus"),
  pdfFile: document.getElementById("pdfFile"),
  extractStatus: document.getElementById("extractStatus"),
  ordem: document.getElementById("ordem"),
  equipe: document.getElementById("equipe"),
  programador: document.getElementById("programador"),
  fiscal: document.getElementById("fiscal"),
  observacoes: document.getElementById("observacoes"),
  polesTableBody: document.querySelector("#polesTable tbody"),
  cablesTableBody: document.querySelector("#cablesTable tbody"),
  btnAddPole: document.getElementById("btnAddPole"),
  btnAddCable: document.getElementById("btnAddCable"),
  btnCalculate: document.getElementById("btnCalculate"),
  calcStatus: document.getElementById("calcStatus"),
  validationBox: document.getElementById("validationBox"),
  structureAuditBox: document.getElementById("structureAuditBox"),
  qualityGateBox: document.getElementById("qualityGateBox"),
  recommendationsBox: document.getElementById("recommendationsBox"),
  bomTableBody: document.querySelector("#bomTable tbody"),
  bomPoleSelect: document.getElementById("bomPoleSelect"),
  bomPoleTableBody: document.querySelector("#bomPoleTable tbody"),
  btnDownloadCsv: document.getElementById("btnDownloadCsv"),
  btnDownloadPdf: document.getElementById("btnDownloadPdf"),
  btnSendWhatsapp: document.getElementById("btnSendWhatsapp"),
  btnLogout: document.getElementById("btnLogout"),
};

const updateState = {
  available: false,
  targetVersion: "",
  packageUrl: "",
};

function resolveBaseUrl() {
  const origin = String(window.location.origin || "");
  if (origin.startsWith("http://") || origin.startsWith("https://")) {
    return origin;
  }
  return "http://127.0.0.1:8600";
}

function apiUrl(path) {
  const cleanPath = String(path || "");
  if (/^https?:\/\//i.test(cleanPath)) {
    return cleanPath;
  }
  const base = resolveBaseUrl();
  return `${base}${cleanPath.startsWith("/") ? cleanPath : `/${cleanPath}`}`;
}

function apiFetch(path, options = {}) {
  return fetch(apiUrl(path), {
    credentials: "include",
    ...options,
  });
}

function navigateWithVersion(path) {
  const stamp = Date.now();
  const base = resolveBaseUrl();
  window.location.href = `${base}${path}?v=${stamp}`;
}

function navigateToPath(path) {
  const base = resolveBaseUrl();
  window.location.href = `${base}${path}`;
}

window.addEventListener("error", (event) => {
  if (els.updateStatus) {
    setStatus(els.updateStatus, `Erro de interface: ${event.message}`, false);
  }
});

function setStatus(el, text, ok = true) {
  el.textContent = text;
  el.className = `status ${ok ? "ok" : "err"}`;
}

function toInt(value, fallback = 0) {
  const parsed = parseInt(String(value ?? "").trim(), 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function toFloat(value, fallback = 0) {
  const parsed = parseFloat(String(value ?? "").replace(",", ".").trim());
  return Number.isFinite(parsed) ? parsed : fallback;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function normalizeIdCodes(prefix, rawValue) {
  const prefixUpper = String(prefix || "").trim().toUpperCase();
  if (!prefixUpper) return [];
  const values = Array.isArray(rawValue)
    ? rawValue
    : String(rawValue ?? "")
      .split(/[;,]+/)
      .map((x) => x.trim())
      .filter(Boolean);
  const out = [];
  values.forEach((item) => {
    const up = String(item ?? "").toUpperCase().trim();
    if (!up) return;
    const cleaned = up.replace(/\s+/g, "");
    const match = cleaned.match(new RegExp(`^${prefixUpper}[\\-:]*([0-9]{6})$`));
    if (!match) return;
    const norm = `${prefixUpper}${match[1]}`;
    if (!out.includes(norm)) out.push(norm);
  });
  return out;
}

function ensurePoleDefaults(pole, idx) {
  const p = pole || {};
  const est = Array.isArray(p.Est) ? p.Est : [];
  const estaiQtd = typeof p.Estai === "object" ? toInt(p.Estai?.Qtd, 0) : toInt(p.Estai, 0);
  const etCodes = normalizeIdCodes("ET", p.EtCodes);
  const estfCodes = normalizeIdCodes("ESTF", p.EstfCodes);
  return {
    id: String(p.id || `P${idx + 1}`).toUpperCase(),
    Pole: String(p.Pole || "Desconhecido"),
    Est: est.map((x) => String(x).trim()).filter(Boolean),
    Trafo: p.Trafo || null,
    Chave: p.Chave || null,
    Estai: { Type: "CC - 14M", Qtd: estaiQtd },
    ParaRaio: { Type: "CRUZETA", Qtd: 0 },
    Aterramento: { Qtd: 0 },
    Ramal: { Type: null, Qtd: 0 },
    EtCodes: etCodes,
    EstfCodes: estfCodes,
  };
}

function ensureCableDefaults(cable) {
  const c = cable || {};
  return {
    Tipo: String(c.Tipo || "BT").toUpperCase(),
    Desc: String(c.Desc || ""),
    Qtd: toFloat(c.Qtd, 0),
  };
}

function renderDatalist(id, options) {
  let el = document.getElementById(id);
  if (!el) {
    el = document.createElement("datalist");
    el.id = id;
    document.body.appendChild(el);
  }
  el.innerHTML = options.map((o) => `<option value="${escapeHtml(o)}"></option>`).join("");
}

async function refreshStructureHints() {
  try {
    const resp = await apiFetch("/api/structures");
    if (!resp.ok) return;
    const data = await resp.json();
    const apiHints = Array.isArray(data?.structures) ? data.structures : [];
    if (!apiHints.length) return;
    const merged = [...new Set([...apiHints, ...structureHints])]
      .map((v) => String(v).trim().toUpperCase())
      .filter(Boolean)
      .sort((a, b) => a.localeCompare(b, "pt-BR"));
    structureHints = merged;
    renderDatalist("structureHints", structureHints);
    renderPolesTable();
  } catch (_err) {
    // fallback silencioso para a lista local
  }
}

function buildSelectOptions(options, currentValue, placeholder = "") {
  const current = String(currentValue ?? "");
  const set = new Set(options.map((x) => String(x)));
  if (current && !set.has(current)) {
    set.add(current);
  }
  const values = [...set];
  const placeholderOpt = placeholder ? `<option value="">${escapeHtml(placeholder)}</option>` : "";
  const items = values
    .map((v) => `<option value="${escapeHtml(v)}" ${v === current ? "selected" : ""}>${escapeHtml(v || "-")}</option>`)
    .join("");
  return `${placeholderOpt}${items}`;
}

function buildGateState(serverGate = {}) {
  const gate = serverGate || {};
  const overrideEnabled = Boolean(state.gateUi.overrideEnabled);
  const overrideReason = String(state.gateUi.overrideReason || "").trim();
  const lowConfReviewConfirmed = Boolean(state.gateUi.lowConfReviewConfirmed);
  const lowConfidenceCount = toInt(gate.low_confidence_count, 0);
  const errors = toInt(gate.errors, state.validation?.errors || 0);
  const warnings = toInt(gate.warnings, state.validation?.warnings || 0);
  const verificarCount = toInt(gate.verificar_count, 0);
  const overrideValid = overrideEnabled && overrideReason.length >= 10;
  const blockedReasons = [];

  if (errors > 0 && !overrideValid) {
    blockedReasons.push("erros_criticos");
  }
  if (lowConfidenceCount > 0 && !lowConfReviewConfirmed) {
    blockedReasons.push("baixa_confianca_sem_confirmacao");
  }

  return {
    ...gate,
    errors,
    warnings,
    verificar_count: verificarCount,
    low_confidence_count: lowConfidenceCount,
    override_enabled: overrideEnabled,
    override_reason: overrideReason,
    override_valid: overrideValid,
    low_conf_review_confirmed: lowConfReviewConfirmed,
    blocked: blockedReasons.length > 0,
    blocked_reasons: blockedReasons,
  };
}

function getExportPayload(extra = {}) {
  const gate = buildGateState(state.qualityGate);
  return {
    bom: state.bom,
    validation: state.validation || {},
    override_enabled: gate.override_enabled,
    override_reason: gate.override_reason,
    low_conf_review_confirmed: gate.low_conf_review_confirmed,
    ...extra,
  };
}

function syncExportButtons() {
  const gate = buildGateState(state.qualityGate);
  const hasBom = state.bom.length > 0;
  const exportDisabled = !hasBom || gate.blocked;
  els.btnDownloadCsv.disabled = exportDisabled;
  els.btnDownloadPdf.disabled = exportDisabled;
  if (els.btnSendWhatsapp) {
    els.btnSendWhatsapp.disabled = !hasBom;
  }
}

function resetGateUi() {
  state.gateUi = {
    overrideEnabled: false,
    overrideReason: "",
    lowConfReviewConfirmed: false,
  };
}

function collectPolesFromTable() {
  const rows = [...els.polesTableBody.querySelectorAll("tr")];
  state.poles = rows.map((row, idx) => {
    const id = row.querySelector('[data-field="id"]').value.trim() || `P${idx + 1}`;
    const poleType = row.querySelector('[data-field="Pole"]').value.trim() || "Desconhecido";
    const structuresRaw = row.querySelector('[data-field="Est"]').value.trim();
    const trafo = row.querySelector('[data-field="Trafo"]').value.trim() || null;
    const chave = row.querySelector('[data-field="Chave"]').value.trim() || null;
    const estaiQtd = toInt(row.querySelector('[data-field="EstaiQtd"]').value, 0);
    const structures = structuresRaw
      .split(",")
      .map((x) => x.trim().toUpperCase())
      .filter(Boolean);
    const etCodesRaw = row.querySelector('[data-field="EtCodes"]')?.value || "";
    const estfCodesRaw = row.querySelector('[data-field="EstfCodes"]')?.value || "";
    return ensurePoleDefaults(
      {
        id: id.toUpperCase(),
        Pole: poleType,
        Est: structures,
        Trafo: trafo,
        Chave: chave,
        Estai: { Type: "CC - 14M", Qtd: estaiQtd },
        EtCodes: normalizeIdCodes("ET", etCodesRaw),
        EstfCodes: [...normalizeIdCodes("ESTF", etCodesRaw), ...normalizeIdCodes("ESTF", estfCodesRaw)].filter(
          (v, i, arr) => arr.indexOf(v) === i
        ),
      },
      idx
    );
  });
}

function collectCablesFromTable() {
  const rows = [...els.cablesTableBody.querySelectorAll("tr")];
  state.cables = rows
    .map((row) => {
      const tipo = row.querySelector('[data-field="Tipo"]').value.trim().toUpperCase() || "BT";
      const desc = row.querySelector('[data-field="Desc"]').value.trim();
      const qtd = toFloat(row.querySelector('[data-field="Qtd"]').value, 0);
      return ensureCableDefaults({ Tipo: tipo, Desc: desc, Qtd: qtd });
    })
    .filter((x) => x.Desc);
}

function renderPolesTable() {
  els.polesTableBody.innerHTML = "";
  state.poles.forEach((pole, idx) => {
    const p = ensurePoleDefaults(pole, idx);
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><input data-field="id" value="${escapeHtml(p.id)}" /></td>
      <td><select data-field="Pole">${buildSelectOptions(POLE_TYPES, p.Pole, "Selecione")}</select></td>
      <td>
        <div class="pole-structure-editor">
          <input data-field="Est" value="${escapeHtml(p.Est.join(", "))}" placeholder="Ex: U3, ET1T" />
          <select data-field="EstPick">${buildSelectOptions(["", ...structureHints], "", "Estrutura")}</select>
          <button type="button" class="btnAddStruct">+</button>
        </div>
      </td>
      <td><select data-field="Trafo">${buildSelectOptions(TRAFO_OPTIONS, p.Trafo || "", "Selecione")}</select></td>
      <td><input data-field="EtCodes" value="${escapeHtml((p.EtCodes || []).join(", "))}" placeholder="ET/ESTF" /></td>
      <td><select data-field="Chave">${buildSelectOptions(CHAVE_OPTIONS, p.Chave || "", "Selecione")}</select></td>
      <td><input data-field="EstaiQtd" type="number" min="0" step="1" value="${p.Estai.Qtd}" /><input type="hidden" data-field="EstfCodes" value="${escapeHtml((p.EstfCodes || []).join(", "))}" /></td>
      <td><button type="button" class="btnRemove" title="Remover"></button></td>
    `;
    tr.querySelector(".btnAddStruct").addEventListener("click", () => {
      const estInput = tr.querySelector('[data-field="Est"]');
      const estPick = tr.querySelector('[data-field="EstPick"]');
      const picked = String(estPick.value || "").trim().toUpperCase();
      if (!picked) return;
      const current = String(estInput.value || "")
        .split(",")
        .map((x) => x.trim().toUpperCase())
        .filter(Boolean);
      if (!current.includes(picked)) {
        current.push(picked);
        estInput.value = current.join(", ");
      }
      estPick.value = "";
      collectPolesFromTable();
    });
    tr.querySelector(".btnRemove").addEventListener("click", () => {
      state.poles.splice(idx, 1);
      renderPolesTable();
    });
    tr.querySelectorAll("input,select").forEach((input) => {
      input.addEventListener("input", () => {
        collectPolesFromTable();
      });
      input.addEventListener("change", () => {
        collectPolesFromTable();
      });
    });
    els.polesTableBody.appendChild(tr);
  });
}

function renderCablesTable() {
  els.cablesTableBody.innerHTML = "";
  state.cables.forEach((cable, idx) => {
    const c = ensureCableDefaults(cable);
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><select data-field="Tipo">${buildSelectOptions(CABLE_TYPES, c.Tipo, "Selecione")}</select></td>
      <td><input data-field="Desc" list="cableDescHints" value="${escapeHtml(c.Desc)}" /></td>
      <td><input data-field="Qtd" type="number" min="0" step="0.01" value="${c.Qtd}" /></td>
      <td><button type="button" class="btnRemove" title="Remover"></button></td>
    `;
    tr.querySelector(".btnRemove").addEventListener("click", () => {
      state.cables.splice(idx, 1);
      renderCablesTable();
    });
    tr.querySelectorAll("input,select").forEach((input) => {
      input.addEventListener("input", () => {
        collectCablesFromTable();
      });
      input.addEventListener("change", () => {
        collectCablesFromTable();
      });
    });
    els.cablesTableBody.appendChild(tr);
  });
}

function renderBom() {
  renderBomRows(els.bomTableBody, state.bom);
}

function renderBomRows(targetBody, rows) {
  if (!targetBody) return;
  targetBody.innerHTML = "";
  for (const row of rows || []) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(row["Código SAP"] ?? "")}</td>
      <td>${escapeHtml(row["Descrição"] ?? "")}</td>
      <td>${escapeHtml(row["Quantidade"] ?? "")}</td>
    `;
    targetBody.appendChild(tr);
  }
}

function renderBomByPoleSelector() {
  if (!els.bomPoleSelect) return;
  const keys = Object.keys(state.bomByPole || {});
  if (keys.length === 0) {
    els.bomPoleSelect.innerHTML = '<option value="">Sem dados</option>';
    els.bomPoleSelect.value = "";
    state.selectedBomPole = "";
    return;
  }
  const hasCurrent = state.selectedBomPole && keys.includes(state.selectedBomPole);
  if (!hasCurrent) {
    state.selectedBomPole = keys[0];
  }
  els.bomPoleSelect.innerHTML = keys
    .map((k) => {
      const label = k === "CABOS_GERAIS" ? "CABOS GERAIS" : k;
      return `<option value="${escapeHtml(k)}">${escapeHtml(label)}</option>`;
    })
    .join("");
  els.bomPoleSelect.value = state.selectedBomPole;
}

function renderBomByPole() {
  if (!els.bomPoleTableBody) return;
  const rows = (state.bomByPole && state.selectedBomPole && state.bomByPole[state.selectedBomPole]) || [];
  renderBomRows(els.bomPoleTableBody, rows);
}

// O conteúdo de Validação Técnica foi unificado no painel único do Gate de
// Qualidade (renderQualityGate). Esta função apenas garante que o box antigo
// permaneça vazio.
function renderValidation() {
  if (els.validationBox) els.validationBox.innerHTML = "";
}

// Extrai os dados de validação técnica (problemas + contagens) para compor o
// painel único, sem renderizar seção própria (evita duplicar erros/avisos).
function buildValidationFragment() {
  const v = state.validation;
  if (!v) return { has: false, issuesHtml: "", errors: 0, warnings: 0 };
  const issues = Array.isArray(v.issues) ? v.issues : [];
  const visibleIssues = issues.filter((issue) => {
    const severity = String(issue.severity || "info").trim().toLowerCase();
    const status = String(issue.status || "").trim().toLowerCase();
    return !["ok", "success", "pass", "passed"].includes(severity) && !["ok", "success", "pass", "passed"].includes(status);
  });
  const errors = toInt(v.errors, 0);
  const warnings = toInt(v.warnings, 0);
  const has = visibleIssues.length > 0 || errors > 0 || warnings > 0;
  const issuesHtml = visibleIssues
    .map((issue) => {
      const severity = String(issue.severity || "info").toUpperCase();
      const message = escapeHtml(issue.message || "");
      const source = escapeHtml(issue.source || "");
      return `<li><strong>[${severity}]</strong> ${message}${source ? ` <span>(${source})</span>` : ""}</li>`;
    })
    .join("");
  return { has, issuesHtml, errors, warnings };
}

function renderRecommendations() {
  const recs = Array.isArray(state.recommendations) ? state.recommendations : [];
  if (recs.length === 0) {
    els.recommendationsBox.innerHTML = "";
    return;
  }
  const lis = recs
    .map((r) => {
      const level = String(r.level || "baixa").toLowerCase();
      const title = escapeHtml(r.title || "Recomendacao");
      const msg = escapeHtml(r.message || "");
      return `<li class="rec-${level}"><strong>${title}:</strong> ${msg}</li>`;
    })
    .join("");
  els.recommendationsBox.innerHTML = `<div class="rec-title">Recomendacoes</div><ul class="rec-list">${lis}</ul>`;
}

function renderStructureAudit() {
  const audit = state.structureAudit;
  if (!audit || !Array.isArray(audit.poles) || audit.poles.length === 0) {
    els.structureAuditBox.innerHTML = "";
    return;
  }

  const summaryClass = audit.ok ? "ok" : "warn";
  const visiblePoles = audit.poles
    .map((pole) => {
      const details = Array.isArray(pole.details) ? pole.details : [];
      const visibleDetails = details.filter((d) => !d.ok);
      return { ...pole, details: visibleDetails };
    })
    .filter((pole) => !pole.ok || pole.details.length > 0);
  const mismatchCount = toInt(audit.mismatch_count, 0);
  if (visiblePoles.length === 0 && mismatchCount === 0 && audit.ok) {
    els.structureAuditBox.innerHTML = "";
    return;
  }
  const metrics = [];
  if (!audit.ok) metrics.push(`<span class="metric-chip warn">Status: Divergências</span>`);
  if (mismatchCount > 0) metrics.push(`<span class="metric-chip warn">Ocorrências: ${mismatchCount}</span>`);

  const polesHtml = visiblePoles
    .map((pole) => {
      const poleStatus = pole.ok ? "ok" : "err";
      const details = Array.isArray(pole.details) ? pole.details : [];
      const detailRows = details
        .map((d) => {
          const detailStatus = d.ok ? "ok" : "err";
          const missing = Array.isArray(d.missing) ? d.missing : [];
          const missingList = missing.length
            ? `<ul class="audit-missing-list">${missing
              .map(
                (m) =>
                  `<li><strong>${escapeHtml(m.sap)}</strong> esperado ${escapeHtml(
                    m.expected
                  )}, calculado ${escapeHtml(m.actual)} (faltante ${escapeHtml(
                    m.shortfall
                  )})</li>`
              )
              .join("")}</ul>`
            : "";

          return `
            <div class="audit-detail-row ${detailStatus}">
              <div class="audit-detail-head">
                <span class="audit-structure">${escapeHtml(d.structure || "-")}</span>
                <span class="audit-canonical">→ ${escapeHtml(d.canonical || "-")}</span>
                <span class="audit-badge ${detailStatus}">${d.ok ? "OK" : "Divergência"}</span>
              </div>
              ${d.reason ? `<div class="audit-reason">Motivo: ${escapeHtml(d.reason)}</div>` : ""}
              ${missingList}
            </div>
          `;
        })
        .join("");

      return `
        <div class="audit-pole-card ${poleStatus}">
          <div class="audit-pole-head">
            <strong>${escapeHtml(pole.pole_id || "-")}</strong>
            <span>${escapeHtml(pole.pole_type || "-")}</span>
            ${pole.ok ? "" : `<span class="audit-badge ${poleStatus}">Com divergências</span>`}
          </div>
          <div class="audit-detail-list">${detailRows || "<div class='audit-empty'>Sem estruturas avaliadas.</div>"}</div>
        </div>
      `;
    })
    .join("");
  const auditContent = polesHtml || "<div class='audit-empty'>Nenhuma divergência de estrutura para exibir.</div>";

  els.structureAuditBox.innerHTML = `
    <div class="panel structure-audit-panel">
      <div class="panel-title">Conferência de Estruturas (Extração × Cálculo)</div>
      ${metrics.length ? `<div class="metrics-row">${metrics.join("")}</div>` : ""}
      <div class="audit-poles-grid">${auditContent}</div>
    </div>
  `;
}

function renderQualityGate() {
  const gate = buildGateState(state.qualityGate);
  const valFrag = buildValidationFragment();
  const gateHasDivergence =
    gate.blocked ||
    gate.errors > 0 ||
    gate.warnings > 0 ||
    gate.verificar_count > 0 ||
    gate.low_confidence_count > 0;
  // Painel único: aparece se houver divergência de validação OU de gate.
  if (!valFrag.has && !gateHasDivergence) {
    els.qualityGateBox.innerHTML = "";
    syncExportButtons();
    return;
  }

  const lowConfItems = state.bom.filter((row) => Number(row["Confiança"] || 0) < 0.7);
  const lowConfList = lowConfItems
    .slice(0, 8)
    .map(
      (row) =>
        `<li><strong>${escapeHtml(row["Código SAP"] || "")}</strong> - ${escapeHtml(row["Descrição"] || "")} (confiança ${Number(
          row["Confiança"] || 0
        ).toFixed(2)})</li>`
    )
    .join("");

  // Métricas unificadas: erros/avisos do gate e da validação são a mesma coisa
  // (o gate deriva da validação) → mostrar uma vez só.
  const errors = Math.max(gate.errors, valFrag.errors);
  const warnings = Math.max(gate.warnings, valFrag.warnings);
  const metrics = [];
  if (errors > 0) metrics.push(`<span class="metric-chip err">Erros: ${errors}</span>`);
  if (warnings > 0) metrics.push(`<span class="metric-chip warn">Avisos: ${warnings}</span>`);
  if (gate.verificar_count > 0) metrics.push(`<span class="metric-chip warn">VERIFICAR: ${gate.verificar_count}</span>`);
  if (gate.low_confidence_count > 0) metrics.push(`<span class="metric-chip warn">Baixa confiança: ${gate.low_confidence_count}</span>`);

  let alertHtml = "";
  if (gate.blocked) {
    const messages = [];
    if (gate.blocked_reasons.includes("erros_criticos")) {
      messages.push("Exportação bloqueada por erros críticos de validação.");
    }
    if (gate.blocked_reasons.includes("baixa_confianca_sem_confirmacao")) {
      messages.push("Exportação bloqueada até confirmar a revisão dos itens de baixa confiança.");
    }
    alertHtml = `<div class="gate-alert err">${messages.join(" ")}</div>`;
  } else if (gate.errors > 0 && gate.override_valid) {
    alertHtml = `<div class="gate-alert warn">Exportação liberada por override justificado.</div>`;
  } else {
    alertHtml = "";
  }

  const controlsHtml = `
      ${gate.low_confidence_count > 0
      ? `
          <div class="gate-check">
            <input id="lowConfReviewConfirmed" type="checkbox" ${gate.low_conf_review_confirmed ? "checked" : ""} />
            <label for="lowConfReviewConfirmed">Confirmo que revisei os itens de baixa confiança antes da exportação.</label>
          </div>
        `
      : ""
    }
      ${gate.errors > 0
      ? `
          <div class="gate-check">
            <input id="overrideEnabled" type="checkbox" ${gate.override_enabled ? "checked" : ""} />
            <label for="overrideEnabled">Forçar exportação mesmo com erro crítico.</label>
          </div>
          ${gate.override_enabled
        ? `<label>Justificativa obrigatória
                <textarea id="overrideReason" placeholder="Descreva o motivo operacional para liberar a exportação. Minimo de 10 caracteres.">${escapeHtml(
          gate.override_reason || ""
        )}</textarea>
              </label>`
        : ""
      }
        `
      : ""
    }`;
  const hasControls = gate.low_confidence_count > 0 || gate.errors > 0;

  els.qualityGateBox.innerHTML = `
    <div class="panel">
      <div class="panel-title">Validação e Qualidade</div>
      ${metrics.length ? `<div class="metrics-row">${metrics.join("")}</div>` : ""}
      ${valFrag.issuesHtml ? `<ul class="issue-list">${valFrag.issuesHtml}</ul>` : ""}
      ${lowConfList
      ? `<div class="panel-subtitle">Itens para revisão manual</div><ul class="low-conf-list">${lowConfList}</ul>`
      : ""
    }
      ${hasControls ? `<div class="gate-controls">${controlsHtml}</div>` : ""}
      ${alertHtml}
    </div>
  `;

  const lowConfCheckbox = document.getElementById("lowConfReviewConfirmed");
  if (lowConfCheckbox) {
    lowConfCheckbox.addEventListener("change", (event) => {
      state.gateUi.lowConfReviewConfirmed = Boolean(event.target.checked);
      renderQualityGate();
    });
  }

  const overrideCheckbox = document.getElementById("overrideEnabled");
  if (overrideCheckbox) {
    overrideCheckbox.addEventListener("change", (event) => {
      state.gateUi.overrideEnabled = Boolean(event.target.checked);
      if (!state.gateUi.overrideEnabled) {
        state.gateUi.overrideReason = "";
      }
      renderQualityGate();
    });
  }

  const overrideReasonEl = document.getElementById("overrideReason");
  if (overrideReasonEl) {
    overrideReasonEl.addEventListener("input", (event) => {
      // NÃO re-renderizar o painel aqui: isso reconstruiria a textarea e faria
      // perder o foco a cada tecla. Apenas atualiza o estado e revalida os
      // botões de exportação (libera quando a justificativa atinge 10 chars).
      state.gateUi.overrideReason = event.target.value;
      syncExportButtons();
    });
  }

  syncExportButtons();
}

async function downloadFromEndpoint(path, payload, filenameFallback) {
  const { blob, filename } = await fetchExportBlob(path, payload, filenameFallback);
  triggerBlobDownload(blob, filename);
}

async function fetchExportBlob(path, payload, filenameFallback) {
  const resp = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    let message = `Falha no download (${resp.status})`;
    try {
      const data = await resp.json();
      message = data.detail || message;
    } catch {
      const text = await resp.text();
      if (text) message = text;
    }
    throw new Error(message);
  }
  const blob = await resp.blob();
  return { blob, filename: filenameFallback };
}

function triggerBlobDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function buildProjectInfo() {
  const responsavel = (els.fiscal?.value || els.programador?.value || "").trim();
  return {
    Ordem: els.ordem.value || "",
    Equipe: els.equipe.value || "",
    Programador: responsavel,
  };
}

function getPdfPayload() {
  return getExportPayload({
    project_info: buildProjectInfo(),
    observacoes: els.observacoes.value || "",
  });
}

function getDiagramIdentifier() {
  const pdfName = String(els.pdfFile?.files?.[0]?.name || "").trim();
  if (pdfName) {
    return pdfName.replace(/\.pdf$/i, "");
  }
  return String(els.ordem?.value || "").trim() || "Nao informado";
}

function buildWhatsappMessage() {
  const diagram = getDiagramIdentifier();
  const equipe = String(els.equipe?.value || "").trim() || "Nao informada";
  return `Segue lista de material em PDF.\nDiagrama: ${diagram}\nEquipe: ${equipe}`;
}

// ── WhatsApp Send Flow ──────────────────────────────────────────────

const WA_RECENT_KEY = "wa_recent_contacts";
const WA_RECENT_MAX = 5;

function waGetRecent() {
  try { return JSON.parse(localStorage.getItem(WA_RECENT_KEY) || "[]"); }
  catch { return []; }
}

function waSaveRecent(phone) {
  const list = waGetRecent().filter(p => p !== phone);
  list.unshift(phone);
  localStorage.setItem(WA_RECENT_KEY, JSON.stringify(list.slice(0, WA_RECENT_MAX)));
}

function phoneToWaDigits(input) {
  const digits = input.replace(/\D/g, "");
  if (!digits) return "";
  if (digits.startsWith("55") && digits.length >= 12) return digits;
  if (digits.length >= 10) return "55" + digits;
  return digits;
}

function waRenderRecent() {
  const recentBox = document.getElementById("waRecentBox");
  const recentList = document.getElementById("waRecentList");
  if (!recentBox || !recentList) return;
  const contacts = waGetRecent();
  if (contacts.length === 0) { recentBox.hidden = true; return; }
  recentBox.hidden = false;
  recentList.innerHTML = "";
  for (const phone of contacts) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "waRecentBtn";
    btn.textContent = phone;
    btn.addEventListener("click", () => {
      const input = document.getElementById("waPhone");
      if (input) input.value = phone;
    });
    recentList.appendChild(btn);
  }
}

function openWhatsappModal() {
  const modal = document.getElementById("whatsappModal");
  const msgArea = document.getElementById("waMessage");
  const phoneInput = document.getElementById("waPhone");
  if (!modal) return;
  if (msgArea) msgArea.value = buildWhatsappMessage();
  if (phoneInput) phoneInput.value = "";
  waRenderRecent();
  modal.hidden = false;
  if (phoneInput) phoneInput.focus();
}

function closeWhatsappModal() {
  const modal = document.getElementById("whatsappModal");
  if (modal) modal.hidden = true;
}

function showWaBanner() {
  const banner = document.getElementById("waBanner");
  if (!banner) return;
  banner.hidden = false;
  document.getElementById("btnCloseWaBanner")?.addEventListener("click", () => {
    banner.hidden = true;
  }, { once: true });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) banner.hidden = true;
  }, { once: true });
}

async function prepareWhatsappSend() {
  const phoneRaw = String(document.getElementById("waPhone")?.value || "").trim();
  const message = String(document.getElementById("waMessage")?.value || buildWhatsappMessage()).trim();
  const btn = document.getElementById("btnPrepareWa");

  const waDigits = phoneToWaDigits(phoneRaw);
  // web.whatsapp.com/send compartilha a sessão já aberta no browser (mesmos cookies/localStorage).
  // wa.me redireciona e pode criar sessão isolada ou abrir o app desktop, exigindo QR.
  // Janela nomeada "wapp_calc": reutilizada a cada envio — sem novo QR após o primeiro login.
  const waUrl = waDigits
    ? `https://web.whatsapp.com/send?phone=${waDigits}&text=${encodeURIComponent(message)}`
    : `https://web.whatsapp.com/`;

  // Abre ANTES do await — preserva o contexto de gesto do usuário.
  // Após qualquer await, o browser classifica a abertura como popup não solicitado e bloqueia.
  const waWindow = window.open(waUrl, "wapp_calc");
  if (!waWindow) {
    throw new Error("O navegador bloqueou a abertura do WhatsApp. Permita popups para este site nas configuracoes do navegador.");
  }

  if (btn) { btn.disabled = true; btn.textContent = "Gerando PDF..."; }

  try {
    const { blob, filename } = await fetchExportBlob("/api/export/pdf", getPdfPayload(), "lista_materiais.pdf");
    triggerBlobDownload(blob, filename);
  } catch (err) {
    if (btn) { btn.disabled = false; btn.textContent = "Preparar Envio"; }
    throw new Error("Falha ao gerar o PDF: " + err.message);
  }

  if (waDigits) waSaveRecent(phoneRaw);

  if (btn) { btn.disabled = false; btn.textContent = "Preparar Envio"; }
  closeWhatsappModal();
  showWaBanner();
  setStatus(els.calcStatus, "PDF baixado e WhatsApp aberto.");
}

// Modal event bindings
document.getElementById("btnCloseWaModal")?.addEventListener("click", closeWhatsappModal);
document.getElementById("btnCancelWa")?.addEventListener("click", closeWhatsappModal);
document.getElementById("waModBackdrop")?.addEventListener("click", closeWhatsappModal);
document.getElementById("btnPrepareWa")?.addEventListener("click", async () => {
  try {
    await prepareWhatsappSend();
  } catch (err) {
    setStatus(els.calcStatus, err.message, false);
    closeWhatsappModal();
  }
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeWhatsappModal();
});

async function parseApiError(resp, fallbackMessage) {
  let message = fallbackMessage;
  const rawBody = await resp.text();
  if (rawBody) {
    try {
      const data = JSON.parse(rawBody);
      message = data?.detail || data?.message || rawBody;
    } catch {
      message = rawBody;
    }
  }
  if (resp.status === 401) {
    navigateToPath("/login");
  }
  if (resp.status === 404 && String(resp.url || "").includes("/api/")) {
    message = "API indisponível na publicação atual. Verifique o deploy das rotas /api no Vercel.";
  }
  return message;
}

function getAuthClient() {
  if (authClient) {
    return authClient;
  }
  if (!window.supabase || typeof window.supabase.createClient !== "function") {
    throw new Error("Biblioteca do Supabase não carregada.");
  }
  authClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
  return authClient;
}

async function ensureAuthenticatedSession() {
  try {
    const client = getAuthClient();
    const {
      data: { session },
      error,
    } = await client.auth.getSession();
    if (error) {
      throw error;
    }
    if (session?.access_token) {
      const syncResp = await apiFetch("/auth/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: session.access_token }),
      });
      if (syncResp.ok) {
        return true;
      }
    }
  } catch (_err) {
    // segue para redirecionamento
  }

  navigateToPath("/login");
  return false;
}

async function logoutAndRedirect() {
  try {
    const client = getAuthClient();
    await client.auth.signOut();
  } catch (_err) {
    // Mesmo com falha no signOut, redireciona para login.
  }
  navigateToPath("/login");
}

async function checkForUpdates() {
  try {
    els.btnCheckUpdate.disabled = true;
    els.btnApplyUpdate.disabled = true;
    setStatus(els.updateStatus, "Consultando atualizacoes...");
    const resp = await apiFetch("/api/update/check");
    if (!resp.ok) {
      const errorMessage = await parseApiError(resp, `Falha ao buscar atualizacao (${resp.status})`);
      throw new Error(errorMessage);
    }
    const data = await resp.json();
    updateState.available = Boolean(data.update_available);
    updateState.targetVersion = String(data.remote_version || "");
    updateState.packageUrl = String(data.package_url || "");

    if (updateState.available) {
      els.btnApplyUpdate.disabled = false;
      setStatus(els.updateStatus, `Nova versao disponivel: ${data.remote_version} (atual: ${data.local_version}).`);
    } else {
      setStatus(els.updateStatus, `Aplicacao atualizada (${data.local_version}).`);
    }
  } catch (err) {
    setStatus(els.updateStatus, err.message, false);
  } finally {
    els.btnCheckUpdate.disabled = false;
  }
}

async function applyUpdate() {
  try {
    if (!updateState.available || !updateState.packageUrl || !updateState.targetVersion) {
      throw new Error("Nenhuma atualizacao disponivel.");
    }
    els.btnCheckUpdate.disabled = true;
    els.btnApplyUpdate.disabled = true;
    setStatus(els.updateStatus, "Aplicando atualizacao. A aplicacao sera reiniciada ao final...");
    const resp = await apiFetch("/api/update/apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        target_version: updateState.targetVersion,
        package_url: updateState.packageUrl,
      }),
    });
    if (!resp.ok) {
      const errorMessage = await parseApiError(resp, `Falha ao aplicar atualizacao (${resp.status})`);
      throw new Error(errorMessage);
    }
    const data = await resp.json();
    setStatus(els.updateStatus, data.message || "Atualizacao iniciada. Aguarde alguns segundos e reabra o aplicativo.");
  } catch (err) {
    setStatus(els.updateStatus, err.message, false);
  } finally {
    els.btnCheckUpdate.disabled = false;
  }
}

async function loadVersionInfo() {
  if (!els.appVersionInfo) {
    return;
  }
  try {
    const resp = await apiFetch("/api/version");
    if (!resp.ok) {
      els.appVersionInfo.textContent = "Versao indisponivel no momento";
      return;
    }
    const data = await resp.json();
    els.appVersionInfo.textContent = `Versao ${data.version || "desconhecida"} | Autor: Evandro C. Toniolo`;
  } catch {
    els.appVersionInfo.textContent = "Versao indisponivel no momento";
  }
}

if (els.btnAddPole) {
  els.btnAddPole.addEventListener("click", () => {
    state.poles.push(ensurePoleDefaults({}, state.poles.length));
    renderPolesTable();
  });
}

if (els.btnAddCable) {
  els.btnAddCable.addEventListener("click", () => {
    state.cables.push(ensureCableDefaults({ Tipo: "BT", Desc: "", Qtd: 0 }));
    renderCablesTable();
  });
}

async function runCalculate() {
  try {
    collectPolesFromTable();
    collectCablesFromTable();
    resetGateUi();

    setStatus(els.calcStatus, "Calculando BOM...");
    els.bomTableBody.innerHTML = "";
    els.validationBox.innerHTML = "";
    els.structureAuditBox.innerHTML = "";
    els.qualityGateBox.innerHTML = "";
    els.recommendationsBox.innerHTML = "";
    if (els.bomPoleTableBody) {
      els.bomPoleTableBody.innerHTML = "";
    }

    const resp = await apiFetch("/api/calculate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ poles: state.poles, cables: state.cables }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || `Falha no calculo (${resp.status})`);

    state.bom = data.bom || [];
    state.bomByPole = data.bom_by_pole || {};
    state.structureAudit = data.structure_audit || null;
    state.selectedBomPole = "";
    state.validation = data.validation || null;
    state.recommendations = data.recommendations || [];
    state.qualityGate = data.quality_gate || null;

    renderBom();
    renderBomByPoleSelector();
    renderBomByPole();
    renderValidation();
    renderStructureAudit();
    renderQualityGate();
    renderRecommendations();
    setStatus(els.calcStatus, `BOM gerada com ${state.bom.length} itens.`);
  } catch (err) {
    setStatus(els.calcStatus, err.message, false);
  }
}

async function extractSelectedPdf() {
  try {
    const file = els.pdfFile?.files?.[0];
    if (!file) {
      return;
    }

    setStatus(els.extractStatus, "Extraindo PDF...");
    els.validationBox.innerHTML = "";
    els.structureAuditBox.innerHTML = "";
    els.qualityGateBox.innerHTML = "";
    els.recommendationsBox.innerHTML = "";
    const form = new FormData();
    form.append("file", file);

    let resp = await apiFetch("/api/extract", { method: "POST", body: form });
    if (!resp.ok && resp.status >= 500) {
      await new Promise((resolve) => setTimeout(resolve, 1200));
      resp = await apiFetch("/api/extract", { method: "POST", body: form });
    }
    if (!resp.ok) {
      const errorMessage = await parseApiError(resp, `Falha na extracao (${resp.status})`);
      throw new Error(errorMessage);
    }
    const data = await resp.json();

    state.poles = (data.poles || []).map((p, idx) => ensurePoleDefaults(p, idx));
    state.cables = (data.cables || []).map((c) => ensureCableDefaults(c));
    state.validation = null;
    state.recommendations = [];
    state.bom = [];
    state.bomByPole = {};
    state.structureAudit = null;
    state.selectedBomPole = "";
    state.qualityGate = null;
    resetGateUi();

    els.ordem.value = data.project_info?.Ordem || "";

    renderPolesTable();
    renderCablesTable();
    renderBom();
    renderBomByPoleSelector();
    renderBomByPole();
    renderValidation();
    renderStructureAudit();
    renderQualityGate();
    renderRecommendations();
    setStatus(
      els.extractStatus,
      `Extracao concluida: ${state.poles.length} postes, ${state.cables.length} cabos. Calculando BOM...`
    );

    await runCalculate();
    setStatus(els.extractStatus, `Extracao concluida: ${state.poles.length} postes, ${state.cables.length} cabos.`);
  } catch (err) {
    setStatus(els.extractStatus, err.message, false);
  }
}

if (els.pdfFile && APP_MODE === "programacao") {
  els.pdfFile.addEventListener("change", () => {
    void extractSelectedPdf();
  });
}

if (els.btnCalculate) {
  els.btnCalculate.addEventListener("click", runCalculate);
}

if (els.bomPoleSelect) {
  els.bomPoleSelect.addEventListener("change", () => {
    state.selectedBomPole = String(els.bomPoleSelect.value || "");
    renderBomByPole();
  });
}

if (els.btnDownloadCsv) {
  els.btnDownloadCsv.addEventListener("click", async () => {
    try {
      await downloadFromEndpoint("/api/export/csv", getExportPayload(), "lista_materiais.csv");
      setStatus(els.calcStatus, "CSV exportado com sucesso.");
    } catch (err) {
      setStatus(els.calcStatus, err.message, false);
    }
  });
}

if (els.btnDownloadPdf) {
  els.btnDownloadPdf.addEventListener("click", async () => {
    try {
      await downloadFromEndpoint("/api/export/pdf", getPdfPayload(), "lista_materiais.pdf");
      setStatus(els.calcStatus, "PDF exportado com sucesso.");
    } catch (err) {
      setStatus(els.calcStatus, err.message, false);
    }
  });
}

if (els.btnSendWhatsapp) {
  els.btnSendWhatsapp.addEventListener("click", () => openWhatsappModal());
}

if (els.btnCheckUpdate) {
  els.btnCheckUpdate.addEventListener("click", checkForUpdates);
}
if (els.btnApplyUpdate) {
  els.btnApplyUpdate.addEventListener("click", applyUpdate);
}
if (els.btnGoAsBuilt) {
  els.btnGoAsBuilt.addEventListener("click", () => navigateWithVersion("/as-built"));
}
if (els.btnGoProgramacao) {
  els.btnGoProgramacao.addEventListener("click", () => navigateWithVersion("/"));
}
if (els.btnLogout) {
  els.btnLogout.addEventListener("click", () => {
    logoutAndRedirect();
  });
}

async function bootstrapApp() {
  const isAuthenticated = await ensureAuthenticatedSession();
  if (!isAuthenticated) {
    return;
  }

  state.poles = [ensurePoleDefaults({}, 0)];
  state.cables = [ensureCableDefaults({ Tipo: "BT", Desc: "", Qtd: 0 })];
  renderDatalist("structureHints", structureHints);
  renderDatalist("cableDescHints", CABLE_DESC_HINTS);
  refreshStructureHints();
  renderPolesTable();
  renderCablesTable();
  renderBom();
  renderBomByPoleSelector();
  renderBomByPole();
  renderQualityGate();
  loadVersionInfo();
}

bootstrapApp();

window.addEventListener("pageshow", (e) => {
  if (e.persisted) {
    state.bom = [];
    state.bomByPole = {};
    state.qualityGate = null;
    state.validation = null;
    state.structureAudit = null;
    state.recommendations = [];
    renderBom();
    renderBomByPoleSelector();
    renderBomByPole();
    renderQualityGate();
  }
});

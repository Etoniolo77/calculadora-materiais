const state = {
  poles: [],
  cables: [],
  bom: [],
  validation: null,
};

const els = {
  pdfFile: document.getElementById("pdfFile"),
  btnExtract: document.getElementById("btnExtract"),
  extractStatus: document.getElementById("extractStatus"),
  ordem: document.getElementById("ordem"),
  equipe: document.getElementById("equipe"),
  programador: document.getElementById("programador"),
  observacoes: document.getElementById("observacoes"),
  polesTableBody: document.querySelector("#polesTable tbody"),
  cablesTableBody: document.querySelector("#cablesTable tbody"),
  btnAddPole: document.getElementById("btnAddPole"),
  btnAddCable: document.getElementById("btnAddCable"),
  btnCalculate: document.getElementById("btnCalculate"),
  calcStatus: document.getElementById("calcStatus"),
  validationBox: document.getElementById("validationBox"),
  bomTableBody: document.querySelector("#bomTable tbody"),
  btnDownloadCsv: document.getElementById("btnDownloadCsv"),
  btnDownloadPdf: document.getElementById("btnDownloadPdf"),
};

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

function ensurePoleDefaults(pole, idx) {
  const p = pole || {};
  const est = Array.isArray(p.Est) ? p.Est : [];
  const estaiQtd = typeof p.Estai === "object" ? toInt(p.Estai?.Qtd, 0) : toInt(p.Estai, 0);
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
    return ensurePoleDefaults(
      {
        id: id.toUpperCase(),
        Pole: poleType,
        Est: structures,
        Trafo: trafo,
        Chave: chave,
        Estai: { Type: "CC - 14M", Qtd: estaiQtd },
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
      <td><input data-field="id" value="${p.id}" /></td>
      <td><input data-field="Pole" value="${p.Pole}" /></td>
      <td><input data-field="Est" value="${p.Est.join(", ")}" /></td>
      <td><input data-field="Trafo" value="${p.Trafo || ""}" /></td>
      <td><input data-field="Chave" value="${p.Chave || ""}" /></td>
      <td><input data-field="EstaiQtd" type="number" min="0" step="1" value="${p.Estai.Qtd}" /></td>
      <td><button type="button" class="btnRemove">Remover</button></td>
    `;
    tr.querySelector(".btnRemove").addEventListener("click", () => {
      state.poles.splice(idx, 1);
      renderPolesTable();
    });
    tr.querySelectorAll("input").forEach((input) => {
      input.addEventListener("input", () => {
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
      <td><input data-field="Tipo" value="${c.Tipo}" /></td>
      <td><input data-field="Desc" value="${c.Desc}" /></td>
      <td><input data-field="Qtd" type="number" min="0" step="0.01" value="${c.Qtd}" /></td>
      <td><button type="button" class="btnRemove">Remover</button></td>
    `;
    tr.querySelector(".btnRemove").addEventListener("click", () => {
      state.cables.splice(idx, 1);
      renderCablesTable();
    });
    tr.querySelectorAll("input").forEach((input) => {
      input.addEventListener("input", () => {
        collectCablesFromTable();
      });
    });
    els.cablesTableBody.appendChild(tr);
  });
}

function renderBom() {
  els.bomTableBody.innerHTML = "";
  for (const row of state.bom) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row["Código SAP"] ?? ""}</td>
      <td>${row["Descrição"] ?? ""}</td>
      <td>${row["Quantidade"] ?? ""}</td>
    `;
    els.bomTableBody.appendChild(tr);
  }
}

function renderValidation() {
  if (!state.validation) {
    els.validationBox.innerHTML = "";
    return;
  }
  const v = state.validation;
  els.validationBox.innerHTML = `
    <strong>Validacao:</strong>
    Total: ${v.total || 0},
    Erros: ${v.errors || 0},
    Avisos: ${v.warnings || 0},
    Infos: ${v.infos || 0}
  `;
}

async function downloadFromEndpoint(path, payload, filenameFallback) {
  const resp = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    const msg = await resp.text();
    throw new Error(msg || `Falha no download (${resp.status})`);
  }
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filenameFallback;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

els.btnAddPole.addEventListener("click", () => {
  state.poles.push(ensurePoleDefaults({}, state.poles.length));
  renderPolesTable();
});

els.btnAddCable.addEventListener("click", () => {
  state.cables.push(ensureCableDefaults({ Tipo: "BT", Desc: "", Qtd: 0 }));
  renderCablesTable();
});

els.btnExtract.addEventListener("click", async () => {
  try {
    const file = els.pdfFile.files[0];
    if (!file) throw new Error("Selecione um PDF.");

    setStatus(els.extractStatus, "Extraindo PDF...");
    const form = new FormData();
    form.append("file", file);

    const resp = await fetch("/api/extract", { method: "POST", body: form });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || `Falha na extracao (${resp.status})`);

    state.poles = (data.poles || []).map((p, idx) => ensurePoleDefaults(p, idx));
    state.cables = (data.cables || []).map((c) => ensureCableDefaults(c));
    state.validation = data.validation || null;

    els.ordem.value = data.project_info?.Ordem || "";

    renderPolesTable();
    renderCablesTable();
    renderValidation();
    setStatus(els.extractStatus, `Extracao concluida: ${state.poles.length} postes, ${state.cables.length} cabos.`);
  } catch (err) {
    setStatus(els.extractStatus, err.message, false);
  }
});

els.btnCalculate.addEventListener("click", async () => {
  try {
    collectPolesFromTable();
    collectCablesFromTable();

    setStatus(els.calcStatus, "Calculando BOM...");
    const resp = await fetch("/api/calculate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ poles: state.poles, cables: state.cables }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || `Falha no calculo (${resp.status})`);

    state.bom = data.bom || [];
    state.validation = data.validation || null;

    renderBom();
    renderValidation();
    els.btnDownloadCsv.disabled = state.bom.length === 0;
    els.btnDownloadPdf.disabled = state.bom.length === 0;
    setStatus(els.calcStatus, `BOM gerada com ${state.bom.length} itens.`);
  } catch (err) {
    setStatus(els.calcStatus, err.message, false);
  }
});

els.btnDownloadCsv.addEventListener("click", async () => {
  try {
    await downloadFromEndpoint("/api/export/csv", { bom: state.bom }, "lista_materiais.csv");
  } catch (err) {
    setStatus(els.calcStatus, err.message, false);
  }
});

els.btnDownloadPdf.addEventListener("click", async () => {
  try {
    const project_info = {
      Ordem: els.ordem.value || "",
      Equipe: els.equipe.value || "",
      Programador: els.programador.value || "",
    };
    const observacoes = els.observacoes.value || "";
    await downloadFromEndpoint("/api/export/pdf", { bom: state.bom, project_info, observacoes }, "lista_materiais.pdf");
  } catch (err) {
    setStatus(els.calcStatus, err.message, false);
  }
});

state.poles = [ensurePoleDefaults({}, 0)];
state.cables = [ensureCableDefaults({ Tipo: "BT", Desc: "", Qtd: 0 })];
renderPolesTable();
renderCablesTable();

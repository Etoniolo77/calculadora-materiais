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
  polesJson: document.getElementById("polesJson"),
  cablesJson: document.getElementById("cablesJson"),
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

function safeJsonParse(raw, label) {
  try {
    return JSON.parse(raw);
  } catch (err) {
    throw new Error(`JSON invalido em ${label}: ${err.message}`);
  }
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

els.btnExtract.addEventListener("click", async () => {
  try {
    const file = els.pdfFile.files[0];
    if (!file) {
      throw new Error("Selecione um PDF.");
    }

    setStatus(els.extractStatus, "Extraindo PDF...");
    const form = new FormData();
    form.append("file", file);

    const resp = await fetch("/api/extract", { method: "POST", body: form });
    const data = await resp.json();
    if (!resp.ok) {
      throw new Error(data.detail || `Falha na extracao (${resp.status})`);
    }

    state.poles = data.poles || [];
    state.cables = data.cables || [];
    state.validation = data.validation || null;

    els.ordem.value = data.project_info?.Ordem || "";
    els.polesJson.value = JSON.stringify(state.poles, null, 2);
    els.cablesJson.value = JSON.stringify(state.cables, null, 2);

    renderValidation();
    setStatus(els.extractStatus, `Extracao concluida: ${state.poles.length} postes, ${state.cables.length} cabos.`);
  } catch (err) {
    setStatus(els.extractStatus, err.message, false);
  }
});

els.btnCalculate.addEventListener("click", async () => {
  try {
    const poles = safeJsonParse(els.polesJson.value || "[]", "postes");
    const cables = safeJsonParse(els.cablesJson.value || "[]", "cabos");
    if (!Array.isArray(poles)) {
      throw new Error("JSON de postes precisa ser array.");
    }
    if (!Array.isArray(cables)) {
      throw new Error("JSON de cabos precisa ser array.");
    }

    setStatus(els.calcStatus, "Calculando BOM...");
    const resp = await fetch("/api/calculate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ poles, cables }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      throw new Error(data.detail || `Falha no calculo (${resp.status})`);
    }

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
    await downloadFromEndpoint(
      "/api/export/pdf",
      { bom: state.bom, project_info, observacoes },
      "lista_materiais.pdf"
    );
  } catch (err) {
    setStatus(els.calcStatus, err.message, false);
  }
});

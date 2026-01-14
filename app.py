import streamlit as st
import pandas as pd
import os
import tempfile
import base64
from io import BytesIO
from extractor import ProjectExtractor
from engine import MaterialEngine
from final_report import PDFReport

st.set_page_config(page_title="Calculadora de Materiais", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    /* ═══════════════════════════════════════════════════════════════════════════
       DESIGN SYSTEM - CALCULADORA DE MATERIAIS
       Estilo técnico minimalista para engenharia elétrica
       ═══════════════════════════════════════════════════════════════════════════ */
    
    /* ─── TOKENS DE DESIGN ─────────────────────────────────────────────────── */
    :root {
        /* Cores Base */
        --bg-page: #FFFFFF;
        --panel-bg: #F7F7F7;
        --panel-border: #CCCCCC;
        --text-primary: #1A1A1A;
        --text-secondary: #555555;
        --divider: #E6E6E6;
        
        /* Cores de Marca */
        --brand: #0AA06E;           /* Verde Eletromarquez */
        --accent: #555555;          /* Cinza neutro (harmoniza com sidebar) */
        --accent-hover: #333333;
        --accent-bg: #F7F7F7;
        
        /* Cores de Estado */
        --danger: #C53939;
        --warning: #D98E04;
        --warning-bg: #FFF8E6;
        --warning-border: #F1D08B;
        --success: #2D8F55;
        
        /* Tabela */
        --table-header-bg: #FAFAFA;
        --table-row-alt: #FCFCFC;
        --table-hover: #F2F8FF;
        
        /* Espaçamentos */
        --spacing-xs: 4px;
        --spacing-sm: 8px;
        --spacing-md: 16px;
        --spacing-lg: 24px;
        --spacing-xl: 32px;
        
        /* Bordas */
        --radius-sm: 4px;
        --radius-md: 6px;
        --radius-lg: 8px;
    }
    
    /* ─── TIPOGRAFIA ───────────────────────────────────────────────────────── */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Roboto+Mono:wght@400;500&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
        font-size: 14px !important;
        line-height: 1.45 !important;
        color: var(--text-primary) !important;
        background-color: var(--bg-page) !important;
    }
    
    /* Títulos de Painéis - CAIXA ALTA */
    h1 { 
        font-size: 20px !important; 
        font-weight: 600 !important; 
        color: var(--text-primary) !important;
        text-transform: uppercase !important;
        letter-spacing: 0.5px !important;
        margin-bottom: var(--spacing-md) !important;
    }
    
    h2 { 
        font-size: 16px !important; 
        font-weight: 600 !important; 
        color: var(--text-primary) !important;
        margin-top: var(--spacing-sm) !important;
        margin-bottom: var(--spacing-sm) !important;
    }
    
    h3 { 
        font-size: 15px !important; 
        font-weight: 600 !important; 
        color: var(--text-primary) !important;
        text-transform: uppercase !important;
        letter-spacing: 0.3px !important;
        margin-top: var(--spacing-sm) !important; 
        margin-bottom: var(--spacing-md) !important; 
        border-bottom: 1px solid var(--divider) !important;
        padding-bottom: var(--spacing-sm) !important;
    }
    
    p, span, label, li { 
        font-size: 14px !important;
        color: var(--text-primary) !important;
    }
    
    /* Números e códigos - Roboto Mono */
    input[type="number"], 
    [data-testid="stNumberInput"] input,
    .stDataFrame td:last-child,
    code {
        font-family: 'Roboto Mono', monospace !important;
        font-size: 14px !important;
    }
    
    /* ─── LAYOUT PRINCIPAL ─────────────────────────────────────────────────── */
    .block-container {
        padding-top: 3rem !important; 
        max-width: 96% !important;
        padding-left: 2% !important;
        padding-right: 2% !important;
    }
    
    div[data-testid="stHorizontalBlock"] { 
        gap: var(--spacing-md) !important; 
    }
    
    /* ─── SIDEBAR ──────────────────────────────────────────────────────────── */
    section[data-testid="stSidebar"] { 
        background-color: var(--panel-bg) !important;
        border-right: 1px solid var(--panel-border) !important;
        padding-top: var(--spacing-lg) !important;
        width: 280px !important;
    }
    
    section[data-testid="stSidebar"] > div {
        padding: var(--spacing-md) !important;
    }

    /* Logo centralizado - reduzir margem */
    [data-testid="stSidebar"] [data-testid="stImage"] {
        display: flex !important; 
        justify-content: center !important; 
        width: 100% !important; 
        margin-bottom: var(--spacing-md) !important;
        margin-top: 0 !important;
    }
    [data-testid="stSidebar"] [data-testid="stImage"] img { 
        margin: 0 auto !important; 
    }
    
    /* ─── FILE UPLOADER (DRAG & DROP) ──────────────────────────────────────── */
    [data-testid='stFileUploader'] { 
        width: 100% !important; 
    }
    
    [data-testid='stFileUploader'] section {
        border: 1.5px dashed var(--panel-border) !important;
        border-radius: var(--radius-lg) !important;
        background: var(--bg-page) !important;
        padding: var(--spacing-lg) var(--spacing-md) !important;
        text-align: center !important;
        transition: all 0.2s ease !important;
    }
    
    [data-testid='stFileUploader'] section:hover {
        border-color: var(--accent) !important;
        background: var(--accent-bg) !important;
    }
    
    [data-testid='stFileUploader'] section > div {
        display: flex !important; 
        flex-direction: column !important; 
        align-items: center !important; 
        justify-content: center !important;
    }
    
    /* Ocultar texto padrão em inglês */
    [data-testid='stFileUploader'] section > div > div:first-child {
        font-size: 0 !important;
    }
    
    [data-testid='stFileUploader'] section > div > div:first-child::before {
        content: 'Arraste o arquivo PDF aqui' !important;
        font-size: 14px !important;
        color: var(--text-secondary) !important;
        display: block !important;
    }
    
    [data-testid='stFileUploader'] section > div > small {
        font-size: 0 !important;
    }
    
    [data-testid='stFileUploader'] section > div > small::before {
        content: 'Limite: 200MB por arquivo' !important;
        font-size: 12px !important;
        color: var(--text-secondary) !important;
    }
    
    [data-testid='stFileUploader'] section button { 
        margin: var(--spacing-md) auto 0 auto !important; 
        display: block !important;
        background: transparent !important;
        border: 1.5px solid var(--accent) !important;
        color: var(--accent) !important;
        border-radius: var(--radius-md) !important;
        padding: var(--spacing-sm) var(--spacing-md) !important;
        font-weight: 500 !important;
        font-size: 0 !important;
        transition: all 0.2s ease !important;
    }
    
    [data-testid='stFileUploader'] section button::before {
        content: 'Selecionar Arquivo' !important;
        font-size: 14px !important;
    }
    
    [data-testid='stFileUploader'] section button:hover {
        background: var(--accent-bg) !important;
        border-color: var(--accent-hover) !important;
        color: var(--accent-hover) !important;
    }
    
    [data-testid='stFileUploader'] label { 
        display: none !important; 
    }
    
    /* ─── LABELS DE WIDGETS ────────────────────────────────────────────────── */
    [data-testid="stWidgetLabel"] { 
        margin-bottom: 2px !important; 
        min-height: 0px !important; 
    }
    
    [data-testid="stWidgetLabel"] p {
        font-size: 12px !important;
        font-weight: 600 !important;
        color: var(--text-secondary) !important;
        text-transform: uppercase !important;
        letter-spacing: 0.3px !important;
    }
    
    .stSelectbox, .stNumberInput, .stTextInput, .stMultiSelect { 
        margin-bottom: 0px !important; 
    }
    
    /* ─── INPUTS E SELECTS ─────────────────────────────────────────────────── */
    input, select, [data-baseweb="select"] {
        border: 1px solid var(--panel-border) !important;
        border-radius: var(--radius-md) !important;
        background: var(--bg-page) !important;
        font-size: 14px !important;
        transition: all 0.2s ease !important;
    }
    
    input:focus, select:focus, [data-baseweb="select"]:focus-within {
        border-color: var(--accent) !important;
        outline: 2px solid var(--accent) !important;
        outline-offset: 2px !important;
        box-shadow: none !important;
    }
    
    /* ─── EXPANDERS (PAINÉIS DE POSTES) ────────────────────────────────────── */
    div[data-testid="stExpander"] {
        margin-bottom: var(--spacing-sm) !important;
        border: 1px solid var(--panel-border) !important;
        border-radius: var(--radius-md) !important;
        background: var(--panel-bg) !important;
        overflow: hidden !important;
    }
    
    div[data-testid="stExpander"] > details {
        border: none !important;
    }
    
    div[data-testid="stExpander"] summary {
        background: var(--panel-bg) !important;
        padding: var(--spacing-md) !important;
        font-weight: 500 !important;
        color: var(--text-primary) !important;
        border-bottom: 1px solid var(--divider) !important;
    }
    
    div[data-testid="stExpander"] summary:hover {
        background: var(--bg-page) !important;
    }
    
    div[data-testid="stExpander"] > details > div {
        padding: var(--spacing-md) !important;
        background: var(--bg-page) !important;
    }
    
    /* ─── BOTÕES ───────────────────────────────────────────────────────────── */
    .stButton > button {
        background: var(--panel-bg) !important;
        border: 1px solid var(--panel-border) !important;
        color: var(--text-primary) !important;
        border-radius: var(--radius-md) !important;
        padding: var(--spacing-sm) var(--spacing-md) !important;
        font-weight: 500 !important;
        font-size: 14px !important;
        transition: all 0.2s ease !important;
        cursor: pointer !important;
    }
    
    .stButton > button:hover {
        background: var(--accent-bg) !important;
        border-color: var(--accent-hover) !important;
        color: var(--accent-hover) !important;
    }
    
    .stButton > button:focus {
        outline: 2px solid var(--accent) !important;
        outline-offset: 2px !important;
        box-shadow: none !important;
    }
    
    .stButton > button:disabled {
        opacity: 0.6 !important;
        cursor: not-allowed !important;
    }
    
    /* Botão de download (estilo neutro igual sidebar) */
    .stDownloadButton > button, .pdf-btn {
        background: var(--panel-bg) !important;
        border: 1px solid var(--panel-border) !important;
        color: var(--text-primary) !important;
        border-radius: var(--radius-md) !important;
        padding: var(--spacing-sm) var(--spacing-lg) !important;
        font-weight: 600 !important;
        font-size: 14px !important;
        transition: all 0.2s ease !important;
        text-decoration: none !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        width: 100% !important;
        height: 42px !important;
    }
    
    .stDownloadButton > button:hover, .pdf-btn:hover {
        background: var(--divider) !important;
        border-color: var(--text-secondary) !important;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05) !important;
        color: var(--text-primary) !important;
    }
    
    /* Botão de exclusão (perigo) */
    button[kind="secondary"]:has(span:contains("🗑️")),
    .stButton > button:has(span:contains("🗑️")) {
        border-color: var(--danger) !important;
        color: var(--danger) !important;
    }
    
    .stButton > button:has(span:contains("🗑️")):hover {
        background: #FDEAEA !important;
    }
    
    /* ─── DATA EDITOR / TABELAS ────────────────────────────────────────────── */
    [data-testid="stDataFrame"] {
        border: 1px solid var(--panel-border) !important;
        border-radius: var(--radius-md) !important;
        overflow: hidden !important;
    }
    
    /* Header da tabela */
    [data-testid="stDataFrame"] [role="columnheader"] {
        background: var(--table-header-bg) !important;
        color: var(--text-primary) !important;
        font-weight: 600 !important;
        font-size: 13px !important;
        text-transform: uppercase !important;
        letter-spacing: 0.3px !important;
        border-bottom: 1px solid var(--divider) !important;
        position: sticky !important;
        top: 0 !important;
        z-index: 10 !important;
    }
    
    /* Células da tabela */
    [data-testid="stDataFrame"] [role="gridcell"] {
        font-size: 13px !important;
        border-bottom: 1px solid var(--divider) !important;
        padding: var(--spacing-sm) !important;
    }
    
    /* Zebra striping sutil */
    [data-testid="stDataFrame"] [role="row"]:nth-child(even) {
        background: var(--table-row-alt) !important;
    }
    
    [data-testid="stDataFrame"] [role="row"]:nth-child(odd) {
        background: var(--bg-page) !important;
    }
    
    /* Hover na linha */
    [data-testid="stDataFrame"] [role="row"]:hover {
        background: var(--table-hover) !important;
    }
    
    /* Números alinhados à direita com Roboto Mono */
    [data-testid="stDataFrame"] [role="gridcell"]:last-child {
        font-family: 'Roboto Mono', monospace !important;
        text-align: right !important;
    }
    
    /* Ocultar coluna de índice */
    [data-testid="stDataFrameResizable"] [data-testid="StyledDataFrameRowNumber"] { 
        display: none !important; 
    }
    div[data-testid="stDataFrame"] [class*="glideDataEditor"] [aria-colindex="1"] { 
        display: none !important; 
    }
    
    [data-testid="stTable"] thead tr th:first-child { display: none !important; }
    [data-testid="stTable"] tbody tr td:first-child { display: none !important; }
    
    /* ─── CONTAINERS / PAINÉIS ─────────────────────────────────────────────── */
    [data-testid="stVerticalBlock"] > div:has(> [data-testid="stDataFrame"]) {
        background: var(--panel-bg) !important;
        border: 1px solid var(--panel-border) !important;
        border-radius: var(--radius-md) !important;
        padding: var(--spacing-md) !important;
    }
    
    /* Container com borda */
    div[data-testid="stContainer"]:has(> div) {
        border: 1px solid var(--panel-border) !important;
        border-radius: var(--radius-md) !important;
        background: var(--panel-bg) !important;
        padding: var(--spacing-md) !important;
    }
    
    /* ─── AVISOS E ALERTAS ─────────────────────────────────────────────────── */
    .stAlert {
        border-radius: var(--radius-md) !important;
        border: 1px solid !important;
    }
    
    /* Info (neutro) */
    [data-testid="stAlert"][data-baseweb="notification"]:has([data-testid*="info"]),
    .stAlert:has(.stAlertContentInfo) {
        background: var(--accent-bg) !important;
        border-color: var(--accent) !important;
    }
    
    /* Warning */
    div[data-testid="stAlert"]:has(svg[data-testid*="warning"]),
    .element-container:has(.stAlert) .stAlert:not(:has([data-testid*="success"])):not(:has([data-testid*="error"])) {
        background: var(--warning-bg) !important;
        border-color: var(--warning-border) !important;
    }
    
    /* Success */
    [data-testid="stAlert"]:has([data-testid*="success"]) {
        background: #E8F5EC !important;
        border-color: var(--success) !important;
    }
    
    /* Error */
    [data-testid="stAlert"]:has([data-testid*="error"]) {
        background: #FDEAEA !important;
        border-color: var(--danger) !important;
    }
    
    /* st.info específico para sidebar */
    section[data-testid="stSidebar"] .stAlert {
        background: var(--warning-bg) !important;
        border: 1px solid var(--warning-border) !important;
        border-radius: var(--radius-md) !important;
        padding: var(--spacing-sm) var(--spacing-md) !important;
    }
    
    /* ─── DIVIDERS ─────────────────────────────────────────────────────────── */
    hr, [data-testid="stHorizontalBlock"] + hr {
        border: none !important;
        border-top: 1px solid var(--divider) !important;
        margin: var(--spacing-md) 0 !important;
    }
    
    /* ─── CAPTIONS E METADADOS ─────────────────────────────────────────────── */
    .stCaption, [data-testid="stCaption"] {
        color: var(--text-secondary) !important;
        font-size: 12px !important;
    }
    
    /* Totais em destaque */
    .stCaption strong, [data-testid="stCaption"] strong {
        font-weight: 600 !important;
        color: var(--text-primary) !important;
    }
    
    /* ─── SPINNER / LOADING ────────────────────────────────────────────────── */
    .stSpinner > div {
        border-color: var(--accent) transparent transparent transparent !important;
    }
    
    /* ─── MULTISELECT TAGS ─────────────────────────────────────────────────── */
    [data-baseweb="tag"] {
        background: var(--panel-bg) !important;
        border: 1px solid var(--panel-border) !important;
        border-radius: var(--radius-md) !important;
        color: var(--text-primary) !important;
        font-size: 13px !important;
    }
    
    /* ─── TOOLTIP ──────────────────────────────────────────────────────────── */
    [data-baseweb="tooltip"] {
        background: var(--text-primary) !important;
        color: var(--bg-page) !important;
        border-radius: var(--radius-sm) !important;
        font-size: 12px !important;
    }
    
    /* ─── ACESSIBILIDADE ───────────────────────────────────────────────────── */
    *:focus-visible {
        outline: 2px solid var(--accent) !important;
        outline-offset: 2px !important;
    }
    
    /* Skip to content para leitores de tela */
    .sr-only {
        position: absolute !important;
        width: 1px !important;
        height: 1px !important;
        padding: 0 !important;
        margin: -1px !important;
        overflow: hidden !important;
        clip: rect(0, 0, 0, 0) !important;
        white-space: nowrap !important;
        border: 0 !important;
    }

</style>
""", unsafe_allow_html=True)

# JavaScript para traduzir textos do uploader para português-BR
import streamlit.components.v1 as components
components.html("""
<script>
    // Função para traduzir textos do uploader
    function translateUploader() {
        const parent = window.parent.document;
        // Traduzir textos
        parent.querySelectorAll('[data-testid="stFileUploader"] section').forEach(section => {
            section.querySelectorAll('div, span, p').forEach(el => {
                if (el.textContent && el.textContent.includes('Drag and drop')) {
                    el.textContent = 'Arraste o arquivo aqui';
                }
                if (el.textContent && el.textContent.includes('Limit 200MB')) {
                    el.textContent = 'Limite: 200MB • PDF';
                }
            });
            // Traduzir botão Browse files
            section.querySelectorAll('button').forEach(btn => {
                if (btn.textContent && btn.textContent.includes('Browse')) {
                    btn.textContent = 'Selecionar Arquivo';
                }
            });
        });
    }
    
    // Executar após carregar e observar mudanças
    setTimeout(translateUploader, 500);
    setTimeout(translateUploader, 1500);
    const observer = new MutationObserver(translateUploader);
    observer.observe(window.parent.document.body, { childList: true, subtree: true });
</script>
""", height=0)

# Inicializar Engine
if 'engine' not in st.session_state:
    st.session_state.engine = MaterialEngine()
    with st.spinner("🚀 Iniciando motor de cálculo..."):
        st.session_state.engine.load_databases()

# Inicializar Session State para dados
if 'project_data' not in st.session_state:
    st.session_state.project_data = {}
if 'cables_data' not in st.session_state:
    st.session_state.cables_data = pd.DataFrame(columns=['Tipo', 'Desc', 'Qtd'])
if 'poles_data' not in st.session_state:
    st.session_state.poles_data = {}
if 'bom_df' not in st.session_state:
    st.session_state.bom_df = pd.DataFrame()

def calculate_bom():
    """Recalcula BOM baseado no estado atual dos widgets"""
    print("--- CALC_BOM STARTED ---")
    try:
        engine = st.session_state.engine
        materials = []
        
        # 1. Processar Cabos primeiro (necessário para resoluções dinâmicas como alças de bitola)
        cables_df = st.session_state.cables_data
        if not cables_df.empty:
            cables_list = cables_df.to_dict('records')
            materials.extend(engine.process_cables(cables_list))
            print(f"DEBUG: Materials after cables: {len(materials)}")
            
        # 2. Processar Postes
        current_poles = st.session_state.get('poles_data', {})
        print(f"DEBUG: Processing {len(current_poles)} poles")
        
        if current_poles:
            materials.extend(engine.process_form_data(current_poles))
            print(f"DEBUG: Materials after poles: {len(materials)}")
        else:
             print("DEBUG: No poles data found in session_state")
        
        # 3. Agrupar
        if materials:
            df = pd.DataFrame(materials)
            df_grouped = df.groupby(['Código SAP', 'Descrição']).agg({'Quantidade': 'sum'}).reset_index()
            # Ordenar por Descrição
            df_grouped = df_grouped.sort_values('Descrição')
            # Arredondar quantidades
            df_grouped['Quantidade'] = df_grouped['Quantidade'].apply(lambda x: round(x, 2))
            st.session_state.bom_df = df_grouped
        else:
            st.session_state.bom_df = pd.DataFrame()
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        st.error(f"Erro no cálculo: {e}")
        print(f"ERROR in calculate_bom: {e}")

# --- SIDEBAR: INFO DO PROJETO ---
with st.sidebar:
    # Logos
    if os.path.exists("assets/logo_eletromarquez.png"):
        # Centralizar logo
        caux1, caux2, caux3 = st.columns([1, 2, 1])
        with caux2:
            st.image("assets/logo_eletromarquez.png", width=120)
    
    # Exibir usuário logado
    try:
        if hasattr(st, 'user') and st.user:
            user_name = st.user.email.split('@')[0].upper()
            st.caption(f"👤 Usuário: **{user_name}**")
        elif hasattr(st, 'experimental_user') and st.experimental_user:
            user_name = st.experimental_user.email.split('@')[0].upper()
            st.caption(f"👤 Usuário: **{user_name}**")
    except:
        pass

    # st.title("⚡ DataProject") # Removido pedido user
    
    uploaded_file = st.file_uploader("📤 UPLOAD DO PROJETO", type="pdf", help="Arraste o PDF aqui ou clique para selecionar")
    
    st.divider()
    
    p_info = st.session_state.project_data
    
    p_info['Ordem'] = st.text_input("Ordem", value=p_info.get('Ordem', ''))
    
    # Dropdown de Equipes
    equipes_lista = sorted([
        "ELITR01", "ELITR02", "EMITR07", "EMVNO07", "EMBSF02", "ELVNO01", "EMIUN01", "EMNVE07", 
        "ELNVE01", "EMMCH01", "EMBSF03", "EMITR06", "EMBSF01", "EMITR03", "EMITR04", "EMMCH02", 
        "EMVNO01", "EMARA02", "EMVNO03", "EMARA01", "EMVNO04", "EMVNO05", "EMARA03", "EMITR05", 
        "EMVNO02", "EMITR02", "EMVNO09", "EMITR01", "EMITR08", "EMVNO06", "EMVNO08", "EMVNO10", 
        "EMARA04", "EMNVE10", "EMNVE11", "EMNVE04", "EMNVE03", "EMNVE08", "EMNVE09", "EMNVE06", 
        "EMNVE01", "EMNVE02", "EMNVE05"
    ])
    
    curr_equipe = p_info.get('Equipe', '')
    try: idx_eq = equipes_lista.index(curr_equipe)
    except: idx_eq = 0
    
    p_info['Equipe'] = st.selectbox("Equipe", options=equipes_lista, index=idx_eq)
    
    # Auto-preencher Programador se estiver vazio
    prog_value = p_info.get('Programador', '')
    if not prog_value:
        try:
            # Tentar pegar usuário do Streamlit Cloud
            if hasattr(st, 'user'):
                prog_value = st.user.email.split('@')[0].upper()
            elif hasattr(st, 'experimental_user'):
                prog_value = st.experimental_user.email.split('@')[0].upper()
            elif 'user' in st.session_state: # Fallback custom
                prog_value = st.session_state.user
        except:
            pass
            
    p_info['Programador'] = st.text_input("Programador", value=prog_value)
    
    # Data removida da UI conforme pedido (mantida internamente para o PDF)
    if 'Data' not in p_info or p_info['Data'] is None:
        from datetime import date
        p_info['Data'] = date.today()


# --- ÁREA PRINCIPAL ---

if uploaded_file:
    # Lógica de processamento apenas se for novo arquivo
    if 'last_uploaded' not in st.session_state or st.session_state.last_uploaded != uploaded_file.name:
        st.session_state.last_uploaded = uploaded_file.name
        
        # Salvar e processar
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded_file.read())
            tmp_path = tmp.name
        
        try:
            ext = ProjectExtractor(tmp_path)
            ext.extract_text()
            
            # Extrair Info
            info = ext.extract_project_info()
            st.session_state.project_data.update(info)
            
            # Extrair Cabos
            cables = ext.find_cables()
            if cables:
                st.session_state.cables_data = pd.DataFrame(cables)
            
            # Extrair Postes
            raw_poles = ext.find_structures_per_pole()
            st.session_state.poles_data = raw_poles
            
            # Autocalcular inicial
            calculate_bom()
            st.rerun() # Refresh para carregar dados
            
        except Exception as e:
            st.error(f"Erro ao ler PDF: {e}")
        finally:
            os.unlink(tmp_path)

    # Layout Principal: 2 Colunas (Editor vs Resultado) - Simétrico (50/50)
    col_editor, col_results = st.columns([1, 1])
    
    with col_editor:
        # Título da seção
        st.markdown("### ⚙️ POSTES E ESTRUTURAS")
        
        # Botão de adição abaixo do título
        if st.button("＋ ADICIONAR POSTE", key="add_pole_manual", help="Adicionar novo poste manualmente", use_container_width=True):
                new_pid = f"P{len(st.session_state.poles_data) + 1}M"
                st.session_state.poles_data[new_pid] = {
                    'Pole': 'C11/600',
                    'Est': [],
                    'Trafo': None,
                    'Chave': None,
                    'Estai': {'Type': 'CC - 14M', 'Qtd': 0},
                    'ParaRaio': {'Type': 'CRUZETA', 'Qtd': 0},
                    'Aterramento': {'Qtd': 0},
                    'Ramal': {'Type': None, 'Qtd': 0.0}
                }
                st.rerun()

        poles = st.session_state.poles_data
        if not poles:
            st.warning("Nenhum poste detectado. Use o botão acima para adicionar.")
        else:
            # Ordenar IDs (P1, P2, P10...)
            import re
            def sort_key(s):
                nums = re.findall(r'\d+', s)
                return int(nums[0]) if nums else 999

            sorted_ids = sorted(poles.keys(), key=sort_key)
            
            for p_id in sorted_ids:
                p_data = poles[p_id]
                
                # Resumo Inteligente
                summary = f"📍 {p_id} — {p_data.get('Pole', '---')}"
                est_preview = ', '.join(p_data.get('Est', []))
                if est_preview: summary += f" | {est_preview[:40]}..."
                
                with st.expander(summary, expanded=False):
                    
                    # LAYOUT EM DUAS LINHAS (Mais legível)
                    
                    # LINHA 1: Poste e Estruturas (Fundamentais)
                    row1_c1, row1_c2 = st.columns([1.2, 2.5])
                    
                    with row1_c1:
                        pole_opts = ["C12/1000", "C12/600", "C12/300", "C11/600", "C11/300", "DT11/1000", "DT11/600", "DT11/300"]
                        curr_p = p_data.get('Pole', 'C11/600')
                        if curr_p not in pole_opts: pole_opts.insert(0, curr_p)
                        new_p = st.selectbox("Tipo de Poste", pole_opts, index=pole_opts.index(curr_p), key=f"sel_p_{p_id}")
                        poles[p_id]['Pole'] = new_p
                        
                    with row1_c2:
                        # Verificar se db_loader e unified_db existem
                        if st.session_state.engine.db_loader and st.session_state.engine.db_loader.unified_db:
                            all_est_db = sorted(list(set(st.session_state.engine.db_loader.unified_db.get('structures', {}).keys())))
                        else:
                            all_est_db = []
                        curr_ests = [e for e in p_data.get('Est', []) if e]
                        combined_ests = sorted(list(set(all_est_db + curr_ests)))
                        new_ests = st.multiselect("Estruturas (Kits)", options=combined_ests, default=curr_ests, key=f"ms_est_{p_id}")
                        poles[p_id]['Est'] = new_ests

                    # LINHA 2: Equipamentos e Acessórios
                    row2_c1, row2_c2, row2_c3, row2_c4, row2_c5 = st.columns([1.2, 1.2, 0.8, 1.0, 0.4])
                    
                    with row2_c1:
                        trafo_opts = [None, "MONO-5", "MONO-10", "MONO-15", "MONO-25", "TRI-30", "TRI-45", "TRI-75", "TRI-112.5"]
                        curr_t = p_data.get('Trafo')
                        curr_t_short = curr_t.replace("kVA", "") if curr_t else None
                        new_t = st.selectbox("Trafo", trafo_opts, index=trafo_opts.index(curr_t_short) if curr_t_short in trafo_opts else 0, key=f"t_{p_id}")
                        poles[p_id]['Trafo'] = f"{new_t}kVA" if new_t else None
                        
                    with row2_c2:
                        chave_opts = [None, "FUSIVEL", "FACA", "RELIG", "SECC"]
                        curr_c = p_data.get('Chave')
                        new_c = st.selectbox("Chave", chave_opts, index=chave_opts.index(curr_c) if curr_c in chave_opts else 0, key=f"c_{p_id}")
                        poles[p_id]['Chave'] = new_c
                        
                    with row2_c3:
                        val_at = p_data.get('Aterramento', {})
                        curr_at = val_at.get('Qtd', 0) if isinstance(val_at, dict) else (int(val_at) if val_at else 0)
                        new_at = st.number_input("Terra (Qtd)", min_value=0, max_value=5, value=int(curr_at), key=f"at_{p_id}")
                        poles[p_id]['Aterramento'] = {'Qtd': new_at}
                        
                    with row2_c4:
                        estai_opts = [0, 1, 2, 3]
                        val_est = p_data.get('Estai', {})
                        curr_est_qtd = val_est.get('Qtd', 0) if isinstance(val_est, dict) else 0
                        new_est_qtd = st.selectbox("Estai (Qtd)", estai_opts, index=estai_opts.index(curr_est_qtd) if curr_est_qtd in estai_opts else 0, key=f"es_{p_id}")
                        poles[p_id]['Estai'] = {'Type': 'CC - 14M', 'Qtd': new_est_qtd}
                        
                    with row2_c5:
                        st.write("") # Espaçador para alinhar com inputs
                        st.write("")
                        if st.button("🗑️", key=f"del_{p_id}", help="Excluir poste"):
                            del st.session_state.poles_data[p_id]
                            st.rerun()

        st.divider()
        st.markdown("### ⚡ CONDUTORES")
        
        # Editor de Cabos
        cables_df = st.session_state.cables_data
        edited_cables = st.data_editor(
            cables_df,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Tipo": st.column_config.SelectboxColumn("Tipo", options=["MT", "BT"], width="small"),
                "Desc": st.column_config.TextColumn("Descrição", width="large"),
                "Qtd": st.column_config.NumberColumn("Metros", format="%.2f", width="small")
            },
            key="cables_editor"
        )
        st.session_state.cables_data = edited_cables
        
        # Campo de Observações
        st.divider()
        st.markdown("### 📝 OBSERVAÇÕES")
        if 'observacoes' not in st.session_state:
            st.session_state.observacoes = ""
        st.session_state.observacoes = st.text_area(
            "Observações do projeto",
            value=st.session_state.observacoes,
            height=100,
            placeholder="Digite observações que serão incluídas no relatório PDF...",
            label_visibility="collapsed"
        )

    # --- CÁLCULO SÍNCRONO ---
    # Agora que todos os inputs (poles e cabos) foram coletados e o session_state atualizado, 
    # rodamos o cálculo para garantir que os resultados reflitam o estado ATUAL da UI.
    if st.session_state.poles_data:
        calculate_bom()

    with col_results:
        st.markdown("### 📝 LISTA DE MATERIAIS")
        
        res_container = st.container(border=True)
        with res_container:
            df_bom = st.session_state.bom_df
            
            if not df_bom.empty:
                # Resetar índice para garantir que hide_index funcione
                df_bom_display = df_bom.reset_index(drop=True)
                
                # Tornar a lista EDITÁVEL
                edited_bom = st.data_editor(
                    df_bom_display,
                    column_config={
                        "Código SAP": st.column_config.TextColumn("SAP", width="small"),
                        "Descrição": st.column_config.TextColumn("Material", width="medium"),
                        "Quantidade": st.column_config.NumberColumn("Qtd", format="%.2f")
                    },
                    use_container_width=True,
                    height=600,
                    hide_index=True,
                    num_rows="dynamic",
                    key="bom_editor",
                    disabled=["Desc"] # Apenas exemplo se quiséssemos travar a descrição
                )
                
                # Lógica para preencher descrição automaticamente e validar quantidade
                if not edited_bom.equals(df_bom):
                    needs_update = False
                    error_msg = None
                    
                    for idx, row in edited_bom.iterrows():
                        sap = str(row['Código SAP']).strip()
                        desc = str(row['Descrição']).strip()
                        qty = row['Quantidade']
                        
                        # A. Autofill Descrição
                        if sap and (not desc or desc == "Material não localizado"):
                            if st.session_state.engine.db_loader and sap in st.session_state.engine.db_loader.sap_codes:
                                new_desc = st.session_state.engine.db_loader.sap_codes[sap]
                                if desc != new_desc:
                                    edited_bom.at[idx, 'Descrição'] = new_desc
                                    needs_update = True
                        
                        # B. Validação de Quantidade
                        if pd.isna(qty) or qty <= 0:
                            error_msg = f"Erro na linha {idx+1}: Quantidade deve ser superior a zero."
                    
                    if error_msg:
                        st.error(error_msg)
                    elif needs_update:
                        st.session_state.bom_df = edited_bom
                        st.rerun()
                    else:
                        st.session_state.bom_df = edited_bom

                total_itens = len(st.session_state.bom_df)
                total_pecas = st.session_state.bom_df['Quantidade'].sum()
                st.caption(f"**Total:** {total_itens} itens distintos | {total_pecas:.0f} peças")
                
                col_csv, col_pdf = st.columns(2)
                
                with col_csv:
                    # Garantir encoding utf-8-sig para Excel
                    csv_data = df_bom.to_csv(index=False, sep=';', encoding='utf-8-sig').encode('utf-8-sig')
                    st.download_button(
                        label="⬇ BAIXAR CSV",
                        data=csv_data,
                        file_name="lista_materiais_final.csv",
                        mime="text/csv",
                        use_container_width=True,
                        key="btn_csv_vfinal_stable"
                    )
                
                with col_pdf:
                    try:
                        p_data_clean = {k: str(v) if v is not None else "" for k,v in st.session_state.project_data.items()}
                        obs = st.session_state.get('observacoes', '')
                        
                        pdf_buffer = BytesIO()
                        pdf_gen = PDFReport(pdf_buffer)
                        pdf_gen.generate(p_data_clean, df_bom, obs)
                        pdf_bytes = pdf_buffer.getvalue()
                        
                        # Botão NATIVO para garantir o download correto
                        st.download_button(
                            label="📄 BAIXAR PDF",
                            data=pdf_bytes,
                            file_name="lista_materiais.pdf",
                            mime="application/pdf",
                            use_container_width=True,
                            key="btn_pdf_vfinal_stable"
                        )
                            
                    except Exception as e:
                        st.error(f"Erro ao gerar PDF: {e}")
            else:
                st.info("A lista será gerada aqui automaticamente.")

else:
    st.info("📤 Faça upload do PDF do projeto na barra lateral para começar.")

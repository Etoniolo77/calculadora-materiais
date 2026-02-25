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
       DESIGN SYSTEM - INDUSTRIAL PRECISION v2.0
       Estética brutalista-técnica para engenharia de alta performance.
       Agente: Frontend Specialist
       ═══════════════════════════════════════════════════════════════════════════ */
    
    /* ─── TOKENS DE DESIGN (INDUSTRIAL THEME) ─────────────────────────────── */
    :root {
        /* Base */
        --bg-page: #F4F5F7;          /* Cinza técnico muito claro */
        --bg-panel: #FFFFFF;         /* Branco puro para áreas de dados */
        --text-primary: #09090B;     /* Preto Quase Absoluto (Ink) */
        --text-secondary: #52525B;   /* Cinza Zinco Escuro */
        
        /* Marca & Acentos */
        --brand: #0AA06E;            /* Verde Eletromarquez (Identidade) */
        --brand-dark: #056B49;
        --accent: #18181B;           /* Preto Zinco (Acento Industrial) */
        
        /* Bordas & Linhas - O Segredo do Brutalismo Técnico */
        --border-default: 1px solid #D4D4D8;
        --border-strong: 1px solid #71717A;
        --border-focus: 2px solid #0AA06E;
        
        /* Estados */
        --success-bg: #DCFCE7;
        --success-text: #14532D;
        --warning-bg: #FEF3C7;
        --warning-text: #78350F;
        --danger-bg: #FEE2E2;
        --danger-text: #7F1D1D;
        
        /* Geometria (SHARP EDGES - 0px) */
        --radius-none: 0px;
        --radius-sm: 2px;
        
        /* Sombras (Hard Shadows) */
        --shadow-card: 4px 4px 0px 0px rgba(0,0,0,0.1);
        --shadow-hover: 6px 6px 0px 0px rgba(0,0,0,0.15);
    }
    
    /* ─── HERO LANDING PAGE ───────────────────────────────────────────────── */
    .hero-container {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 4rem 2rem;
        background: #FFFFFF;
        border: 1px solid #D4D4D8;
        box-shadow: var(--shadow-card);
        margin-bottom: 2rem;
        text-align: center;
    }
    
    .hero-title {
        font-family: 'JetBrains Mono', monospace;
        font-size: 24px;
        font-weight: 700;
        letter-spacing: -1px;
        margin-bottom: 1rem;
        color: var(--text-primary);
    }
    
    .hero-subtitle {
        color: var(--text-secondary);
        font-size: 14px;
        margin-bottom: 3rem;
        max-width: 500px;
    }
    
    /* ─── TIPOGRAFIA TÉCNICA ──────────────────────────────────────────────── */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif !important;
        color: var(--text-primary) !important;
        background-color: var(--bg-page) !important;
    }
    
    /* Dados Numéricos e Códigos = HERO */
    .stDataFrame td, input[type="number"], code, .stNumberInput input {
        font-family: 'JetBrains Mono', 'Roboto Mono', monospace !important;
        font-variant-numeric: tabular-nums !important; /* Alinhamento tabular */
        letter-spacing: -0.5px !important;
    }
    
    h1, h2, h3 {
        font-family: 'Inter', sans-serif !important;
        text-transform: uppercase !important;
        letter-spacing: 0.5px !important;
        font-weight: 700 !important;
        color: var(--accent) !important;
    }
    
    /* ─── COMPONENTES INDUSTRIAIS ─────────────────────────────────────────── */
    
    /* Cards / Containers (Sem bordas arredondadas, Sombra Dura) */
    div[data-testid="stExpander"], div[data-testid="stContainer"], 
    [data-testid="stVerticalBlock"] > div:has(> [data-testid="stDataFrame"]) {
        border: var(--border-default) !important;
        border-radius: var(--radius-none) !important;
        background: var(--bg-panel) !important;
        box-shadow: var(--shadow-card) !important;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }
    
    /* Hover Effect: "Lift" mecânico */
    div[data-testid="stExpander"]:hover {
        transform: translateY(-1px);
        box-shadow: var(--shadow-hover) !important;
        border-color: var(--border-strong) !important;
    }
    
    /* Inputs: Brutalistas */
    input, select, [data-baseweb="select"] {
        border-radius: var(--radius-none) !important;
        border: var(--border-default) !important;
        background-color: #FAFAFA !important;
        font-size: 14px !important;
    }
    
    input:focus, select:focus, [data-baseweb="select"]:focus-within {
        border: var(--border-focus) !important;
        background-color: #FFFFFF !important;
        box-shadow: none !important;
    }
    
    /* Botões: Engenharia Pura */
    .stButton > button {
        border-radius: var(--radius-none) !important;
        text-transform: uppercase !important;
        font-weight: 600 !important;
        letter-spacing: 0.5px !important;
        border: 1px solid var(--accent) !important;
        background: transparent !important;
        color: var(--accent) !important;
        transition: all 0.1s !important;
        box-shadow: 2px 2px 0px 0px var(--accent) !important; /* Botão 3D Flat */
    }
    
    .stButton > button:hover {
        transform: translate(1px, 1px) !important;
        box-shadow: 1px 1px 0px 0px var(--accent) !important;
        background: #F4F4F5 !important;
    }
    
    .stButton > button:active {
        transform: translate(2px, 2px) !important;
        box-shadow: none !important;
    }
    
    /* Botão Principal (Upload/Ação) */
    .stDownloadButton > button, .pdf-btn {
        background: var(--brand) !important;
        color: #FFFFFF !important;
        border: 1px solid var(--brand-dark) !important;
        box-shadow: 2px 2px 0px 0px var(--brand-dark) !important;
    }
    
    .stDownloadButton > button:hover {
        background: var(--brand-dark) !important;
        color: #FFFFFF !important;
    }
    
    /* ─── SIDEBAR TÉCNICA ─────────────────────────────────────────────────── */
    section[data-testid="stSidebar"] {
        background-color: #E4E4E7 !important; /* Zinc 200 */
        border-right: 1px solid #A1A1AA !important;
    }
    
    section[data-testid="stSidebar"] .stAlert {
        border-radius: var(--radius-none) !important;
        background: #FFFFFF !important;
        border: 1px solid #000 !important;
    }
    
    /* ─── TABELAS DE DADOS (DENSE) ────────────────────────────────────────── */
    [data-testid="stDataFrame"] {
        border: var(--border-strong) !important;
        border-radius: var(--radius-none) !important;
    }
    
    [data-testid="stDataFrame"] [role="columnheader"] {
        background: #E4E4E7 !important;
        color: #000 !important;
        font-weight: 700 !important;
        text-transform: uppercase !important;
        border-bottom: 2px solid #000 !important;
    }
    
    [data-testid="stDataFrame"] [role="row"]:nth-child(even) {
        background-color: #FAFAFA !important;
    }
    
    /* Coluna de Quantidade (Destaque) */
    [data-testid="stDataFrame"] [role="gridcell"]:last-child {
        font-weight: 700 !important;
        background-color: #F0FDF4 !important; /* Leve verde para números */
        color: var(--brand-dark) !important;
    }
    
    /* ─── ALERTS INDUSTRIAIS ──────────────────────────────────────────────── */
    .stAlert {
        border-radius: var(--radius-none) !important;
        border-left: 4px solid !important; /* Borda lateral grossa */
    }
    
    [data-testid="stAlert"]:has([data-testid*="success"]) {
        border-color: var(--success-text) !important;
        background: var(--success-bg) !important;
        color: var(--success-text) !important;
    }
    
    [data-testid="stAlert"]:has([data-testid*="warning"]) {
        border-color: var(--warning-text) !important;
        background: var(--warning-bg) !important;
        color: var(--warning-text) !important;
    }
    
    /* ─── LANDING PAGE: BIG BUTTONS ───────────────────────────────────────── */
    
    /* Configuração Base das Colunas da Landing */
    [data-testid="column"] {
        background: #FFFFFF;
        border: 1px solid #E4E4E7;
        padding: 2rem;
        border-radius: 0px;
        box-shadow: 4px 4px 0px 0px rgba(0,0,0,0.05);
        transition: all 0.2s ease;
        text-align: center;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        min-height: 200px; /* Altura fixa para simetria */
    }
    
    [data-testid="column"]:hover {
        transform: translateY(-2px);
        box-shadow: 6px 6px 0px 0px rgba(0,0,0,0.1);
        border-color: var(--brand);
    }

    /* Títulos dentro das colunas */
    [data-testid="column"] h5 {
        font-family: 'Inter', sans-serif !important;
        font-size: 16px !important;
        font-weight: 600 !important;
        color: var(--text-secondary) !important;
        margin-bottom: 1.5rem !important;
        text-transform: uppercase !important;
        letter-spacing: 1px !important;
    }

    /* ─── LANDING PAGE: BIG BUTTONS NATIVOS ───────────────────────────────── */
    .stButton button {
        width: 100% !important;
        height: 60px !important;
        border: 2px solid #18181B !important;
        border-radius: 0px !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-weight: 700 !important;
        font-size: 14px !important;
        color: #18181B !important;
        background: #FFFFFF !important;
        text-transform: uppercase !important;
        padding: 0 !important;
        transition: all 0.2s ease !important;
        box-shadow: none !important;
    }

    .stButton button:hover {
        background: #F4F4F5 !important;
        border-color: #0AA06E !important;
        color: #0AA06E !important;
        transform: translateY(-1px) !important;
    }
    
    .stButton button:active {
        background: #E4E4E7 !important;
        transform: translateY(1px) !important;
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
    
# --- CONTROLE DE FLUXO (NOVO) ---
if 'project_started' not in st.session_state:
    st.session_state.project_started = False
if 'manual_mode' not in st.session_state:
    st.session_state.manual_mode = False
if 'show_uploader' not in st.session_state:
    st.session_state.show_uploader = False

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
        # Filtrar postes válidos (que têm tipo definido)
        valid_poles = {k: v for k, v in current_poles.items() if v.get('Pole') and v.get('Pole') != "Selecione..."}
        
        print(f"DEBUG: Processing {len(valid_poles)} valid poles")
        
        if valid_poles:
            materials.extend(engine.process_form_data(valid_poles))
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
    
    # Init user_name safe
    user_name = "USUÁRIO"
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
    
    # Badge de Modo
    st.markdown("""
    <div style="text-align: center; margin-bottom: 20px;">
        <span style="background: #18181B; color: #FFF; padding: 4px 8px; border-radius: 0px; font-size: 10px; font-family: 'JetBrains Mono', monospace; letter-spacing: 1px; text-transform: uppercase;">
            INDUSTRIAL MODE v2.0
        </span>
    </div>
    """, unsafe_allow_html=True)
    
    st.divider()
    
    # DADOS DO PROJETO (Sempre visíveis mas discretos)
    p_info = st.session_state.project_data
    
    if st.session_state.project_started:
        st.markdown("### 📋 DADOS DO PROJETO")
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
        # Adicionar opção padrão
        equipes_lista.insert(0, "Selecione a Equipe...")
        
        curr_equipe = p_info.get('Equipe', '')
        try: idx_eq = equipes_lista.index(curr_equipe)
        except: idx_eq = 0
        
        sel_eq = st.selectbox("Equipe", options=equipes_lista, index=idx_eq)
        # Salvar apenas se não for o placeholder
        p_info['Equipe'] = sel_eq if sel_eq != "Selecione a Equipe..." else ""
        
        p_info['Programador'] = st.text_input("Programador", value=p_info.get('Programador', user_name))
        
        # Botão de Reset
        st.divider()
        if st.button("↺ NOVO PROJETO", type="primary", use_container_width=True):
             # Limpar estado
             st.session_state.project_started = False
             st.session_state.manual_mode = False
             st.session_state.poles_data = {}
             st.session_state.cables_data = pd.DataFrame(columns=['Tipo', 'Desc', 'Qtd'])
             st.session_state.bom_df = pd.DataFrame()
             st.session_state.last_uploaded = None
             st.rerun()

    # Data (hidden logic)
    if 'Data' not in p_info or p_info['Data'] is None:
        from datetime import date
        p_info['Data'] = date.today()


# --- ÁREA PRINCIPAL (LANDING PAGE & APP) ---

# Container para o Uploader (Para persistir estado)
# Se o projeto já começou, movemos para um expander discreto no topo
uploader_container = st.container()

if not st.session_state.project_started:
    # --- MODO LANDING PAGE ---
    with uploader_container:

        
        # Lógica de Alternância: Botões Simétricos vs Área de Upload
        st.markdown("""
        <style>
        /* Card Styling for Landing Page */
        .landing-card {
            background-color: #FFFFFF;
            border: 1px solid #E4E4E7;
            padding: 2rem;
            border-radius: 0px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
            height: 100%;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 1.5rem;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .landing-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
            border-color: #0AA06E;
        }
        .card-icon {
            font-size: 2rem;
            color: #18181B;
        }
        .card-title {
            font-family: 'Inter', sans-serif;
            font-weight: 600;
            font-size: 1.1rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #18181B;
            margin: 0;
        }
        .card-desc {
            font-size: 0.875rem;
            color: #71717A;
            text-align: center;
            margin: 0;
            line-height: 1.5;
        }
        /* Hide default uploader file list to keep it clean initially if desired, 
           but for now let's keep it standard functionality */
        </style>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="hero-container">
            <h1 class="hero-title">CALCULADORA DE MATERIAIS</h1>
            <p class="hero-subtitle">Selecione o método de entrada para iniciar o projeto.</p>
        </div>
        """, unsafe_allow_html=True)
        
        # --- CARD LAYOUT (New Implementation) ---
        c_upload, c_manual = st.columns(2, gap="large")

        with c_upload:
            with st.container():
                st.markdown("""
                <div class="landing-card-header" style="text-align: center; margin-bottom: 20px;">
                    <div class="card-title">📂 IMPORTAR PDF</div>
                    <div class="card-desc" style="margin-top: 5px;">Processamento automático via IA</div>
                </div>
                """, unsafe_allow_html=True)
                
                # Uploader direto
                uploaded_file = st.file_uploader("Arraste seu PDF aqui", type="pdf", key="main_uploader", label_visibility="visible")

        with c_manual:
             with st.container():
                # Espaçamento para alinhar visualmente com o uploader se necessário, 
                # mas vamos criar um visual de card similar
                st.markdown("""
                <div class="landing-card-header" style="text-align: center; margin-bottom: 20px;">
                    <div class="card-title">✏️ MODO MANUAL</div>
                    <div class="card-desc" style="margin-top: 5px;">Inserção direta de dados</div>
                </div>
                """, unsafe_allow_html=True)
                
                # Usar um container vazio para empurrar o botão para baixo se precisar alinhar alturas
                st.write("") 
                st.write("")
                
                if st.button("INICIAR PROJETO MANUAL", use_container_width=True, key="btn_manual_start", type="primary"):
                    st.session_state.manual_mode = True
                    st.session_state.project_started = True
                    st.session_state.last_uploaded = "MANUAL_START"
                    st.rerun()

else:
    # --- MODO APLICAÇÃO ---
    # Manter o uploader vivo mas discreto
    with uploader_container:
        if not st.session_state.manual_mode:
            with st.expander(f"📁 ARQUIVO ATUAL: {st.session_state.get('last_uploaded', 'Desconhecido')}", expanded=False):
                uploaded_file = st.file_uploader("Substituir PDF", type="pdf", key="main_uploader_persist", label_visibility="collapsed")
        else:
            uploaded_file = None # Modo manual não tem arquivo ativo

# LÓGICA DE PROCESSAMENTO (Unificada)
if uploaded_file or st.session_state.get('last_uploaded') == "MANUAL_START":
    
    # Detectar Novo Upload (Mudança de estado)
    if uploaded_file and (st.session_state.get('last_uploaded') != uploaded_file.name):
        st.session_state.last_uploaded = uploaded_file.name
        st.session_state.project_started = True 
        st.session_state.manual_mode = False
        
        # Limpar dados anteriores para evitar mistura
        st.session_state.poles_data = {}
        st.session_state.cables_data = pd.DataFrame(columns=['Tipo', 'Desc', 'Qtd'])
        st.session_state.bom_df = pd.DataFrame()
        # Resetar info básica mantendo o layout
        st.session_state.project_data = {'Ordem': '', 'Equipe': '', 'Programador': ''}
        
        # Processamento (Extração)
        with st.spinner("⚙️ Processando PDF Industrial..."):
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
                
            except Exception as e:
                st.error(f"Erro Crítico ao ler PDF: {e}")
            finally:
                if os.path.exists(tmp_path): os.unlink(tmp_path)
        
        st.rerun()

# Se não iniciou, parar renderização aqui (Landing Page only)
if not st.session_state.project_started:
    st.stop()

# --- ABAIXO: UI DO EDITOR (Só renderiza se project_started == True) ---

# Layout Principal: 2 Colunas (Editor vs Resultado)
col_editor, col_results = st.columns([1, 1])
    
with col_editor:
    # Título da seção
    st.markdown("### ⚙️ POSTES E ESTRUTURAS")
    
    # Botão de adição abaixo do título
    if st.button("＋ ADICIONAR POSTE", key="add_pole_manual", help="Adicionar novo poste manualmente", use_container_width=True):
            new_pid = f"P{len(st.session_state.poles_data) + 1}M"
            st.session_state.poles_data[new_pid] = {
                'Pole': None, # Iniciar vazio
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
                    pole_opts = ["C12/1000", "C12/600", "C12/300", "C11/600", "C11/300", "DT11/1000", "DT11/600", "DT11/300", "FC 11/600", "FC 11/300", "FC 12/600"]
                    curr_p = p_data.get('Pole')
                    
                    # Lógica para "Selecione..." ou valor atual
                    if not curr_p:
                        pole_opts.insert(0, "Selecione...")
                        idx = 0
                    elif curr_p not in pole_opts:
                        pole_opts.insert(0, curr_p)
                        idx = 0
                    else:
                        idx = pole_opts.index(curr_p)
                        
                    new_p_sel = st.selectbox("Tipo de Poste", pole_opts, index=idx, key=f"sel_p_{p_id}")
                    
                    # Salvar apenas se não for placeholder
                    if new_p_sel == "Selecione...":
                        poles[p_id]['Pole'] = None
                    else:
                        poles[p_id]['Pole'] = new_p_sel
                    
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
    
    # Auditoria Zero-Loss: Exibir GAPs se houver
    engine = st.session_state.engine
    if hasattr(engine, 'audit_log') and engine.audit_log:
        with st.expander(f"⚠️ GAPS DE INTEGRIDADE ({len(engine.audit_log)})", expanded=True):
            for gap in engine.audit_log:
                st.error(f"**{gap['type']}**: {gap['item']} em {gap['source']}")
            st.caption("DICA: Adicione o termo ao `vocabulary.json` ou valide o código no `Codigos de Materiais.xlsx`.")

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
            # Removido total de peças conforme solicitado (unidades mistas causavam confusão)
            st.caption(f"**Total:** {total_itens} itens distintos")
            
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


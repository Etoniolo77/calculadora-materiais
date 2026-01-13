import streamlit as st
import pandas as pd
import os
import tempfile
from extractor import ProjectExtractor
from engine import MaterialEngine

st.set_page_config(page_title="Calculadora de Materiais", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    /* Estilo Geral Premium */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif !important;
    }
    
    .block-container {padding-top: 2rem; padding-bottom: 2rem; max-width: 95%;}
    
    /* Fontes Menores e Cores Suaves */
    p, span { font-size: 0.8rem !important; color: #666; }
    h1 { font-size: 1.5rem !important; font-weight: 700; color: #2C3E50; margin-bottom: 0.8rem; }
    h3 { font-size: 1.05rem !important; font-weight: 600; color: #1F77B4; margin-top: 0.5rem; margin-bottom: 0.8rem; border-bottom: 1px solid #eee; padding-bottom: 5px; }
    
    /* Títulos de Widgets (Labels) Padronizados */
    [data-testid="stWidgetLabel"] p {
        font-size: 0.75rem !important;
        font-weight: 600 !important;
        color: #444 !important;
        margin-bottom: -2px !important;
        text-transform: uppercase;
        letter-spacing: 0.3px;
    }
    
    /* Inputs Compactos */
    .stSelectbox, .stNumberInput, .stTextInput, .stMultiSelect {
        margin-bottom: 0.4rem !important;
    }
    
    /* Expander Moderno */
    div[data-testid="stExpander"] {
        border: 1px solid #E9ECEF;
        border-radius: 10px;
        background-color: white;
        box-shadow: 0 2px 4px rgba(0,0,0,0.02);
        margin-bottom: 0.6rem;
    }
    
    div[data-testid="stExpander"] div[role="button"] p {
        font-size: 0.85rem !important;
        font-weight: 500;
        color: #2C3E50;
    }
    
    /* Buttons */
    .stButton button {
        border-radius: 8px !important;
        font-size: 0.8rem !important;
        border: 1px solid #ddd !important;
        background-color: white !important;
        color: #444 !important;
        padding: 0.25rem 0.5rem !important;
        height: auto !important;
    }
    
    /* Botão de Adição (Primary Style) */
    div[data-testid="column"] button[key*="add"] {
        background-color: #1F77B4 !important;
        color: white !important;
        border: none !important;
    }

    /* Otimização de Colunas e Alinhamento */
    [data-testid="column"] {
        gap: 0.5rem !important;
    }
    
    /* Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #F8F9FA;
    }
    
    /* Tradução File Uploader */
    [data-testid='stFileUploader'] section button::after {
        content: "Procurar arquivos";
        color: #333;
        visibility: visible;
        position: absolute;
        left: 50%;
        top: 50%;
        transform: translate(-50%, -50%);
        white-space: nowrap;
    }
    [data-testid='stFileUploader'] section > div:first-child > div > div > span { visibility: hidden; }
    [data-testid='stFileUploader'] section > div:first-child > div > div > span::after {
        content: "Arraste e solte o PDF aqui";
        visibility: visible;
        position: absolute; left: 0; right: 0; text-align: center;
    }
</style>
""", unsafe_allow_html=True)

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
            print(f"DEBUG: Final BOM size: {len(df_grouped)}")
        else:
            st.session_state.bom_df = pd.DataFrame()
            print("DEBUG: No materials generated")
            
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

    # st.title("⚡ DataProject") # Removido pedido user
    
    uploaded_file = st.file_uploader("📂 PDF do Projeto", type="pdf")
    
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
        
    st.info("💡 As alterações são processadas automaticamente.")

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
        # Título e Botão de Adição Manual
        header_l, header_r = st.columns([3, 1])
        with header_l:
            st.markdown("### 🏗️ Configuração de Postes e Ferragens")
        with header_r:
            if st.button("➕ Adicionar", key="add_pole_manual", help="Adicionar novo poste manualmente"):
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
                
                # Resumo para o título do expander
                summary = f"{p_id} — {p_data.get('Pole', '---')} | {', '.join(p_data.get('Est', []))[:20]}"
                with st.expander(f"📍 {summary}", expanded=False):
                    
                    # Linha 1: Poste e Estruturas
                    c1, c2 = st.columns([1, 2])
                    with c1:
                        pole_opts = ["C12/1000", "C12/600", "C12/300", "C11/600", "C11/300", "DT11/1000", "DT11/600", "DT11/300"]
                        curr_p = p_data.get('Pole', 'C11/600')
                        if curr_p not in pole_opts: pole_opts.insert(0, curr_p)
                        new_p = st.selectbox("Tipo de Poste", pole_opts, index=pole_opts.index(curr_p), key=f"sel_p_{p_id}")
                        poles[p_id]['Pole'] = new_p
                        
                    with c2:
                        all_est_db = sorted(list(set(st.session_state.engine.db_loader.unified_db.get('structures', {}).keys()))) if st.session_state.engine.db_loader else []
                        curr_ests = [e for e in p_data.get('Est', []) if e]
                        combined_ests = sorted(list(set(all_est_db + curr_ests)))
                        new_ests = st.multiselect("Estruturas (Kits)", options=combined_ests, default=curr_ests, key=f"ms_est_{p_id}")
                        poles[p_id]['Est'] = new_ests

                    st.markdown("<hr style='margin: 8px 0; opacity: 0.2;'>", unsafe_allow_html=True)
                    
                    # Linha 2: Trafo, Chave, Aterramento
                    h1, h2, h3 = st.columns(3)
                    with h1:
                        trafo_opts = [None, "MONO-5kVA", "MONO-10kVA", "MONO-15kVA", "MONO-25kVA", "TRI-30kVA", "TRI-45kVA", "TRI-75kVA", "TRI-112.5kVA"]
                        curr_t = p_data.get('Trafo')
                        if curr_t and curr_t not in trafo_opts: trafo_opts.append(curr_t)
                        new_t = st.selectbox("Equipamento Trafo", trafo_opts, index=trafo_opts.index(curr_t) if curr_t in trafo_opts else 0, key=f"t_{p_id}")
                        poles[p_id]['Trafo'] = new_t
                        
                    with h2:
                        chave_opts = [None, "FUSIVEL", "FACA", "RELIGADORA", "SECCIONADORA"]
                        curr_c = p_data.get('Chave')
                        if curr_c and curr_c not in chave_opts: chave_opts.append(curr_c)
                        new_c = st.selectbox("Equipamento Manobra", chave_opts, index=chave_opts.index(curr_c) if curr_c in chave_opts else 0, key=f"c_{p_id}")
                        poles[p_id]['Chave'] = new_c
                        
                    with h3:
                        val_at = p_data.get('Aterramento', {})
                        curr_at = val_at.get('Qtd', 0) if isinstance(val_at, dict) else (int(val_at) if val_at else 0)
                        new_at = st.number_input("Hastes Aterr.", min_value=0, value=int(curr_at), key=f"at_{p_id}")
                        poles[p_id]['Aterramento'] = {'Qtd': new_at}

                    # Linha 3: Estai e Para-Raio
                    r3c1, r3c2, r3c3, r3c4 = st.columns([1.4, 0.6, 1.4, 0.6])
                    with r3c1:
                        estai_opts = ["CC - 14M", "CC - 28M", "DT - 14M", "DT - 28M"]
                        val_e = p_data.get('Estai', {})
                        curr_et = val_e.get('Type', estai_opts[0]) if isinstance(val_e, dict) else estai_opts[0]
                        new_et = st.selectbox("Tipo de Estai", estai_opts, index=estai_opts.index(curr_et) if curr_et in estai_opts else 0, key=f"et_{p_id}")
                    with r3c2:
                        curr_eq = val_e.get('Qtd', 0) if isinstance(val_e, dict) else 0
                        new_eq = st.number_input("Estai (Qtd)", min_value=0, value=int(curr_eq), key=f"eq_{p_id}")
                        poles[p_id]['Estai'] = {'Type': new_et, 'Qtd': new_eq}
                    
                    with r3c3:
                        pr_opts = ["CRUZETA", "REDE COMPACTA", "REDE MONOFÁSICA"]
                        val_pr = p_data.get('ParaRaio', {})
                        curr_prt = val_pr.get('Type', pr_opts[0]) if isinstance(val_pr, dict) else pr_opts[0]
                        new_prt = st.selectbox("Tipo Para-Raio", pr_opts, index=pr_opts.index(curr_prt) if curr_prt in pr_opts else 0, key=f"prt_{p_id}")
                    with r3c4:
                        curr_prq = val_pr.get('Qtd', 0) if isinstance(val_pr, dict) else 0
                        new_prq = st.number_input("PR (Qtd)", min_value=0, value=int(curr_prq), key=f"prq_{p_id}")
                        poles[p_id]['ParaRaio'] = {'Type': new_prt, 'Qtd': new_prq}

                    # Linha 4: Ramal e Exclusão
                    r4c1, r4c2, r4c3 = st.columns([2.5, 1, 0.5])
                    with r4c1:
                        ramal_opts = [None, "CABO MULT 3X120+70", "CABO MULT 3X70+70", "CABO MULT 3X35+35", "CABO CONCENTRICO 1X16+16"]
                        val_r = p_data.get('Ramal', {})
                        curr_rt = val_r.get('Type') if isinstance(val_r, dict) else None
                        if curr_rt and curr_rt not in ramal_opts: ramal_opts.append(curr_rt)
                        new_rt = st.selectbox("Ramal de Ligação", ramal_opts, index=ramal_opts.index(curr_rt) if curr_rt in ramal_opts else 0, key=f"rt_{p_id}")
                    with r4c2:
                        curr_rq = val_r.get('Qtd', 0.0) if isinstance(val_r, dict) else 0.0
                        new_rq = st.number_input("Ramal (m)", min_value=0.0, step=1.0, value=float(curr_rq), key=f"rq_{p_id}")
                        poles[p_id]['Ramal'] = {'Type': new_rt, 'Qtd': new_rq}
                    with r4c3:
                        st.write("") # Spacer
                        if st.button("🗑️", key=f"del_{p_id}", help="Excluir este poste"):
                            del st.session_state.poles_data[p_id]
                            st.rerun()

        st.divider()
        st.markdown("### 🔌 Condutores e Vãos")
        
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

    # --- CÁLCULO SÍNCRONO ---
    # Agora que todos os inputs (poles e cabos) foram coletados e o session_state atualizado, 
    # rodamos o cálculo para garantir que os resultados reflitam o estado ATUAL da UI.
    if st.session_state.poles_data:
        calculate_bom()

    with col_results:
        st.markdown("### 📦 Lista de Materiais")
        
        res_container = st.container(border=True)
        with res_container:
            df_bom = st.session_state.bom_df
            
            if not df_bom.empty:
                # Tornar a lista EDITÁVEL
                edited_bom = st.data_editor(
                    df_bom,
                    column_config={
                        "Código SAP": st.column_config.TextColumn("SAP", width="small"),
                        "Descrição": st.column_config.TextColumn("Material", width="medium"),
                        "Quantidade": st.column_config.NumberColumn("Qtd", format="%.2f")
                    },
                    use_container_width=True,
                    height=600,
                    hide_index=True,
                    num_rows="dynamic",
                    key="bom_editor"
                )
                
                # Lógica para preencher descrição automaticamente se o SAP mudar
                # Se detectarmos uma linha nova ou SAP alterado sem descrição
                if not edited_bom.equals(df_bom):
                    # Verificar se há códigos SAP sem descrição
                    needs_update = False
                    for idx, row in edited_bom.iterrows():
                        sap = str(row['Código SAP']).strip()
                        desc = str(row['Descrição']).strip()
                        if sap and (not desc or desc == "Material não localizado"):
                            if st.session_state.engine.db_loader and sap in st.session_state.engine.db_loader.sap_codes:
                                edited_bom.at[idx, 'Descrição'] = st.session_state.engine.db_loader.sap_codes[sap]
                                needs_update = True
                    
                    st.session_state.bom_df = edited_bom
                    if needs_update:
                        st.rerun()

                total_itens = len(st.session_state.bom_df)
                total_pecas = st.session_state.bom_df['Quantidade'].sum()
                st.caption(f"Total: {total_itens} itens distintos | {total_pecas:.0f} peças")
                
                col_csv, col_pdf = st.columns(2)
                
                with col_csv:
                    csv = df_bom.to_csv(index=False, sep=';', encoding='utf-8-sig')
                    st.download_button(
                        "💾 Baixar CSV",
                        csv,
                        "lista_materiais_final.csv",
                        "text/csv",
                        use_container_width=True
                    )
                
                with col_pdf:
                    from final_report import PDFReport
                    from io import BytesIO
                    
                    buff = BytesIO()
                    report = PDFReport(buff)
                    
                    p_data_clean = {k: str(v) if v is not None else "" for k,v in st.session_state.project_data.items()}
                    
                    report.generate(p_data_clean, df_bom)
                    
                    st.download_button(
                        "📄 Baixar PDF",
                        data=buff.getvalue(),
                        file_name="lista_materiais.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
            else:
                st.info("A lista será gerada aqui automaticamente.")

else:
    st.info("👈 Comece fazendo upload do PDF na barra lateral.")

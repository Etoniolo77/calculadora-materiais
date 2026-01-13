import streamlit as st
import pandas as pd
import os
import tempfile
from extractor import ProjectExtractor
from engine import MaterialEngine

st.set_page_config(page_title="Calculadora de Materiais", layout="wide", initial_sidebar_state="expanded")

# CSS para tornar a UI mais compacta
st.markdown("""
<style>
    .block-container {padding-top: 1rem; padding-bottom: 2rem;}
    .element-container {margin-bottom: 0.5rem;}
    div[data-testid="stExpander"] div[role="button"] p {font-size: 1rem; font-weight: bold;}
    .small-font {font-size: 0.85rem;}
    h1 {font-size: 1.8rem; margin-bottom: 0px;}
    h3 {font-size: 1.2rem; margin-top: 10px; margin-bottom: 5px; color: #1f77b4;}
    .stButton button {width: 100%;}
    hr {margin-top: 10px; margin-bottom: 10px;}
    
    /* Reduce Sidebar Top Padding */
    section[data-testid="stSidebar"] div.block-container {
        padding-top: 1rem;
    }
    
    /* Tradução File Uploader (Hack CSS) */
    [data-testid='stFileUploader'] {
        width: 100%;
    }
    [data-testid='stFileUploader'] section > input + div {
        display: none;
    }
    /* Texto "Drag and drop file here" */
    [data-testid='stFileUploader'] section > div:first-child > div > div > span {
        visibility: hidden;
    }
    [data-testid='stFileUploader'] section > div:first-child > div > div > span::after {
        content: "Arraste e solte o arquivo PDF aqui";
        visibility: visible;
        position: absolute;
        left: 0;
        right: 0;
        text-align: center;
    }
    /* Texto "Limit 200MB per file • PDF" */
    [data-testid='stFileUploader'] section > div:first-child > div > small {
        visibility: hidden;
    }
    [data-testid='stFileUploader'] section > div:first-child > div > small::after {
        content: "Limite 200MB por arquivo • PDF";
        visibility: visible;
        position: absolute;
        left: 0;
        right: 0;
        text-align: center;
    }
    /* Botão "Browse files" */
    [data-testid='stFileUploader'] section button {
        color: transparent; /* Esconde texto original */
        position: relative;
        min-width: 160px; /* Garante tamanho para texto PT-BR */
    }
    [data-testid='stFileUploader'] section button::after {
        content: "Procurar arquivos";
        color: rgb(49, 51, 63); /* Cor do texto original */
        visibility: visible;
        position: absolute;
        left: 50%;
        top: 50%;
        transform: translate(-50%, -50%);
        white-space: nowrap;
        font-weight: normal;
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
        
        # 1. Processar Postes (do session_state.poles_data)
        current_poles = st.session_state.get('poles_data', {})
        print(f"DEBUG: Processing {len(current_poles)} poles")
        
        if not current_poles:
             print("DEBUG: No poles data found in session_state")

        materials.extend(engine.process_form_data(current_poles))
        print(f"DEBUG: Materials after poles: {len(materials)}")
        
        # 2. Processar Cabos (do editor)
        cables_df = st.session_state.cables_data
        if not cables_df.empty:
            cables_list = cables_df.to_dict('records')
            materials.extend(engine.process_cables(cables_list))
            print(f"DEBUG: Materials after cables: {len(materials)}")
        
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
    p_info['Programador'] = st.text_input("Programador", value=p_info.get('Programador', ''))
    
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
        # 1. Postes e Estruturas
        st.markdown("### 🏗️ Postes e Estruturas")
        
        poles = st.session_state.poles_data
        if not poles:
            st.warning("Nenhum poste detectado.")
        else:
            sorted_ids = sorted(poles.keys(), key=lambda x: int(x.replace('P', '')))
            
            for p_id in sorted_ids:
                p_data = poles[p_id]
                
                with st.expander(f"📍 **{p_id}** - {p_data.get('Pole', 'Desconhecido')}", expanded=False):
                    
                    # Linha 1: Tipo Poste + Estruturas (Multiselect)
                    c1, c2 = st.columns([1, 2])
                    with c1:
                        new_pole = st.selectbox(
                            "Tipo Poste",
                            options=[p_data['Pole'], "C12/1000", "C12/600", "C11/600", "C11/300", "DT 12/1000"],
                            index=0,
                            key=f"pole_type_{p_id}",
                            label_visibility="collapsed"
                        )
                        poles[p_id]['Pole'] = new_pole
                        
                    with c2:
                        all_opts = sorted(set(p_data['Est'] + ["N1", "N2", "N3", "B1", "B2F", "B3", "U3", "U4", "1S1", "1S3", "1S4", "ET1T", "ET4A"]))
                        new_est = st.multiselect(
                            "Estruturas",
                            options=all_opts,
                            default=p_data['Est'],
                            key=f"est_{p_id}",
                            label_visibility="collapsed"
                        )
                        poles[p_id]['Est'] = new_est

                    st.markdown("<hr style='margin: 5px 0;'>", unsafe_allow_html=True)

                    st.markdown("<hr style='margin: 5px 0;'>", unsafe_allow_html=True)
                    
                    # --- CONFIG HARDWARE ---
                    
                    # Linha 1: Trafo, Chave, Aterramento
                    h1, h2, h3 = st.columns(3)
                    
                    with h1:
                        curr_trafo = p_data.get('Trafo')
                        trafo_opts = [None, "MONO-10kVA", "MONO-15kVA", "MONO-25kVA", "TRI-30kVA", "TRI-45kVA", "TRI-75kVA", "TRI-112.5kVA"]
                        
                        # Se existe um valor extraído que não está na lista padrão, adicioná-lo
                        if curr_trafo and curr_trafo not in trafo_opts:
                            trafo_opts.append(curr_trafo)
                            
                        try: idx = trafo_opts.index(curr_trafo)
                        except: idx = 0
                        new_trafo = st.selectbox("Trafo", trafo_opts, index=idx, key=f"trafo_{p_id}")
                        poles[p_id]['Trafo'] = new_trafo
                    
                    with h2:
                        curr_chave = p_data.get('Chave')
                        chave_opts = [None, "FUSIVEL", "FACA", "RELIGADORA"]
                        
                        # Se existe um valor extraído que não está na lista padrão, adicioná-lo
                        if curr_chave and curr_chave not in chave_opts:
                            chave_opts.append(curr_chave)
 
                        try: idx_c = chave_opts.index(curr_chave)
                        except: idx_c = 0
                        new_chave = st.selectbox("Chave", chave_opts, index=idx_c, key=f"chave_{p_id}")
                        poles[p_id]['Chave'] = new_chave
                        
                    with h3:
                        val_aterr = p_data.get('Aterramento', 0)
                        if isinstance(val_aterr, dict):
                            curr_aterr_qtd = int(val_aterr.get('Qtd', 0))
                        else:
                            curr_aterr_qtd = int(val_aterr) if val_aterr else 0
                        
                        new_aterr = st.number_input("Aterramento (Qtd)", min_value=0, value=curr_aterr_qtd, key=f"aterr_{p_id}")
                        poles[p_id]['Aterramento'] = {'Qtd': new_aterr} # Padronizando como dict

                    # Linha 2: Estai e Para-Raio
                    r2c1, r2c2, r2c3, r2c4 = st.columns([2, 1, 2, 1])
                    
                    # Estai
                    with r2c1:
                        estai_opts = ["CC - 14M", "CC - 28M", "DT - 14M", "DT - 28M"]
                        val_estai = p_data.get('Estai', {})
                        curr_estai_type = val_estai.get('Type', estai_opts[0]) if isinstance(val_estai, dict) else estai_opts[0]
                        # Tentar recuperar índice seguro
                        try: idx_e = estai_opts.index(curr_estai_type) 
                        except: idx_e = 0
                        new_estai_type = st.selectbox("Estai Tipo", estai_opts, index=idx_e, key=f"estai_t_{p_id}", label_visibility="collapsed")
                    
                    with r2c2:
                        curr_estai_qtd = int(val_estai.get('Qtd', 0)) if isinstance(val_estai, dict) else (int(val_estai) if val_estai else 0)
                        new_estai_qtd = st.number_input("Qtd", min_value=0, value=curr_estai_qtd, key=f"estai_q_{p_id}", label_visibility="collapsed")
                        poles[p_id]['Estai'] = {'Type': new_estai_type, 'Qtd': new_estai_qtd}
 
                    # Para-Raio
                    with r2c3:
                        pr_opts = ["CRUZETA", "REDE COMPACTA", "REDE MONOFÁSICA"]
                        val_pr = p_data.get('ParaRaio', {})
                        curr_pr_type = val_pr.get('Type', pr_opts[0]) if isinstance(val_pr, dict) else pr_opts[0]
                        try: idx_pr = pr_opts.index(curr_pr_type)
                        except: idx_pr = 0
                        new_pr_type = st.selectbox("Para-Raio", pr_opts, index=idx_pr, key=f"pr_t_{p_id}", label_visibility="collapsed")
                        
                    with r2c4:
                        curr_pr_qtd = int(val_pr.get('Qtd', 0)) if isinstance(val_pr, dict) else 0
                        new_pr_qtd = st.number_input("Qtd", min_value=0, value=curr_pr_qtd, key=f"pr_q_{p_id}", label_visibility="collapsed")
                        poles[p_id]['ParaRaio'] = {'Type': new_pr_type, 'Qtd': new_pr_qtd}
                        
                    # Labels auxiliares linha 2
                    st.markdown("""<div style="margin-top: -15px; display: flex; justify-content: space-between;">
                        <span style="width: 48%; text-align: center; color: gray; font-size: 0.8em;">Estai (Tipo | Qtd)</span>
                        <span style="width: 48%; text-align: center; color: gray; font-size: 0.8em;">Para-Raio (Tipo | Qtd)</span>
                    </div>""", unsafe_allow_html=True)

                    # Linha 3: Ramal
                    st.caption("Ramal de Ligação")
                    r3c1, r3c2 = st.columns([3, 1])
                    
                    with r3c1:
                        ramal_opts = [
                            "CABO COL MULT AL 0,60/1KV 3X1X120 NEUTRO ISOLADO",
                            "CABO COL MULT AL 0,60/1KV 3X1X35+3 NEUTRO ISOLADO",
                            "CABO COL MULT AL 0,60/1KV 3X1X70+7 NEUTRO ISOLADO",
                            "CABO MULT AL XLPE 0,60/1KV 1X1X16+16MM2 (NEUTRO AZUL)",
                            "CABO MULT AL XLPE 0,60/1KV 2X1X16+16MM2 (NEUTRO AZUL)",
                            "CABO MULTIPLEXADO 2 X 35 + ( 35MM² ) (NEUTRO ISOLADO)",
                            "CABO MULTIPLEXADO 2 X 70 + ( 70MM² ) TRIPLEX",
                            "CABO MX AL XLPE 0,6/1KV 3X1X16+16MM2 (NEUTRO ISOLADO)",
                            "CABO MX AL XLPE 0,6/1KV 3X1X25+25MM2 (NEUTRO ISOLADO)",
                            "CONCENTRICO 25MM"
                        ]
                        val_ramal = p_data.get('Ramal', {})
                        curr_ramal_type = val_ramal.get('Type', ramal_opts[0]) if isinstance(val_ramal, dict) else ramal_opts[0]
                        try: idx_r = ramal_opts.index(curr_ramal_type)
                        except: idx_r = 0
                        new_ramal_type = st.selectbox("Ramal Tipo", ramal_opts, index=idx_r, key=f"ramal_t_{p_id}", label_visibility="collapsed")
                        
                    with r3c2:
                        curr_ramal_qtd = float(val_ramal.get('Qtd', 0)) if isinstance(val_ramal, dict) else 0.0
                        new_ramal_qtd = st.number_input("Metros", min_value=0.0, value=curr_ramal_qtd, key=f"ramal_q_{p_id}", label_visibility="collapsed")
                        poles[p_id]['Ramal'] = {'Type': new_ramal_type, 'Qtd': new_ramal_qtd}

        st.divider()

        # 2. Cabos (SEGUNDO)
        st.markdown("### 🔌 Cabos e Condutores")
        edited_cables = st.data_editor(
            st.session_state.cables_data,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Tipo": st.column_config.SelectboxColumn("Tipo", options=["MT", "BT"]),
                "Desc": st.column_config.TextColumn("Descrição", width="large"),
                "Qtd": st.column_config.NumberColumn("Metros", format="%.2f")
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
                st.dataframe(
                    df_bom,
                    column_config={
                        "Código SAP": st.column_config.TextColumn("SAP", width="small"),
                        "Descrição": st.column_config.TextColumn("Material", width="medium"),
                        "Quantidade": st.column_config.NumberColumn("Qtd", format="%.2f")
                    },
                    use_container_width=True,
                    height=600,
                    hide_index=True
                )
                
                total_itens = len(df_bom)
                total_pecas = df_bom['Quantidade'].sum()
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

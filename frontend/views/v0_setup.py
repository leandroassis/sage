import streamlit as st
import os
import sys

# Adiciona o diretório raiz ao path para poder importar o pre_study
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
from core.ingestion.pre_study import run_pre_study
from core.database import update_session_state
from core.config import DATA_DIR, PROJECT_ROOT
import json

def render_setup():
    st.header("Fase 0: Setup do Projeto (Pre-Study)")
    
    if "setup_step" not in st.session_state:
        st.session_state.setup_step = 1

    # Função Helper para salvar o estado no banco
    def save_state():
        state_data = {
            "setup_step": st.session_state.setup_step,
            "logs": st.session_state.logs,
            "historical_pdfs": st.session_state.get("historical_pdfs", []),
            "requisitos": st.session_state.get("requisitos", []),
            "equipment_docs": st.session_state.get("equipment_docs", []),
            "equipment_folder": st.session_state.get("equipment_folder", None)
        }
        update_session_state(st.session_state.project_id, "v0_setup", state_data)

    st.progress(st.session_state.setup_step / 3.0, text=f"Etapa {st.session_state.setup_step} de 3")
    st.divider()

    if st.session_state.setup_step == 1:
        st.subheader("1. Ingestão de Relatórios Históricos")
        st.write("Faça o upload dos PDFs contendo os relatórios anteriores para inicializar a memória de longo prazo.")
        st.info("💡 **Dica:** Você pode selecionar múltiplos arquivos de uma vez ou **arrastar uma pasta inteira** para dentro da área pontilhada abaixo (se o seu navegador suportar).")
        
        hist_docs = st.file_uploader("Upload de Relatórios Antigos", accept_multiple_files=True, type=['pdf'])
        
        if hist_docs:
            if st.button("Salvar e Registrar Histórico"):
                st.session_state.logs.append(f"[Pre-Study] Recebidos {len(hist_docs)} PDFs via upload direto.")
                
                # Salvando fisicamente na pasta de histórico
                hist_dir = os.path.join(DATA_DIR, "historical_reports")
                os.makedirs(hist_dir, exist_ok=True)
                for doc in hist_docs:
                    file_path = os.path.join(hist_dir, doc.name)
                    with open(file_path, "wb") as f:
                        f.write(doc.getbuffer())
                        
                st.session_state.historical_pdfs = [d.name for d in hist_docs]
                st.session_state.setup_step = 2
                save_state()
                st.rerun()
                
        st.info("Caso não queira adicionar mais nenhum relatório histórico agora, apenas deixe em branco e clique em Avançar.")
        if st.button("Pular esta etapa"):
            st.session_state.historical_pdfs = []
            st.session_state.setup_step = 2
            save_state()
            st.rerun()

    elif st.session_state.setup_step == 2:
        st.subheader("2. Template do Relatório de Ensaios")
        st.write("Faça o upload do documento LaTeX (arquivo base `.tex`) contendo os requisitos a serem avaliados.")
        
        uploaded_file = st.file_uploader("Upload do Template do Relatório (.tex)", type=['tex'])
        
        if uploaded_file is not None:
            if st.button("Processar e Fatiar Documento Base"):
                with st.spinner("Lendo documento LaTeX e dividindo em Requisitos..."):
                    # Salva temporário
                    temp_path = os.path.join(PROJECT_ROOT, "temp_main.tex")
                    with open(temp_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    
                    project_dir = os.path.join(DATA_DIR, "projects", st.session_state.project_id)
                    
                    # Executa script real
                    run_pre_study(temp_path, project_dir)
                    
                    # Carrega as pastas pro estado visual lendo o json
                    req_json_path = os.path.join(project_dir, "requisitos", "requisitos.json")
                    if os.path.exists(req_json_path):
                        with open(req_json_path, 'r', encoding='utf-8') as f:
                            st.session_state.requisitos = json.load(f)
                    else:
                        st.session_state.requisitos = []
                    
                    st.session_state.logs.append("[Pre-Study] Árvore de requisitos criada com sucesso.")
                    os.remove(temp_path)
                    st.session_state.setup_step = 3
                    save_state()
                    st.rerun()

    elif st.session_state.setup_step == 3:
        st.subheader("3. Documentação do Equipamento")
        st.write("Faça o upload dos manuais, PDFs e código-fonte associados ao projeto que está sendo avaliado agora.")
        st.info("💡 **Dica:** Para código-fonte pesado ou diretórios aninhados, prefira informar o caminho da pasta local.")
        
        docs = st.file_uploader("Arquivos do Equipamento", accept_multiple_files=True)
        
        st.markdown("**OU**")
        folder_path = st.text_input("Caminho absoluto de uma pasta local (Ex: /home/user/projeto/src):")
        
        if docs or folder_path:
            if folder_path and not os.path.isdir(folder_path):
                st.warning("O caminho fornecido não é um diretório válido ou não existe.")
            else:
                st.success("Arquivos/Pasta prontos para processamento.")
                if st.button("Finalizar Pre-Study e Iniciar Study"):
                    # Salva os arquivos upados fisicamente no projeto
                    project_docs_dir = os.path.join(DATA_DIR, "projects", st.session_state.project_id, "documentacao")
                    os.makedirs(project_docs_dir, exist_ok=True)
                    
                    saved_names = []
                    if docs:
                        for doc in docs:
                            file_path = os.path.join(project_docs_dir, doc.name)
                            with open(file_path, "wb") as f:
                                f.write(doc.getbuffer())
                            saved_names.append(doc.name)
                    
                    st.session_state.equipment_docs = saved_names
                    st.session_state.equipment_folder = folder_path if folder_path else None
                    
                    msg = f"[Pre-Study] Registrados {len(saved_names)} arquivos individuais"
                    if folder_path:
                        msg += f" e a pasta {folder_path}."
                    st.session_state.logs.append(msg)
                    
                    # Limpeza de estado e avanço de fase global
                    st.session_state.setup_step = 1 
                    st.session_state.progress = 25
                    st.session_state.current_phase = 1
                    
                    # Salva como v1_study agora
                    state_data = {
                        "setup_step": 1,
                        "logs": st.session_state.logs,
                        "historical_pdfs": st.session_state.get("historical_pdfs", []),
                        "requisitos": st.session_state.get("requisitos", []),
                        "equipment_docs": st.session_state.get("equipment_docs", []),
                        "equipment_folder": st.session_state.get("equipment_folder", None)
                    }
                    update_session_state(st.session_state.project_id, "v1_study", state_data)
                    st.rerun()

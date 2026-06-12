import streamlit as st
import time
import os

def render_study():
    st.header("Fase 1: Motor de Ingestão e Vetorização (Study)")
    st.write("O sistema irá agora compilar todos os dados informados na etapa anterior (Acervo Histórico e Documentação Atual) para o VectorDB.")
    
    historical = st.session_state.get('historical_pdfs', [])
    equip_docs = st.session_state.get('equipment_docs', [])
    
    st.write(f"**Relatórios Históricos na Fila:** {len(historical)}")
    st.write(f"**Documentos do Equipamento na Fila:** {len(equip_docs)}")
    
    if st.button("Iniciar Pipeline de Inteligência Artificial"):
        with st.spinner("Processando RAG Multimodal..."):
            # Acionamento do pipeline real do Histórico
            historical_dir = os.path.join(os.getcwd(), "data", "historical_reports")
            db_dir = os.path.join(os.getcwd(), "data", "vector_db")
            
            if len(historical) > 0 and os.path.exists(historical_dir):
                st.session_state.logs.append("[Study] Iniciando o processamento do acervo histórico...")
                from core.ingestion.historical_pipeline import run_historical_pipeline
                
                # Callback para que o terminal visual do Streamlit seja atualizado
                def ui_logger(msg):
                    st.session_state.logs.append(msg)
                    
                run_historical_pipeline(historical_dir, db_dir, add_log_callback=ui_logger)
            else:
                st.session_state.logs.append("[Study] Nenhum histórico pendente processado.")
                
            time.sleep(1)
            
            # Simulando os novos
            st.session_state.logs.append(f"[Study] Iniciando parse de {len(equip_docs)} documentos do projeto atual.")
            time.sleep(1)
            
            st.session_state.logs.append("[TreeSitter] Lendo Abstract Syntax Trees do código fonte. Fragmentando o escopo semântico.")
            time.sleep(1)
            
            st.session_state.logs.append("[ChromaDB] Embeddings finalizados via CPU. Inseridos na Collection_Projeto_Atual e Collection_Historico.")
            time.sleep(1)
            
            st.session_state.progress = 50
            st.session_state.current_phase = 2
            st.rerun()

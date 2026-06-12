import streamlit as st
import time
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from core.database import enqueue_job, get_session_active_job, update_session_state, get_connection

def render_study():
    st.header("Fase 1: Motor de Ingestão e Vetorização (Study)")
    st.write("O sistema irá agora compilar todos os dados informados na etapa anterior (Acervo Histórico e Documentação Atual) para o VectorDB.")
    
    historical = st.session_state.get('historical_pdfs', [])
    equip_docs = st.session_state.get('equipment_docs', [])
    
    st.write(f"**Relatórios Históricos na Fila:** {len(historical)}")
    st.write(f"**Documentos do Equipamento na Fila:** {len(equip_docs)}")
    
    project_id = st.session_state.get("project_id")
    
    # Verifica se há um job ativo na fila
    active_job = get_session_active_job(project_id)
    
    # Verifica se o job foi concluído recentemente
    conn = get_connection()
    conn.row_factory = sqlite3.Row if 'sqlite3' in globals() else None
    import sqlite3
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs_queue WHERE session_id = ? AND task_type = 'STUDY_PIPELINE' ORDER BY created_at DESC LIMIT 1", (project_id,))
    last_job = cursor.fetchone()
    conn.close()
    
    if last_job and last_job['status'] == 'COMPLETED':
        st.success("O pipeline de IA foi finalizado com sucesso!")
        st.session_state.progress = 50
        st.session_state.current_phase = 2
        
        # Salva o avanço para v2
        state_data = {
            "setup_step": 1,
            "logs": st.session_state.logs,
            "historical_pdfs": st.session_state.get("historical_pdfs", []),
            "requisitos": st.session_state.get("requisitos", []),
            "equipment_docs": st.session_state.get("equipment_docs", []),
            "equipment_folder": st.session_state.get("equipment_folder", None)
        }
        update_session_state(project_id, "v2_acquire", state_data)
        
        time.sleep(1)
        st.rerun()
        
    elif active_job:
        status = active_job['status']
        if status == 'PENDING':
            st.info("Sua requisição está na Fila aguardando a GPU ficar livre...")
        else:
            st.warning("Executando! O modelo de IA está processando seus documentos. Não feche o navegador...")
            
        with st.spinner(f"Status atual: {status}"):
            time.sleep(3)
            st.rerun()
            
    else:
        if last_job and last_job['status'] == 'FAILED':
            st.error(f"Ocorreu um erro no processamento: {last_job['error_message']}. Tente novamente.")
            
        if st.button("Iniciar Pipeline de Inteligência Artificial"):
            enqueue_job(project_id, "STUDY_PIPELINE")
            st.session_state.logs.append("[Study] Adicionado à fila global de processamento de Inteligência Artificial.")
            update_session_state(project_id, "v1_study", {"logs": st.session_state.logs})
            st.rerun()

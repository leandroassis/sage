import streamlit as st
import time
import sqlite3
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from core.database import enqueue_job, get_session_active_job, update_session_state, get_connection

def render_fill():
    st.header("Fase 3: Geração de Parecer e Injeção no LaTeX (Fill)")
    
    project_id = st.session_state.get("project_id")
    active_job = get_session_active_job(project_id)
    
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs_queue WHERE session_id = ? AND task_type = 'FILL_GENERATION' ORDER BY created_at DESC LIMIT 1", (project_id,))
    last_job = cursor.fetchone()
    conn.close()
    
    if last_job and last_job['status'] == 'COMPLETED':
        st.success("Relatório gerado com sucesso!")
        st.session_state.progress = 100
        
        st.download_button(
            label="Baixar Relatório Compilado (MOCK)",
            data="Dados do MOCK",
            file_name="relatorio_final_sage.zip",
            mime="application/zip"
        )
        return
        
    if active_job:
        status = active_job['status']
        st.info("Gerando pareceres e compilando relatórios. Aguardando...")
        with st.spinner(f"Status atual: {status}"):
            time.sleep(3)
            st.rerun()
            
    else:
        if st.button("Iniciar Motor de Geração LaTeX (LLM)"):
            enqueue_job(project_id, "FILL_GENERATION")
            st.rerun()

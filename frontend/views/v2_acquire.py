import streamlit as st
import os
import sys
import time
import sqlite3

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from core.database import enqueue_job, get_session_active_job, update_session_state, get_connection
from core.config import DATA_DIR

def render_acquire():
    st.header("Fase 2: Roteamento de Evidências (Acquire)")
    st.write("Agente Planejador cruzará os requisitos com o banco vetorial.")
    
    project_id = st.session_state.get("project_id")
    
    # Verifica fila para o Acquire Planning
    active_job = get_session_active_job(project_id)
    
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs_queue WHERE session_id = ? AND task_type = 'ACQUIRE_PLANNING' ORDER BY created_at DESC LIMIT 1", (project_id,))
    last_job = cursor.fetchone()
    conn.close()
    if last_job and last_job['status'] == 'COMPLETED' and not st.session_state.get("acquire_mocked"):
        # O Worker terminou. Vamos mocar o preenchimento aqui até a Fase real ser desenvolvida.
        for i, req in enumerate(st.session_state.requisitos):
            if i % 3 == 0:
                req['status'] = "Autônomo"
                req['instruction'] = "Encontrei a função `zerize()` no arquivo `main.c`. Evidência registrada em memória."
                req['synthesis'] = "O código fonte do equipamento contém rotinas explícitas de zerização de memória, cumprindo o requisito integralmente."
            else:
                req['status'] = "Ação Pendente"
                req['instruction'] = "O histórico indica necessidade de evidência visual. Por favor, anexe um print da tela do terminal demonstrando a compilação."
                req['synthesis'] = "As normativas exigem evidência fotográfica/visual do equipamento ou do console para atestar a versão do firmware em execução."
        st.session_state.acquire_mocked = True
        update_session_state(project_id, "v2_acquire", {"acquire_mocked": True, "requisitos": st.session_state.requisitos, "logs": st.session_state.logs})
        st.rerun()

    if active_job:
        status = active_job['status']
        st.info("Planejador de IA ativo. Aguardando...")
        with st.spinner(f"Status atual: {status}"):
            time.sleep(3)
            st.rerun()
            
    elif not st.session_state.get("acquire_mocked"):
        if st.button("Iniciar Agente Planejador"):
            enqueue_job(project_id, "ACQUIRE_PLANNING")
            st.rerun()
        return

    all_ready = True

    for req in st.session_state.requisitos:
        # Define cor e ícone baseado no status
        if req['status'] == "Autônomo":
            icon = "🟢"
        elif req['status'] == "Pronto":
            icon = "✅"
        else:
            icon = "🔴"
            all_ready = False
            
        with st.expander(f"{icon} {req['id']} - Status: {req['status']}"):
            st.write(f"**Instrução do Agente Planejador:** {req.get('instruction', '')}")
            
            # Novo campo com a síntese do modelo
            if req.get('synthesis'):
                st.info(f"🧠 **Entendimento Sintetizado pelo Modelo:** {req['synthesis']}")
            
            # Novo campo de prompt de texto para a IA
            user_prompt = st.text_area("Prompt / Instrução Adicional para a IA (Opcional)", key=f"prompt_{req['id']}", placeholder="Ex: Ao gerar o parecer, enfatize que a porta serial estava desativada.")
            
            if req['status'] == "Ação Pendente":
                uploaded_file = st.file_uploader(f"Anexar Evidência para {req['id']}", key=f"up_{req['id']}")
                if uploaded_file is not None or st.button("Salvar Prompt e Avançar", key=f"btn_{req['id']}"):
                    # Salvar arquivo se existir
                    if uploaded_file is not None:
                        project_dir = os.path.join(DATA_DIR, "projects", project_id)
                        evidencias_dir = os.path.join(project_dir, "requisitos", req['id'], "evidencias")
                        os.makedirs(evidencias_dir, exist_ok=True)
                        
                        file_path = os.path.join(evidencias_dir, uploaded_file.name)
                        with open(file_path, "wb") as f:
                            f.write(uploaded_file.getbuffer())
                            
                        req['evidencias'].append(file_path)
                    
                    if user_prompt:
                        req['user_prompt'] = user_prompt
                        
                    req['status'] = "Pronto"
                    update_session_state(project_id, "v2_acquire", {"acquire_mocked": True, "requisitos": st.session_state.requisitos, "logs": st.session_state.logs})
                    st.success("Informações salvas e vinculadas!")
                    st.rerun()

    if all_ready:
        st.success("Todos os requisitos estão prontos para a Geração do Parecer!")
        if st.button("Avançar para a Geração (Fill)"):
            st.session_state.progress = 75
            st.session_state.current_phase = 3
            update_session_state(project_id, "v3_fill", {"requisitos": st.session_state.requisitos, "logs": st.session_state.logs})
            st.rerun()

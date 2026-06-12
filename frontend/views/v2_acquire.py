import streamlit as st
import os
import sys
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from core.database import enqueue_job, get_session_active_job, update_session_state, get_session_state
from core.config import DATA_DIR

def render_acquire():
    st.header("Fase 2: Roteamento de Evidências (Acquire)")
    st.write("Agente Planejador cruzará os requisitos com o banco vetorial para identificar evidências autônomas e mapear ações pendentes.")
    
    project_id = st.session_state.get("project_id")
    active_job = get_session_active_job(project_id)
    
    db_state = get_session_state(project_id, "v2_acquire") or {}
    
    # Se o RAG falhar, o worker não deve limpar acquire_finished, mas em caso de loop contínuo:
    if active_job and active_job['task_type'] == 'ACQUIRE_PLANNING':
        status = active_job['status']
        if status in ['PENDING', 'RUNNING']:
            st.info("🧠 Agente Planejador de IA ativo. Analisando...")
            
            progress_data = db_state.get("progress", {})
            curr = progress_data.get("current", 0)
            total = progress_data.get("total", 1)
            eta = progress_data.get("eta", 0)
            
            progress_pct = curr / total if total > 0 else 0.0
            st.progress(progress_pct, text=f"Progresso Real: {curr}/{total} requisitos analisados")
            
            if eta > 0:
                mins, secs = divmod(eta, 60)
                st.caption(f"ETA Inteligente: ~{int(mins)}m {int(secs)}s restantes")
                
            with st.expander("Terminal Virtual (Logs do Agente)", expanded=True):
                logs = db_state.get("acquire_logs", [])
                log_text = "\n".join(logs[-10:])
                st.code(log_text, language="bash")
                
            time.sleep(2)
            st.rerun()

    if not db_state.get("acquire_finished"):
        if active_job and active_job['status'] == 'FAILED':
            st.error(f"Erro no processamento anterior: {active_job.get('error_message')}")
            
        if st.button("Iniciar Agente Planejador", type="primary"):
            enqueue_job(project_id, "ACQUIRE_PLANNING")
            st.rerun()
        return

    st.success("O Agente Planejador concluiu a varredura!")
    
    requisitos = db_state.get("requisitos", [])
    all_ready = True
    
    for i, req in enumerate(requisitos):
        if req['status'] == "Autônomo":
            icon = "🟢"
        elif req['status'] == "Pronto":
            icon = "✅"
        else:
            icon = "🔴"
            all_ready = False
            
        with st.expander(f"{icon} {req['id']} - Status: {req['status']}", expanded=(req['status'] != "Pronto")):
            st.write(f"**Instrução do Agente:** {req.get('instruction', '')}")
            
            if req.get('synthesis'):
                st.info(f"🧠 **Síntese do Modelo:** {req['synthesis']}")
            
            user_prompt = st.text_area("Prompt Adicional / Feedback (Opcional)", value=req.get('user_prompt', ''), key=f"prompt_{req['id']}", placeholder="Sugerir alteração ou forçar uma interpretação...")
            
            uploaded_file = st.file_uploader(f"Anexar Evidência Complementar (Opcional para Autônomos)", key=f"up_{req['id']}")
            
            if st.button("Salvar e Marcar como Pronto", key=f"btn_{req['id']}"):
                if uploaded_file is not None:
                    project_dir = os.path.join(DATA_DIR, "projects", project_id)
                    evidencias_dir = os.path.join(project_dir, "requisitos", req['id'], "evidencias")
                    os.makedirs(evidencias_dir, exist_ok=True)
                    
                    file_path = os.path.join(evidencias_dir, uploaded_file.name)
                    with open(file_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                        
                    if 'evidencias' not in req:
                        req['evidencias'] = []
                    req['evidencias'].append(file_path)
                
                req['user_prompt'] = user_prompt
                req['status'] = "Pronto"
                
                # Salva o estado atualizado no DB
                update_session_state(project_id, "v2_acquire", db_state)
                st.success("Salvo com sucesso!")
                time.sleep(1)
                st.rerun()

    if all_ready:
        st.success("Todos os requisitos estão prontos para a Geração do Parecer!")
        if st.button("Avançar para a Geração (Fill)", type="primary"):
            st.session_state.progress = 75
            st.session_state.current_phase = 3
            update_session_state(project_id, "v3_fill", {"requisitos": requisitos, "logs": st.session_state.logs})
            st.rerun()

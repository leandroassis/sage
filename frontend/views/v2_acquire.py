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
            
            progress_data = db_state.get("task_progress", {})
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
    
    for req in requisitos:
        st.markdown(f"### Requisito: {req['id']}")
        ensaios = req.get('ensaios', [])
        
        if not ensaios:
            st.info("Nenhum ensaio encontrado neste requisito.")
            continue
            
        for ensaio in ensaios:
            if ensaio['status'] == "Autônomo":
                icon = "🟢"
            elif ensaio['status'] == "Pronto":
                icon = "✅"
            else:
                icon = "🔴"
                all_ready = False
                
            with st.expander(f"{icon} Ensaio {ensaio['id']} - Status: {ensaio['status']}", expanded=(ensaio['status'] != "Pronto")):
                st.write(f"**Instrução do Agente:** {ensaio.get('instruction', '')}")
                st.info(f"🧠 **Síntese:** {ensaio.get('synthesis', '')}")
                
                user_prompt = st.text_area("Prompt Adicional / Feedback (Opcional)", value=ensaio.get('user_prompt', ''), key=f"prompt_{req['id']}_{ensaio['id']}", placeholder="Sugerir alteração ou forçar uma interpretação para reavaliar...")
                
                uploaded_file = st.file_uploader(f"Anexar Evidência Complementar", key=f"up_{req['id']}_{ensaio['id']}")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Salvar e Marcar como Pronto", key=f"btn_pronto_{req['id']}_{ensaio['id']}"):
                        if uploaded_file is not None:
                            project_dir = os.path.join(DATA_DIR, "projects", project_id)
                            evidencias_dir = os.path.join(project_dir, "requisitos", req['id'], "evidencias")
                            os.makedirs(evidencias_dir, exist_ok=True)
                            file_path = os.path.join(evidencias_dir, uploaded_file.name)
                            with open(file_path, "wb") as f:
                                f.write(uploaded_file.getbuffer())
                            if 'evidencias' not in ensaio:
                                ensaio['evidencias'] = []
                            ensaio['evidencias'].append(file_path)
                        
                        ensaio['user_prompt'] = user_prompt
                        ensaio['status'] = "Pronto"
                        update_session_state(project_id, "v2_acquire", db_state)
                        st.success("Marcado como Pronto!")
                        time.sleep(1)
                        st.rerun()
                        
                with col2:
                    if st.button("Gerar Nova Resposta (Aplicar Prompt)", key=f"btn_reprocess_{req['id']}_{ensaio['id']}"):
                        ensaio['user_prompt'] = user_prompt
                        update_session_state(project_id, "v2_acquire", db_state)
                        enqueue_job(project_id, f"ACQUIRE_REPROCESS:{req['id']}:{ensaio['id']}")
                        st.rerun()

    if all_ready and requisitos:
        st.success("Todos os ensaios estão prontos para a Geração do Parecer!")
        if st.button("Avançar para a Geração (Fill)", type="primary"):
            st.session_state.progress = 75
            st.session_state.current_phase = 3
            update_session_state(project_id, "v3_fill", {"requisitos": requisitos, "logs": st.session_state.logs})
            st.rerun()

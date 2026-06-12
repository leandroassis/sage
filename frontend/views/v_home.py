import streamlit as st
import uuid
import json
import sys
import os

# Adiciona o diretório raiz ao path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from core.database import get_all_sessions, create_session, get_queue

def render_home():
    st.markdown("<h1 class='phase-title'>Central de Projetos SAGE</h1>", unsafe_allow_html=True)
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Projetos (Sessões)")
        sessions = get_all_sessions()
        
        if not sessions:
            st.info("Nenhum projeto encontrado. Crie um novo ao lado.")
        else:
            for s in sessions:
                with st.container():
                    st.write(f"**{s['name']}** (Etapa: {s['current_stage']})")
                    if st.button("Abrir Projeto", key=f"btn_{s['id']}"):
                        st.session_state.project_id = s['id']
                        # Carrega estado retido
                        state = json.loads(s['state_data'])
                        for k, v in state.items():
                            st.session_state[k] = v
                            
                        stage_map = {'v0_setup': 0, 'v1_study': 1, 'v2_acquire': 2, 'v3_fill': 3}
                        st.session_state.current_phase = stage_map.get(s['current_stage'], 0)
                        st.rerun()
                    st.divider()
                    
    with col2:
        st.subheader("Novo Equipamento")
        with st.form("new_project_form"):
            p_name = st.text_input("Nome do Equipamento/Projeto")
            if st.form_submit_button("Criar e Iniciar"):
                if p_name:
                    new_id = str(uuid.uuid4())
                    create_session(new_id, p_name)
                    st.session_state.project_id = new_id
                    st.session_state.current_phase = 0
                    st.rerun()
                else:
                    st.error("Informe um nome para o projeto.")
                    
    st.divider()
    st.subheader("Fila de Execução Global (IA)")
    
    # Auto-refresh helper button for queue viewing
    if st.button("Atualizar Fila"):
        st.rerun()
        
    queue = get_queue()
    if not queue:
        st.info("Nenhuma tarefa pesada rodando ou pendente na fila.")
    else:
        for q in queue:
            if q['status'] == 'COMPLETED':
                status_color = "🟢"
            elif q['status'] == 'RUNNING':
                status_color = "⏳"
            elif q['status'] == 'FAILED':
                status_color = "🔴"
            else:
                status_color = "⚪"
                
            session_name = next((s['name'] for s in sessions if s['id'] == q['session_id']), q['session_id'])
                
            st.write(f"{status_color} **{q['task_type']}** - Status: `{q['status']}` | Projeto: {session_name} | Criado em: {q['created_at']}")

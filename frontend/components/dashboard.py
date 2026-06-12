import streamlit as st

def render_dashboard():
    st.markdown("<h2 class='phase-title'>[SAGE] Painel de Bordo</h2>", unsafe_allow_html=True)
    
    phases = ["0: Setup (Pre-Study)", "1: Ingestão (Study)", "2: Análise (Acquire)", "3: Geração (Fill)"]
    
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        st.write(f"**Fase Atual:** {phases[st.session_state.current_phase]}")
        st.progress(st.session_state.progress)
        
    with col2:
        req_total = len(st.session_state.requisitos)
        req_done = sum(1 for r in st.session_state.requisitos if r.get('status') == 'Pronto')
        st.metric(label="Requisitos Analisados", value=f"{req_done}/{req_total}")
        
    with col3:
        st.metric(label="ETA", value="12 mins" if st.session_state.current_phase > 0 else "--")
        
    # Terminal Virtual
    with st.expander("Terminal Virtual (Logs do Backend)", expanded=False):
        if not st.session_state.logs:
            st.code("Aguardando inicialização...", language="bash")
        else:
            log_text = "\\n".join(st.session_state.logs[-15:]) # Mostrar os últimos 15 logs
            st.code(log_text, language="bash")

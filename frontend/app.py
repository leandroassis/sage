import streamlit as st
import os

# Configuração da Página
st.set_page_config(page_title="SAGE - Gestão de Ensaios", layout="wide")

# Inicialização de Variáveis de Estado
if "current_phase" not in st.session_state:
    st.session_state.current_phase = 0

if "logs" not in st.session_state:
    st.session_state.logs = []

if "requisitos" not in st.session_state:
    st.session_state.requisitos = []

if "progress" not in st.session_state:
    st.session_state.progress = 0

def add_log(msg: str):
    st.session_state.logs.append(msg)

from components.dashboard import render_dashboard
from views.v0_setup import render_setup
from views.v1_study import render_study
from views.v2_acquire import render_acquire
from views.v3_fill import render_fill

# Estilo Global (Design Limpo e Moderno)
st.markdown("""
<style>
    .stApp {
        background-color: #0E1117;
        color: #FAFAFA;
    }
    .phase-title {
        font-family: 'Inter', sans-serif;
        color: #4CAF50;
        font-weight: 700;
    }
</style>
""", unsafe_allow_html=True)

# Main App Loop
render_dashboard()

st.divider()

if st.session_state.current_phase == 0:
    render_setup()
elif st.session_state.current_phase == 1:
    render_study()
elif st.session_state.current_phase == 2:
    render_acquire()
elif st.session_state.current_phase == 3:
    render_fill()

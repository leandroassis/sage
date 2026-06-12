import streamlit as st
import time

def render_fill():
    st.header("Fase 3: Geração de Parecer e Injeção no LaTeX (Fill)")
    
    if st.button("Iniciar Motor de Geração LaTeX (MOCK)"):
        with st.spinner("Gerando pareceres e compilando relatórios..."):
            st.session_state.logs.append("[Ollama] Carregando Qwen2.5-Coder na VRAM.")
            
            for req in st.session_state.requisitos:
                time.sleep(0.5)
                st.session_state.logs.append(f"[LLM] Parecer gerado para {req['id']}. Injetando com Regex...")
                
            st.session_state.logs.append("[Python] Relatório final concatenado em main_modular.tex.")
            st.session_state.progress = 100
            
            st.success("Relatório gerado com sucesso!")
            
            st.download_button(
                label="Baixar Relatório Compilado (MOCK)",
                data="Dados do MOCK",
                file_name="relatorio_final_sage.zip",
                mime="application/zip"
            )

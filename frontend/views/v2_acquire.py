import streamlit as st
import os

def render_acquire():
    st.header("Fase 2: Roteamento de Evidências (Acquire)")
    st.write("Agente Planejador cruzou os requisitos com o banco vetorial.")
    
    # Mocking the AI decision for demonstration
    if not st.session_state.get("acquire_mocked"):
        st.session_state.logs.append("[Ollama] Carregando Qwen2.5-Coder:7b (LLM) na VRAM...")
        for i, req in enumerate(st.session_state.requisitos):
            # Simulando que alguns são automáticos e outros requerem ação manual
            if i % 3 == 0:
                req['status'] = "Autônomo"
                req['instruction'] = "Encontrei a função `zerize()` no arquivo `main.c`. Evidência registrada em memória."
                req['synthesis'] = "O código fonte do equipamento contém rotinas explícitas de zerização de memória, cumprindo o requisito integralmente."
            else:
                req['status'] = "Ação Pendente"
                req['instruction'] = "O histórico indica necessidade de evidência visual. Por favor, anexe um print da tela do terminal demonstrando a compilação."
                req['synthesis'] = "As normativas exigem evidência fotográfica/visual do equipamento ou do console para atestar a versão do firmware em execução."
        
        st.session_state.logs.append("[LLM] 45 Requisitos analisados. Roteamento finalizado.")
        st.session_state.logs.append("[Ollama] Descarregando Qwen2.5-Coder da VRAM.")
        st.session_state.acquire_mocked = True

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
                        project_dir = os.path.join(os.getcwd(), "sage", "data", "current_project")
                        evidencias_dir = os.path.join(project_dir, "requisitos", req['id'], "evidencias")
                        os.makedirs(evidencias_dir, exist_ok=True)
                        
                        file_path = os.path.join(evidencias_dir, uploaded_file.name)
                        with open(file_path, "wb") as f:
                            f.write(uploaded_file.getbuffer())
                            
                        req['evidencias'].append(file_path)
                    
                    if user_prompt:
                        req['user_prompt'] = user_prompt
                        
                    req['status'] = "Pronto"
                    st.success("Informações salvas e vinculadas!")
                    st.rerun()

    if all_ready:
        st.success("Todos os requisitos estão prontos para a Geração do Parecer!")
        if st.button("Avançar para a Geração (Fill)"):
            st.session_state.progress = 75
            st.session_state.current_phase = 3
            st.rerun()

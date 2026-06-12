import os
import json
import time
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage
from core.database import get_session_state, update_session_state
from core.config import DATA_DIR, get_logger

logger = get_logger("AcquireAgent")

SYSTEM_PROMPT = """Você é um Agente Planejador Lógico especializado em auditoria técnica e análise de código fonte.
Seu objetivo é analisar um requisito de conformidade e o contexto (documentação e código fonte) do equipamento, e determinar se há evidências suficientes para aprovar o requisito automaticamente ou se é necessária uma ação humana (ex: enviar uma foto, print do terminal).

O usuário fornecerá:
1. O texto do Requisito.
2. Contexto extraído do repositório/documentação.

Você DEVE responder ESTRITAMENTE em formato JSON com as seguintes chaves:
{
  "status": "Autônomo" ou "Ação Pendente",
  "synthesis": "Sua análise detalhada sobre o que encontrou no contexto e por que é suficiente ou não.",
  "instruction": "Se for Ação Pendente, diga o que o operador deve fazer (ex: 'Anexe um print do console'). Se for Autônomo, diga 'Evidência registrada em memória.'"
}

Regras:
- Retorne APENAS o JSON válido. Sem markdown, sem texto extra.
- Responda em Português do Brasil.
"""

def run_acquire_agent(session_id: str):
    logger.info(f"Iniciando Acquire Agent para sessão {session_id}...")
    
    state = get_session_state(session_id, "v2_acquire") or {}
    
    if 'requisitos' not in state:
        v1_state = get_session_state(session_id, "v1_study") or {}
        if 'requisitos' in v1_state:
            state['requisitos'] = v1_state['requisitos']
        else:
            v0_state = get_session_state(session_id, "v0_setup") or {}
            state['requisitos'] = v0_state.get('requisitos', [])
    
    requisitos = state.get('requisitos', [])
    if not requisitos:
        logger.warning("Nenhum requisito encontrado para processar.")
        return
        
    if 'acquire_logs' not in state:
        state['acquire_logs'] = []
        
    def add_log(msg):
        logger.info(msg)
        state['acquire_logs'].append(f"[{time.strftime('%H:%M:%S')}] {msg}")
        update_session_state(session_id, "v2_acquire", state)

    db_dir = os.path.join(DATA_DIR, "vector_db")
    embeddings = OllamaEmbeddings(
        model="nomic-embed-text",
        model_kwargs={"num_gpu": 19, "num_ctx": 4096, "keep_alive": 0}
    )
    collection_name = f"Collection_Project_{session_id.replace('-', '_')}"
    vectorstore = Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=db_dir
    )
    
    llm = ChatOllama(
        model="qwen2.5-coder:7b",
        format="json",
        temperature=0.0
    )
    
    total = len(requisitos)
    start_time = time.time()
    
    for i, req in enumerate(requisitos):
        if req.get('synthesis') and req.get('status') in ["Autônomo", "Ação Pendente", "Pronto"]:
            continue
            
        req_text = req.get('text', '')
        add_log(f"Analisando requisito {i+1}/{total}: {req['id']}...")
        
        docs = vectorstore.similarity_search(req_text, k=15)
        context_str = "\n\n".join([f"[Fonte: {d.metadata.get('source', 'Desconhecida')}]\n{d.page_content}" for d in docs])
        
        human_msg = f"REQUISITO:\n{req_text}\n\nCONTEXTO:\n{context_str}"
        
        add_log(f"Consultando LLM Planejador para o {req['id']}...")
        try:
            response = llm.invoke([
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=human_msg)
            ])
            
            result = json.loads(response.content)
            
            req['status'] = result.get('status', 'Ação Pendente')
            req['instruction'] = result.get('instruction', 'Nenhuma instrução gerada.')
            req['synthesis'] = result.get('synthesis', 'Nenhuma síntese gerada.')
            
            add_log(f"-> Status definido como: {req['status']}")
            
        except Exception as e:
            add_log(f"Erro ao processar {req['id']} via LLM: {str(e)}")
            req['status'] = 'Ação Pendente'
            req['instruction'] = 'Falha no processamento LLM. Trate manualmente.'
            req['synthesis'] = 'Erro no agente planejador.'
        
        # Calculate ETA
        elapsed = time.time() - start_time
        items_done = i + 1
        eta_seconds = (elapsed / items_done) * (total - items_done)
        
        state['requisitos'] = requisitos
        state['progress'] = {
            "current": items_done,
            "total": total,
            "eta": int(eta_seconds)
        }
        update_session_state(session_id, "v2_acquire", state)
        
    add_log("Auto-Acquire Finalizado com sucesso.")
    state['acquire_finished'] = True
    update_session_state(session_id, "v2_acquire", state)

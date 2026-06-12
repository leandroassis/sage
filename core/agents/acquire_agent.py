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

SYSTEM_PROMPT = """Você é um Agente Planejador Lógico especializado em auditoria técnica e análise de código fonte e documentação (Padrões ICP-Brasil e INMETRO).
Seu objetivo é analisar o texto fonte de um requisito normativo em LaTeX, identificar os ensaios solicitados (geralmente sob a tag \\item \\textbf{EN...}) e cruzar essas informações com:
1. Documentação atual do equipamento.
2. Relatórios históricos de equipamentos semelhantes.

O usuário pode fornecer instruções adicionais (prompt iterativo) para corrigir ou forçar um raciocínio.

Sua saída DEVE ser ESTRITAMENTE em formato JSON com as seguintes chaves:
{
  "status": "Autônomo" ou "Ação Pendente",
  "instruction": "Instrução geral para o operador humano se houver pendências (ex: Quais fotos tirar).",
  "ensaios": [
    {
      "id": "EN.III.1.1.01",
      "synthesis": "Sua análise: o que o ensaio pede + como a documentação e histórico respondem."
    }
  ]
}

Regras:
- Retorne APENAS o JSON válido.
- Responda em Português do Brasil.
"""

def run_acquire_agent(session_id: str, target_req_id: str = None):
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
    vectorstore_proj = Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=db_dir
    )
    
    vectorstore_hist = Chroma(
        collection_name="Collection_Historico",
        embedding_function=embeddings,
        persist_directory=db_dir
    )
    
    llm = ChatOllama(
        model="qwen2.5-coder:7b",
        format="json",
        temperature=0.0
    )
    
    reqs_to_process = [r for r in requisitos if r['id'] == target_req_id] if target_req_id else requisitos
    total = len(reqs_to_process)
    start_time = time.time()
    
    for i, req in enumerate(reqs_to_process):
        if not target_req_id and req.get('ensaios') and req.get('status') in ["Autônomo", "Ação Pendente", "Pronto"]:
            continue
            
        add_log(f"Analisando requisito {req['id']}...")
        
        req_id = req['id']
        tex_filename = f"REQUISITO_{req_id.replace('REQ_', '')}.tex"
        tex_path = os.path.join(DATA_DIR, "projects", session_id, "requisitos", req_id, tex_filename)
        
        req_text = ""
        if os.path.exists(tex_path):
            with open(tex_path, "r", encoding="utf-8") as f:
                req_text = f.read()
        else:
            add_log(f"Aviso: Arquivo {tex_path} não encontrado. Usando texto vazio.")
            
        query_text = req_text[:6000] # Limita o tamanho para não estourar o contexto do modelo de embedding (nomic-embed-text)
        
        docs_proj = vectorstore_proj.similarity_search(query_text, k=10)
        context_proj = "\n\n".join([f"[Fonte: {d.metadata.get('source', 'Desconhecida')}]\n{d.page_content}" for d in docs_proj])
        
        docs_hist = vectorstore_hist.similarity_search(query_text, k=5)
        context_hist = "\n\n".join([f"[Histórico: {d.metadata.get('source', 'Desconhecida')}]\n{d.page_content}" for d in docs_hist])
        
        user_prompt = req.get('user_prompt', '')
        
        human_msg = f"CONTEÚDO DO REQUISITO (.tex):\n{req_text}\n\nCONTEXTO DO PROJETO ATUAL:\n{context_proj}\n\nCONTEXTO HISTÓRICO:\n{context_hist}\n"
        if user_prompt:
            human_msg += f"\nINSTRUÇÃO ADICIONAL DO USUÁRIO:\n{user_prompt}\n(Use esta instrução para corrigir seu raciocínio e gerar uma nova resposta)"
        
        add_log(f"Consultando LLM Planejador para o {req['id']}...")
        try:
            response = llm.invoke([
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=human_msg)
            ])
            
            result = json.loads(response.content)
            
            req['status'] = result.get('status', 'Ação Pendente')
            req['instruction'] = result.get('instruction', 'Nenhuma instrução gerada.')
            req['ensaios'] = result.get('ensaios', [])
            req['synthesis'] = "Consulte os ensaios individuais."
            
            add_log(f"-> Status: {req['status']} | Ensaios: {len(req['ensaios'])}")
            
        except Exception as e:
            add_log(f"Erro ao processar {req['id']} via LLM: {str(e)}")
            req['status'] = 'Ação Pendente'
            req['instruction'] = 'Falha no processamento LLM. Trate manualmente.'
            req['ensaios'] = []
            req['synthesis'] = 'Erro no agente.'
        
        if not target_req_id:
            elapsed = time.time() - start_time
            items_done = i + 1
            eta_seconds = (elapsed / items_done) * (total - items_done)
            state['progress'] = {
                "current": items_done,
                "total": total,
                "eta": int(eta_seconds)
            }
            
        state['requisitos'] = requisitos
        update_session_state(session_id, "v2_acquire", state)
        
    add_log(f"Processamento concluído. ({target_req_id if target_req_id else 'Batch Completo'})")
    
    if not target_req_id:
        state['acquire_finished'] = True
        update_session_state(session_id, "v2_acquire", state)

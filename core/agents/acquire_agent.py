import os
import json
import time
# pyrefly: ignore [missing-import]
from langchain_community.embeddings import OllamaEmbeddings
# pyrefly: ignore [missing-import]
from langchain_community.vectorstores import Chroma
# pyrefly: ignore [missing-import]
from langchain_ollama import ChatOllama
# pyrefly: ignore [missing-import]
from langchain_core.messages import SystemMessage, HumanMessage
from core.database import get_session_state, update_session_state
from core.config import DATA_DIR, get_logger

logger = get_logger("AcquireAgent")

SYSTEM_PROMPT = """Você é um Agente Planejador Lógico especializado em auditoria técnica e análise de código fonte e documentação (Padrões ICP-Brasil e INMETRO).
Seu objetivo é analisar o texto fonte de um requisito normativo em LaTeX, identificar os ensaios solicitados (geralmente sob a tag \\item \\textbf{EN...}) e elaborar uma resposta detalhada com base no contexto fornecido.

INSTRUÇÕES DE OPERAÇÃO:
1. DETERMINAÇÃO DE STATUS:
   - Baseado nos pareceres anteriores do mesmo ensaio/requisito (encontrados no contexto histórico), determine primeiramente se o ensaio pode ser completamente satisfeito apenas com uma explicação textual (Status: "Autônomo") ou se necessita de evidências adicionais visuais, como tabelas e imagens (Status: "Ação Pendente").
   - Caso você não consiga identificar algum trecho necessário na documentação atual para sustentar a resposta, mude o status de "Autônomo" para "Ação Pendente".

2. ELABORAÇÃO DA RESPOSTA (synthesis):
   - Após determinar o status, concentre-se em elaborar uma resposta para o ensaio utilizando a documentação adicional (específica do processo/projeto atual).
   - A resposta elaborada deve seguir rigorosamente o padrão de formatação e redação utilizado nos pareceres anteriores presentes nos relatórios históricos.
   - Por padrão, suas respostas devem referenciar as documentações, anexos e ferramentas que comprovem a sua linha argumentativa.
   - As respostas (synthesis) devem ser sempre completas, objetivas e claras.
   - A síntese (synthesis) do modelo DEVE ser apresentada independentemente do status ser "Autônomo" ou "Ação Pendente".

3. INSTRUÇÕES AO USUÁRIO (instruction):
   - O campo "instruction" deve conter instruções construtivas.
   - Deixe claro quais são as suas dúvidas e quais informações estão faltando, para que o usuário possa dar mais contexto e apontar (através de upload ou prompt adicional) quais itens da documentação podem ser usados para gerar a resposta.

Sua saída DEVE ser ESTRITAMENTE em formato JSON válido para não quebrar o pipeline, com a seguinte estrutura:
{
  "status": "Autônomo" ou "Ação Pendente",
  "instruction": "Instruções construtivas e claras sobre as dúvidas do modelo e o que o usuário deve fornecer (ex: fotos, tabelas, apontamento de documentação).",
  "ensaios": [
    {
      "id": "EN.III.1.1.01",
      "synthesis": "Sua resposta completa, objetiva e referenciada, seguindo o padrão histórico, apresentada tanto para Autônomo quanto para Ação Pendente."
    }
  ]
}

Regras adicionais:
- O usuário pode fornecer instruções adicionais (prompt iterativo) para corrigir ou forçar um raciocínio.
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
                raw_text = f.read()
                
            import re
            # Extrair apenas o enunciado e os ensaios, descartando a seção de Pareceres
            cutoff_match = re.search(r'\\(?:sub)*section\*?\{EN\.[^}]+\s*-\s*Parecer:\}', raw_text)
            if cutoff_match:
                req_text = raw_text[:cutoff_match.start()].strip()
            else:
                req_text = raw_text.strip()
        else:
            add_log(f"Aviso: Arquivo {tex_path} não encontrado. Usando texto vazio.")
            
        query_text = req_text[:6000] # Limita o tamanho para não estourar o contexto do modelo de embedding (nomic-embed-text)
        
        docs_proj = vectorstore_proj.similarity_search(query_text, k=10)
        context_proj = "\n\n".join([f"[Fonte: {d.metadata.get('source', 'Desconhecida')}]\n{d.page_content}" for d in docs_proj])
        
        docs_hist = vectorstore_hist.similarity_search(query_text, k=5)
        context_hist = "\n\n".join([f"[Histórico: {d.metadata.get('source', 'Desconhecida')}]\n{d.page_content}" for d in docs_hist])
        
        add_log(f"Contexto recuperado: {len(docs_proj)} chunks do projeto, {len(docs_hist)} chunks históricos")
        
        user_prompt = req.get('user_prompt', '')
        
        human_msg = f"CONTEÚDO DO REQUISITO (.tex):\n{req_text}\n\nCONTEXTO DO PROJETO ATUAL:\n{context_proj}\n\nCONTEXTO HISTÓRICO:\n{context_hist}\n"
        if user_prompt:
            human_msg += f"\nINSTRUÇÃO ADICIONAL DO USUÁRIO:\n{user_prompt}\n(Use esta instrução para corrigir seu raciocínio e gerar uma nova resposta)"
        
        add_log(f"Consultando LLM Planejador para o {req['id']}...")
        
        # Log do trace para o Worker (avaliação do modelo)
        logger.info(f"=== TRACE LLM para {req['id']} ===")
        logger.info(f"System:\n{SYSTEM_PROMPT}")
        logger.info(f"Human:\n{human_msg}")
        logger.info(f"====================================")
        
        try:
            response = llm.invoke([
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=human_msg)
            ])
            
            logger.info(f"=== RESPOSTA LLM {req['id']} ===")
            logger.info(response.content)
            logger.info(f"====================================")
            
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
            state['task_progress'] = {
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

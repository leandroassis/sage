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
Seu objetivo é analisar o texto fonte de um ensaio normativo em LaTeX e elaborar uma resposta detalhada com base no contexto fornecido.

<instrucoes_operacao>
1. DETERMINAÇÃO DE STATUS:
   - Baseado no histórico deste mesmo ensaio (se houver), determine se ele pode ser satisfeito apenas com a síntese textual que você vai escrever (Status: "Autônomo") ou se necessita de evidências adicionais anexadas pelo usuário, como tabelas, prints e fotos (Status: "Ação Pendente").
   - Se o projeto atual não tiver informações suficientes para satisfazer o requisito, marque o status como "Ação Pendente".

2. ELABORAÇÃO DA RESPOSTA (synthesis):
   - A sua resposta elaborada deve seguir rigorosamente o padrão de redação dos pareceres históricos.
   - Referencie o contexto do projeto atual (manual, código, etc) para embasar a aprovação ou reprovação do ensaio.
   - Sempre forneça a síntese detalhada.

3. INSTRUÇÕES AO USUÁRIO (instruction):
   - Se houver lacunas, descreva construtivamente o que o usuário deve fornecer (ex: enviar foto da placa, apontar trecho do manual).
</instrucoes_operacao>

Sua saída DEVE ser ESTRITAMENTE em formato JSON, retornando APENAS o JSON válido. Exemplo:
{
  "status": "Autônomo",
  "instruction": "Nenhuma evidência externa necessária, a documentação atende ao requisito.",
  "synthesis": "O equipamento analisado apresenta na documentação a especificação de que..."
}

Retorne em Português do Brasil e apenas o JSON.
"""

def run_acquire_agent(session_id: str, target_req_id: str = None, target_ensaio_id: str = None):
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
        model="llama3:latest",
        format="json",
        temperature=0.0
    )
    
    # Montar a lista flat de tarefas (ensaios)
    tasks = []
    for req in requisitos:
        if target_req_id and req['id'] != target_req_id:
            continue
        for ensaio in req.get('ensaios', []):
            if target_ensaio_id and ensaio['id'] != target_ensaio_id:
                continue
            # Pula os que já estão finalizados ou em andamento, exceto se for target
            if not target_req_id and ensaio.get('status') in ["Autônomo", "Ação Pendente", "Pronto"] and ensaio.get('synthesis'):
                continue
            tasks.append((req, ensaio))
            
    total = len(tasks)
    start_time = time.time()
    
    for i, (req, ensaio) in enumerate(tasks):
        add_log(f"Analisando ensaio {ensaio['id']} do requisito {req['id']}...")
        
        req_id = req['id']
        ensaio_safe = ensaio['id'].replace('.', '_').replace(':', '')
        tex_filename = f"{ensaio_safe}.tex"
        tex_path = os.path.join(DATA_DIR, "projects", session_id, "requisitos", req_id, tex_filename)
        
        ensaio_text = ""
        if os.path.exists(tex_path):
            with open(tex_path, "r", encoding="utf-8") as f:
                ensaio_text = f.read().strip()
        else:
            add_log(f"Aviso: Arquivo {tex_path} não encontrado.")
            
        query_text = ensaio_text[:6000]
        
        docs_proj = vectorstore_proj.similarity_search(query_text, k=10)
        context_proj = "\n\n".join([f"[Fonte: {d.metadata.get('source', 'Desconhecida')}]\n{d.page_content}" for d in docs_proj])
        
        # Filtra histórico por ensaio_id
        filter_dict = {"ensaio_id": ensaio['id']}
        docs_hist = vectorstore_hist.similarity_search(query_text, k=5, filter=filter_dict)
        # Se não achar nada com o filtro, tenta sem o filtro
        if not docs_hist:
            docs_hist = vectorstore_hist.similarity_search(query_text, k=3)
            
        context_hist = "\n\n".join([f"[Histórico: {d.metadata.get('source', 'Desconhecida')}]\n{d.page_content}" for d in docs_hist])
        
        add_log(f"Contexto recuperado: {len(docs_proj)} chunks do projeto, {len(docs_hist)} chunks históricos")
        
        user_prompt = ensaio.get('user_prompt', '')
        
        human_msg = f"<ensaio_especifico>\n{ensaio_text}\n</ensaio_especifico>\n\n<contexto_projeto_atual>\n{context_proj}\n</contexto_projeto_atual>\n\n<contexto_historico>\n{context_hist}\n</contexto_historico>\n"
        if user_prompt:
            human_msg += f"\n<instrucao_adicional_usuario>\n{user_prompt}\n(Use esta instrução para corrigir seu raciocínio e gerar a síntese de forma alinhada com o usuário)\n</instrucao_adicional_usuario>"
            
        add_log(f"Consultando LLM Planejador ({llm.model}) para {ensaio['id']}...")
        
        logger.info(f"=== TRACE LLM para {ensaio['id']} ===")
        logger.info(f"System:\n{SYSTEM_PROMPT}")
        logger.info(f"Human:\n{human_msg}")
        logger.info(f"====================================")
        
        try:
            response = llm.invoke([
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=human_msg)
            ])
            
            logger.info(f"=== RESPOSTA LLM {ensaio['id']} ===")
            logger.info(response.content)
            logger.info(f"====================================")
            
            result = json.loads(response.content)
            
            ensaio['status'] = result.get('status', 'Ação Pendente')
            ensaio['instruction'] = result.get('instruction', 'Nenhuma instrução gerada.')
            ensaio['synthesis'] = result.get('synthesis', 'Erro ao obter síntese.')
            
            add_log(f"-> Status: {ensaio['status']}")
            
        except Exception as e:
            add_log(f"Erro ao processar {ensaio['id']} via LLM: {str(e)}")
            ensaio['status'] = 'Ação Pendente'
            ensaio['instruction'] = 'Falha no processamento LLM. Trate manualmente.'
            ensaio['synthesis'] = 'Erro no agente.'
        
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

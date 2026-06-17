import time
import sys
import os
import traceback

sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from core.database import get_pending_job, update_job_status
from core.ingestion.historical_pipeline import run_historical_pipeline
from core.ingestion.project_pipeline import run_project_pipeline
from core.agents.acquire_agent import run_acquire_agent
from core.config import DATA_DIR, get_logger

logger = get_logger("Worker")

def run_worker():
    logger.info("==========================================================")
    logger.info("🤖 SAGE Worker Daemon Iniciado")
    logger.info("==========================================================")
    logger.info("[Worker] Escutando a Fila de Execução Global...")
    
    while True:
        try:
            job = get_pending_job()
            if not job:
                time.sleep(3)
                continue
                
            job_id = job['id']
            task_type = job['task_type']
            session_id = job['session_id']
            
            logger.info(f"Pegou job {job_id} | Tipo: {task_type} | Sessão: {session_id}")
            update_job_status(job_id, "RUNNING")
            
            if task_type == "STUDY_PIPELINE":
                db_dir = os.path.join(DATA_DIR, "vector_db")
                historical_dir = os.path.join(DATA_DIR, "historical_reports")
                
                logger.info("Iniciando Pipeline Histórico...")
                if os.path.exists(historical_dir):
                    run_historical_pipeline(historical_dir, db_dir, add_log_callback=logger.info)
                    
                logger.info("Iniciando Pipeline do Projeto Atual (AST e PDFs)...")
                run_project_pipeline(session_id, db_dir)
                
            elif task_type == "ACQUIRE_PLANNING":
                logger.info("Executando Planejador de Acquire via LLM...")
                run_acquire_agent(session_id)
                
            elif task_type.startswith("ACQUIRE_REPROCESS:"):
                parts = task_type.split(":")
                req_id = parts[1]
                ensaio_id = parts[2] if len(parts) > 2 else None
                logger.info(f"Re-processando Requisito {req_id} / Ensaio {ensaio_id}...")
                run_acquire_agent(session_id, target_req_id=req_id, target_ensaio_id=ensaio_id)
                
            elif task_type.startswith("AST_TRANSLATE:"):
                file_path = task_type.split(":", 1)[1]
                logger.info(f"Executando Tradução AST para {file_path}...")
                from core.ingestion.ast_extractor import extract_ast_chunks
                from langchain_ollama import ChatOllama
                from langchain_core.messages import HumanMessage
                from langchain_core.documents import Document
                from langchain_community.embeddings import OllamaEmbeddings
                from langchain_community.vectorstores import Chroma
                
                coder_llm = ChatOllama(model="qwen2.5-coder:7b", temperature=0.0)
                chunks = extract_ast_chunks(file_path)
                documents_to_insert = []
                
                for c in chunks:
                    raw_code = c["content"]
                    prompt = f"Descreva em PORTUGUES DO BRASIL técnico o que este trecho de código faz, detalhando manipulação de variáveis, bibliotecas utilizadas e funcionalidades:\n\n{raw_code}"
                    try:
                        logger.info(f"[Worker] Traduzindo bloco AST ({c['metadata'].get('type')}) com LLM...")
                        logger.info(f"=== TRACE LLM AST para {file_path} ===")
                        logger.info(f"Prompt:\n{prompt}")
                        logger.info("=======================================")
                        
                        response = coder_llm.invoke([HumanMessage(content=prompt)])
                        translated_text = response.content
                        
                        logger.info(f"=== RESPOSTA LLM AST ===")
                        logger.info(translated_text)
                        logger.info("========================")
                        
                        final_content = f"CÓDIGO ORIGINAL:\n{raw_code}\n\nDESCRIÇÃO TÉCNICA:\n{translated_text}"
                    except Exception as e:
                        logger.warning(f"[Worker] Erro ao traduzir AST com LLM: {e}")
                        final_content = raw_code
                        
                    meta = c["metadata"].copy()
                    file_name = os.path.basename(meta.get('file', file_path))
                    start = meta.get('start_line', 0)
                    end = meta.get('end_line', 0)
                    meta['source'] = f"{file_name} (linhas {start}-{end})"
                    
                    from langchain_text_splitters import RecursiveCharacterTextSplitter
                    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=200)
                    chunks_text = text_splitter.split_text(final_content)
                    
                    for txt in chunks_text:
                        documents_to_insert.append(Document(page_content=txt, metadata=meta))
                
                if documents_to_insert:
                    logger.info(f"[Worker] Inserindo {len(documents_to_insert)} chunks traduzidos de {file_path} no VectorDB...")
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
                    vectorstore.add_documents(documents_to_insert)
                
            elif task_type == "FILL_GENERATION":
                logger.info("Executando Geração de Parecer (Simulando 5s de IA)...")
                time.sleep(5)
            
            else:
                logger.warning(f"Task type desconhecido: {task_type}")
                
            logger.info(f"Job {job_id} concluído com sucesso.")
            update_job_status(job_id, "COMPLETED")
            
        except Exception as e:
            err_msg = str(e)
            _jid = job_id if 'job_id' in locals() else 'N/A'
            logger.error(f"Erro no job {_jid}: {err_msg}")
            traceback.print_exc()
            if _jid != 'N/A':
                update_job_status(_jid, "FAILED", error_message=err_msg)
            
        time.sleep(1)

if __name__ == "__main__":
    run_worker()

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

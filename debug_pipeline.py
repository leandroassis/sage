import os
import shutil
import argparse
import logging
import time

from core.config import DATA_DIR, get_logger
from core.ingestion.historical_pipeline import run_historical_pipeline
from core.ingestion.project_pipeline import run_project_pipeline
from core.agents.acquire_agent import run_acquire_agent
from core.database import update_session_state, get_session_state, create_session, enqueue_job, get_session_active_job

# Configuração de logger pra tela
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = get_logger("DebugPipeline")

def main():
    parser = argparse.ArgumentParser(description="Testa o pipeline completo do SAGE (debug rápido).")
    parser.add_argument("--doc_pdf", required=True, help="PDF de documentação do projeto atual.")
    parser.add_argument("--req_tex", required=True, help="Arquivo .tex com o requisito e ensaios.")
    parser.add_argument("--hist_pdf", required=True, help="PDF simulando relatórios históricos.")
    args = parser.parse_args()

    for path in [args.doc_pdf, args.req_tex, args.hist_pdf]:
        if not os.path.exists(path):
            logger.error(f"Arquivo não encontrado: {path}")
            return

    # Ativa o modo debug para os pipelines
    os.environ["SAGE_DEBUG"] = "1"

    session_id = f"debug_session_{int(time.time())}"
    db_dir = os.path.join(DATA_DIR, "vector_db")
    
    print("\n" + "="*60)
    print("🚀 INICIANDO DEBUG DE PIPELINE COMPLETO SAGE")
    print("="*60 + "\n")

    # Limpeza total do vector_db para garantir estado limpo
    # (remove tracker.db e coleções ChromaDB de runs anteriores)
    if os.path.exists(db_dir):
        shutil.rmtree(db_dir)
        logger.info(f"[Debug] vector_db limpo: {db_dir}")
    os.makedirs(db_dir, exist_ok=True)

    # 1. Pipeline Histórico
    print(">>> FASE 1A: PREPARANDO INGESTÃO HISTÓRICA")
    hist_dir = os.path.join(DATA_DIR, "historical_reports")
    if os.path.exists(hist_dir):
        shutil.rmtree(hist_dir)
    os.makedirs(hist_dir, exist_ok=True)
    shutil.copy(args.hist_pdf, os.path.join(hist_dir, os.path.basename(args.hist_pdf)))
    
    # 2. Pipeline do Projeto
    print("\n>>> FASE 1B: PREPARANDO INGESTÃO DO PROJETO")
    proj_doc_dir = os.path.join(DATA_DIR, "projects", session_id, "documentacao")
    os.makedirs(proj_doc_dir, exist_ok=True)
    shutil.copy(args.doc_pdf, os.path.join(proj_doc_dir, os.path.basename(args.doc_pdf)))
    
    # Cria estado de sessão vazio pra nao quebrar
    create_session(session_id, "Sessão de Debug")
    state = {}
    update_session_state(session_id, "v1_study", state)
    
    print("\n>>> ENFILEIRANDO FASE 1 (STUDY_PIPELINE) NO WORKER")
    enqueue_job(session_id, "STUDY_PIPELINE")
    
    while True:
        job = get_session_active_job(session_id)
        if not job:
            break
        print(f"Aguardando worker processar FASE 1... (Acompanhe em logs/worker.log) | Status: {job['status']}")
        time.sleep(3)
    
    # 3. Pipeline de Acquire
    print("\n>>> FASE 2: PREPARANDO ACQUIRE AGENT")
    req_id = "REQ_DEBUG"
    req_dir = os.path.join(DATA_DIR, "projects", session_id, "requisitos", req_id)
    os.makedirs(req_dir, exist_ok=True)
    
    # Precisamos salvar o .tex com o nome esperado (REQUISITO_DEBUG.tex)
    tex_filename = f"REQUISITO_{req_id.replace('REQ_', '')}.tex"
    shutil.copy(args.req_tex, os.path.join(req_dir, tex_filename))
    
    state = get_session_state(session_id, "v1_study") or {}
    state["requisitos"] = [
        {
            "id": req_id,
            "status": "Ação Pendente",
            "ensaios": []
        }
    ]
    update_session_state(session_id, "v1_study", state)
    
    print("\n>>> ENFILEIRANDO FASE 2 (ACQUIRE_REPROCESS) NO WORKER")
    enqueue_job(session_id, f"ACQUIRE_REPROCESS:{req_id}")
    
    while True:
        job = get_session_active_job(session_id)
        if not job:
            break
        print(f"Aguardando worker processar FASE 2... (Acompanhe em logs/worker.log) | Status: {job['status']}")
        time.sleep(3)
        
    print("\n" + "="*60)
    print("✅ TESTE DO PIPELINE FINALIZADO COM SUCESSO!")
    print(f"Session ID de debug usado: {session_id}")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()

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
    
    # Copiar também código-fonte de teste, se houver
    test_code_path = os.path.join("tests", "code.c")
    if os.path.exists(test_code_path):
        shutil.copy(test_code_path, os.path.join(proj_doc_dir, "code.c"))
        logger.info("[Debug] Arquivo de código code.c adicionado à documentação.")
    
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
    
    # Extrair os ensaios do test.tex para simular o pre_study
    ensaios_list = []
    with open(args.req_tex, "r", encoding="utf-8") as f:
        tex_content = f.read()
    
    import re
    # Encontra todos os \item \textbf{EN...
    en_pattern = re.compile(r'\\item\s+\\textbf\{(EN\.[^:}]+)(.*?)(?=\\item\s+\\textbf\{EN|\\end\{itemize\}|\\end\{document\}|$)', re.DOTALL)
    ensaios_matches = en_pattern.finditer(tex_content)
    
    for match in ensaios_matches:
        en_id = match.group(1).strip()
        ensaio_safe = en_id.replace('.', '_').replace(':', '')
        bloco_completo = match.group(0).strip()
        
        # Salva o bloco inteiro no tex do ensaio
        with open(os.path.join(req_dir, f"{ensaio_safe}.tex"), "w", encoding="utf-8") as fe:
            fe.write(bloco_completo)
        
        ensaios_list.append({
            "id": en_id,
            "status": "Ação Pendente",
            "instruction": "",
            "synthesis": ""
        })
    
    state = get_session_state(session_id, "v1_study") or {}
    state["requisitos"] = [
        {
            "id": req_id,
            "status": "Ação Pendente",
            "ensaios": ensaios_list
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

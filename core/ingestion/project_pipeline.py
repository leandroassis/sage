import os
import subprocess
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from core.ingestion.ast_extractor import extract_ast_chunks
from core.config import DATA_DIR, PROJECT_ROOT, get_logger

logger = get_logger("ProjectPipeline")

def log(msg):
    logger.info(msg)

def run_project_pipeline(project_id: str, db_dir: str):
    docs_dir = os.path.join(DATA_DIR, "projects", project_id, "documentacao")
    if not os.path.exists(docs_dir):
        log("[Project Pipeline] Nenhuma documentação encontrada.")
        return

    embeddings = OllamaEmbeddings(
        model="nomic-embed-text",
        model_kwargs={
            "num_gpu": 19,
            "num_ctx": 4096,
            "keep_alive": 0
        }
    )
    
    collection_name = f"Collection_Project_{project_id.replace('-', '_')}"
    vectorstore = Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=db_dir
    )
    
    # Limpar coleção antiga se existir (para isolar/resetar)
    try:
        vectorstore._client.delete_collection(collection_name)
        vectorstore = Chroma(
            collection_name=collection_name,
            embedding_function=embeddings,
            persist_directory=db_dir
        )
    except:
        pass

    documents_to_insert = []
    
    for root, _, files in os.walk(docs_dir):
        for file in files:
            file_path = os.path.join(root, file)
            ext = os.path.splitext(file)[1].lower()
            
            if ext == '.xlsx':
                log(f"[Project Pipeline] Ignorando planilha: {file}")
                continue
                
            elif ext == '.pdf':
                log(f"[Project Pipeline] Processando PDF via Marker: {file}")
                out_dir = os.path.join(PROJECT_ROOT, "tmp_marker_project", project_id)
                os.makedirs(out_dir, exist_ok=True)
                
                try:
                    env = os.environ.copy()
                    env["CUDA_VISIBLE_DEVICES"] = ""
                    import multiprocessing
                    cpu_cores = str(multiprocessing.cpu_count())
                    env["OMP_NUM_THREADS"] = cpu_cores
                    env["MKL_NUM_THREADS"] = cpu_cores
                    
                    subprocess.run(
                        ["marker_single", file_path, "--output_dir", out_dir],
                        check=True, env=env
                    )
                    
                    pdf_basename = file.replace('.pdf', '')
                    md_file = os.path.join(out_dir, pdf_basename, f"{pdf_basename}.md")
                    if os.path.exists(md_file):
                        with open(md_file, "r", encoding="utf-8") as f:
                            content = f.read()
                            documents_to_insert.append(Document(page_content=content, metadata={"source": file_path, "type": "manual_pdf"}))
                        log(f"[Project Pipeline] PDF {file} lido com sucesso.")
                    else:
                        log(f"[Project Pipeline] Arquivo gerado não encontrado: {md_file}")
                except Exception as e:
                    log(f"[Project Pipeline] Erro Marker {file}: {e}")
            else:
                log(f"[Project Pipeline] Extraindo AST de código fonte: {file}")
                chunks = extract_ast_chunks(file_path)
                for c in chunks:
                    documents_to_insert.append(Document(page_content=c["content"], metadata=c["metadata"]))
                    
    if documents_to_insert:
        log(f"[Project Pipeline] Inserindo {len(documents_to_insert)} chunks no VectorDB...")
        vectorstore.add_documents(documents_to_insert)
        # Em versoes mais novas do Chroma persist() não é necessario mas deixamos para garantir.
        try:
            vectorstore.persist()
        except AttributeError:
            pass
    else:
        log("[Project Pipeline] Nenhum chunk extraído.")
        
    log("[Project Pipeline] Ingestão do projeto atual finalizada.")

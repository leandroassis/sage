import os
import re
import subprocess
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from core.ingestion.ast_extractor import extract_ast_chunks
from core.config import DATA_DIR, PROJECT_ROOT, get_logger

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.base_models import InputFormat
from docling_core.types.doc import ImageRefMode
from core.ingestion.vlm_processor import describe_image_base64
from core.ingestion.docling_utils import export_to_markdown_with_pages, extract_page_from_content
from core.database import get_session_state, update_session_state
import time
logger = get_logger("ProjectPipeline")

def log(msg):
    logger.info(msg)

def run_project_pipeline(project_id: str, db_dir: str):
    state = get_session_state(project_id, "v1_study") or {}
    equipment_folder = state.get("equipment_folder")
    
    docs_dir = os.path.join(DATA_DIR, "projects", project_id, "documentacao")
    dirs_to_scan = []
    
    if os.path.exists(docs_dir):
        dirs_to_scan.append(docs_dir)
        
    if equipment_folder and os.path.exists(equipment_folder):
        dirs_to_scan.append(equipment_folder)
        
    if not dirs_to_scan:
        log("[Project Pipeline] Nenhuma documentação encontrada nas pastas do projeto ou no caminho absoluto fornecido.")
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
    files_to_process = []
    
    for scan_dir in dirs_to_scan:
        for root, _, files in os.walk(scan_dir):
            for file in files:
                files_to_process.append((root, file))
                
    total_files = len(files_to_process)
    start_time = time.time()
    
    for i, (root, file) in enumerate(files_to_process):
        file_path = os.path.join(root, file)
        ext = os.path.splitext(file)[1].lower()
        
        elapsed = time.time() - start_time
        items_done = i + 1
        eta_seconds = (elapsed / items_done) * (total_files - items_done)
        state['task_progress'] = {
            "current": items_done,
            "total": total_files,
            "eta": int(eta_seconds)
        }
        update_session_state(project_id, "v1_study", state)
        
        if ext == '.xlsx':
            log(f"[Project Pipeline] Ignorando planilha: {file}")
            continue
            
        if ext == '.pdf':
            log(f"[Docling] Convertendo {file} para Markdown com OCR e extração de imagens em memória...")
            
            pipeline_options = PdfPipelineOptions()
            pipeline_options.generate_picture_images = True
            
            converter = DocumentConverter(
                format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
            )
            
            try:
                result = converter.convert(file_path)
                md_content = export_to_markdown_with_pages(result.document)
            except Exception as e:
                log(f"[Docling] Erro ao converter {file}: {e}")
                continue
                
            if not md_content:
                log(f"[Docling] Falha: Markdown gerado de {file} está vazio.")
                continue
                
            # VLM Processor
            log(f"[Ollama] Inspecionando imagens extraídas de {file} (on-the-fly) com VLM...")
            img_pattern = re.compile(r'!\[.*?\]\(data:image/[a-zA-Z]+;base64,([A-Za-z0-9+/=]+)\)')
            matches = list(img_pattern.finditer(md_content))
            
            log(f"[Ollama] Encontradas {len(matches)} imagens em {file} para processamento VLM.")
            for idx, match in enumerate(matches):
                img_base64 = match.group(1)
                vlm_description = describe_image_base64(img_base64)
                log(f"[VLM] Imagem {idx+1}/{len(matches)}: {vlm_description[:80]}...")
                md_content = md_content.replace(match.group(0), vlm_description)
                
            # FALLBACK: Remove agressivamente qualquer outra string base64 que tenha sobrado
            md_content = re.sub(r'data:image/[a-zA-Z]+;base64,[A-Za-z0-9+/=]+', '[IMAGEM IGNORADA/REMOVIDA]', md_content)
            
            if project_id.startswith("debug_"):
                frag_dir = os.path.join(PROJECT_ROOT, "tests", "fragments")
                os.makedirs(frag_dir, exist_ok=True)
                frag_path = os.path.join(frag_dir, f"{file}_project.md")
                with open(frag_path, "w", encoding="utf-8") as f:
                    f.write(md_content)
                log(f"[Project Pipeline] Fragmento MD salvo em {frag_path}")
                
            # Fatiar o Markdown para evitar estouro de limite de contexto do modelo de Embeddings
            from langchain_text_splitters import MarkdownHeaderTextSplitter
            headers_to_split_on = [
                ("#", "Header 1"),
                ("##", "Header 2"),
                ("###", "Header 3"),
            ]
            markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
            md_header_splits = markdown_splitter.split_text(md_content)
            
            text_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=300)
            final_splits = text_splitter.split_documents(md_header_splits)
            
            for doc in final_splits:
                section_info = []
                for h in ["Header 1", "Header 2", "Header 3"]:
                    if h in doc.metadata:
                        section_info.append(doc.metadata[h])
                section_str = " > ".join(section_info)
                
                page = extract_page_from_content(doc.page_content)
                source_parts = [file]
                if page:
                    source_parts.append(f"p.{page}")
                if section_str:
                    source_parts.append(f"Seção: {section_str}")
                source_val = f"{source_parts[0]} ({', '.join(source_parts[1:])})" if len(source_parts) > 1 else file_path
                
                # Limpar marcadores de página do conteúdo final
                clean_content = re.sub(r'\n?<!-- PAGE \d+ -->\n?', '\n', doc.page_content).strip()
                
                documents_to_insert.append(Document(page_content=clean_content, metadata={"source": source_val, "type": "manual_pdf"}))
                
            log(f"[Project Pipeline] PDF {file} fatiado em {len(final_splits)} blocos e processado.")
        else:
            log(f"[Project Pipeline] Enfileirando análise de AST para o arquivo: {file}")
            from core.database import enqueue_job
            enqueue_job(project_id, f"AST_TRANSLATE:{file_path}")
                    
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

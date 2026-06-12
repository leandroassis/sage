import os
import re
import shutil
import subprocess
# pyrefly: ignore [missing-import]
from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OllamaEmbeddings
from .hash_tracker import HashTracker
from .vlm_processor import describe_image

def run_historical_pipeline(historical_dir: str, db_dir: str, add_log_callback=None):
    """
    Orquestra a ingestão de PDFs históricos:
    1. Calcula MD5 e verifica duplicidade.
    2. Converte PDF para Markdown (Marker).
    3. Multimodal: VLM descreve as imagens extraídas e substitui as tags no MD.
    4. Chunking (MarkdownHeaderTextSplitter).
    5. Inserção no ChromaDB via OllamaEmbeddings.
    """
    def log(msg):
        if add_log_callback:
            add_log_callback(msg)
        else:
            print(msg)
            
    tracker_path = os.path.join(db_dir, "tracker.db")
    tracker = HashTracker(tracker_path)
    
    chroma_path = os.path.join(db_dir, "chroma")
    # Utilizando Ollama para Embeddings conforme instrução (carrega sequencialmente)
    embeddings = OllamaEmbeddings(
        model="nomic-embed-text",
        model_kwargs={
            "num_gpu": 19,
            "num_ctx": 4096
        }
    )
    
    pdfs = [f for f in os.listdir(historical_dir) if f.lower().endswith('.pdf')]
    if not pdfs:
        log("[Study - Histórico] Nenhum PDF histórico encontrado.")
        return

    for pdf_file in pdfs:
        pdf_path = os.path.join(historical_dir, pdf_file)
        
        if tracker.is_processed(pdf_path):
            log(f"[Study - Histórico] Ignorado (Hash já processado): {pdf_file}")
            continue
            
        log(f"[Study - Histórico] Processando novo arquivo: {pdf_file}")
        
        # 1. Conversão com Marker
        out_dir = os.path.join(os.getcwd(), "tmp_marker", pdf_file.replace('.pdf', ''))
        os.makedirs(out_dir, exist_ok=True)
        
        log(f"[Marker] Convertendo {pdf_file} para Markdown...")
        # Comando CLI do marker-pdf (supondo que está no PATH do ambiente virtual)
        try:
            env = os.environ.copy()
            env["CUDA_VISIBLE_DEVICES"] = ""
            
            # Força o PyTorch a usar o máximo de threads disponíveis na CPU
            import multiprocessing
            
            cpu_cores = str(multiprocessing.cpu_count()-2)
            env["OMP_NUM_THREADS"] = cpu_cores
            env["MKL_NUM_THREADS"] = cpu_cores
            env["OPENBLAS_NUM_THREADS"] = cpu_cores
            env["VECLIB_MAXIMUM_THREADS"] = cpu_cores
            env["NUMEXPR_NUM_THREADS"] = cpu_cores
            
            subprocess.run(
                ["marker_single", pdf_path, "--output_dir", out_dir],
                check=True, capture_output=True, text=True, env=env
            )
        except Exception as e:
            log(f"[Marker] Erro ao converter {pdf_file}. Verifique a instalação do marker-pdf. Erro: {e}")
            continue
            
        # O marker cria um .md com o mesmo nome do pdf dentro da pasta
        md_file = os.path.join(out_dir, pdf_file.replace('.pdf', '.md'))
        if not os.path.exists(md_file):
            log(f"[Marker] Falha: Arquivo {md_file} não foi gerado.")
            continue
            
        with open(md_file, "r", encoding="utf-8") as f:
            md_content = f.read()
            
        # 2. Tratamento Multimodal (VLM)
        log(f"[Ollama] Inspecionando imagens extraídas de {pdf_file} com VLM...")
        # Regex para encontrar ![alt](path) no Markdown
        # O Marker salva as imagens geralmente em caminhos relativos na mesma pasta
        img_pattern = re.compile(r'!\[.*?\]\((.*?)\)')
        matches = list(img_pattern.finditer(md_content))
        
        for match in matches:
            img_rel_path = match.group(1)
            img_abs_path = os.path.join(out_dir, img_rel_path)
            
            if os.path.exists(img_abs_path):
                vlm_description = describe_image(img_abs_path)
                # Substitui a tag da imagem pela descrição textual gerada pelo VLM
                md_content = md_content.replace(match.group(0), vlm_description)
                
        # 3. Chunking
        log(f"[LangChain] Fatiando Markdown resultante...")
        headers_to_split_on = [
            ("#", "Header 1"),
            ("##", "Requisito"),
            ("###", "Subrequisito"),
        ]
        markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
        md_header_splits = markdown_splitter.split_text(md_content)
        
        # Adicionando metadados de origem
        for doc in md_header_splits:
            doc.metadata["source"] = pdf_file
            
        # 4. Vetorização no ChromaDB
        log(f"[ChromaDB] Vetorizando {len(md_header_splits)} blocos de {pdf_file} via Ollama...")
        # Usa Chroma.from_documents() para inserir
        vectorstore = Chroma(
            collection_name="Collection_Historico",
            embedding_function=embeddings,
            persist_directory=chroma_path
        )
        vectorstore.add_documents(documents=md_header_splits)
        
        # 5. Finalização
        tracker.mark_as_processed(pdf_path)
        log(f"[Study - Histórico] Concluído com sucesso: {pdf_file}")
        
        # Limpeza do temporário
        try:
            shutil.rmtree(os.path.join(os.getcwd(), "tmp_marker"))
        except:
            pass

    log("[Study - Histórico] Pipeline de ingestão finalizado.")

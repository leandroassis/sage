import os
import re
import shutil
# pyrefly: ignore [missing-import]
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
# pyrefly: ignore [missing-import]
from langchain_community.vectorstores import Chroma
# pyrefly: ignore [missing-import]
from langchain_community.embeddings import OllamaEmbeddings

# Docling imports
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.base_models import InputFormat, DocumentStream
from docling_core.types.doc import ImageRefMode

from .hash_tracker import HashTracker
from .vlm_processor import describe_image_base64
from .docling_utils import export_to_markdown_with_pages, extract_page_from_content
from core.config import PROJECT_ROOT

def run_historical_pipeline(reports_dir: str, db_dir: str, add_log_callback=None):
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
    
    # Utilizando Ollama para Embeddings conforme instrução (carrega sequencialmente)
    embeddings = OllamaEmbeddings(
        model="nomic-embed-text",
        model_kwargs={
            "num_gpu": 19,
            "num_ctx": 4096,
            "keep_alive": 0
        }
    )
    
    pdfs = [f for f in os.listdir(reports_dir) if f.lower().endswith('.pdf')]
    if not pdfs:
        log("[Study - Histórico] Nenhum PDF histórico encontrado.")
        return

    for pdf_file in pdfs:
        pdf_path = os.path.join(reports_dir, pdf_file)
        
        if tracker.is_processed(pdf_path):
            log(f"[Study - Histórico] Ignorado (Hash já processado): {pdf_file}")
            continue
            
        log(f"[Study - Histórico] Processando novo arquivo: {pdf_file}")
        
        log(f"[Docling] Convertendo {pdf_file} para Markdown com OCR e extração de imagens em memória...")
        
        # Configurar Docling
        pipeline_options = PdfPipelineOptions()
        pipeline_options.generate_picture_images = True
        
        converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
        )
        
        try:
            result = converter.convert(pdf_path)
            # Exporta para Markdown com marcadores de página e imagens em base64
            md_content = export_to_markdown_with_pages(result.document)
        except Exception as e:
            log(f"[Docling] Erro ao converter {pdf_file}: {e}")
            continue
            
        if not md_content:
            log(f"[Docling] Falha: Markdown gerado de {pdf_file} está vazio.")
            continue
            
        # 2. Tratamento Multimodal (VLM)
        log(f"[Ollama] Inspecionando imagens extraídas de {pdf_file} (on-the-fly) com VLM...")
        # Docling salva as imagens embarcadas como: ![Alt text](data:image/png;base64,iVBORw0KG...)
        img_pattern = re.compile(r'!\[.*?\]\(data:image/[a-zA-Z]+;base64,([A-Za-z0-9+/=]+)\)')
        matches = list(img_pattern.finditer(md_content))
        
        log(f"[Ollama] Encontradas {len(matches)} imagens em {pdf_file} para processamento VLM.")
        for idx, match in enumerate(matches):
            img_base64 = match.group(1)
            vlm_description = describe_image_base64(img_base64)
            log(f"[VLM] Imagem {idx+1}/{len(matches)}: {vlm_description[:80]}...")
            # Substitui a tag da imagem base64 inteira pela descrição textual
            md_content = md_content.replace(match.group(0), vlm_description)
            
        # FALLBACK: Remove agressivamente qualquer outra string base64 que tenha sobrado
        # (ex: tags HTML <img src="...">) para não poluir o ChromaDB e gerar milhares de chunks inúteis
        md_content = re.sub(r'data:image/[a-zA-Z]+;base64,[A-Za-z0-9+/=]+', '[IMAGEM IGNORADA/REMOVIDA]', md_content)
                
        frag_dir = os.path.join(PROJECT_ROOT, "tests", "fragments")
        os.makedirs(frag_dir, exist_ok=True)
        frag_path = os.path.join(frag_dir, f"{pdf_file}_hist.md")
        with open(frag_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        log(f"[Study - Histórico] Fragmento MD salvo em {frag_path}")

        # 3. Chunking
        log(f"[LangChain] Fatiando Markdown resultante...")
        headers_to_split_on = [
            ("#", "Header 1"),
            ("##", "Requisito"),
            ("###", "Subrequisito"),
        ]
        markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
        md_header_splits = markdown_splitter.split_text(md_content)
        
        # Como o splitter de markdown não tem limite de tamanho por bloco (apenas quebra por cabeçalho), 
        # precisamos garantir que nenhum bloco ultrapasse o contexto da nomic-embed-text
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=300)
        final_splits = text_splitter.split_documents(md_header_splits)
        
        # Adicionando metadados de origem com página
        for doc in final_splits:
            section_info = []
            for h in ["Header 1", "Requisito", "Subrequisito"]:
                if h in doc.metadata:
                    section_info.append(doc.metadata[h])
            section_str = " > ".join(section_info)
            
            page = extract_page_from_content(doc.page_content)
            source_parts = [pdf_file]
            if page:
                source_parts.append(f"p.{page}")
            if section_str:
                source_parts.append(f"Seção: {section_str}")
            doc.metadata["source"] = f"{source_parts[0]} ({', '.join(source_parts[1:])})" if len(source_parts) > 1 else pdf_file
            
            # Extract ensaio_id
            ensaio_match = re.search(r'(EN\.[A-Z0-9\.]+)', doc.page_content)
            if not ensaio_match and section_str:
                ensaio_match = re.search(r'(EN\.[A-Z0-9\.]+)', section_str)
            if ensaio_match:
                # remove dot at the end if caught by regex accidentally
                doc.metadata["ensaio_id"] = ensaio_match.group(1).rstrip('.')
            
            # Limpar marcadores de página do conteúdo final
            doc.page_content = re.sub(r'\n?<!-- PAGE \d+ -->\n?', '\n', doc.page_content).strip()
            
        # 4. Vetorização no ChromaDB
        log(f"[ChromaDB] Vetorizando {len(final_splits)} blocos de {pdf_file} via Ollama...")
        # Usa Chroma.from_documents() para inserir
        vectorstore = Chroma(
            collection_name="Collection_Historico",
            embedding_function=embeddings,
            persist_directory=db_dir
        )
        vectorstore.add_documents(documents=final_splits)
        
        # 5. Finalização
        tracker.mark_as_processed(pdf_path)
        log(f"[Study - Histórico] Concluído com sucesso: {pdf_file}")
            
    # Não temos mais tmp_marker para limpar
    log("[Study - Histórico] Pipeline de ingestão finalizado.")

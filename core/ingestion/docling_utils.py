"""
Utilitários compartilhados para extração de Markdown com metadados de página
a partir de documentos processados pelo Docling.
"""
from docling_core.types.doc import ImageRefMode, DocItemLabel


def export_to_markdown_with_pages(doc) -> str:
    """
    Exporta um DoclingDocument para Markdown inserindo marcadores de página
    (<!-- PAGE X -->) sempre que a página muda. Isso permite que o chunker
    posterior associe cada trecho à sua página de origem.
    
    Mantém imagens em base64 (ImageRefMode.EMBEDDED) para processamento VLM posterior.
    """
    md_parts = []
    current_page = None
    
    for item, level in doc.iterate_items():
        # Determinar página do item a partir da proveniência
        page_no = None
        if hasattr(item, 'prov') and item.prov:
            page_no = item.prov[0].page_no
        
        # Inserir marcador de página quando muda
        if page_no is not None and page_no != current_page:
            current_page = page_no
            md_parts.append(f"\n<!-- PAGE {current_page} -->\n")
        
        # Exportar o item para Markdown
        label = item.label if hasattr(item, 'label') else None
        
        if label == DocItemLabel.PICTURE:
            # Exportar imagem em base64 para processamento VLM
            try:
                img_md = item.export_to_markdown(doc=doc, image_mode=ImageRefMode.EMBEDDED)
                if img_md:
                    md_parts.append(img_md)
            except Exception:
                md_parts.append("[IMAGEM NÃO EXPORTÁVEL]")
        elif label == DocItemLabel.TABLE:
            try:
                table_md = item.export_to_markdown(doc=doc)
                if table_md:
                    md_parts.append(table_md)
            except Exception:
                md_parts.append("[TABELA NÃO EXPORTÁVEL]")
        elif hasattr(item, 'text') and item.text:
            text = item.text.strip()
            if not text:
                continue
                
            # Aplicar formatação de cabeçalhos baseado no nível hierárquico
            if label in (DocItemLabel.SECTION_HEADER, DocItemLabel.TITLE):
                prefix = "#" * min(level, 6)
                md_parts.append(f"{prefix} {text}")
            elif label == DocItemLabel.LIST_ITEM:
                md_parts.append(f"- {text}")
            elif label == DocItemLabel.CAPTION:
                md_parts.append(text)
            else:
                md_parts.append(text)
    
    return "\n".join(md_parts)


def extract_page_from_content(text: str) -> str:
    """
    Extrai o último marcador de página (<!-- PAGE X -->) encontrado
    ANTES do conteúdo do chunk. Retorna o número da página como string
    ou None se não encontrado.
    """
    import re
    pages = re.findall(r'<!-- PAGE (\d+) -->', text)
    if pages:
        return pages[0]  # Primeira página referenciada no chunk
    return None

import os
from tree_sitter_languages import get_language, get_parser

LANGUAGE_MAP = {
    ".py": "python",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "cpp",
    ".hpp": "cpp",
    ".ts": "typescript",
    ".js": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".php": "php",
    ".cs": "c_sharp",
    ".ex": "elixir",
    ".exs": "elixir",
    ".html": "html",
    ".css": "css"
}

# Substrings or exact matches for AST node types that represent semantic blocks
BLOCK_NODE_TYPES = [
    "function_definition", "class_definition", "method_definition", 
    "struct_specifier", "interface_declaration", "function_declaration",
    "method_declaration", "class_specifier", "struct_declaration",
    "function_item", "struct_item", "impl_item"
]

def extract_ast_chunks(file_path):
    _, ext = os.path.splitext(file_path)
    lang_name = LANGUAGE_MAP.get(ext.lower())
    
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        source_code = f.read()
        
    if not lang_name:
        return [{"content": source_code, "metadata": {"file": file_path, "type": "unknown_file"}}]
        
    try:
        parser = get_parser(lang_name)
        tree = parser.parse(source_code.encode("utf-8"))
        
        chunks = []
        code_bytes = source_code.encode("utf-8")
        
        def is_semantic_block(node_type):
            return any(b in node_type for b in BLOCK_NODE_TYPES)
        
        def traverse_and_chunk(node):
            if is_semantic_block(node.type):
                chunk_code = code_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")
                chunks.append({
                    "content": chunk_code,
                    "metadata": {
                        "file": file_path,
                        "type": node.type,
                        "start_line": node.start_point[0],
                        "end_line": node.end_point[0]
                    }
                })
                # We do not traverse children of a semantic block so we keep the class/function intact
                return
            
            for child in node.children:
                traverse_and_chunk(child)
                
        traverse_and_chunk(tree.root_node)
        
        if not chunks:
            # If no functions/classes found (e.g. simple script), return full file
            return [{"content": source_code, "metadata": {"file": file_path, "type": "full_file"}}]
            
        return chunks
        
    except Exception as e:
        print(f"[AST Extractor] Erro ao extrair AST de {file_path}: {e}")
        return [{"content": source_code, "metadata": {"file": file_path, "type": "error_fallback"}}]

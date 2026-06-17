import os
import re
import shutil

def run_pre_study(main_tex_path: str, project_dir: str):
    """
    Fase 0: Pre-Study
    Lê o main.tex base, fatia os requisitos em diretórios separados
    e gera um main_modular.tex com os includes.
    """
    print(f"[{__name__}] Iniciando Pre-Study...")
    print(f"[{__name__}] Arquivo de entrada: {main_tex_path}")
    print(f"[{__name__}] Diretório do projeto: {project_dir}")

    if not os.path.exists(main_tex_path):
        print(f"Erro: Arquivo {main_tex_path} não encontrado.")
        return

    with open(main_tex_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Regex to find \subsection{REQUISITO <NAME>}
    # We use re.finditer to get start and end positions
    pattern = re.compile(r'\\subsection\{REQUISITO\s+([^}]+)\}')
    matches = list(pattern.finditer(content))

    if not matches:
        print("Nenhum 'REQUISITO' encontrado no formato \\subsection{REQUISITO ...}.")
        return

    requisitos_dir = os.path.join(project_dir, "requisitos")
    os.makedirs(requisitos_dir, exist_ok=True)

    # Copia o conteúdo antes do primeiro requisito
    first_req_start = matches[0].start()
    new_main_content = content[:first_req_start]

    # Para identificar o final do documento
    end_doc_idx = content.find(r'\end{document}')
    if end_doc_idx == -1:
        end_doc_idx = len(content)

    import json
    
    print(f"[{__name__}] Encontrados {len(matches)} requisitos.")

    requisitos_list = []

    for i, match in enumerate(matches):
        full_tag = match.group(0)
        req_name_raw = match.group(1).strip()
        
        # Formata o nome, ex: III.1.1 -> III_1_1
        req_name_safe = req_name_raw.replace('.', '_').replace(' ', '_')
        folder_name = f"REQ_{req_name_safe}"
        req_filename = f"REQUISITO_{req_name_safe}.tex"
        
        req_dir = os.path.join(requisitos_dir, folder_name)
        evidencias_dir = os.path.join(req_dir, "evidencias")
        
        os.makedirs(evidencias_dir, exist_ok=True)
        
        start_idx = match.start()
        if i + 1 < len(matches):
            end_idx = matches[i+1].start()
        else:
            end_idx = end_doc_idx
            
        req_content = content[start_idx:end_idx]
        
        # Salva o arquivo principal do requisito
        req_filepath = os.path.join(req_dir, req_filename)
        with open(req_filepath, 'w', encoding='utf-8') as f:
            f.write(req_content)
            
        # EXTRAIR ENSAIOS
        ensaio_pattern = re.compile(r'\\item\s+\\textbf\{(EN\.[^}]+)\}(.*?)(?=\\item\s+\\textbf\{|\\end\{itemize\})', re.DOTALL)
        ensaios_matches = list(ensaio_pattern.finditer(req_content))
        
        ensaios_info = []
        for em in ensaios_matches:
            ensaio_id_raw = em.group(1).strip()
            if ensaio_id_raw.endswith(':'):
                ensaio_id_raw = ensaio_id_raw[:-1]
            ensaio_content = em.group(0)
            
            ensaio_safe = ensaio_id_raw.replace('.', '_').replace(':', '')
            ensaio_filename = f"{ensaio_safe}.tex"
            ensaio_filepath = os.path.join(req_dir, ensaio_filename)
            
            with open(ensaio_filepath, 'w', encoding='utf-8') as ef:
                ef.write(ensaio_content)
                
            ensaios_info.append({
                "id": ensaio_id_raw,
                "status": "Ação Pendente",
                "instruction": "",
                "synthesis": "",
                "evidencias": []
            })
            
        # Salva metadados do requisito
        with open(os.path.join(req_dir, "metadata.json"), 'w', encoding='utf-8') as mf:
            json.dump({"ensaios": ensaios_info}, mf, indent=4)
            
        requisitos_list.append({
            "id": folder_name,
            "status": "Pendente",
            "ensaios": ensaios_info
        })
            
        print(f"[{__name__}] Criado fragmento: {req_filepath} com {len(ensaios_info)} ensaios.")
        
        # Adiciona o \input{} no main_modular
        # Na verdade, como as extrações não deletaram nada do .tex original, o main pode continuar referenciando o requisito
        input_cmd = f"\\input{{requisitos/{folder_name}/{req_filename}}}\n\n"
        new_main_content += input_cmd

    # Adiciona o conteúdo do fim do documento
    new_main_content += content[end_doc_idx:]

    # Salva o main_modular.tex no diretório do projeto
    main_modular_path = os.path.join(project_dir, "main_modular.tex")
    with open(main_modular_path, 'w', encoding='utf-8') as f:
        f.write(new_main_content)
        
    # Salva a lista consolidada de requisitos no diretório base
    with open(os.path.join(requisitos_dir, "requisitos.json"), 'w', encoding='utf-8') as f:
        json.dump(requisitos_list, f, indent=4)
        
    print(f"[{__name__}] Criado arquivo principal modular: {main_modular_path}")
    print(f"[{__name__}] Pre-Study finalizado com sucesso!")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Uso: python pre_study.py <caminho_main.tex> <diretorio_projeto>")
    else:
        run_pre_study(sys.argv[1], sys.argv[2])

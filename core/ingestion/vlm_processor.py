import base64
# pyrefly: ignore [missing-import]
import ollama

def describe_image(image_path: str) -> str:
    """
    Carrega a imagem, envia para o modelo Moondream via Ollama,
    e retorna a descrição gerada. A diretiva keep_alive=0 garante 
    que o VLM seja imediatamente descarregado da VRAM após a inferência.
    """
    with open(image_path, "rb") as image_file:
        image_base64 = base64.b64encode(image_file.read()).decode('utf-8')
        
    prompt = (
        "Descreva detalhadamente o que está nesta imagem. "
        "Se for uma interface gráfica, terminal ou console, transcreva os comandos e logs visíveis. "
        "Seja direto e foque nas evidências técnicas."
    )
    
    try:
        response = ollama.generate(
            model='moondream',
            prompt=prompt,
            images=[image_base64],
            keep_alive=0,  # Força a descarga imediata da VRAM
            options={
                'num_gpu': 19,
                'num_ctx': 4096
            }
        )
        return f"[Descrição Visual: {response.get('response', '').strip()}]"
    except Exception as e:
        print(f"[VLM_Processor] Erro ao processar a imagem {image_path}: {str(e)}")
        return f"[Descrição Visual: Falha ao processar com Moondream - {str(e)}]"

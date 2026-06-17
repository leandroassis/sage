import base64
# pyrefly: ignore [missing-import]
import ollama

def describe_image_base64(image_base64: str) -> str:
    """
    Recebe a imagem em base64, envia para o modelo Moondream via Ollama,
    e retorna a descrição gerada. A diretiva keep_alive=0 garante 
    que o VLM seja imediatamente descarregado da VRAM após a inferência.
    """
    # Ignorar imagens muito pequenas (< 1KB em base64 ~ 750 bytes reais)
    # que geralmente são artefatos, ícones ou imagens corrompidas
    if len(image_base64) < 1000:
        return "[Descrição Visual: Imagem muito pequena/ignorada]"
    
    prompt = (
        "Descreva EM PORTUGUES DO BRASIL detalhadamente o que está nesta imagem. "
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
        description = response.get('response', '').strip()
        if not description:
            return "[Descrição Visual: Modelo não retornou descrição para esta imagem]"
        return f"[Descrição Visual: {description}]"
    except Exception as e:
        print(f"[VLM_Processor] Erro ao processar a imagem base64 no VLM: {str(e)}")
        return f"[Descrição Visual: Falha ao processar com Moondream - {str(e)}]"


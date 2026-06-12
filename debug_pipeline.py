import os
from core.ingestion.historical_pipeline import run_historical_pipeline
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OllamaEmbeddings

def main():
    # Caminhos para os dados
    historical_dir = os.path.join(os.getcwd(), "data", "historical_reports")
    db_dir = os.path.join(os.getcwd(), "data", "vector_db")
    
    os.makedirs(historical_dir, exist_ok=True)
    os.makedirs(db_dir, exist_ok=True)
    
    # Verifica se há PDFs para processar
    pdfs = [f for f in os.listdir(historical_dir) if f.lower().endswith('.pdf')]
    if not pdfs:
        print("===============================================================")
        print("Nenhum PDF encontrado na pasta: data/historical_reports")
        print("Por favor, adicione pelo menos um PDF de teste lá e rode novamente.")
        print("===============================================================")
        return

    print("===============================================================")
    print("Iniciando o Pipeline de Ingestão Histórica em modo de Debug...")
    print("===============================================================")
    
    # Executa o pipeline (os logs já são printados na tela por padrão)
    run_historical_pipeline(historical_dir, db_dir)
    
    print("\n===============================================================")
    print("Verificando a persistência no ChromaDB...")
    print("===============================================================")
    
    chroma_path = os.path.join(db_dir, "chroma")
    if not os.path.exists(chroma_path):
        print("O diretório do ChromaDB não foi encontrado. Algo pode ter falhado.")
        return
        
    embeddings = OllamaEmbeddings(
        model="nomic-embed-text",
        model_kwargs={
            "num_gpu": 19,
            "num_ctx": 4096
        }
    )
    
    vectorstore = Chroma(
        collection_name="Collection_Historico",
        embedding_function=embeddings,
        persist_directory=chroma_path
    )
    
    # Obtém todos os documentos da coleção
    collection_data = vectorstore.get()
    
    doc_count = len(collection_data.get('documents', []))
    print(f"Total de chunks vetorizados no banco: {doc_count}\n")
    
    if doc_count > 0:
        print("Amostra dos 3 primeiros chunks:")
        for i in range(min(3, doc_count)):
            print(f"\n--- Chunk {i+1} ---")
            print(f"Metadados: {collection_data['metadatas'][i]}")
            print(f"Conteúdo: {collection_data['documents'][i][:200]}...")
            
    print("\nDebug finalizado com sucesso!")

if __name__ == "__main__":
    main()

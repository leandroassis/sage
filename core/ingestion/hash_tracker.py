import sqlite3
import hashlib
import os

class HashTracker:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS historical_files (
                    filename TEXT PRIMARY KEY,
                    md5_hash TEXT NOT NULL,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

    def _calculate_md5(self, file_path: str) -> str:
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def is_processed(self, file_path: str) -> bool:
        """
        Calcula o hash do arquivo e verifica se já existe na base de dados.
        Retorna True se o arquivo já foi processado e seu hash não mudou.
        """
        if not os.path.exists(file_path):
            return False
            
        current_hash = self._calculate_md5(file_path)
        filename = os.path.basename(file_path)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT md5_hash FROM historical_files WHERE filename = ?', (filename,))
            result = cursor.fetchone()
            
            if result and result[0] == current_hash:
                return True
        return False

    def mark_as_processed(self, file_path: str):
        """
        Grava ou atualiza o registro do arquivo como processado.
        """
        current_hash = self._calculate_md5(file_path)
        filename = os.path.basename(file_path)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO historical_files (filename, md5_hash)
                VALUES (?, ?)
            ''', (filename, current_hash))
            conn.commit()

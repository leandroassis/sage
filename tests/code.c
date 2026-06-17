#include <stdio.h>
#include <stdlib.h>

// Função que verifica autenticidade do equipamento
int verify_authenticity(char* hw_id) {
    if (hw_id == NULL) return 0;
    
    // Algoritmo de hash simplificado para o exemplo
    unsigned long hash = 5381;
    int c;
    while ((c = *hw_id++)) {
        hash = ((hash << 5) + hash) + c; // hash * 33 + c
    }
    
    // Compara com o hash armazenado na memória segura
    unsigned long secure_hash = 0x8badf00d; 
    return (hash == secure_hash) ? 1 : 0;
}

int main() {
    printf("Iniciando rotina de checagem do equipamento...\n");
    return 0;
}

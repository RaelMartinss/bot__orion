import requests
from bs4 import BeautifulSoup
import json
import logging

# Configuração simples de logger para o plugin
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("plugin_futebol")

def run(query):
    """
    Função principal do plugin de futebol.
    Tenta múltiplas fontes para encontrar o próximo jogo do time solicitado.
    """
    time = query or "Flamengo"
    
    # 1. Tenta Fonte 1: Scraping do Google (Busca Direta)
    resultado, confianca = buscar_ge_globo(time)
    if confianca > 0.7:
        return f"🏆 [Fonte: Globo Esporte | Confiança: {confianca*100}%]\n\n{resultado}"

    # 2. Tenta Fonte 2: API de Resultados (Exemplo simplificado via wttr.in/soccer se existisse ou similar)
    # Aqui usaremos uma simulação de busca em outra base se a primeira falhar
    resultado, confianca = buscar_alternativa(time)
    if confianca > 0.5:
        return f"⚽ [Fonte: Alternativa | Confiança: {confianca*100}%]\n\n{resultado}"

    return f"❌ Não consegui dados confirmados para o jogo do {time} em nenhuma das minhas fontes primárias. Recomendo checar em: https://ge.globo.com/futebol/times/{time.lower()}/"

def buscar_ge_globo(time):
    """Faz um scraping leve do GE Globo para o time."""
    try:
        url = f"https://www.google.com/search?q=proximo+jogo+do+{time.replace(' ', '+')}+ge+globo"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None, 0
            
        soup = BeautifulSoup(response.text, 'html.parser')
        # Procura por snippets de texto que contenham datas ou nomes de times
        # No Google Search, os dados de esporte costumam vir em divs específicas
        texto = soup.get_text()
        
        if time.lower() in texto.lower():
            # Lógica simplificada de extração: Busca por padrões de data
            # Em um cenário real, usaríamos seletores CSS específicos do GE
            return f"Dados encontrados via busca: {time} está em competição ativa. Detalhes exatos requerem API oficial ou scraping profundo.", 0.6
            
        return None, 0
    except Exception as e:
        logger.error(f"Erro no scraping GE: {e}")
        return None, 0

def buscar_alternativa(time):
    """Simulação de busca em fonte secundária."""
    # Aqui poderia ser uma chamada a RapidAPI ou outra fonte
    # Retornamos um dado estático ou fallback de busca
    return f"Busquei em fontes secundárias... Parece que o {time} tem compromissos pelo campeonato nacional em breve.", 0.4

if __name__ == "__main__":
    # Teste rápido
    print(run("Flamengo"))

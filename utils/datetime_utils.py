"""
utils/datetime_utils.py
Provides localized date/time strings for Orion's system prompt.
"""

from datetime import datetime
import locale

# Tenta configurar o locale para Português (Brasil) — fallback para 'pt_BR' no Windows/Linux
try:
    locale.setlocale(locale.LC_ALL, 'pt_BR.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, 'Portuguese_Brazil.1252')
    except locale.Error:
        # Fallback manual se não conseguir carregar o locale do SO
        pass

DIAS_SEMANA = [
    "Segunda-feira", "Terça-feira", "Quarta-feira", 
    "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"
]

MESES = [
    "", "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"
]

def get_current_datetime_string() -> str:
    """Calcula a data e hora atual em formato por extenso para o ORION."""
    now = datetime.now()
    dia_semana = DIAS_SEMANA[now.weekday()]
    dia = now.day
    mes = MESES[now.month]
    ano = now.year
    hora = now.strftime("%H:%M")
    
    return f"Hoje é {dia_semana}, {dia} de {mes} de {ano}. Hora atual: {hora}."

if __name__ == "__main__":
    print(get_current_datetime_string())

# 🛰️ Orion Bot

Bot Telegram para controle remoto do seu PC Windows.

## Instalação

```bash
pip install -r requirements.txt
```

## Configuração

1. Crie um bot no [@BotFather](https://t.me/BotFather) e copie o token.
2. Abra `main.py` e substitua `SEU_TOKEN_AQUI` pelo token.
3. Execute:

```bash
python main.py
```

## Comandos

| Comando | Descrição |
|---|---|
| `/jogos` | Lista todos os jogos Steam instalados |
| `/jogo <nome>` | Abre um jogo (aceita nome parcial) |
| `/youtube <busca>` | Abre o YouTube com busca |
| `/netflix <busca>` | Abre a Netflix com busca |
| `/spotify <busca>` | Abre o Spotify com busca |
| `/vol_up [%]` | Aumenta o volume (padrão 10%) |
| `/vol_down [%]` | Diminui o volume (padrão 10%) |
| `/mute` | Muta/desmuta |
| `/desligar [s]` | Desliga o PC em N segundos (padrão 60) |
| `/reiniciar [s]` | Reinicia o PC em N segundos (padrão 60) |
| `/cancelar` | Cancela desligamento agendado |

## Como a descoberta de jogos funciona

O bot lê os arquivos `.acf` (AppManifest) do Steam para encontrar
todos os jogos instalados em todas as suas bibliotecas — incluindo
jogos em outros HDs/SSDs configurados no Steam.

Não é necessário configurar nenhum caminho manualmente.
Se você mudar de PC, o bot encontra os jogos automaticamente.

## Estrutura

```
orion_bot/
├── main.py                  # Ponto de entrada
├── requirements.txt
├── handlers/
│   ├── start.py             # /start e /ajuda
│   ├── jogos.py             # /jogos e /jogo
│   ├── midia.py             # /youtube, /netflix, /spotify
│   ├── volume.py            # /vol_up, /vol_down, /mute
│   └── sistema.py           # /desligar, /reiniciar, /cancelar
└── utils/
    └── steam_scanner.py     # Descoberta automática de jogos Steam
```

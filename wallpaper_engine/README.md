# ORION no Wallpaper Engine

Esta pasta contem uma versao do front do ORION pronta para importar no Wallpaper Engine.

## Pasta do wallpaper

Use:

`wallpaper_engine/orion_core/`

O arquivo principal e:

`wallpaper_engine/orion_core/index.html`

## Como importar

1. Abra o Wallpaper Engine.
2. Clique em `Create Wallpaper`.
3. Escolha `Web`.
4. Arraste o arquivo `index.html` da pasta `wallpaper_engine/orion_core/` para o editor.
5. Salve o projeto.

## Como testar com o backend do ORION

1. Inicie o Orion normalmente:

```powershell
uv run python .\main.py
```

2. O front do wallpaper tenta conectar em:

`ws://127.0.0.1:8765`

3. Quando o backend estiver ativo, o wallpaper deve sair de `OFFLINE` para `ONLINE` e reagir aos estados do Orion.

## Observacoes

- Esta versao foi preparada para rodar localmente, sem depender de browser externo.
- Se o Wallpaper Engine estiver em outra maquina ou sandbox diferente, a conexao local via WebSocket pode precisar de ajuste.

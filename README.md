# Discord Presence Bot — Fresh Start Kit

Um template **enxuto** para começar do zero, monitorando presença e oferecendo comandos básicos de estatística.

## Requisitos
- Python 3.10+
- Token de bot do Discord
- **Ativar Intents** no Portal do Discord (aplicativo do bot):
  - **MESSAGE CONTENT INTENT**
  - **PRESENCE INTENT**
  - **SERVER MEMBERS INTENT**

## Instalação
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
# source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
# Edite .env e cole o token
python run.py
```

## Comandos (prefixo padrão `!`)
- `!ping` — teste rápido
- `!status_now [@usuário]` — mostra o status atual do usuário (padrão: você)
- `!leaderboard [dias]` — ranking de usuários por ocorrências de presença registradas (padrão: 7 dias)
- `!stats [@usuário] [dias]` — contagem por status (online/idle/dnd/offline) do usuário em janelas (padrão: 7 dias)

## Observações
- Este bot **não altera a presença de outros usuários**; ele **lê** e **registra** mudanças de presença (quando as Intents estão ativas).
- O banco é um SQLite local (`presence_data.db` por padrão).

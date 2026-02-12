import gspread
from google.oauth2.service_account import Credentials

# 1) Caminho do JSON do robô
SERVICE_ACOUNT_FILE = "secrets/google_service_acount.json"

# 2) Escopos = permissões (o que o robo pode fazer)
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly"   

]

def main():
    # 3) Carregar as credenciais do robo
    creds = Credentials.from_service_account_file(
        SERVICE_ACOUNT_FILE,
        scopes = SCOPES

    )

    # 4) Cria o cliente que conversa com o robo
    client = gspread.authorize(creds)

    # 5) Abrir a planilha pelo nome
    spreadsheet_name = "NR1_Psicossociais_Respostas"
    sh = client.open(spreadsheet_name)

    # 6) Selecionar a primeira aba
    ws = sh.sheet1

    # 7) Ler respostas como listas de dicionarios
    rows = ws.get_all_records()

    print("Planilha carregada com Sucesso!")
    print(f"Total de respostas: {len(rows)}")

    if rows:
        print("\n Primeira resposta (Exemplo):")
        print(rows[0])

if __name__ == "__main__":
    main()
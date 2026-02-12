import re
import gspread
from google.oauth2.service_account import Credentials

SERVICE_ACCOUNT_FILE = "secrets/google_service_account.json"

# ✅ ESCOPO CORRETO
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
]

SPREADSHEET_ID = "1BaS2goahKS8KkhbUgFJSVcMHtfW_KoaZ0RIkOBne0go"


def parse_likert(value):
    """
    Converte respostas tipo:
    '4 = Frequentemente' -> 4
    '3' -> 3
    '' -> None
    """
    if value is None:
        return None

    value = str(value).strip()
    if value == "":
        return None

    # pega o primeiro número (1 a 5) que aparecer
    m = re.search(r"([1-5])", value)
    if not m:
        return None

    return int(m.group(1))


def normalize_column_name(col):
    """
    Limpa espaços extras e padroniza nomes.
    """
    if col is None:
        return ""
    return " ".join(str(col).strip().split())


def main():
    # 1) autenticação
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=SCOPES
    )
    client = gspread.authorize(creds)

    # 2) abrir planilha
    sh = client.open_by_key(SPREADSHEET_ID)
    ws = sh.sheet1
    rows = ws.get_all_records()

    print(f"Total de linhas lidas: {len(rows)}")

    if not rows:
        print("⚠️ Nenhuma linha encontrada na planilha.")
        return

    # 3) normalizar nomes das colunas
    cleaned_rows = []
    for row in rows:
        cleaned = {}
        for k, v in row.items():  # ✅ items()
            cleaned[normalize_column_name(k)] = v
        cleaned_rows.append(cleaned)

    # 4) localizar coluna do ID
    id_candidates = [k for k in cleaned_rows[0].keys() if "ID da coleta" in k]
    if not id_candidates:
        raise ValueError("Não achei a coluna 'ID da coleta' no Sheets.")
    id_col = id_candidates[0]

    # 5) localizar coluna perfil
    perfil_col = "Cargo / Perfil do respondente"
    if perfil_col not in cleaned_rows[0]:
        raise ValueError("Não achei a coluna 'Cargo / Perfil do respondente'.")

    # 6) filtrar somente respostas com ID preenchido
    valid_rows = [
        r for r in cleaned_rows
        if str(r.get(id_col, "")).strip() != ""
    ]

    print(f"Linhas com ID preenchido: {len(valid_rows)}")

    # 7) separar colaborador e gestão
    colaboradores = []
    gestao = []

    for r in valid_rows:
        perfil = str(r.get(perfil_col, "")).strip().lower()  # ✅ strip()
        if "colaborador" in perfil:
            colaboradores.append(r)
        else:
            gestao.append(r)

    print(f"✅ Colaboradores: {len(colaboradores)}")
    print(f"✅ Gestão/RH/SESMT: {len(gestao)}")

    # 8) exemplo conversão
    if colaboradores:
        a1_key_list = [k for k in colaboradores[0].keys() if k.startswith("A1 -")]
        if a1_key_list:
            a1_key = a1_key_list[0]
            valor_a1 = colaboradores[0][a1_key]
            print("\nExemplo A1 bruto:", valor_a1)
            print("Exemplo A1 convertido:", parse_likert(valor_a1))


if __name__ == "__main__":
    main()

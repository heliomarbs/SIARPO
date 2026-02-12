from logging import config
import gspread
from google.oauth2.service_account import Credentials

from src.config_loader import load_config
from src.engine import (
    calc_dimension_score,
    classify_status,
    parse_likert,
    get_interpretation_text
)
from src.roi import calc_roi
from src.finance import calc_payroll_monthly_from_responses


SERVICE_ACCOUNT_FILE = "secrets/google_service_account.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

SPREADSHEET_ID = "1BaS2goahKS8KkhbUgFJSVcMHtfW_KoaZ0RIkOBne0go"

# nomes das colunas conforme seu Forms
UNIT_COL_NAME = "Informe o código da unidade (Uxx) fornecido pela consultoria/empresa"
SHIFT_COL_NAME = "Turno"

# colunas financeiras (RH/Diretoria)
FIN_COL_PAYROLL = "Faixa de folha salarial mensal total (R$)"
FIN_COL_SALARY = "Faixa de salário médio mensal (R$)"  # não usado no ROI (apenas contexto/debug)
FIN_COL_EMPLOYEES = "Número de colaboradores (empresa/unidade)"


def normalize_column_name(col):
    """Remove espaços duplicados no título das colunas"""
    if col is None:
        return ""
    return " ".join(str(col).strip().split())


def find_column_key(row: dict, contains_text: str) -> str | None:
    """Acha a coluna que contém um texto (ex: ID da coleta)"""
    for k in row.keys():
        if contains_text.lower() in k.lower():
            return k
    return None


def mean(values):
    values = [v for v in values if v is not None]
    if not values:
        return None
    return sum(values) / len(values)


def calc_items_mean(rows: list[dict], item_codes: list[str]) -> dict:
    """
    Calcula a média de itens individuais (ex G1..G6 ou M1..M12)
    Retorna dict { "G1": 75.0, ... }
    """
    result = {}
    for code in item_codes:
        vals = []
        for r in rows:
            key = next((k for k in r.keys() if k.startswith(f"{code} -")), None)
            if not key:
                continue

            v = parse_likert(r.get(key))
            if v is None:
                continue

            vals.append(v)

        result[code] = mean(vals)

    return result


def likert_to_0_100(avg_likert):
    """Likert 1..5 -> escala 0..100"""
    if avg_likert is None:
        return None
    return ((avg_likert - 1) / 4) * 100


def format_brl(x: float | None) -> str:
    """Formata valor em BRL de forma amigável no terminal."""
    if x is None:
        return "SEM DADOS"
    return f"R$ {x:,.2f}"


def pct_text(x: float | None) -> str:
    if x is None:
        return "SEM DADOS"
    return f"{x*100:.1f}%"


def get_group_value(row: dict, col_name: str, default="SEM_DADOS") -> str:
    v = str(row.get(col_name, "")).strip()
    if v == "":
        return default
    return v


def normalize_profile(perfil: str) -> str:
    if not perfil:
        return "UNKNOWN"

    p = str(perfil).strip().lower()

    if p.startswith("1."):
        return "COLABORADOR"

    if p.startswith("2."):
        return "LIDERANCA"

    if p.startswith("3."):
        return "RH_DP_FINANCEIRO"

    if p.startswith("4."):
        return "DIRETORIA"

    if p.startswith("5."):
        return "SESMT"

    return "UNKNOWN"



def calc_risk_block(config, rows_block):
    """Calcula R1..R6 + status + texto para um subconjunto"""
    risk_results = {}

    for dim_id in ["R1", "R2", "R3", "R4", "R5", "R6"]:
        dim_scores = []
        for row in rows_block:
            r = calc_dimension_score(row, config, dim_id)
            dim_scores.append(r["score_0_100"])

        avg_dim = mean(dim_scores)
        status = classify_status(avg_dim, config["thresholds"]["risk_status"])
        interpretation = get_interpretation_text(config, "dimension_status", status["label"])

        risk_results[dim_id] = {
            "name": config["dimensions"][dim_id]["name"],
            "score": avg_dim,
            "status": status["label"],
            "icon": status["icon"],
            "interpretation": interpretation
        }

    return risk_results


def calc_impact_block(config, rows_block):
    """Calcula impactos G1..G6 + status + texto para um subconjunto"""
    impacto_items = config["dimensions"]["IMPACTO"]["items"]
    g_likert = calc_items_mean(rows_block, impacto_items)

    impactos = {}
    for code, avg_lik in g_likert.items():
        score_0_100 = likert_to_0_100(avg_lik)
        status = classify_status(score_0_100, config["thresholds"]["impact_status"])
        interpretation = get_interpretation_text(config, "impact_status", status["label"])

        impactos[code] = {
            "avg_likert": avg_lik,
            "score": score_0_100,
            "status": status["label"],
            "icon": status["icon"],
            "interpretation": interpretation
        }

    return impactos


def main():
    config = load_config("config.json")

    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)

    ws = client.open_by_key(SPREADSHEET_ID).sheet1
    raw_rows = ws.get_all_records()

    if not raw_rows:
        print("⚠️ Nenhuma resposta encontrada.")
        return

    # normalizar nomes das colunas
    rows = []
    for row in raw_rows:
        cleaned = {}
        for k, v in row.items():
            cleaned[normalize_column_name(k)] = v
        rows.append(cleaned)

    # localizar colunas dinâmicas
    id_col = find_column_key(rows[0], "ID da coleta")
    perfil_col = find_column_key(rows[0], "Cargo / Perfil do respondente")
    obs_col = find_column_key(rows[0], "Deseja relatar algo relevante")

    if not id_col:
        raise ValueError("Não encontrei a coluna do ID da coleta.")
    if not perfil_col:
        raise ValueError("Não encontrei a coluna de perfil do respondente.")

    # listar IDs disponíveis
    ids = sorted(
        set(
            str(r.get(id_col, "")).strip()
            for r in rows
            if str(r.get(id_col, "")).strip() != ""
        )
    )

    print("\nIDs de coleta encontrados:")
    for x in ids:
        print(" -", x)

    if not ids:
        print("⚠️ Nenhuma resposta com ID da coleta preenchido.")
        return

    # =====================
    # Escolha do ID no terminal
    # =====================
    print("\nEscolha o ID da coleta para gerar o relatório:")
    for i, x in enumerate(ids, 1):
        print(f"{i}) {x}")

    while True:
        choice = input("\nDigite o número do ID escolhido: ").strip()

        if not choice.isdigit():
            print("❌ Entrada inválida. Digite apenas o número.")
            continue

        idx = int(choice)
        if idx < 1 or idx > len(ids):
            print("❌ Número fora da lista. Tente novamente.")
            continue

        collection_id = ids[idx - 1]
        break

    print("\n✅ Gerando relatório para ID:", collection_id)

    # filtrar apenas respostas desse ID
    collection_rows = [
        r for r in rows
        if str(r.get(id_col, "")).strip() == collection_id
    ]

    # separar colaboradores e gestão + financeiros
    colaboradores = []
    operacional_rows = []
    strategic_rows = []
    finance_rows = []

    for r in collection_rows:
        perfil_raw = r.get(perfil_col, "")
        perfil = normalize_profile(perfil_raw)

        if perfil == "COLABORADOR":
            colaboradores.append(r)

        elif perfil in {"LIDERANCA", "RH_DP_FINANCEIRO", "SESMT"}:
            operacional_rows.append(r)

        elif perfil == "DIRETORIA":
            strategic_rows.append(r)
            finance_rows.append(r)  # ✅ financeiro só aqui


    print(f"Colaboradores: {len(colaboradores)}")
    print(f"Gestão / Operacional (Liderança + RH + SESMT): {len(operacional_rows)}")
    print(f"Diretoria (estratégico): {len(strategic_rows)}")
    print(f"Respondentes financeiros válidos: {len(finance_rows)}")


    # =====================
    # 1) RISCO GERAL (R1..R6)
    # =====================
    risk_results = calc_risk_block(config, collection_rows)

    # =====================
    # 2) IMPACTOS GERAL (G1..G6)
    # =====================
    impactos = calc_impact_block(config, collection_rows)
    impact_base = colaboradores + operacional_rows
    impactos = calc_impact_block(config, impact_base)


    # =====================
    # 3) MATURIDADE (somente gestão)
    # =====================
    maturidade_items = config["dimensions"]["MATURIDADE"]["items"]
    m_likert = calc_items_mean(operacional_rows, maturidade_items)
    m_strategic = None

    if strategic_rows:
        m_likert_str = calc_items_mean(strategic_rows, maturidade_items)
        m_avg_str = mean(list(m_likert_str.values()))
        m_score_str = likert_to_0_100(m_avg_str)
        m_status_str = classify_status(m_score_str, config["thresholds"]["maturity_status"])
        m_text_str = get_interpretation_text(config, "maturity", m_status_str["label"])

        m_strategic = {
            "avg_likert": m_avg_str,
            "score": m_score_str,
            "status": m_status_str["label"],
            "interpretation": m_text_str
        }
    
    maturidade_strategic = m_strategic


    m_avg = mean(list(m_likert.values()))
    m_score = likert_to_0_100(m_avg)
    m_status = classify_status(m_score, config["thresholds"]["maturity_status"])
    m_text = get_interpretation_text(config, "maturity", m_status["label"])

    maturidade = {
        "avg_likert": m_avg,
        "score": m_score,
        "status": m_status["label"],
        "interpretation": m_text
    }

    # =====================
    # 4) OBSERVAÇÕES QUALITATIVAS
    # =====================
    observacoes = []
    if obs_col:
        for r in collection_rows:
            txt = str(r.get(obs_col, "")).strip()
            if txt:
                observacoes.append(txt)

    # =====================
    # 5) ROI REAL (somente folha)
    # =====================
    payroll_info = calc_payroll_monthly_from_responses(
        financial_rows=finance_rows,
        col_employees=FIN_COL_EMPLOYEES,
        col_salary_range=FIN_COL_SALARY,
        col_payroll_range=FIN_COL_PAYROLL,
    )

    payroll_monthly = payroll_info["payroll_monthly"]

    maturity_for_roi = (
    maturidade_strategic["status"]
    if maturidade_strategic is not None
    else None
    )

    roi = None
    if payroll_monthly is not None:
        roi = calc_roi(
            config=config,
            risk_results=risk_results,
            maturity_status=maturity_for_roi,
            payroll_monthly=payroll_monthly
        )


    # =====================
    # 6) AGRUPAMENTOS (Unidade / Turno)
    # =====================
    units = sorted(set(get_group_value(r, UNIT_COL_NAME) for r in collection_rows))
    shifts = sorted(set(get_group_value(r, SHIFT_COL_NAME) for r in collection_rows))

    # =====================
    # OUTPUT
    # =====================
    print("\n================ RELATÓRIO (RESUMO) ================")

    print("\n--- RISCO POR DIMENSÃO (GERAL) ---")
    for dim_id, x in risk_results.items():
        sc = x["score"]
        sc_text = "SEM DADOS" if sc is None else f"{sc:.2f}"
        print(f"{dim_id} - {x['name']}: {sc_text} ({x['icon']} {x['status']})")
        if x.get("interpretation"):
            print(f"   ↳ {x['interpretation']}")

    print("\n--- IMPACTOS (GERAL) ---")
    for code, x in impactos.items():
        sc = x["score"]
        sc_text = "SEM DADOS" if sc is None else f"{sc:.2f}"
        print(f"{code}: {sc_text} ({x['icon']} {x['status']})")
        if x.get("interpretation"):
            print(f"   ↳ {x['interpretation']}")

    print("\n--- MATURIDADE ---")
    sc = maturidade["score"]
    sc_text = "SEM DADOS" if sc is None else f"{sc:.2f}"
    print(f"Maturidade: {sc_text} ({maturidade['status']})")
    if maturidade.get("interpretation"):
        print(f"   ↳ {maturidade['interpretation']}")

    print("\n--- ROI REAL (Produtividade) ---")
    print(f"Fonte payroll: {payroll_info['source']}")
    print(
        f"Amostras financeiras: "
        f"folha={payroll_info['samples_payroll']}, "
        f"colaboradores={payroll_info['samples_employees']}"
    )

    if payroll_info.get("employees_median") is not None:
        print(f"Colaboradores (mediana): {int(payroll_info['employees_median'])}")

    if roi is None:
        print("\nROI: SEM DADOS FINANCEIROS VÁLIDOS (folha salarial não informada).")
    else:
        perda_mensal = roi["annual_cost"] / 12
        queda = roi["final_percent"] * 100

        print(f"Folha salarial mensal (estimada): {format_brl(payroll_monthly)}")

        # Alertas de consistência
        ALERT_PAYROLL = 0.20
        ALERT_EMP = 0.10

        alerts = []
        if payroll_info.get("div_payroll") is not None and payroll_info["div_payroll"] > ALERT_PAYROLL:
            alerts.append(f"- Divergência em folha salarial: {pct_text(payroll_info['div_payroll'])} (limite {ALERT_PAYROLL*100:.0f}%)")
        if payroll_info.get("div_employees") is not None and payroll_info["div_employees"] > ALERT_EMP:
            alerts.append(f"- Divergência em colaboradores: {pct_text(payroll_info['div_employees'])} (limite {ALERT_EMP*100:.0f}%)")

        if alerts:
            print("\n⚠️ ALERTA DE VALIDAÇÃO FINANCEIRA")
            print("Foram detectadas divergências relevantes entre as respostas financeiras (RH/Diretoria).")
            print("Recomendação: validar os números antes de usar o ROI em apresentação executiva.")
            for a in alerts:
                print(a)

        # Texto explicável / vendável
        print(f"\nQueda de produtividade estimada: {queda:.2f}%")

        print("\nPerda financeira estimada:")
        print(f" - Mensal: {format_brl(perda_mensal)}")
        print(f" - Anual:  {format_brl(roi['annual_cost'])}")

        print("\nPotencial de recuperação (ações de intervenção):")
        print(f" - Recuperável (até {roi['recoverable_factor']*100:.0f}%): {format_brl(roi['recoverable_value'])} / ano")

    print("\n--- RECORTE POR UNIDADE (R1..R6) ---")
    for u in units:
        block = [r for r in collection_rows if get_group_value(r, UNIT_COL_NAME) == u]
        if len(block) < 2:
            print(f"\nUnidade {u}: (amostra insuficiente: {len(block)})")
            continue

        r_unit = calc_risk_block(config, block)
        print(f"\nUnidade {u}: n={len(block)}")
        for dim_id, x in r_unit.items():
            sc = x["score"]
            sc_text = "SEM DADOS" if sc is None else f"{sc:.1f}"
            print(f"  - {dim_id}: {sc_text} ({x['icon']} {x['status']})")

    print("\n--- RECORTE POR TURNO (R1..R6) ---")
    for t in shifts:
        block = [r for r in collection_rows if get_group_value(r, SHIFT_COL_NAME) == t]
        if len(block) < 2:
            print(f"\nTurno {t}: (amostra insuficiente: {len(block)})")
            continue

        r_shift = calc_risk_block(config, block)
        print(f"\nTurno {t}: n={len(block)}")
        for dim_id, x in r_shift.items():
            sc = x["score"]
            sc_text = "SEM DADOS" if sc is None else f"{sc:.1f}"
            print(f"  - {dim_id}: {sc_text} ({x['icon']} {x['status']})")

    print("\n--- ROI (comparativo) por UNIDADE ---")
    if roi is None:
        print("Sem dados financeiros para calcular ROI por unidade.")
    else:
        payroll_global = payroll_monthly

        for u in units:
            block = [r for r in collection_rows if get_group_value(r, UNIT_COL_NAME) == u]
            if len(block) < 2:
                continue

            risk_u = calc_risk_block(config, block)

            roi_u = calc_roi(
                config=config,
                risk_results=risk_u,
                maturity_status=maturidade["status"] if maturidade["status"] != "SEM_DADOS" else None,
                payroll_monthly=payroll_global
            )

            queda_u = roi_u["final_percent"] * 100
            perda_anual_u = roi_u["annual_cost"]
            perda_mensal_u = perda_anual_u / 12

            print(f"\nUnidade {u} (n={len(block)})")
            print(f" - Queda estimada: {queda_u:.2f}%")
            print(f" - Perda mensal:   {format_brl(perda_mensal_u)}")
            print(f" - Perda anual:    {format_brl(perda_anual_u)}")

    print("\n--- OBSERVAÇÕES QUALITATIVAS ---")
    if not observacoes:
        print("Nenhuma observação registrada.")
    else:
        for i, txt in enumerate(observacoes, 1):
            print(f"{i}. {txt}")

    print("\n====================================================")


if __name__ == "__main__":
    main()

import os
import json
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

from config_loader import load_config
from report_by_collection import (
    normalize_column_name,
    find_column_key,
    calc_risk_block,
    calc_impact_block,
    mean,
    likert_to_0_100,
    is_financial_profile,
    get_group_value,
    UNIT_COL_NAME,
    SHIFT_COL_NAME,
    FIN_COL_PAYROLL,
    FIN_COL_EMPLOYEES,
    format_brl,
)

from finance import calc_payroll_monthly_from_responses
from engine import classify_status, get_interpretation_text, parse_likert
from roi import calc_roi


# =========================
# CONFIG
# =========================
SERVICE_ACCOUNT_FILE = "secrets/google_service_account.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
SPREADSHEET_ID = "1BaS2goahKS8KkhbUgFJSVcMHtfW_KoaZ0RIkOBne0go"


# =========================
# Helpers
# =========================
def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def safe_folder_name(text: str) -> str:
    return "".join(c for c in text if c.isalnum() or c in ("_", "-", ".")).strip()


def save_json(path: str, obj: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def save_text(path: str, content: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def safe_status_code(s: str | None) -> str:
    if not s:
        return "SEM_DADOS"
    s2 = str(s).strip().upper()
    if "CRIT" in s2:
        return "CRITICO"
    if "ATEN" in s2:
        return "ATENCAO"
    if "OK" in s2 or "ADEQ" in s2:
        return "OK"
    if "SEM" in s2:
        return "SEM_DADOS"
    return s2


def icon_for_status(code: str):
    return {
        "OK": "🟢",
        "ATENCAO": "🟡",
        "CRITICO": "🔴",
        "SEM_DADOS": "⚪",
        "BAIXA": "🟠",
        "MEDIA": "🟡",
        "ALTA": "🟢",
    }.get(code, "⚪")


def score_bucket(score: float | None) -> str:
    if score is None:
        return "SEM_DADOS"
    if score >= 70:
        return "CRITICO"
    if score >= 40:
        return "ATENCAO"
    return "OK"


def clean_qualitative(text: str) -> str | None:
    t = (text or "").strip()
    if not t:
        return None
    low = t.lower()
    if low in {"nao", "não", "ok", "sem", "n/a", "nenhum", "nenhuma", "ainda nao", "ainda não"}:
        return None
    return t


def build_priority_list(risk_dict: dict) -> list[str]:
    items = []
    for dim_id, x in risk_dict.items():
        sc = x.get("score")
        items.append((dim_id, sc if sc is not None else -1))
    items.sort(key=lambda z: z[1], reverse=True)
    return [dim for dim, _ in items]


def detect_combinations(risk: dict, impact: dict, maturity_code: str) -> list[dict]:
    risk_crit = [k for k, v in risk.items() if safe_status_code(v.get("status")) == "CRITICO"]
    impact_crit = [k for k, v in impact.items() if safe_status_code(v.get("status")) == "CRITICO"]

    combos = []

    if risk_crit and impact_crit:
        combos.append({
            "type": "RISK_X_IMPACT",
            "severity": "ALTA",
            "description": "Há risco elevado simultâneo com impacto funcional crítico (quadro já instalado).",
            "risk_critical": risk_crit,
            "impact_critical": impact_crit
        })

    r5 = safe_status_code(risk.get("R5", {}).get("status"))
    r6 = safe_status_code(risk.get("R6", {}).get("status"))
    if r5 == "CRITICO" or r6 == "CRITICO":
        combos.append({
            "type": "LEADERSHIP_CLIMATE",
            "severity": "ALTA",
            "description": "Indicadores críticos de liderança/clima e/ou segurança psicológica comprometida (R5/R6).",
            "dimensions": ["R5", "R6"]
        })

    if maturity_code in {"BAIXA", "MEDIA"} and (r5 == "CRITICO" or r6 == "CRITICO"):
        combos.append({
            "type": "LOW_READINESS_HIGH_RISK",
            "severity": "ALTA",
            "description": "Risco elevado com maturidade insuficiente: recomenda-se intervenção escalonada e governança imediata.",
            "maturity": maturity_code
        })

    return combos


def build_prompt_ai(premium: dict) -> str:
    ai = premium["ai_payload"]
    payload_str = json.dumps(ai, indent=2, ensure_ascii=False)

    return f"""
Você é um Sistema Especialista de Apoio à Decisão Técnica em riscos psicossociais ocupacionais, estruturado segundo a NR-1, GRO e PGR.

Você:
- NÃO diagnostica clinicamente
- NÃO emite laudos finais
- NÃO toma decisões autônomas
- NÃO faz julgamentos morais

Você:
- Analisa dados estruturados
- Identifica padrões de risco e impacto
- Prioriza cenários
- Sugere estratégias, formatos e temas de intervenção
- Aponta pontos de validação humana

Toda resposta deve ser técnica, objetiva, rastreável e defensável.

## ENTRADA DE DADOS (JSON PREMIUM)
A seguir estão os dados estruturados calculados da coleta:

{payload_str}

## PROCESSAMENTO OBRIGATÓRIO
Siga esta ordem:
1) Leitura técnica dos dados
2) Identificação de dimensões críticas
3) Combinações críticas (risco x impacto, liderança/clima, etc.)
4) Avaliação de maturidade organizacional
5) Definição de prioridade (Alta/Média/Baixa)
6) Estratégia de intervenção
7) Formato recomendado (Palestra, Treinamento líderes, Workshop, Imersão, Ciclo)
8) Temas
9) Comunicação para diretoria
10) Pontos obrigatórios de validação humana
11) Observações técnicas/jurídicas (se aplicável)

## FORMATO DE SAÍDA (OBRIGATÓRIO)
Responda exatamente nesta estrutura:

1. Classificação Geral
2. Dimensões Críticas Identificadas
3. Combinações Críticas
4. Prioridade Estratégica
5. Estratégia de Intervenção
6. Formato de Intervenção Recomendado
7. Temas Prioritários a Trabalhar
8. Recomendação de Comunicação
9. Pontos de Validação Humana Obrigatória
10. Observações Técnicas e Jurídicas

FRASE PADRÃO DE RODAPÉ
> Análise gerada por sistema de apoio à decisão. Recomendações sujeitas à validação técnica por consultor responsável.
""".strip()


# =========================
# Main
# =========================
def main():
    config = load_config("config.json")

    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)

    ws = client.open_by_key(SPREADSHEET_ID).sheet1
    raw_rows = ws.get_all_records()

    if not raw_rows:
        print("⚠️ Nenhuma resposta encontrada.")
        return

    # normalizar colunas
    rows = []
    for row in raw_rows:
        cleaned = {}
        for k, v in row.items():
            cleaned[normalize_column_name(k)] = v
        rows.append(cleaned)

    id_col = find_column_key(rows[0], "ID da coleta")
    perfil_col = find_column_key(rows[0], "Cargo / Perfil do respondente")
    obs_col = find_column_key(rows[0], "Deseja relatar algo relevante")

    if not id_col:
        raise ValueError("Não encontrei a coluna do ID da coleta.")
    if not perfil_col:
        raise ValueError("Não encontrei a coluna de perfil do respondente.")

    ids = sorted(set(str(r.get(id_col, "")).strip() for r in rows if str(r.get(id_col, "")).strip() != ""))

    print("\nIDs de coleta encontrados:")
    for x in ids:
        print(" -", x)

    if not ids:
        print("⚠️ Nenhuma resposta com ID preenchido.")
        return

    print("\nEscolha o ID da coleta para gerar o pacote premium:")
    for i, x in enumerate(ids, 1):
        print(f"{i}) {x}")

    while True:
        choice = input("\nDigite o número do ID escolhido: ").strip()
        if not choice.isdigit():
            print("❌ Digite apenas o número.")
            continue
        idx = int(choice)
        if idx < 1 or idx > len(ids):
            print("❌ Fora da lista.")
            continue
        collection_id = ids[idx - 1]
        break

    print("\n✅ Gerando pacote premium para ID:", collection_id)

    collection_rows = [r for r in rows if str(r.get(id_col, "")).strip() == collection_id]

    colaboradores = []
    gestao = []
    finance_rows = []

    for r in collection_rows:
        perfil = r.get(perfil_col, "")
        if "colaborador" in str(perfil).strip().lower():
            colaboradores.append(r)
        else:
            gestao.append(r)

        if is_financial_profile(perfil):
            finance_rows.append(r)

    # ===== risco e impacto
    risk_results = calc_risk_block(config, collection_rows)
    impactos = calc_impact_block(config, collection_rows)

    # ===== maturidade
    maturidade_items = config["dimensions"]["MATURIDADE"]["items"]
    m_likert = {}
    for code in maturidade_items:
        vals = []
        for r in gestao:
            key = next((k for k in r.keys() if k.startswith(f"{code} -")), None)
            if key:
                v = parse_likert(r.get(key))
                if v is not None:
                    vals.append(v)
        m_likert[code] = mean(vals)

    m_avg = mean(list(m_likert.values()))
    m_score = likert_to_0_100(m_avg)
    m_status = classify_status(m_score, config["thresholds"]["maturity_status"])
    m_text = get_interpretation_text(config, "maturity", m_status["label"])

    maturidade = {
        "avg_likert": m_avg,
        "score_0_100": m_score,
        "status": m_status["label"],
        "interpretation": m_text,
        "items": m_likert,
        "n_gestao": len(gestao)
    }

    # ===== qualitativas
    qual_raw = []
    if obs_col:
        for r in collection_rows:
            txt = str(r.get(obs_col, "")).strip()
            if txt:
                qual_raw.append(txt)

    qual_clean = [clean_qualitative(x) for x in qual_raw]
    qual_clean = [x for x in qual_clean if x]

    # ===== ROI
    payroll_info = calc_payroll_monthly_from_responses(
        financial_rows=finance_rows,
        col_employees=FIN_COL_EMPLOYEES,
        col_salary_range=None,
        col_payroll_range=FIN_COL_PAYROLL,
    )
    payroll_monthly = payroll_info["payroll_monthly"]

    roi = None
    if payroll_monthly is not None:
        roi = calc_roi(
            config=config,
            risk_results=risk_results,
            maturity_status=maturidade["status"] if maturidade["status"] != "SEM_DADOS" else None,
            payroll_monthly=payroll_monthly
        )

    # ===== breakdown
    units = sorted(set(get_group_value(r, UNIT_COL_NAME) for r in collection_rows))
    shifts = sorted(set(get_group_value(r, SHIFT_COL_NAME) for r in collection_rows))

    breakdown_units = {}
    for u in units:
        block = [r for r in collection_rows if get_group_value(r, UNIT_COL_NAME) == u]
        if len(block) < 2:
            continue
        breakdown_units[u] = calc_risk_block(config, block)

    breakdown_shifts = {}
    for t in shifts:
        block = [r for r in collection_rows if get_group_value(r, SHIFT_COL_NAME) == t]
        if len(block) < 2:
            continue
        breakdown_shifts[t] = calc_risk_block(config, block)

    # ===== PREMIUM JSON
    maturity_code = safe_status_code(maturidade["status"])

    risk_ranked = build_priority_list(risk_results)

    general_risk_score = max([v.get("score") for v in risk_results.values() if v.get("score") is not None], default=None)
    general_impact_score = max([v.get("score") for v in impactos.values() if v.get("score") is not None], default=None)

    general_risk_code = score_bucket(general_risk_score)
    general_impact_code = score_bucket(general_impact_score)

    combinations = detect_combinations(risk_results, impactos, maturity_code)

    premium = {
        "version": "2.0-premium",
        "generated_at": now_iso(),
        "collection_id": collection_id,

        "computed": {
            "counts": {
                "total": len(collection_rows),
                "colaboradores": len(colaboradores),
                "gestao": len(gestao),
                "financeiro": len(finance_rows),
            },
            "risk": risk_results,
            "impact": impactos,
            "maturity": maturidade,
            "roi": {
                "payroll_info": payroll_info,
                "payroll_monthly": payroll_monthly,
                "roi_calc": roi
            },
            "breakdown": {
                "units": breakdown_units,
                "shifts": breakdown_shifts
            }
        },

        "ai_payload": {
            "collection_id": collection_id,
            "generated_at": now_iso(),

            "summary": {
                "general_risk_status": general_risk_code,
                "general_risk_icon": icon_for_status(general_risk_code),
                "general_impact_status": general_impact_code,
                "general_impact_icon": icon_for_status(general_impact_code),
                "maturity_status": maturity_code,
                "maturity_icon": icon_for_status(maturity_code),
            },

            "risk_ranked": risk_ranked,
            "critical_combinations": combinations,

            "roi": roi,
            "qualitative_notes": qual_clean,

            "required_outputs": [
                "classificacao_geral",
                "dimensoes_criticas",
                "combinacoes_criticas",
                "prioridade_estrategica",
                "estrategia_intervencao",
                "formato_recomendado",
                "temas_prioritarios",
                "recomendacao_comunicacao",
                "validacao_humana",
                "observacoes_tecnicas_juridicas"
            ]
        }
    }

    # ===== salvar arquivos finais
    folder = os.path.join("reports", safe_folder_name(collection_id))
    ensure_dir(folder)

    premium_path = os.path.join(folder, "report_premium.json")
    save_json(premium_path, premium)

    # ===== TXT (completo)
    lines = []
    lines.append("RELATÓRIO TÉCNICO — RISCOS PSICOSSOCIAIS (NR-1 / GRO / PGR)")
    lines.append(f"ID da coleta: {collection_id}")
    lines.append(f"Gerado em: {premium['generated_at']}")
    lines.append("")

    lines.append("1) RISCO POR DIMENSÃO (R)")
    for dim_id, x in risk_results.items():
        sc = x.get("score")
        sc_text = "SEM DADOS" if sc is None else f"{sc:.2f}"
        lines.append(f"- {dim_id} — {x['name']}: {sc_text} ({x['icon']} {x['status']})")
        if x.get("interpretation"):
            lines.append(f"  ↳ {x['interpretation']}")
    lines.append("")

    lines.append("2) IMPACTOS FUNCIONAIS PERCEBIDOS (G)")
    for code, x in impactos.items():
        sc = x.get("score")
        sc_text = "SEM DADOS" if sc is None else f"{sc:.2f}"
        lines.append(f"- {code}: {sc_text} ({x['icon']} {x['status']})")
        if x.get("interpretation"):
            lines.append(f"  ↳ {x['interpretation']}")
    lines.append("")

    lines.append("3) MATURIDADE ORGANIZACIONAL")
    m_sc = maturidade["score_0_100"]
    m_sc_text = "SEM DADOS" if m_sc is None else f"{m_sc:.2f}"
    lines.append(f"- Maturidade geral: {m_sc_text} ({maturidade['status']})")
    if maturidade.get("interpretation"):
        lines.append(f"  ↳ {maturidade['interpretation']}")
    lines.append("")

    lines.append("4) ROI (Produtividade — Estimativa Financeira)")
    if roi is None:
        lines.append("- ROI: SEM DADOS FINANCEIROS (folha salarial mensal não informada).")
    else:
        queda = roi["final_percent"] * 100
        perda_mensal = roi["annual_cost"] / 12
        lines.append(f"- Folha salarial mensal estimada: {format_brl(payroll_monthly)}")
        lines.append(f"- Queda de produtividade estimada: {queda:.2f}%")
        lines.append(f"- Perda financeira mensal estimada: {format_brl(perda_mensal)}")
        lines.append(f"- Perda financeira anual estimada:  {format_brl(roi['annual_cost'])}")
        lines.append(f"- Recuperável (até 30%): {format_brl(roi['recoverable_value'])}/ano")

    lines.append("")
    lines.append("5) OBSERVAÇÕES QUALITATIVAS")
    if not qual_raw:
        lines.append("- Nenhuma observação registrada.")
    else:
        for i, txt in enumerate(qual_raw, 1):
            lines.append(f"{i}. {txt}")

    lines.append("")
    lines.append("—")
    lines.append("Este relatório é um produto de apoio à decisão. Recomendações devem ser validadas por consultor responsável.")

    txt_path = os.path.join(folder, "report.txt")
    save_text(txt_path, "\n".join(lines))

    # ===== PROMPT AI (Padrão Ouro - JSON puro para IA)
    prompt_payload = premium["ai_payload"]

    prompt_text = json.dumps(prompt_payload, indent=2, ensure_ascii=False)

    prompt_path = os.path.join(folder, "prompt_ai.txt")
    save_text(prompt_path, prompt_text)

    print("\n✅ PACOTE PREMIUM GERADO COM SUCESSO")
    print(" -", premium_path)
    print(" -", txt_path)
    print(" -", prompt_path)


if __name__ == "__main__":
    main()
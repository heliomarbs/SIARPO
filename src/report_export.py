# engine/report_export.py

import os
import sys
import json
import argparse
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

from src.config_loader import load_config
from src.report_by_collection import (
    normalize_column_name,
    find_column_key,
    UNIT_COL_NAME,
    get_group_value,
)

from src.engine import parse_likert, classify_status, get_interpretation_text
from src.finance import calc_payroll_monthly_from_responses
from src.roi import calc_roi



SERVICE_ACCOUNT_FILE = "secrets/google_service_account.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
SPREADSHEET_ID = "1BaS2goahKS8KkhbUgFJSVcMHtfW_KoaZ0RIkOBne0go"

MATURITY_ITEM_LABELS = {
    "M1": "Base estrutural",
    "M2": "Clareza de diretrizes",
    "M3": "Papéis e responsabilidades",
    "M4": "Processos formalizados",
    "M5": "Governança",
    "M6": "Comprometimento da liderança",
    "M7": "Comunicação interna",
    "M8": "Capacitação",
    "M9": "Monitoramento",
    "M10": "Execução das ações",
    "M11": "Responsabilização",
    "M12": "Sustentação do sistema"
}

MATURITY_TEXT_BY_LEVEL = {
    "critico": "muito frágil",
    "frágil": "frágil",
    "intermediario": "em desenvolvimento",
    "forte": "bem estruturado"
}


# ======================================
# Helpers
# ======================================

def calc_cross_risk_maturity(risk_block, maturity_score):
    cross = {}

    if maturity_score is None:
        for k in risk_block:
            cross[k] = {
                "risk_score": risk_block[k]["score"],
                "maturity_score": None,
                "gap": None,
                "severity": "SEM_DADOS"
            }
        return cross

    for k, v in risk_block.items():
        r = v["score"]
        if r is None:
            cross[k] = {
                "risk_score": None,
                "maturity_score": maturity_score,
                "gap": None,
                "severity": "SEM_DADOS"
            }
            continue

        gap = r - maturity_score

        if gap >= 40:
            sev = "CRITICO"
        elif gap >= 20:
            sev = "ALTO"
        elif gap >= 5:
            sev = "MODERADO"
        else:
            sev = "CONTROLADO"

        cross[k] = {
            "risk_score": r,
            "maturity_score": maturity_score,
            "gap": gap,
            "severity": sev
        }

    return cross



def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def safe_folder_name(text):
    return "".join(c for c in text if c.isalnum() or c in ("_", "-", ".")).strip()


def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def save_text(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def mean(values):
    values = [v for v in values if v is not None]
    return None if not values else sum(values) / len(values)


def likert_to_0_100(v):
    return None if v is None else ((v - 1) / 4) * 100


def print_header(t):
    print("\n" + "=" * 60)
    print(t)
    print("=" * 60)


# ======================================
# Status geral
# ======================================

def general_status_from_blocks(block):
    statuses = [v.get("status") for v in block.values() if v.get("status")]

    if "CRITICO" in statuses:
        return "CRITICO"
    if "ATENCAO" in statuses:
        return "ATENCAO"
    if "OK" in statuses:
        return "OK"
    if "ADEQUADO" in statuses:
        return "ADEQUADO"
    return "SEM_DADOS"


def calc_confidence(total, collab, gestao):
    reasons = []
    level = "ALTA"

    if total < 8:
        level = "BAIXA"
        reasons.append("Amostra total pequena.")
    elif total < 20:
        level = "MEDIA"
        reasons.append("Amostra moderada.")

    if collab == 0:
        level = "BAIXA"
        reasons.append("Sem colaboradores.")

    if gestao == 0:
        if level == "ALTA":
            level = "MEDIA"
        reasons.append("Sem gestão operacional.")

    return {"level": level, "reasons": reasons}


# ======================================
# Blocos analíticos
# ======================================
def get_dimension_interpretation(config, dim_id, status):
    return (
        config
        .get("texts", {})
        .get("dimension_status", {})
        .get(dim_id, {})
        .get(status)
    )


def calc_risk_dimension(config, dim_id, rows):
    dim_cfg = config["dimensions"].get(dim_id)
    if not dim_cfg:
        return {"name": dim_id, "score": None, "status": "SEM_DADOS", "icon": "⚪", "interpretation": ""}

    scores, wsum = [], 0

    for code in dim_cfg["items"]:
        item_cfg = config["items"].get(code, {})
        vals = []

        for r in rows:
            key = next((k for k in r if k.startswith(f"{code} -")), None)
            if not key:
                continue
            v = parse_likert(r.get(key))
            if v is None:
                continue
            if item_cfg.get("invert"):
                v = 6 - v
            vals.append(v)

        avg = mean(vals)
        if avg is None:
            continue

        score = likert_to_0_100(avg)
        w = config["weights"]["levels"].get(item_cfg.get("weight", "MEDIO"), 1)
        scores.append(score * w)
        wsum += w

    final = None if not scores else sum(scores) / wsum
    st = classify_status(final, config["thresholds"]["risk_status"])
    interp = get_dimension_interpretation(config, dim_id, st["label"])

    return {
        "name": dim_cfg["name"],
        "score": final,
        "status": st["label"],
        "icon": st.get("icon"),
        "interpretation": interp,
    }


def calc_risk_block(config, rows):
    return {d: calc_risk_dimension(config, d, rows) for d in ["R1","R2","R3","R4","R5","R6"]}


def calc_impact_block(config, rows):
    out = {}
    for code in config["dimensions"]["IMPACTO"]["items"]:
        vals = []
        for r in rows:
            key = next((k for k in r if k.startswith(f"{code} -")), None)
            if key:
                v = parse_likert(r.get(key))
                if v is not None:
                    vals.append(v)

        avg = mean(vals)
        score = likert_to_0_100(avg)
        st = classify_status(score, config["thresholds"]["impact_status"])
        interp = (
            config
            .get("texts", {})
            .get("impact_status", {})
            .get(code, {})
            .get(st["label"])
        )

        out[code] = {
            "avg_likert": avg,
            "score": score,
            "status": st["label"],
            "icon": st.get("icon"),
            "interpretation": interp or "Interpretação não disponível."
        }
    return out

def calc_abs_pres_indexes(config, risk_results, impact_results, cross_strategic=None):
    """
    Calcula índices de:
    - Risco de Absenteísmo
    - Risco de Presenteísmo
    """

    def get_score(block, key):
        v = block.get(key, {})
        return v.get("score")

    impacto = get_score(impact_results, "G1")  # usaremos média depois
    impacto_scores = [
        v.get("score") for v in impact_results.values()
        if v.get("score") is not None
    ]
    impacto_global = None if not impacto_scores else sum(impacto_scores) / len(impacto_scores)

    pressao = get_score(risk_results, "R1")
    lideranca = get_score(risk_results, "R5")

    indexes = {}

    # =========================
    # RISCO DE ABSENTEÍSMO
    # =========================
    if impacto_global is not None and pressao is not None:
        score_abs = (impacto_global * 0.6) + (pressao * 0.4)
    else:
        score_abs = None

    st_abs = classify_status(score_abs, config["thresholds"]["risk_status"])

    indexes["RISCO_ABSENTEISMO"] = {
        "name": "Risco de Absenteísmo",
        "score": score_abs,
        "status": st_abs["label"],
        "icon": st_abs.get("icon"),
        "description": "Probabilidade de faltas ou afastamentos por desgaste físico ou emocional."
    }

    # =========================
    # RISCO DE PRESENTEÍSMO
    # =========================
    if impacto_global is not None and pressao is not None and lideranca is not None:
        score_pre = (
            impacto_global * 0.5 +
            pressao * 0.3 +
            lideranca * 0.2
        )
    else:
        score_pre = None

    st_pre = classify_status(score_pre, config["thresholds"]["risk_status"])

    indexes["RISCO_PRESENTEISMO"] = {
        "name": "Risco de Presenteísmo",
        "score": score_pre,
        "status": st_pre["label"],
        "icon": st_pre.get("icon"),
        "description": "Presença no trabalho com queda de desempenho por sobrecarga ou desgaste emocional."
    }



    # =========================
    # RISCO DE BURNOUT (CORRIGIDO)
    # =========================
    if impacto_global is not None and pressao is not None:
        score_burnout = (impacto_global * 0.5) + (pressao * 0.5)
    else:
        score_burnout = None

    st_burn = classify_status(score_burnout, config["thresholds"]["risk_status"])

    indexes["RISCO_BURNOUT"] = {
        "name": "Risco de Burnout",
        "score": score_burnout,
        "status": st_burn["label"],
        "icon": st_burn.get("icon"),
        "description": (
            "Esgotamento progressivo associado à pressão contínua "
            "e impacto funcional elevado, com recuperação insuficiente."
        )
    }


    # =========================
    # RISCO DE ASSÉDIO
    # =========================

    r6 = get_score(risk_results, "R6")  # condutas inadequadas
    r5 = get_score(risk_results, "R5")  # liderança

    gap_estrategico = None
    if cross_strategic:
        r6_cross = cross_strategic.get("R6", {})
        gap_estrategico = r6_cross.get("gap")

    if r6 is not None and r5 is not None:
        score_assedio = (
            r6 * 0.6 +
            r5 * 0.25 +
            (gap_estrategico * 0.15 if gap_estrategico is not None else 0)
        )
    else:
        score_assedio = None

    st_assedio = classify_status(score_assedio, config["thresholds"]["risk_status"])

    indexes["RISCO_ASSEDIO"] = {
        "name": "Risco de Assédio",
        "score": score_assedio,
        "status": st_assedio["label"],
        "icon": st_assedio.get("icon"),
        "description": (
            "Probabilidade estrutural de condutas inadequadas persistentes, "
            "associadas a falhas de liderança e segurança psicológica."
        )
    }

    # =========================
    # RISCO DE ABUSO
    # =========================
    r6 = get_score(risk_results, "R6")
    burnout = indexes.get("RISCO_BURNOUT", {}).get("score")

    if r6 is not None and pressao is not None and burnout is not None:
        score_abuso = (
            r6 * 0.4 +
            pressao * 0.3 +
            burnout * 0.3
        )
    else:
        score_abuso = None

    st_abuso = classify_status(score_abuso, config["thresholds"]["risk_status"])

    indexes["RISCO_ABUSO"] = {
        "name": "Risco de Abuso",
        "score": score_abuso,
        "status": st_abuso["label"],
        "icon": st_abuso.get("icon"),
        "description": (
            "Probabilidade estrutural de práticas abusivas sustentadas por "
            "pressão excessiva, falhas de liderança e desgaste emocional contínuo."
        )
    }

    return indexes



def calc_maturity_block(config, rows):
    items = config["dimensions"]["MATURIDADE"]["items"]

    if not rows:
        return {
            "avg_likert": None,
            "score_0_100": None,
            "status": "SEM_DADOS",
            "interpretation": "SEM DADOS",
            "items": {},
            "n": 0,
        }

    mvals = {}
    for code in items:
        vals = []
        for r in rows:
            key = next((k for k in r if k.startswith(f"{code} -")), None)
            if key:
                v = parse_likert(r.get(key))
                if v is not None:
                    vals.append(v)
        mvals[code] = mean(vals)

    avg = mean(mvals.values())
    score = likert_to_0_100(avg)
    st = classify_status(score, config["thresholds"]["maturity_status"])
    interp = get_interpretation_text(config, "maturity", st["label"])

    return {
        "avg_likert": avg,
        "score_0_100": score,
        "status": st["label"],
        "interpretation": interp,
        "items": mvals,
        "n": len(rows),
    }

def build_maturity_item_insights(items: dict):
    insights = []

    for code, score in items.items():
        if score is None:
            continue

        label = MATURITY_ITEM_LABELS.get(code, code)

        if score <= 2.0:
            level = "critico"
        elif score <= 3.0:
            level = "frágil"
        elif score < 4.0:
            level = "intermediario"
        else:
            level = "forte"

        text = MATURITY_TEXT_BY_LEVEL[level]
        insights.append(f"{code} = {round(score, 2)} → {label} {text}")

    return insights


def calc_legal_triggers(config, risk_results, cross_analysis):
    alerts = []

    # 1️⃣ Assédio / Condutas inadequadas críticas
    r6 = risk_results.get("R6", {})
    if r6.get("status") == "CRITICO":
        alerts.append({
            "id": "assedio_direto",
            "label": "Condutas inadequadas recorrentes com risco jurídico crítico."
        })

    # 2️⃣ Ambiente tóxico (R6 + liderança fraca)
    r5 = risk_results.get("R5", {})
    if r6.get("status") in {"ATENCAO", "CRITICO"} and r5.get("status") == "ATENCAO":
        alerts.append({
            "id": "ambiente_toxico",
            "label": "Ambiente de trabalho com comportamentos inadequados frequentes."
        })

    # 3️⃣ Assédio + falha de gestão (cruzamento estratégico)
    cross_stg = cross_analysis.get("risk_vs_strategic_maturity", {})
    for dim, v in cross_stg.items():
        if dim == "R6" and v.get("severity") in {"ALTO", "CRITICO"}:
            alerts.append({
                "id": "assedio_com_falha_gestao",
                "label": "Condutas inadequadas associadas a falhas de liderança."
            })
            break

    # 4️⃣ Pressão excessiva + risco jurídico
    r1 = risk_results.get("R1", {})
    if r1.get("status") == "CRITICO" and r6.get("status") in {"ATENCAO", "CRITICO"}:
        alerts.append({
            "id": "pressao_com_risco_juridico",
            "label": "Pressão excessiva combinada com comportamentos inadequados."
        })

    return {
        "active_count": len(alerts),
        "alerts": alerts
    }


# ======================================
# EXPORT PRINCIPAL
# ======================================

def export_report(collection_id):

    config = load_config("config.json")

    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    ws = gspread.authorize(creds).open_by_key(SPREADSHEET_ID).sheet1

    values = ws.get_all_values()
    headers, data = values[0], values[1:]

    rows = []
    for r in data:
        rows.append({normalize_column_name(k): v for k, v in zip(headers, r)})

    id_col = find_column_key(rows[0], "ID da coleta")
    perfil_col = find_column_key(rows[0], "Cargo / Perfil")

    # =========================
    # OBSERVAÇÕES QUALITATIVAS
    # =========================

    qualitative_col = find_column_key(
        rows[0],
        "relatar algo relevante"
    )

    
    collection_rows = [
    r for r in rows 
    if str(r.get(id_col, "")).strip() == collection_id
    ]

    observacoes_raw = []
    observacoes_filtered = []

    if qualitative_col:
        for r in collection_rows:
            txt = str(r.get(qualitative_col, "")).strip()

            if not txt:
                continue

            observacoes_raw.append(txt)

            # filtro mínimo: evita lixo e respostas vazias
            if len(txt) >= 10:
                observacoes_filtered.append(txt)

    colaboradores = []
    gestao_operacional = []
    diretoria = []
    finance_rows = []

    for r in collection_rows:
        perfil_raw = str(r.get(perfil_col, "")).lower()

        if "colaborador" in perfil_raw:
            colaboradores.append(r)

        elif "diretoria" in perfil_raw:
            diretoria.append(r)
            finance_rows.append(r)

        elif (
            "liderança" in perfil_raw
            or "supervisor" in perfil_raw
            or "rh" in perfil_raw
            or "dp" in perfil_raw
            or "financeiro" in perfil_raw
            or "sesmt" in perfil_raw
            or "segurança do trabalho" in perfil_raw
        ):
            gestao_operacional.append(r)


    # ===================== RESULTADOS =====================

    risk_results = calc_risk_block(config, collection_rows)
    impactos = calc_impact_block(config, collection_rows)

    maturidade_operacional = calc_maturity_block(config, gestao_operacional)
    maturidade_estrategica = calc_maturity_block(config, diretoria)

    cross_operational = calc_cross_risk_maturity(
        risk_results,
        maturidade_operacional["score_0_100"]
    )

    cross_strategic = calc_cross_risk_maturity(
        risk_results,
        maturidade_estrategica["score_0_100"]
    )

    abs_pres_indexes = calc_abs_pres_indexes(
    config=config,
    risk_results=risk_results,
    impact_results=impactos,
    cross_strategic=cross_strategic
    )


    legal_triggers = calc_legal_triggers(
    config=config,
    risk_results=risk_results,
    cross_analysis={
        "risk_vs_strategic_maturity": cross_strategic
    }
    )


    payroll_info = calc_payroll_monthly_from_responses(
        financial_rows=finance_rows,
        col_employees="Número de colaboradores (empresa/unidade)",
        col_salary_range="Faixa de salário médio mensal (R$)",
        col_payroll_range="Faixa de folha salarial mensal total (R$)",
    )

    payroll_monthly = payroll_info.get("payroll_monthly")


    roi_calc = None
    if payroll_monthly:
        roi_calc = calc_roi(
            config=config,
            risk_results=risk_results,
            maturity_status=maturidade_estrategica["status"],
            payroll_monthly=payroll_monthly
        )
    
    impact_roi = {}

    if roi_calc:
        for k, v in impactos.items():
            sc = v["score"]
            if sc is None:
                impact_roi[k] = None
                continue

            impact_roi[k] = {
                "impact_score": sc,
                "estimated_annual_loss": roi_calc["annual_cost"] * (sc / 100),
                "recoverable": roi_calc["recoverable_value"] * (sc / 100)
            }

    general_risk = general_status_from_blocks(risk_results)
    general_impact = general_status_from_blocks(impactos)

    confidence = calc_confidence(
        len(collection_rows),
        len(colaboradores),
        len(gestao_operacional)
    )

    priority = "BAIXA"
    if general_risk == "CRITICO" or general_impact == "CRITICO":
        priority = "ALTA"
    elif general_risk == "ATENCAO" or general_impact == "ATENCAO":
        priority = "MEDIA"

    premium = {
        "schema": {
            "name": "nr1_psicossocial_report",
            "version": "2.1.0",
            "generated_at": now_iso()
        },
        "collection": {
            "collection_id": collection_id,
            "counts": {
                "total": len(collection_rows),
                "colaboradores": len(colaboradores),
                "gestao_operacional": len(gestao_operacional),
                "diretoria": len(diretoria)
            }
        },
        "results": {
            "risk": risk_results,
            "impact": impactos,
            "maturity_operational": maturidade_operacional,
            "maturity_strategic": maturidade_estrategica
        },
        "indices": abs_pres_indexes,
        "diagnosis": {
            "general_risk_status": general_risk,
            "general_impact_status": general_impact,
            "priority": priority,
            "confidence": confidence
        },
        "roi": {
            "payroll_monthly": payroll_monthly,
            "payroll_info": payroll_info,
            "roi_calc": roi_calc
        },

        "cross_analysis": {
            "risk_vs_operational_maturity": cross_operational,
            "risk_vs_strategic_maturity": cross_strategic,
            "impact_vs_roi": impact_roi
        },
        "legal_triggers": legal_triggers,

        "qualitative_notes": {
            "raw": observacoes_raw,
            "filtered": observacoes_filtered,
            "count_valid": len(observacoes_filtered)
        }

    }

    folder = os.path.join("reports", safe_folder_name(collection_id))
    ensure_dir(folder)

    save_json(os.path.join(folder, "report_premium.json"), premium)
    save_text(os.path.join(folder, "prompt_ai.txt"), json.dumps(premium, indent=2, ensure_ascii=False))

    

    



# ======================================
# CLI
# ======================================

def main():
    args = argparse.ArgumentParser()
    args.add_argument("--id", required=True)
    cid = args.parse_args().id

    print_header("EXPORT REPORT — PADRÃO OURO")
    export_report(cid)
    print("Exportação concluída.")




if __name__ == "__main__":
    main()

import os
import sys
import json
import subprocess
import streamlit as st
import pandas as pd
import unicodedata

import gspread
from google.oauth2.service_account import Credentials

SERVICE_ACCOUNT_FILE = "secrets/google_service_account.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
SPREADSHEET_ID = "1BaS2goahKS8KkhbUgFJSVcMHtfW_KoaZ0RIkOBne0go"

STATUS_COLORS = {
    "OK": "#22c55e",        # verde
    "ADEQUADO": "#22c55e",
    "ATENCAO": "#facc15",   # amarelo
    "ALTO": "#f97316",      # laranja
    "CRITICO": "#ef4444",   # vermelho
    "SEM_DADOS": "#9ca3af"  # cinza
}

def section_title(icon, text, size=18):
    st.markdown(
        f"""
        <div style="font-size:{size}px; font-weight:600;">
            {icon} {text}
        </div>
        """,
        unsafe_allow_html=True
    )


def maturity_to_status(level):
    """
    Converte nível de maturidade para status padrão do sistema
    """
    if level == "ALTA":
        return "OK"
    if level == "MÉDIA":
        return "ATENCAO"
    if level == "BAIXA":
        return "CRITICO"
    return "SEM_DADOS"


def maturity_level_text(score):
    if score is None:
        return "SEM DADOS"
    if score < 40:
        return "BAIXA"
    if score < 70:
        return "MÉDIA"
    return "ALTA"

def normalize_column_name(col):
    if col is None:
        return ""
    return " ".join(str(col).strip().split())


def find_column_key(row: dict, contains_text: str):
    for k in row.keys():
        if contains_text.lower() in k.lower():
            return k
    return None


@st.cache_data(ttl=30)
@st.cache_data(ttl=30)
def list_ids_from_sheets():
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)

    ws = client.open_by_key(SPREADSHEET_ID).sheet1

    values = ws.get_all_values()
    if len(values) < 2:
        return []

    headers = values[0]
    data_rows = values[1:]

    rows = []
    for row in data_rows:
        cleaned = {}
        for k, v in zip(headers, row):
            cleaned[normalize_column_name(k)] = v
        rows.append(cleaned)

    if not rows:
        return []

    id_col = find_column_key(rows[0], "ID da coleta")
    if not id_col:
        return []

    ids = sorted(
        set(
            str(r.get(id_col, "")).strip()
            for r in rows
            if str(r.get(id_col, "")).strip() != ""
        )
    )

    return ids




# -----------------------------
# Utils
# -----------------------------

IMPACT_NAMES = {
    "G1": "Impacto emocional",
    "G2": "Impacto cognitivo",
    "G3": "Impacto comportamental",
    "G4": "Impacto organizacional",
    "G5": "Impacto na saúde",
    "G6": "Impacto funcional",
}



def build_cross_insights(cross_block: dict, mode: str):
    """
    mode:
      - 'operational'
      - 'strategic'
      - 'impact'
    """
    insights = []

    if not cross_block:
        return insights

    for k, v in cross_block.items():
        if not isinstance(v, dict):
            continue

        sev = v.get("severity")
        gap = v.get("gap")

        # -------------------------
        # RISCO × MATURIDADE
        # -------------------------
        if mode in ("operational", "strategic"):
            if sev == "CRITICO":
                insights.append(
                    f"🔴 **{k} crítico** — risco muito acima da maturidade "
                    f"{'operacional' if mode=='operational' else 'estratégica'}. "
                    f"Indica falha estrutural e alta probabilidade de impacto."
                )

            elif sev == "ALTO":
                insights.append(
                    f"🟠 **{k} em nível alto** — maturidade insuficiente para sustentar o risco atual. "
                    f"Recomenda-se intervenção prioritária."
                )

            elif sev == "MODERADO":
                insights.append(
                    f"🟡 **{k} moderado** — risco existente, parcialmente absorvido pela maturidade. "
                    f"Ajustes preventivos recomendados."
                )

        # -------------------------
        # IMPACTO × ROI
        # -------------------------
        if mode == "impact":
            loss = v.get("estimated_annual_loss")
            if loss and loss > 0:
                insights.append(
                    f"💰 **{k} gera impacto financeiro estimado** — perdas associadas a este fator "
                    f"podem ser mitigadas com ações direcionadas."
                )

    return insights



def severity_badge(sev: str):
    s = (sev or "").upper()
    if s == "CRITICO":
        return "🔴 CRÍTICO"
    if s == "ALTO":
        return "🟠 ALTO"
    if s == "MODERADO":
        return "🟡 MODERADO"
    if s == "CONTROLADO":
        return "🟢 CONTROLADO"
    return "⚪ SEM DADOS"


def colored_progress(value, status):
    color = STATUS_COLORS.get(status, "#3b82f6")
    percent = 0 if value is None else min(int(value), 100)

    st.markdown(
        f"""
        <div style="background:#1f2933;border-radius:8px;height:10px;width:100%;">
            <div style="
                background:{color};
                width:{percent}%;
                height:10px;
                border-radius:8px;
                transition: width 0.6s ease;">
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_ids_from_reports(base="reports"):
    """Lista os IDs (pastas) dentro de reports/ que possuam report_premium.json"""
    if not os.path.exists(base):
        return []
    ids = []
    for name in os.listdir(base):
        folder = os.path.join(base, name)
        if os.path.isdir(folder):
            premium_path = os.path.join(folder, "report_premium.json")
            if os.path.exists(premium_path):
                ids.append(name)
    return sorted(ids)


def get_paths(collection_id: str) -> dict:
    base = os.path.join("reports", collection_id)
    return {
        "premium": os.path.join(base, "report_premium.json"),
        "txt": os.path.join(base, "report.txt"),
        "prompt": os.path.join(base, "prompt_ai.txt"),
        # IA outputs
        "ai_folder": os.path.join(base, "ai"),
        "ai_txt": os.path.join(base, "ai", "analysis_ai.txt"),
        "ai_json": os.path.join(base, "ai", "analysis_ai.json"),
    }


def fmt_money(v):
    if v is None:
        return "SEM DADOS"
    try:
        v = float(v)
        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return str(v)


def fmt_pct(v):
    if v is None:
        return "SEM DADOS"
    try:
        v = float(v)
        return f"{v*100:.1f}%"
    except:
        return str(v)


def safe_get(d: dict, path: list, default=None):
    """safe nested get: safe_get(obj, ["a","b","c"])"""
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur

def normalize(text):
    return unicodedata.normalize("NFKD", text).encode("ASCII", "ignore").decode()

def status_badge(status: str):
    s = (status or "").upper()
    if s == "CRITICO":
        return "🔴 CRÍTICO"
    if s == "ATENCAO":
        return "🟡 ATENÇÃO"
    if s in {"OK", "ADEQUADO"}:
        return "🟢 OK"
    if s == "MEDIA":
        return "🟡 MÉDIA"
    if s == "ALTA":
        return "🟢 ALTA"
    if s == "BAIXA":
        return "🔴 BAIXA"
    return f"⚪ {s or 'SEM_DADOS'}"

def cross_maturity_status(score_op, score_st):
    if score_op is None or score_st is None:
        return "SEM_DADOS"

    if score_op < 40 or score_st < 40:
        return "CRITICO"

    if score_op < 70 or score_st < 70:
        return "ATENCAO"

    return "ADEQUADO"


# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(page_title="NR-1 Dashboard (Padrão Ouro)", layout="wide")

# -----------------------------
# Ajuste visual: métricas responsivas (anti-corte)
# -----------------------------
st.markdown("""
<style>
/* Valor numérico do st.metric */
div[data-testid="stMetricValue"] {
    font-size: clamp(16px, 2.5vw, 28px);
    line-height: 1.1;
    white-space: nowrap;
}

/* Label do st.metric (título) */
div[data-testid="stMetricLabel"] {
    font-size: 14px;
}
</style>
""", unsafe_allow_html=True)


st.title("📊 Dashboard — Sistema Especialista NR-1 (Riscos Psicossociais)")
st.caption("Análise técnica automatizada de riscos psicossociais conforme NR-1.")


# =========================
# Sidebar — SaaS Style
# =========================

st.sidebar.markdown("""
<div style="padding-bottom:18px;">
    <h2 style="margin-bottom:0;">📊 NR-1 Dashboard</h2>
    <span style="font-size:12px; color:#9ca3af;">
        Sistema Analítico • Riscos Psicossociais
    </span>
</div>
""", unsafe_allow_html=True)

# =========================
# Seleção de ID
# =========================

st.sidebar.markdown("#### 📂 Coleta")

processed_ids = list_ids_from_reports()
sheet_ids = list_ids_from_sheets()
all_ids = sorted(set(processed_ids + sheet_ids))

selected_id = st.sidebar.selectbox(
    "ID disponível",
    [""] + all_ids,
    index=0,
    help="Selecione um ID já processado ou disponível na planilha."
)

manual_id = st.sidebar.text_input(
    "Inserir ID manualmente",
    value=(selected_id or ""),
    help="Use se desejar forçar um ID específico."
).strip()

report_id = manual_id if manual_id else selected_id

st.sidebar.markdown("<br>", unsafe_allow_html=True)

# =========================
# Reprocessamento
# =========================

st.sidebar.markdown("#### 🔄 Atualização")

st.sidebar.caption(
    "Reprocessa o ID selecionado e recria os arquivos técnicos."
)

if st.sidebar.button("Atualizar relatório", use_container_width=True):

    if not report_id:
        st.sidebar.error("Selecione ou digite um ID válido.")
    else:
        with st.spinner("Executando pipeline..."):
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "src.report_export",
                    "--id",
                    report_id
                ],
                capture_output=True,
                text=True
            )

        if result.returncode != 0:
            st.sidebar.error("Erro no processamento.")
            if result.stderr:
                st.sidebar.code(result.stderr)
        else:
            st.sidebar.success("Atualização concluída.")
            st.rerun()

st.sidebar.markdown("---")

# =========================
# Rodapé minimalista
# =========================

st.sidebar.caption(
    "🔒 Modo leitura\n"
    "⚙️ Reprocessamento por ID\n"
    "📁 Relatórios rastreáveis"
)



# =========================
# Main: carregar report
# =========================
if not report_id:
    st.info("Selecione um ID na barra lateral ou digite manualmente.")
    st.stop()

paths = get_paths(report_id)

if not os.path.exists(paths["premium"]):
    st.warning(
        f"Ainda não existe `report_premium.json` para o ID **{report_id}**.\n\n"
        "Clique em **Atualizar relatório agora** para gerar."
    )
    st.stop()

premium = load_json(paths["premium"])

# -------------------------
# Blocos principais
# -------------------------
schema = premium.get("schema", {})
collection = premium.get("collection", {})
counts = safe_get(collection, ["counts"], {})
results = premium.get("results", {})
diagnosis = premium.get("diagnosis", {})
roi_block = premium.get("roi", {})
legal = premium.get("legal_triggers", {})
qual = premium.get("qualitative_notes", {})

risk = safe_get(results, ["risk"], {})
impact = safe_get(results, ["impact"], {})
maturity = safe_get(results, ["maturity"], {})

roi_calc = safe_get(roi_block, ["roi_calc"], None)
payroll_monthly = safe_get(roi_block, ["payroll_monthly"], None)
payroll_info = safe_get(roi_block, ["payroll_info"], {})

st.markdown("## 📌 Visão Executiva")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown("### 🎯 Prioridade")
    st.write(status_badge(diagnosis.get("priority", "SEM_DADOS")))

with col2:
    st.markdown("### ⚠️ Risco Geral")
    st.write(status_badge(diagnosis.get("general_risk_status", "SEM_DADOS")))

with col3:
    st.markdown("### 📉 Impacto Geral")
    st.write(status_badge(diagnosis.get("general_impact_status", "SEM_DADOS")))

with col4:
    st.markdown("### 📊 Confiabilidade")
    st.write(status_badge(safe_get(diagnosis, ["confidence", "level"], "SEM_DADOS")))

with st.expander("📎 Dados da Coleta"):
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("ID", report_id)
    col2.metric("Respondentes", counts.get("total", 0))
    col3.metric("Gestão", counts.get("gestao_operacional", 0))
    col4.metric("Diretoria", counts.get("diretoria", 0))

def build_executive_synthesis(diagnosis, results):
    risk_status = diagnosis.get("general_risk_status", "SEM_DADOS")
    impact_status = diagnosis.get("general_impact_status", "SEM_DADOS")
    priority = diagnosis.get("priority", "SEM_DADOS")

    score_op = results.get("maturity_operational", {}).get("score_0_100")
    score_st = results.get("maturity_strategic", {}).get("score_0_100")

    level_op = maturity_level_text(score_op)
    level_st = maturity_level_text(score_st)

    # =========================
    # CLASSIFICAÇÃO GERAL
    # =========================
    if priority == "ALTA" or risk_status == "CRITICO":
        level = "CRITICO"
    elif priority == "MEDIA" or risk_status == "ATENCAO":
        level = "ATENCAO"
    else:
        level = "ADEQUADO"

    # =========================
    # TEXTOS PADRÃO OURO
    # =========================
    texts = {

        "CRITICO": {
            "icon": "🔴",
            "title": "Nível Crítico — Exposição Organizacional Elevada",
            "context": (
                f"O cenário atual indica risco psicossocial elevado, "
                f"com impacto funcional relevante e maturidade "
                f"operacional ({level_op}) e estratégica ({level_st}) "
                f"insuficientes para sustentar o nível de pressão identificado."
            ),
            "analysis": (
                "Há desalinhamento estrutural entre risco, execução e governança. "
                "O sistema opera no limite de absorção."
            ),
            "implication": (
                "Sem intervenção estruturada, a tendência é evolução para "
                "desgaste organizacional, aumento de afastamentos "
                "e potencial exposição jurídica."
            ),
            "direction": (
                "Recomenda-se ação prioritária em governança estratégica, "
                "padronização operacional e fortalecimento de liderança."
            )
        },

        "ATENCAO": {
            "icon": "🟡",
            "title": "Nível de Atenção — Sistema Sob Pressão Controlável",
            "context": (
                f"O cenário indica risco psicossocial moderado, "
                f"com impacto funcional administrável e maturidade "
                f"operacional ({level_op}) e estratégica ({level_st}) "
                f"em estágio intermediário."
            ),
            "analysis": (
                "A organização demonstra esforço e reconhecimento do tema, "
                "porém ainda com fragilidades estruturais."
            ),
            "implication": (
                "Sem ajustes preventivos, os riscos tendem a se tornar recorrentes "
                "e financeiramente mais relevantes."
            ),
            "direction": (
                "Recomenda-se fortalecimento gradual da governança psicossocial "
                "e institucionalização das práticas de gestão."
            )
        },

        "ADEQUADO": {
            "icon": "🟢",
            "title": "Nível Adequado — Estrutura Compatível com os Riscos",
            "context": (
                f"O cenário indica alinhamento entre risco psicossocial, "
                f"impacto funcional e maturidade organizacional "
                f"(Operacional: {level_op} | Estratégica: {level_st})."
            ),
            "analysis": (
                "O sistema demonstra capacidade de absorção e resposta "
                "proporcional aos riscos identificados."
            ),
            "implication": (
                "O principal desafio passa a ser manter consistência e "
                "evitar regressão estrutural."
            ),
            "direction": (
                "Recomenda-se monitoramento contínuo e evolução progressiva "
                "dos indicadores."
            )
        }
    }

    return texts.get(level)


with st.expander("🎯 Síntese Estratégica", expanded=False):
    st.markdown("### 🧠 Leitura Integrada de Exposição Organizacional")
    synthesis = build_executive_synthesis(diagnosis, results)

    if synthesis:
        st.markdown(f"### {synthesis['icon']} {synthesis['title']}")

        st.markdown("**Contexto Atual**")
        st.write(synthesis["context"])

        st.markdown("**Leitura Estratégica**")
        st.write(synthesis["analysis"])

        st.markdown("**Implicação Organizacional**")
        st.write(synthesis["implication"])

        st.markdown("**Direcionamento Executivo**")
        st.write(synthesis["direction"])



# =========================
# Tabs
# =========================
tab1, tab2, tab_funcionais, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(
    [
        "📌 Riscos (R)",
        "⚠️ Impactos (G)",
        "📉 Indicadores Funcionais",
        "🏛️ Maturidade Operacional / Estratégica",
        "🧠 Cruzamentos",
        "🔥 Prioridades",
        "💰 ROI",
        "⚖️ Jurídico",
        "📦 Downloads & IA"
    ]
)


# -------------------------
# TAB 1: Riscos Psicossociais
# -------------------------
with tab1:

    st.subheader("📌 Riscos Psicossociais")

    st.caption(
        "Indicadores de risco psicossocial por dimensão. "
        "A leitura deve priorizar o **status** e o **significado organizacional**."
    )

    if not risk:
        st.info("Sem dados de risco disponíveis.")
    else:
        for k, v in risk.items():

            score = v.get("score")
            status = v.get("status", "SEM_DADOS")
            icon = v.get("icon", "")
            name = v.get("name", k)
            interpretation = v.get("interpretation", "")

            score_pct = f"{round(score, 1)}%" if score is not None else "—"

            col1, col2, col3 = st.columns([2, 1, 4])

            # Nome do risco
            with col1:
                st.markdown(f"##### {icon} {name}")

            # Status + score (igual indicadores funcionais)
            with col2:
                st.metric(
                    label="Status",
                    value=status,
                    delta=score_pct
                )

            # Interpretação executiva
            with col3:
                st.write(interpretation or "Interpretação não disponível.")

            # Barra de progresso colorida (mesma lógica dos indicadores)
            colored_progress(score, status)

            st.markdown("---")

# -------------------------
# TAB 2: Impactos Psicossociais
# -------------------------
with tab2:
    st.subheader("⚠️ Impactos Psicossociais")

    st.caption(
        "Impactos funcionais associados aos riscos psicossociais. "
        "Esta seção mostra como o risco já se manifesta na operação."
    )

    if not impact:
        st.info("Sem dados de impactos disponíveis.")
    else:
        for k, v in impact.items():

            score = v.get("score")
            status = v.get("status", "SEM_DADOS")
            icon = v.get("icon", "")
            name = IMPACT_NAMES.get(k, k).replace("Atenção ", "")
            interpretation = v.get("interpretation", "")
            raw_icon = v.get("icon", "")
            icon_only = raw_icon[:2]  # pega só o emoji

            score_pct = f"{round(score, 1)}%" if score is not None else "—"

            col1, col2, col3 = st.columns([2, 1, 4])

            # Nome do impacto (SEM status textual)
            with col1:
                st.markdown(f"##### {icon_only} {name}")


            # Status + score (igual riscos e indicadores)
            with col2:
                st.metric(
                    label="Status",
                    value=status,
                    delta=score_pct
                )

            # Interpretação executiva do impacto
            with col3:
                st.write(interpretation or "Interpretação não disponível.")

            # Barra de progresso colorida (mesma função)
            colored_progress(score, status)

            st.markdown("---")

    # =========================
    # Observações qualitativas
    # =========================
    notes_filtered = qual.get("filtered", [])

    with st.expander("🧾 Observações qualitativas dos respondentes", expanded=False):
        if not notes_filtered:
            st.info("Nenhuma observação qualitativa relevante foi registrada.")
        else:
            for i, t in enumerate(notes_filtered, 1):
                st.write(f"{i}. {t}")


# -------------------------
# TAB: Indicadores Funcionais
# -------------------------
with tab_funcionais:

    st.subheader("📊 Indicadores Funcionais de Risco")

    indices = premium.get("indices", {})

    INDICES_FUNCIONAIS_V1 = [
    "RISCO_BURNOUT",
    "RISCO_ABSENTEISMO",
    "RISCO_PRESENTEISMO"
    ]

    indices_funcionais = {
        k: v for k, v in indices.items()
        if k in INDICES_FUNCIONAIS_V1
    }

    if not indices_funcionais:
        st.info("Sem indicadores funcionais disponíveis.")
    else:
        for key, v in indices_funcionais.items():

            score = v.get("score")
            score_pct = f"{round(score, 1)}%" if score is not None else "—"
            status = v.get("status", "SEM_DADOS")

            col1, col2, col3 = st.columns([2, 1, 4])

            with col1:
                st.markdown(f"### {v.get('icon', '')} {v.get('name')}")

            with col2:
                st.metric(
                    label="Status",
                    value=status,
                    delta=score_pct
                )

            with col3:
                st.write(v.get("description", ""))

            colored_progress(score, status)
            st.markdown("---")



# -------------------------
# TAB 3: Maturidade
# -------------------------
with tab3:

    def maturity_executive_text_operational(level):
        texts = {
            "BAIXA": {
                "title": "Maturidade Operacional — BAIXA",
                "body": (
                    "A gestão psicossocial **não está estruturada na operação**.\n\n"
                    "As ações são **pontuais, reativas e desconectadas**, dependentes de pessoas "
                    "e não de processos.\n\n"
                    "A liderança atua sem direcionamento claro, o que **aumenta a exposição a riscos, "
                    "retrabalho e crises recorrentes**."
                ),
                "key": (
                    "Sem estrutura operacional, o risco psicossocial se manifesta "
                    "antes que a organização consiga reagir."
                )
            },
            "MÉDIA": {
                "title": "Maturidade Operacional — MÉDIA",
                "body": (
                    "Existe uma **estrutura parcial de gestão psicossocial**.\n\n"
                    "Alguns processos funcionam, porém **não são padronizados nem sustentáveis**.\n\n"
                    "A liderança executa, mas **sem consistência**, e a gestão atua de forma "
                    "**reativa**, apagando incêndios."
                ),
                "key": (
                    "A operação sustenta o dia a dia, "
                    "mas **não sustenta crescimento, pressão prolongada ou crise**."
                )
            },
            "ALTA": {
                "title": "Maturidade Operacional — ALTA",
                "body": (
                    "A gestão psicossocial está **integrada à rotina operacional**.\n\n"
                    "Processos são padronizados, monitorados e executados com consistência.\n\n"
                    "A liderança atua de forma previsível, permitindo **prevenção, resposta rápida "
                    "e estabilidade operacional**."
                ),
                "key": (
                    "A operação apresenta resiliência e baixa exposição "
                    "a riscos psicossociais críticos."
                )
            }
        }
        return texts.get(level)
    
    def maturity_executive_text_strategic(level):
        texts = {
            "BAIXA": {
                "title": "Maturidade Estratégica — BAIXA",
                "body": (
                    "A gestão psicossocial **não faz parte da estratégia organizacional**.\n\n"
                    "As decisões são **reativas**, sem governança, indicadores ou responsabilização clara.\n\n"
                    "O risco é tratado apenas quando gera impacto jurídico, humano ou reputacional."
                ),
                "key": (
                    "Sem direção estratégica, a organização reage ao dano — não o previne."
                )
            },
            "MÉDIA": {
                "title": "Maturidade Estratégica — MÉDIA",
                "body": (
                    "A diretoria **reconhece a importância do tema**, mas ainda não estruturou "
                    "a gestão psicossocial como sistema.\n\n"
                    "Existem decisões corretas, porém **reativas e desconectadas** de processos, "
                    "indicadores e governança."
                ),
                "key": (
                    "A estratégia existe na intenção, "
                    "mas **não está incorporada ao sistema de gestão**."
                )
            },
            "ALTA": {
                "title": "Maturidade Estratégica — ALTA",
                "body": (
                    "A gestão psicossocial está **integrada à estratégia organizacional**.\n\n"
                    "Há governança clara, responsabilização definida e decisões sustentadas por dados.\n\n"
                    "O risco psicossocial é tratado como **variável estratégica de negócio**."
                ),
                "key": (
                    "A organização antecipa riscos e protege pessoas, resultados e reputação."
                )
            }
        }
        return texts.get(level)

    st.subheader("🏗️ Maturidade de Gestão Psicossocial")

    matur_op = results.get("maturity_operational", {})
    matur_st = results.get("maturity_strategic", {})

    score_op = matur_op.get("score_0_100")
    score_st = matur_st.get("score_0_100")

    level_op = maturity_level_text(score_op)
    level_st = maturity_level_text(score_st)
    status_op = maturity_to_status(level_op)
    status_st = maturity_to_status(level_st)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 🏛️ Maturidade Operacional")
        st.markdown(f"## {round(score_op,1)}%")
        st.write(status_badge(status_op))

    with col2:
        st.markdown("### 🏢 Maturidade Estratégica")
        st.markdown(f"## {round(score_st,1)}%")
        st.write(status_badge(status_st))


    st.markdown("---")

    # OPERACIONAL
    op_text = maturity_executive_text_operational(level_op)
    with st.expander("🔎 Leitura Executiva — Maturidade Operacional", expanded=False):
        st.markdown(f"📌 **{op_text['title']}**")
        st.write(op_text["body"])
        st.markdown("👉 **Mensagem-chave:**")
        st.info(op_text["key"])

    # ESTRATÉGICA
    st_text = maturity_executive_text_strategic(level_st)
    with st.expander("🔎 Leitura Executiva — Maturidade Estratégica", expanded=False):
        st.markdown(f"📌 **{st_text['title']}**")
        st.write(st_text["body"])
        st.markdown("👉 **Mensagem-chave:**")
        st.info(st_text["key"])


# -------------------------
# TAB 6: ROI  (✅ ÚNICA PARTE ALTERADA)
# -------------------------
with tab6:
    st.subheader("💰 ROI (Produtividade — Estimativa Financeira)")

    if roi_calc is None:
        st.warning("Sem dados financeiros suficientes para estimar ROI.")
        st.write("**Dica:** confira se RH/Diretoria respondeu os campos financeiros corretamente.")
    else:
        final_percent = roi_calc.get("final_percent")  # ex: 0.156
        annual_cost = roi_calc.get("annual_cost")
        recoverable_value = roi_calc.get("recoverable_value")
        recoverable_factor = roi_calc.get("recoverable_factor", 0.30)

        # defensável: mensal derivado do anual
        monthly_cost = None if annual_cost is None else annual_cost / 12

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Folha mensal analisada", fmt_money(payroll_monthly))
        c2.metric("Impacto estimado na produtividade", fmt_pct(final_percent))
        c3.metric("Custo mensal estimado", fmt_money(monthly_cost))
        c4.metric("Custo anual estimado", fmt_money(annual_cost))       


        st.markdown("### ✅ Leitura executiva")

        st.info(
            f"📉 **Impacto estimado na produtividade:** {fmt_pct(final_percent)}\n\n"
            f"💰 **Base financeira analisada (folha mensal):** {fmt_money(payroll_monthly)}\n\n"
            f"➡️ **Custo estimado:** {fmt_money(monthly_cost)} / mês "
            f"({fmt_money(annual_cost)} / ano)\n\n"
            f"🔁 **Potencial de recuperação anual:** até {fmt_money(recoverable_value)} "
            f"(≈ {recoverable_factor*100:.0f}% do impacto estimado)\n\n"
            f"📌 *Valores baseados em modelo de risco psicossocial e maturidade organizacional.*"
        )



        st.markdown("### 🔍 Transparência técnica (modelo de cálculo)")
        st.write("**Fórmulas usadas:**")
        st.code(
            "Perda mensal = Folha mensal × Queda estimada\n"
            "Perda anual  = Perda mensal × 12\n"
            "Recuperável  = Perda anual × 30% (fator de recuperação do modelo)",
            language="text"
        )

        st.markdown("### 📌 Fonte financeira (explicação das amostras)")
        src = payroll_info.get("source", "SEM_DADOS")
        st.write("**Fonte:**", src)

        # “amostras” = quantos respondentes financeiros preencheram o campo (não é amostra estatística do questionário)
        samples_payroll = payroll_info.get("samples_payroll")
        samples_employees = payroll_info.get("samples_employees")
        samples_salary = payroll_info.get("samples_salary")

        st.write(
            "**Amostras financeiras (N):** "
            f"folha={samples_payroll}, colaboradores={samples_employees}, salário={samples_salary}"
        )
        st.caption(
            "ℹ️ Os valores apresentados são estimativas baseadas nas respostas financeiras disponíveis "
            "e não substituem análise contábil ou auditoria financeira formal."
        )   


        with st.expander("🔍 Detalhes técnicos (valores coletados / auditoria)"):
            st.json(payroll_info)


with tab4:

    # ======================================================
    # 🔀 Cruzamento 1 — Risco × Maturidade Estratégica
    # ======================================================

    cross_strategic = safe_get(
    premium,
    ["cross_analysis", "risk_vs_strategic_maturity"],
    {}
    )


    # =========================
    # Avaliação geral do cruzamento
    # =========================
    severity_order = ["CRITICO", "ALTO", "MODERADO", "CONTROLADO"]
    severity_found = "CONTROLADO"

    for s in severity_order:
        if any(v.get("severity") == s for v in cross_strategic.values()):
            severity_found = s
            break

    with st.expander("🔀 Risco × Maturidade Estratégica (Diretoria)", expanded=False):
        st.subheader("🔀 Risco × Maturidade Estratégica (Diretoria)")

        if severity_found == "CRITICO":
            st.error("🔴 Desalinhamento crítico entre riscos psicossociais e maturidade estratégica")

            st.markdown(
                "Os riscos psicossociais identificados **superam claramente a capacidade estratégica atual da organização**. "
                "Isso indica que a diretoria **não estruturou governança, processos ou responsabilização suficientes** para "
                "sustentar o nível de pressão, conflito e desgaste presente na operação."
            )

            st.markdown(
                "**Impacto direto:**\n"
                "- Alta probabilidade de passivo trabalhista\n"
                "- Adoecimento organizacional progressivo\n"
                "- Perda de controle institucional sobre os riscos\n"
            )

            st.markdown(
                "**Leitura executiva:** enquanto a estratégia não amadurecer, "
                "**nenhuma ação operacional isolada será suficiente**."
            )


        elif severity_found == "ALTO":
            st.warning("🟠 Desalinhamento relevante entre riscos e maturidade estratégica")

            st.markdown(
                "Os riscos psicossociais estão **acima da capacidade estratégica em áreas importantes da organização**. "
                "A diretoria demonstra intenção, mas **ainda não transformou isso em sistema, governança e acompanhamento real**."
            )

            st.markdown(
                "**Impacto direto:**\n"
                "- Ações acontecem, mas não se sustentam\n"
                "- A organização reage, mas não previne\n"
                "- O risco tende a se repetir e se acumular\n"
            )

            st.markdown(
                "**Leitura executiva:** é necessário sair do discurso e "
                "**instituir mecanismos claros de decisão, prioridade e responsabilização**."
            )


        elif severity_found == "MODERADO":
            st.info("🟡 Atenção: riscos exigem reforço estratégico")

            st.markdown(
                "A maturidade estratégica **cobre parte dos riscos psicossociais**, "
                "porém ainda existem **gaps entre intenção estratégica e execução sistêmica**."
            )

            st.markdown(
                "**Impacto direto:**\n"
                "- O sistema funciona sob condições normais\n"
                "- Situações de pressão elevada expõem fragilidades\n"
            )

            st.markdown(
                "**Leitura executiva:** pequenos ajustes estratégicos agora "
                "**evitam crises maiores no médio prazo**."
            )


        else:
            st.success("🟢 Alinhamento adequado entre riscos e maturidade estratégica")

            st.markdown(
                "A maturidade estratégica atual é **compatível com os riscos psicossociais identificados**. "
                "A diretoria demonstra capacidade de sustentar decisões, governança e direcionamento institucional."
            )

            st.markdown(
                "**Impacto direto:**\n"
                "- Riscos monitorados\n"
                "- Ações coerentes com a estratégia\n"
                "- Capacidade de resposta e prevenção\n"
            )

            st.markdown(
                "**Leitura executiva:** o desafio passa a ser "
                "**manter consistência e evitar regressão do sistema**."
            )



    with st.expander("🔀 Risco × Maturidade Operacional", expanded=False):
        st.subheader("🔀 Risco × Maturidade Operacional (Gestão / RH / SESMT)")

        if severity_found == "CRITICO":
            st.error("🔴 Execução operacional incapaz de sustentar os riscos psicossociais")

            st.markdown(
                "Os riscos psicossociais identificados **não estão sendo sustentados pela prática diária da gestão**. "
                "Isso indica falhas graves na atuação das lideranças, nos processos operacionais "
                "e na condução cotidiana das equipes."
            )

            st.markdown(
                "**Impacto direto:**\n"
                "- Adoecimento recorrente das equipes\n"
                "- Conflitos mal geridos\n"
                "- Desgaste contínuo e perda de produtividade\n"
            )

            st.markdown(
                "**Leitura executiva:** a estratégia pode até existir, "
                "mas **a operação está falhando em transformar diretrizes em comportamento real**."
            )


        elif severity_found == "ALTO":
            st.warning("🟠 Capacidade operacional abaixo do necessário para sustentar os riscos")

            st.markdown(
                "A gestão operacional **não consegue sustentar de forma consistente os riscos psicossociais existentes**. "
                "As ações acontecem, mas são **irregulares, dependentes de pessoas específicas e pouco padronizadas**."
            )

            st.markdown(
                "**Impacto direto:**\n"
                "- A organização reage, mas não previne\n"
                "- Os mesmos problemas reaparecem\n"
                "- A liderança atua mais no improviso do que no método\n"
            )

            st.markdown(
                "**Leitura executiva:** é necessário fortalecer rotinas, "
                "**padronizar práticas de liderança e institucionalizar a gestão do risco**."
            )


        elif severity_found == "MODERADO":
            st.info("🟡 Atenção: execução operacional exige ajustes")

            st.markdown(
                "A operação consegue **absorver parte dos riscos psicossociais**, "
                "porém ainda apresenta **fragilidades na consistência da execução**."
            )

            st.markdown(
                "**Impacto direto:**\n"
                "- O sistema funciona em cenários estáveis\n"
                "- Situações de pressão expõem falhas de liderança e processo\n"
            )

            st.markdown(
                "**Leitura executiva:** ajustes operacionais agora "
                "**evitam que riscos moderados evoluam para quadros críticos**."
            )


        else:
            st.success("🟢 Execução operacional compatível com os riscos identificados")

            st.markdown(
                "As práticas operacionais atuais são **suficientes para sustentar os riscos psicossociais mapeados**. "
                "A liderança atua de forma previsível, com rotinas claras e resposta adequada."
            )

            st.markdown(
                "**Impacto direto:**\n"
                "- Riscos monitorados no dia a dia\n"
                "- Atuação coerente da liderança\n"
                "- Menor desgaste operacional\n"
            )

            st.markdown(
                "**Leitura executiva:** o foco passa a ser "
                "**manter disciplina operacional e evitar retrocessos**."
            )


    st.subheader("🔀 Alinhamento entre Maturidade Estratégica e Operacional")

    score_op = results.get("maturity_operational", {}).get("score_0_100")
    score_st = results.get("maturity_strategic", {}).get("score_0_100")

    status_cross = cross_maturity_status(score_op, score_st)

    # =========================
    # STATUS EXECUTIVO
    # =========================
    if status_cross == "CRITICO":
        st.error("🔴 Status: CRÍTICO — Estratégia e operação estão desalinhadas")
    elif status_cross == "ATENCAO":
        st.warning("🟡 Status: ATENÇÃO — Esforço existe, mas não há sustentação")
    elif status_cross == "ADEQUADO":
        st.success("🟢 Status: ADEQUADO — Estratégia e operação estão alinhadas")
    else:
        st.info("⚪ Status: SEM DADOS SUFICIENTES")

    # =========================
    # LEITURA EXECUTIVA
    # =========================
    with st.expander("📌 Leitura executiva do alinhamento", expanded=False):

        if status_cross == "CRITICO":
            st.markdown("""
                ### 🔴 Nível Crítico — Gestão Fragilizada

                **O que esse nível sofre?**  
                - Desorganização recorrente  
                - Lideranças sobrecarregadas  
                - Conflitos frequentes e desgaste emocional  
                - Decisões inconsistentes e retrabalho constante  

                **O que isso representa?**  
                A estratégia não sustenta a operação e a operação não entende a estratégia.  
                A gestão funciona no improviso e depende das pessoas “aguentarem”.

                **O que pode ser ferido?**  
                - Clima organizacional  
                - Saúde emocional das lideranças  
                - Produtividade real  
                - Relações de trabalho  
                - Credibilidade da gestão  

                **O que acontece se nada for feito?**  
                O risco psicossocial evolui para risco jurídico, afastamentos aumentam,  
                bons profissionais se desligam e a empresa entra em modo sobrevivência.
                """)

        elif status_cross == "ATENCAO":
            st.markdown("""
                ### 🟡 Nível de Atenção — Esforço sem Sustentação

                **O que esse nível sofre?**  
                - Inconsistência na execução  
                - Boas intenções que não viram sistema  
                - Pressão prolongada sobre a liderança  
                - Fragilidade quando o cenário muda  

                **O que isso representa?**  
                A diretoria reconhece o problema e a operação se esforça para entregar,  
                mas não existe padronização suficiente nem governança consolidada.

                **O que pode ser ferido?**  
                - Energia da liderança  
                - Continuidade das ações  
                - Capacidade de absorver crescimento  
                - Confiança no médio prazo  

                **O que acontece se nada for feito?**  
                O sistema entra em fadiga, o risco se normaliza  
                e o custo emocional começa a virar custo financeiro.
                """)

        elif status_cross == "ADEQUADO":
            st.markdown("""
                ### 🟢 Nível Adequado — Gestão Sustentável

                **O que esse nível sofre?**  
                Poucos impactos estruturais. Os desafios tendem a ser pontuais.

                **O que isso representa?**  
                Estratégia e operação falam a mesma língua.  
                A liderança sabe o que fazer, como fazer e acompanha os riscos.

                **O que pode ser ferido?**  
                Apenas em caso de negligência ou ruptura de governança.

                **O que acontece se nada for feito?**  
                O foco passa a ser melhoria contínua.  
                A organização ganha previsibilidade, resiliência e capacidade de crescimento.
                """)

        else:
            st.markdown("""
                Não há dados suficientes para avaliar o alinhamento entre maturidade estratégica
                e operacional. Recomenda-se ampliar a base de respostas.
                """)


with tab5:
    st.subheader("🔥 Prioridades de Intervenção")

    prio = diagnosis.get("priority", "SEM_DADOS")

    # =========================
    # STATUS EXECUTIVO
    # =========================
    st.metric("Nível de prioridade", status_badge(prio))

    st.markdown("---")

    # =========================
    # LEITURA EXECUTIVA
    # =========================
    if prio == "ALTA":
        st.error("🔴 Prioridade Alta — Ação imediata recomendada")

        st.markdown(
            "A análise integrada dos dados indica **risco psicossocial relevante**, "
            "com **impactos funcionais e organizacionais já perceptíveis**.\n\n"
            "A maturidade atual **não é suficiente para sustentar o nível de pressão identificado**, "
            "o que eleva a probabilidade de escalada emocional, jurídica e financeira."
        )

    elif prio == "MEDIA":
        st.warning("🟡 Prioridade Média — Atenção estratégica necessária")

        st.markdown(
            "Os riscos psicossociais estão **parcialmente sob controle**, "
            "mas existem **fragilidades estruturais** que podem se agravar "
            "caso o cenário de pressão se mantenha ou aumente.\n\n"
            "Intervenções preventivas neste momento **evitam evolução para níveis críticos**."
        )

    elif prio == "BAIXA":
        st.success("🟢 Prioridade Baixa — Monitoramento recomendado")

        st.markdown(
            "O cenário atual indica **boa capacidade de sustentação dos riscos psicossociais**.\n\n"
            "Não há necessidade de intervenção imediata, "
            "mas recomenda-se **manutenção das práticas atuais e monitoramento contínuo**."
        )

    else:
        st.info("⚪ Prioridade não determinada por falta de dados suficientes.")

    st.markdown("---")

    # =========================
    # FRENTES PRIORITÁRIAS
    # =========================
    st.markdown("### 🎯 Frentes prioritárias de atuação")

    if prio == "ALTA":
        st.write(
            "- **Liderança direta:** alinhar expectativas, carga de trabalho e comunicação\n"
            "- **Governança estratégica:** definir papéis, responsabilidades e critérios de decisão\n"
            "- **Prevenção jurídica:** tratar sinais precoces de assédio, abuso ou ambiente vulnerável"
        )

    elif prio == "MEDIA":
        st.write(
            "- **Ajustes na liderança:** fortalecer rotinas e consistência da gestão\n"
            "- **Padronização de processos:** reduzir dependência de pessoas-chave\n"
            "- **Monitoramento psicossocial:** acompanhar evolução dos riscos"
        )

    elif prio == "BAIXA":
        st.write(
            "- **Manutenção das boas práticas atuais**\n"
            "- **Monitoramento periódico dos indicadores**\n"
            "- **Aprimoramentos pontuais conforme crescimento ou mudança de cenário**"
        )

    st.markdown("---")

    # =========================
    # CONSEQUÊNCIA DE INAÇÃO
    # =========================
    st.markdown("### ⚠️ Se nada for feito")

    if prio == "ALTA":
        st.warning(
            "A tendência é de **normalização do desgaste**, "
            "com aumento de conflitos, afastamentos, queda de produtividade "
            "e possível geração de **passivo jurídico**."
        )

    elif prio == "MEDIA":
        st.info(
            "Os riscos podem se **acumular silenciosamente**, "
            "transformando fragilidades atuais em problemas estruturais "
            "no médio prazo."
        )

    elif prio == "BAIXA":
        st.success(
            "O principal risco passa a ser a **perda de disciplina e governança**, "
            "levando a regressão do sistema ao longo do tempo."
        )




# -------------------------
# TAB 8: Jurídico
# -------------------------
with tab7:
    st.subheader("⚖️ Riscos jurídico-psicossociais")

    legal_alerts = legal.get("alerts", [])
    active_count = legal.get("active_count", 0)

    # =========================
    # MENSAGEM EXECUTIVA (FORA)
    # =========================
    st.info(
        "⚖️ Esta seção apresenta **indícios de risco jurídico relacionados a fatores psicossociais**, "
        "identificados por meio de cruzamentos analíticos.\n\n"
        "ℹ️ **Importante:** os itens abaixo **não configuram diagnóstico jurídico**, "
        "mas indicam **situações que exigem validação humana especializada**."
    )

    st.markdown("---")

    # =========================
    # EXPANDER PRINCIPAL
    # =========================
    with st.expander("🔍 Detalhamento dos riscos jurídico-psicossociais", expanded=False):

        # ===== CONTADOR AQUI DENTRO =====
        st.markdown(f"### 🚨 Gatilhos jurídico-psicossociais identificados: **{active_count}**")

        if active_count == 0:
            st.success(
                "✅ Nenhum gatilho jurídico ativo foi identificado nos cruzamentos analisados.\n\n"
                "O cenário atual não indica exposição relevante a passivo trabalhista "
                "de origem psicossocial."
            )
        else:
            st.warning(
                "Foram identificados **indícios de exposição jurídica potencial**, "
                "decorrentes da combinação de fatores organizacionais, psicossociais "
                "e de gestão.\n\n"
                "Esses sinais **não indicam culpa ou irregularidade**, "
                "mas sugerem **atenção preventiva imediata**."
            )

            # =========================
            # POSSÍVEIS SITUAÇÕES OBSERVADAS
            # =========================
            st.markdown("### ⚠️ Possíveis situações associadas aos indícios")

            st.write(
                "- **Situações compatíveis com assédio moral organizacional**, "
                "como práticas recorrentes de pressão excessiva, comunicação inadequada "
                "ou falhas de segurança psicológica.\n\n"
                "- **Situações compatíveis com abuso organizacional**, caracterizadas por "
                "sobrecarga contínua, exigências desproporcionais e ausência de mecanismos "
                "de proteção ao trabalhador.\n\n"
                "- **Ambiente organizacional vulnerável**, onde fragilidades de liderança "
                "e maturidade estratégica podem sustentar comportamentos inadequados."
            )

            st.markdown("---")

            # =========================
            # ALERTAS IDENTIFICADOS (DETALHE)
            # =========================
            st.markdown("### 📌 Gatilhos identificados nos cruzamentos")

            for alert in legal_alerts:
                label = alert.get("label", "Risco jurídico identificado")

                with st.expander(f"⚠️ {label}", expanded=False):
                    st.markdown("**Natureza do risco:** Jurídico-psicossocial (potencial)")
                    st.markdown("**Origem:** Cruzamento de indicadores psicossociais e organizacionais")

                    st.markdown("**Por que isso importa?**")
                    st.write(
                        "- Possível geração de passivo trabalhista\n"
                        "- Risco de ações por dano moral\n"
                        "- Não conformidade preventiva com a NR-1\n"
                        "- Impacto reputacional e organizacional"
                    )

                    st.markdown("**Orientação recomendada:**")
                    st.write(
                        "- Avaliação conjunta por RH e Jurídico\n"
                        "- Escuta ativa e confidencial\n"
                        "- Registro técnico e preventivo\n"
                        "- Definição de ações corretivas e monitoramento contínuo"
                    )

    # ======================================================
    # ⚖️ MÓDULO: RISCOS JURÍDICO-PSICOSSOCIAIS (NR-1)
    # ======================================================
    #
    # OBJETIVO
    # --------
    # Este bloco identifica INDÍCIOS DE EXPOSIÇÃO JURÍDICA POTENCIAL
    # relacionados a fatores psicossociais, com base em cruzamentos
    # analíticos automatizados do sistema.
    #
    # IMPORTANTE:
    # - NÃO realiza diagnóstico jurídico
    # - NÃO atribui culpa
    # - NÃO substitui avaliação humana (RH / Jurídico / SESMT)
    #
    # O foco é PREVENÇÃO, GOVERNANÇA e SUPORTE À DECISÃO.
    #
    #
    # O QUE SÃO OS "GATILHOS JURÍDICO-PSICOSSOCIAIS"
    # --------------------------------------------
    # Gatilhos representam PADRÕES ORGANIZACIONAIS DE RISCO,
    # identificados quando combinações específicas de fatores
    # ultrapassam limites considerados seguros.
    #
    # Esses fatores incluem, por exemplo:
    # - Indicadores de assédio organizacional
    # - Indicadores de abuso organizacional
    # - Pressão excessiva e desgaste contínuo
    # - Fragilidades de maturidade operacional ou estratégica
    #
    #
    # COMO OS GATILHOS DISPARAM
    # ------------------------
    # Cada gatilho é avaliado de forma INDEPENDENTE.
    #
    # Isso significa que:
    # - Assédio pode disparar sozinho
    # - Abuso pode disparar sozinho
    # - Ambos podem disparar simultaneamente
    #
    # NÃO é necessário que todos ocorram juntos.
    #
    # Tecnicamente:
    # Cada alerta é criado por uma condição lógica própria
    # no pipeline (if independente).
    #
    #
    # SOBRE O CONTADOR `active_count`
    # -------------------------------
    # `active_count` representa a QUANTIDADE DE GATILHOS DISTINTOS
    # identificados automaticamente.
    #
    # Ele NÃO representa:
    # - gravidade jurídica
    # - condenação
    # - intensidade do dano
    #
    # Interpretação correta:
    # - 0  → Nenhum indício jurídico relevante detectado
    # - 1  → Atenção preventiva recomendada
    # - >=2 → Exposição organizacional crescente
    #
    #
    # POR QUE OS TEXTOS DA INTERFACE SÃO FIXOS
    # ---------------------------------------
    # Os textos exibidos nesta aba são FIXOS POR DESIGN, pois:
    #
    # - A natureza dos riscos jurídicos (assédio, abuso,
    #   ambiente vulnerável) não muda
    # - O que muda é o CONTEXTO e a QUANTIDADE de gatilhos
    #
    # A personalização ocorre via:
    # - active_count
    # - lista de alertas
    # - cruzamentos analíticos que originaram os gatilhos
    #
    # Isso evita:
    # - acusações indevidas
    # - interpretações subjetivas
    # - risco jurídico adicional
    #
    #
    # O QUE ESTE MÓDULO NÃO FAZ
    # ------------------------
    # - Não define culpa
    # - Não afirma ocorrência de crime
    # - Não substitui advogado ou psicólogo
    # - Não gera diagnóstico conclusivo
    #
    # Ele APENAS SINALIZA PADRÕES DE RISCO
    # para validação humana especializada.
    #
    #
    # DIRETRIZ DE USO
    # ---------------
    # Sempre que houver gatilhos ativos:
    # - Validar com RH / Jurídico / SESMT
    # - Garantir escuta ativa e confidencial
    # - Registrar evidências preventivas
    # - Definir ações corretivas e monitorar
    #
    # Alinhado com:
    # - NR-1 / GRO
    # - Compliance trabalhista
    # - Gestão preventiva de riscos psicossociais
    #
    # ======================================================


# -------------------------
# TAB 9: IA (Análise)  (Downloads)
# -------------------------
with tab8:
    st.subheader("📦 Downloads")

    premium_bytes = json.dumps(premium, indent=2, ensure_ascii=False).encode("utf-8")
    st.download_button(
        "⬇️ report_premium.json (IA-ready)",
        premium_bytes,
        file_name="report_premium.json",
        mime="application/json"
    )

    if os.path.exists(paths["txt"]):
        with open(paths["txt"], "r", encoding="utf-8") as f:
            txt_data = f.read()
        st.download_button(
            "⬇️ report.txt (relatório técnico)",
            txt_data,
            file_name="report.txt",
            mime="text/plain"
        )

    if os.path.exists(paths["prompt"]):
        with open(paths["prompt"], "r", encoding="utf-8") as f:
            prompt_data = f.read()
        st.download_button(
            "⬇️ prompt_ai.txt",
            prompt_data,
            file_name="prompt_ai.txt",
            mime="text/plain"
        )

    st.markdown("---")
    st.caption("✅ Padrão Ouro: este dashboard é somente leitura e suporta reprocessamento do ID com rastreabilidade.")
    with st.expander("🤖 Análise com IA (opcional)", expanded=False):
        # tudo que hoje está abaixo
        st.subheader("🤖 Análise com IA (OpenAI)")

        st.info(
            "Este módulo usa o arquivo `prompt_ai.txt` (gerado pelo pipeline) e gera análise em:\n"
            "- reports/<ID>/ai/analysis_ai.txt\n"
            "- reports/<ID>/ai/analysis_ai.json"
        )

        # pré-checks
        if not os.path.exists(paths["prompt"]):
            st.error("Não encontrei `prompt_ai.txt`. Gere o relatório primeiro (Atualizar relatório).")
            st.stop()

        # ======================================================
        # ✅ Toggle Simulação/API
        # ======================================================
        st.markdown("### ⚙️ Modo de geração")

        use_api = st.toggle("🤖 Usar OpenAI API (gera análise real)", value=False)


        # ======================================================
        # Função: gerar análise simulada
        # ======================================================
        def build_simulated_analysis(report_id: str, premium: dict) -> str:
            diagnosis = premium.get("diagnosis", {})
            results = premium.get("results", {})
            risk = results.get("risk", {})
            impact = results.get("impact", {})
            maturity = results.get("maturity", {})

            # Top 3 riscos por score
            risk_items = []
            for k, v in (risk or {}).items():
                sc = v.get("score")
                risk_items.append((k, sc if sc is not None else -1, v.get("name", "")))
            risk_items.sort(key=lambda x: x[1], reverse=True)
            top_risks = risk_items[:3]

            # Top 3 impactos por score
            impact_items = []
            for k, v in (impact or {}).items():
                sc = v.get("score")
                impact_items.append((k, sc if sc is not None else -1))
            impact_items.sort(key=lambda x: x[1], reverse=True)
            top_impacts = impact_items[:3]

            prio = diagnosis.get("priority", "SEM_DADOS")
            general_risk = diagnosis.get("general_risk_status", "SEM_DADOS")
            general_impact = diagnosis.get("general_impact_status", "SEM_DADOS")

            maturity_status = maturity.get("status", "SEM_DADOS")
            maturity_score = maturity.get("score_0_100", None)

            lines = []
            lines.append("1. Classificação Geral (NR-1 / GRO)")
            lines.append(f"- ID analisado: {report_id}")
            lines.append(f"- Prioridade: {prio}")
            lines.append(f"- Risco geral: {general_risk}")
            lines.append(f"- Impacto geral: {general_impact}")
            lines.append("")

            lines.append("2. Dimensões Críticas Identificadas (R1–R6 e justificativa)")
            if top_risks and top_risks[0][1] != -1:
                for r_id, r_sc, r_name in top_risks:
                    lines.append(f"- {r_id} ({r_name}): score={r_sc:.1f} → foco imediato em gestão/mitigação")
            else:
                lines.append("- Sem dados suficientes para ranking automático (simulação).")
            lines.append("")

            lines.append("3. Impactos Críticos (G1–G6 e justificativa)")
            if top_impacts and top_impacts[0][1] != -1:
                for g_id, g_sc in top_impacts:
                    lines.append(f"- {g_id}: score={g_sc:.1f} → impacto funcional relevante")
            else:
                lines.append("- Sem dados suficientes para ranking automático (simulação).")
            lines.append("")

            lines.append("4. Prioridade Estratégica (Alta/Média/Baixa) e Racional")
            lines.append(
                "- Priorização baseada na leitura combinada de risco, impacto e maturidade. "
                "Em produção, recomenda-se validação humana antes de decisões."
            )
            lines.append("")

            lines.append("5. Estratégia de Intervenção Recomendada")
            lines.append("- Organizacional:")
            lines.append("  - Ajustar rotinas de comunicação, gestão de demandas e alinhamento de expectativas.")
            lines.append("  - Criar rituais de feedback estruturado (semanal/mensal).")
            lines.append("- Liderança:")
            lines.append("  - Treinamento de líderes: comunicação, segurança psicológica, prevenção de condutas abusivas.")
            lines.append("  - 1:1 quinzenal com checklist mínimo.")
            lines.append("- Times:")
            lines.append("  - Workshop: conflitos, acordos de equipe, cooperação e clareza de papéis.")
            lines.append("")

            lines.append("6. Formato de Intervenção Recomendado")
            lines.append("- Ciclo 90 dias (recomendado) + Treinamento de líderes")
            lines.append("- Workshop tático para equipes críticas")
            lines.append("")

            lines.append("7. Temas Prioritários para Conteúdo (lista + objetivos)")
            lines.append("- Segurança psicológica e comunicação assertiva")
            lines.append("- Gestão de conflitos e alinhamento de expectativas")
            lines.append("- Clima organizacional e prevenção de condutas abusivas")
            lines.append("")

            lines.append("8. Plano 30/60/90 dias (ações, donos, evidências)")
            lines.append("- 30 dias: diagnóstico detalhado + validação com RH/SESMT + plano priorizado")
            lines.append("- 60 dias: treinar liderança + ajustar rotinas + executar workshop de time")
            lines.append("- 90 dias: auditoria interna + indicadores + evidências para GRO/PGR")
            lines.append("")

            lines.append("9. Comunicação Executiva (mensagem pronta para diretoria)")
            lines.append(
                "“Os dados sugerem risco psicossocial relevante com impactos funcionais. "
                "Recomenda-se intervenção estruturada com foco em governança, liderança e rotinas, "
                "com rastreabilidade para evidências do GRO/PGR.”"
            )
            lines.append("")

            lines.append("10. Pontos de Validação Humana Obrigatória")
            lines.append("- Verificar representatividade (N) e possíveis vieses da coleta")
            lines.append("- Validar sinais sensíveis (assédio, retaliação, discriminação)")
            lines.append("- Confirmar plano de ação com RH/SESMT e direção")
            lines.append("")

            lines.append("11. Observações Técnicas e Jurídicas (quando aplicável)")
            lines.append("- Esta é uma análise simulada (sem API) para validação do sistema.")
            lines.append("")
            lines.append("> Análise gerada por sistema de apoio à decisão. Recomendações sujeitas à validação técnica por consultor responsável.")

            return "\n".join(lines)

        # ======================================================
        # Seleção do modelo (aparece só se for API)
        # ======================================================
        model = "gpt-4o-mini"
        if use_api:
            col_a, col_b = st.columns([1, 1])
            with col_a:
                model = st.selectbox(
                    "Modelo",
                    ["gpt-4o-mini", "gpt-4o"],
                    index=0
                )
            with col_b:
                st.caption("Recomendação: comece com gpt-4o-mini (mais barato e rápido).")
        else:
            st.caption("Modo Simulação ativo: não usa API e não consome créditos.")

        st.markdown("### ✅ Gerar análise")

        button_label = "🧪 Gerar análise SIMULADA (sem API)" if not use_api else "🤖 Gerar análise com IA agora"

        if st.button(button_label):
            os.makedirs(paths["ai_folder"], exist_ok=True)

            # -------------------------
            # SIMULAÇÃO
            # -------------------------
            if not use_api:
                simulated_text = build_simulated_analysis(report_id, premium)

                with open(paths["ai_txt"], "w", encoding="utf-8") as f:
                    f.write(simulated_text)

                simulated_payload = {
                    "generated_at": "SIMULATED",
                    "collection_id": report_id,
                    "model": "SIMULATED",
                    "status": "SUCCESS_SIMULATED",
                    "analysis_text": simulated_text,
                    "error": None,
                }

                with open(paths["ai_json"], "w", encoding="utf-8") as f:
                    json.dump(simulated_payload, f, indent=2, ensure_ascii=False)

                st.success("✅ Análise simulada gerada (sem custo).")
                st.rerun()

            # -------------------------
            # OPENAI API
            # -------------------------
            else:
                with st.spinner("Chamando OpenAI via run_ai.py..."):
                    result = subprocess.run(
                        ["python", "src/run_ai.py", "--id", report_id, "--model", model],
                        capture_output=True,
                        text=True
                    )

                if result.returncode != 0:
                    st.error("❌ Erro ao gerar análise com IA.")
                    if result.stderr:
                        st.code(result.stderr)
                    if result.stdout:
                        st.code(result.stdout)

                    err = (result.stderr or "") + "\n" + (result.stdout or "")
                    if "RateLimitError" in err or "insufficient_quota" in err or "Error code: 429" in err:
                        st.warning(
                            "⚠️ Sua API retornou erro 429 (quota/billing).\n\n"
                            "Isso não é bug no código.\n"
                            "Você precisa:\n"
                            "- Ativar Billing na OpenAI API\n"
                            "- Inserir cartão / crédito\n"
                            "- Confirmar limites de uso\n"
                            "Obs: ChatGPT pago ≠ créditos API"
                        )
                else:
                    st.success("✅ Análise gerada com sucesso!")
                    if result.stdout:
                        st.code(result.stdout)
                    st.rerun()

        st.markdown("---")
        st.markdown("### 📄 Resultado da análise")

        if not os.path.exists(paths["ai_txt"]):
            st.warning("Ainda não existe análise para este ID. Clique em **Gerar análise**.")
        else:
            with open(paths["ai_txt"], "r", encoding="utf-8") as f:
                ai_txt = f.read()

            st.text_area("Análise IA (texto)", ai_txt, height=500)

            st.markdown("### 📦 Downloads IA")
            st.download_button(
                "⬇️ analysis_ai.txt",
                ai_txt,
                file_name="analysis_ai.txt",
                mime="text/plain"
            )

            if os.path.exists(paths["ai_json"]):
                ai_json = load_json(paths["ai_json"])
                st.download_button(
                    "⬇️ analysis_ai.json",
                    json.dumps(ai_json, indent=2, ensure_ascii=False).encode("utf-8"),
                    file_name="analysis_ai.json",
                    mime="application/json"
                )
                with st.expander("🔍 analysis_ai.json (visualizar)"):
                    st.json(ai_json)

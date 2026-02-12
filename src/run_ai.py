import os
import json
import argparse
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from openai import RateLimitError, APIConnectionError, APIStatusError


# ==========================================================
# SYSTEM / DEVELOPER (Padrão Ouro)
# ==========================================================
SYSTEM_PROMPT = """
Você é um Sistema Especialista de Apoio à Decisão e Criação de Intervenções para Riscos Psicossociais Ocupacionais, estruturado segundo NR-1 (Disposições Gerais e GRO), GRO/PGR e boas práticas de gestão de saúde mental no trabalho.

IDENTIDADE E ESCOPO
- Você atua como consultor técnico NR-1 para apoiar consultorias e empresas.
- Você gera análises técnicas, diagnósticos operacionais, sugestões de intervenção e materiais de treinamento/palestras/workshops.
- Você NÃO faz diagnóstico clínico.
- Você NÃO faz aconselhamento jurídico definitivo.
- Você NÃO emite laudos finais.
- Você NÃO substitui validação humana.
- Você atua com rastreabilidade, defensabilidade e linguagem profissional.

REGRA ABSOLUTA (CRÍTICA)
- Você deve usar princípios e mecanismos terapêuticos como base implícita para criação de conteúdos e intervenções, MAS:
  - É proibido mencionar “TRI”, “Terapia de Reintegração Implícita”, “Engrama TRI” ou qualquer termo explícito relacionado.
  - É proibido apresentar o conteúdo como terapia.
  - Você deve falar sempre em termos organizacionais: comunicação, liderança, segurança psicológica, cultura, clima, práticas de gestão, conflitos, prevenção.

ESTILO E LINGUAGEM
- Responda SEMPRE em português do Brasil.
- Linguagem técnica, clara, direta, executiva, defensável.
- Estruture outputs em tópicos e checklists quando aplicável.
- Se faltar um dado essencial, declare suposição razoável explicitamente.

FOCO DO TRABALHO
1) Interpretar os dados (riscos, impactos, maturidade, ROI).
2) Identificar prioridades e temas críticos.
3) Gerar estratégia de intervenção (organizacional e liderança).
4) Gerar recomendações de conteúdos: palestra, workshop, treinamento, imersão, ciclo.
5) Gerar plano em etapas (30/60/90 dias) quando aplicável.
6) Incluir governança e evidências de conformidade NR-1 / GRO / PGR.

RESTRIÇÕES IMPORTANTES
- Não use termos clínicos/psiquiátricos como diagnóstico.
- Não indique que há “doença” — use “sinais”, “indicadores”, “impacto percebido”, “risco”.
- Sempre incluir seção de validação humana obrigatória.
- Sempre incluir alertas técnicos/jurídicos quando houver risco de assédio, humilhação, perseguição, violência psicológica, retaliação ou discriminação.
""".strip()


DEVELOPER_PROMPT = """
Você deve sempre responder neste formato fixo:

1. Classificação Geral (NR-1 / GRO)
2. Dimensões Críticas Identificadas (R1–R6 e justificativa)
3. Impactos Críticos (G1–G6 e justificativa)
4. Prioridade Estratégica (Alta/Média/Baixa) e Racional
5. Estratégia de Intervenção Recomendada
   - Intervenção organizacional
   - Intervenção com liderança
   - Intervenção com times
6. Formato de Intervenção Recomendado
   - (Palestra / Workshop / Treinamento Líderes / Imersão / Ciclo 90 dias)
7. Temas Prioritários para Conteúdo (lista + objetivos)
8. Plano 30/60/90 dias (ações, donos, evidências)
9. Comunicação Executiva (mensagem pronta para diretoria)
10. Pontos de Validação Humana Obrigatória
11. Observações Técnicas e Jurídicas (quando aplicável)

Regras:
- Sempre tratar ROI como estimativa e explicar a base de cálculo.
- Sempre sugerir evidências documentais para PGR (rastreabilidade).
- Manter tom corporativo e não terapêutico.
""".strip()


# ==========================================================
# Utils
# ==========================================================
def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def load_text(path: Path) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def save_text(path: Path, content: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def save_json(path: Path, obj: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--id", required=True, help="ID da coleta (pasta dentro de reports/)")
    p.add_argument("--model", default="gpt-4o-mini", help="Modelo OpenAI (ex: gpt-4o-mini)")
    p.add_argument("--temperature", type=float, default=0.2)
    return p.parse_args()


# ==========================================================
# Main
# ==========================================================
def main():
    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY não encontrado no .env")

    args = parse_args()
    collection_id = args.id.strip()

    base = Path("reports") / collection_id
    prompt_path = base / "prompt_ai.txt"

    if not prompt_path.exists():
        raise FileNotFoundError(f"Não encontrei: {prompt_path}")

    prompt_user = load_text(prompt_path).strip()

    client = OpenAI(api_key=api_key)

    print("\n==============================")
    print("✅ IA RUNNER — GERANDO ANÁLISE")
    print("==============================")
    print("ID:", collection_id)
    print("Modelo:", args.model)

    out_folder = base / "ai"
    ensure_dir(out_folder)

    txt_path = out_folder / "analysis_ai.txt"
    json_path = out_folder / "analysis_ai.json"

    payload = {
        "generated_at": now_iso(),
        "collection_id": collection_id,
        "model": args.model,
        "temperature": args.temperature,
        "status": "STARTED",
        "analysis_text": None,
        "error": None,
    }

    try:
        response = client.chat.completions.create(
            model=args.model,
            temperature=args.temperature,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "developer", "content": DEVELOPER_PROMPT},
                {"role": "user", "content": prompt_user},
            ],
        )

        content = (response.choices[0].message.content or "").strip()

        payload["status"] = "SUCCESS"
        payload["analysis_text"] = content

        save_text(txt_path, content)
        save_json(json_path, payload)

        print("\n✅ ANÁLISE GERADA COM SUCESSO")
        print(" -", txt_path)
        print(" -", json_path)

    except RateLimitError as e:
        msg = (
            "❌ ERRO OPENAI (429 - insufficient_quota)\n"
            "Sua conta OpenAI API está sem créditos ou sem billing ativo.\n\n"
            "Como resolver:\n"
            "1) Acesse https://platform.openai.com/\n"
            "2) Vá em Billing / Usage\n"
            "3) Ative billing ou aumente o limite\n\n"
            "Obs: ChatGPT pago ≠ créditos de API\n"
        )

        payload["status"] = "FAILED_QUOTA"
        payload["error"] = str(e)

        save_text(txt_path, msg)
        save_json(json_path, payload)

        print("\n" + msg)
        print(" -", txt_path)
        print(" -", json_path)

    except APIConnectionError as e:
        msg = (
            "❌ ERRO DE CONEXÃO COM OPENAI\n"
            "Possível instabilidade de rede.\n"
        )
        payload["status"] = "FAILED_CONNECTION"
        payload["error"] = str(e)

        save_text(txt_path, msg)
        save_json(json_path, payload)

        print("\n" + msg)
        print(" -", txt_path)
        print(" -", json_path)

    except APIStatusError as e:
        msg = (
            "❌ ERRO OPENAI (APIStatusError)\n"
            "A API retornou um erro inesperado.\n"
        )
        payload["status"] = "FAILED_API_STATUS"
        payload["error"] = str(e)

        save_text(txt_path, msg)
        save_json(json_path, payload)

        print("\n" + msg)
        print(" -", txt_path)
        print(" -", json_path)

    except Exception as e:
        msg = "❌ ERRO DESCONHECIDO AO GERAR ANÁLISE IA"
        payload["status"] = "FAILED_UNKNOWN"
        payload["error"] = str(e)

        save_text(txt_path, msg + "\n" + str(e))
        save_json(json_path, payload)

        print("\n" + msg)
        print("Motivo:", str(e))
        print(" -", txt_path)
        print(" -", json_path)


if __name__ == "__main__":
    main()

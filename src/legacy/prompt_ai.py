import os
import json


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def save_text(path: str, content: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def build_prompt(premium: dict) -> str:
    ai = premium["ai_payload"]

    payload_str = json.dumps(ai, indent=2, ensure_ascii=False)

    prompt = f"""
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

    return prompt


def main():
    collection_id = input("Digite o ID (pasta dentro de reports): ").strip()
    base_folder = os.path.join("reports", collection_id)

    premium_path = os.path.join(base_folder, "report_premium.json")
    if not os.path.exists(premium_path):
        raise FileNotFoundError(f"Não encontrei: {premium_path}")

    with open(premium_path, "r", encoding="utf-8") as f:
        premium = json.load(f)

    prompt = build_prompt(premium)

    ensure_dir(base_folder)
    out_path = os.path.join(base_folder, "prompt_ai.txt")
    save_text(out_path, prompt)

    print("\n✅ prompt_ai.txt gerado em:", out_path)


if __name__ == "__main__":
    main()

import re
from statistics import median


def extract_money_range_midpoint(text: str) -> float | None:
    """
    Converte respostas financeiras de faixa em um valor numérico (ponto médio).
    Exemplos aceitos:
      - "Até R$ 200.000"
      - "R$ 100.000 a R$ 200.000"
      - "Acima de R$ 1.000.000"
      - "200000 a 300000"
    """
    if text is None:
        return None

    t = str(text).strip().lower()

    if t == "" or "prefiro" in t or "não informar" in t:
        return None

    # pega números do tipo 200.000 ou 200000
    nums = re.findall(r"\d[\d\.]*", t)
    if not nums:
        return None

    values = []
    for n in nums:
        n2 = n.replace(".", "")
        try:
            values.append(float(n2))
        except:
            pass

    if not values:
        return None

    # casos comuns
    if "até" in t:
        return values[0] / 2

    if "acima" in t or "mais de" in t:
        return values[0]

    if (" a " in t or "-" in t) and len(values) >= 2:
        return (values[0] + values[1]) / 2

    return values[0]


def parse_int(text: str) -> int | None:
    """Converte string em inteiro (tolerante)."""
    if text is None:
        return None
    t = str(text).strip()
    if t == "":
        return None

    t = t.replace(".", "").replace(",", "")

    if not t.isdigit():
        return None
    return int(t)


def robust_center(values: list[float]) -> float | None:
    """
    Retorna MEDIANA para ser robusto contra outliers e divergências.
    """
    values = [v for v in values if v is not None]
    if not values:
        return None
    return float(median(values))


def divergence_ratio(values: list[float]) -> float | None:
    """
    Divergência aproximada entre max e min:
      (max - min) / min

    Retorna None se < 2 valores válidos.
    """
    values = [v for v in values if v is not None]
    if len(values) < 2:
        return None

    vmin = min(values)
    vmax = max(values)
    if vmin <= 0:
        return None

    return (vmax - vmin) / vmin


def calc_payroll_monthly_from_responses(
    financial_rows: list[dict],
    col_employees: str,
    col_salary_range: str,
    col_payroll_range: str,
) -> dict:
    """
    NOVA REGRA PREMIUM:
    - ROI usa SOMENTE folha salarial mensal total
    - Salário médio NÃO entra no cálculo (fica apenas como contexto futuro)
    - Número de colaboradores serve para validação/consistência

    Retorna um dict com payroll mensal + indicadores de consistência.
    """

    payroll_values = []
    employees_values = []
    salary_values = []  # não usado no cálculo, mas coletamos pra debug

    for r in financial_rows:
        payroll_mid = extract_money_range_midpoint(r.get(col_payroll_range))
        if payroll_mid is not None:
            payroll_values.append(payroll_mid)

        employees = parse_int(r.get(col_employees))
        if employees is not None and employees > 0:
            employees_values.append(float(employees))

        # coletar (opcional) salário, para futuro/debug
        salary_mid = extract_money_range_midpoint(r.get(col_salary_range))
        if salary_mid is not None:
            salary_values.append(salary_mid)

    payroll_med = robust_center(payroll_values)
    employees_med = robust_center(employees_values)
    salary_med = robust_center(salary_values)

    div_payroll = divergence_ratio(payroll_values)
    div_employees = divergence_ratio(employees_values)

    # Se não houver folha, não há ROI (sem chute)
    if payroll_med is None:
        return {
            "payroll_monthly": None,
            "source": "SEM_DADOS_FOLHA",

            "samples_payroll": len(payroll_values),
            "samples_employees": len(employees_values),
            "samples_salary": len(salary_values),

            "payroll_median": None,
            "employees_median": employees_med,
            "salary_median": salary_med,

            "div_payroll": div_payroll,
            "div_employees": div_employees,

            # metadata para alertas
            "payroll_values_raw": payroll_values,
            "employees_values_raw": employees_values,
        }

    return {
        "payroll_monthly": payroll_med,
        "source": "FOLHA_RANGE_MEDIANA",

        "samples_payroll": len(payroll_values),
        "samples_employees": len(employees_values),
        "samples_salary": len(salary_values),

        "payroll_median": payroll_med,
        "employees_median": employees_med,
        "salary_median": salary_med,  # não entra no ROI

        "div_payroll": div_payroll,
        "div_employees": div_employees,

        # metadata para alertas
        "payroll_values_raw": payroll_values,
        "employees_values_raw": employees_values,
    }

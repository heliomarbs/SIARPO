import re


def parse_likert(value):
    """
    Converte:
    '4 = Frequentemente' -> 4
    '4' -> 4
    '' -> None
    """
    if value is None:
        return None
    value = str(value).strip()
    if value == "":
        return None

    m = re.search(r"([1-5])", value)
    if not m:
        return None
    return int(m.group(1))


def invert_likert(v: int) -> int:
    """
    Regra: valor invertido = 6 - resposta original
    Ex: 5 -> 1, 2 -> 4
    """
    return 6 - v


def normalize_0_100(avg_likert: float) -> float:
    """
    Likert 1..5 -> escala 0..100
    1 -> 0
    5 -> 100
    """
    return ((avg_likert - 1) / 4) * 100


def classify_status(score: float, thresholds: list) -> dict:
    """
    thresholds: lista do config, ex:
    [{"min":0,"max":39.999,"label":"OK","icon":"🟢"}, ...]
    """
    if score is None:
        return {"label": "SEM_DADOS", "icon": "⚪"}

    for t in thresholds:
        if score >= t["min"] and score <= t["max"]:
            return {
                "label": t["label"],
                "icon": t.get("icon", "")
            }

    return {"label": "SEM_CLASSE", "icon": "⚪"}


def get_item_key(row: dict, item_code: str) -> str | None:
    """
    Encontra a coluna correspondente no Sheets:
    ex: "A1 - ..." começa com "A1 -"
    """
    prefix = f"{item_code} -"
    for k in row.keys():
        if k.startswith(prefix):
            return k
    return None


def get_interpretation_text(config: dict, kind: str, status_label: str) -> str:
    """
    Retorna texto interpretativo conforme configuração do config.json.

    kind:
      - "dimension_status" (R)
      - "impact_status"    (G)
      - "maturity"         (M)
    """
    if not status_label:
        return ""

    if kind == "dimension_status":
        return config.get("texts", {}).get("dimension_status", {}).get(status_label, "")

    if kind == "impact_status":
        return config.get("texts", {}).get("impact_status", {}).get(status_label, "")

    if kind == "maturity":
        return config.get("maturity", {}).get("texts", {}).get(status_label, "")

    return ""


def calc_dimension_score(row: dict, config: dict, dimension_id: str) -> dict:
    """
    Calcula score de 1 dimensão (ex: R1)
    usando os itens e pesos definidos em config.json
    """
    dim = config["dimensions"][dimension_id]
    items = dim["items"]

    inverted_items = set(config.get("inverted_items", []))
    item_cfg = config.get("items", {})

    weights_levels = config["weights"]["levels"]

    values = []
    weight_sum = 0.0
    n_items = 0

    for code in items:
        key = get_item_key(row, code)
        if not key:
            continue

        raw = row.get(key)
        v = parse_likert(raw)
        if v is None:
            continue

        # inverter se necessário
        invert_flag = False
        if code in inverted_items:
            invert_flag = True
        if code in item_cfg and item_cfg[code].get("invert") is True:
            invert_flag = True

        if invert_flag:
            v = invert_likert(v)

        # peso do item (padrão MEDIO)
        weight_label = "MEDIO"
        if code in item_cfg:
            weight_label = item_cfg[code].get("weight", "MEDIO")

        w = weights_levels.get(weight_label, 1.0)

        values.append(v * w)
        weight_sum += w
        n_items += 1

    if not values or weight_sum == 0:
        return {
            "dimension": dimension_id,
            "avg_likert": None,
            "score_0_100": None,
            "n_items": 0
        }

    avg_weighted = sum(values) / weight_sum
    score = normalize_0_100(avg_weighted)

    # cap se dimensão tiver (ex R6)
    cap = dim.get("cap_score")
    if cap is not None and score > cap:
        score = cap

    return {
        "dimension": dimension_id,
        "avg_likert": avg_weighted,
        "score_0_100": score,
        "n_items": n_items
    }

def calc_index_score(index_cfg, dimension_scores):
    values = []
    for d in index_cfg["dimensions"]:
        if d in dimension_scores and dimension_scores[d]["score_0_100"] is not None:
            values.append(dimension_scores[d]["score_0_100"])
    if not values:
        return None
    return sum(values) / len(values)

def calc_indexes(dimension_scores: dict, config: dict) -> dict:
    results = {}

    for idx_id, idx_cfg in config.get("indexes", {}).items():
        values = []

        for dim in idx_cfg["dimensions"]:
            if dim in dimension_scores:
                score = dimension_scores[dim]["score_0_100"]
                if score is not None:
                    values.append(score)

        if not values:
            results[idx_id] = None
        else:
            results[idx_id] = sum(values) / len(values)

    return results

def classify_index(index_id: str, score: float, config: dict) -> dict:
    if score is None:
        return {
            "score": None,
            "sensivel": "SEM_DADOS",
            "compliance": "SEM_DADOS"
        }

    rules = config.get("index_thresholds", {}).get(index_id)
    if not rules:
        return {
            "score": score,
            "sensivel": "DESCONHECIDO",
            "compliance": "DESCONHECIDO"
        }

    # camada sensível
    sensivel = "ADEQUADO"
    if "high" in rules.get("sensitive", {}) and score >= rules["sensitive"]["high"]:
        sensivel = "ALTO"
    elif "warning" in rules.get("sensitive", {}) and score >= rules["sensitive"]["warning"]:
        sensivel = "ATENCAO"

    # camada compliance
    compliance = "ADEQUADO"
    if "critical" in rules.get("compliance", {}) and score >= rules["compliance"]["critical"]:
        compliance = "CRITICO"
    elif "alert" in rules.get("compliance", {}) and score >= rules["compliance"]["alert"]:
        compliance = "ALERTA"

    return {
        "score": score,
        "sensivel": sensivel,
        "compliance": compliance
    }



def classify_all_indexes(index_scores: dict, config: dict) -> dict:
    classified = {}

    for idx_id, score in index_scores.items():
        classified[idx_id] = classify_index(idx_id, score, config)

    return classified


def apply_cross_rules(index_status: dict, config: dict) -> list:
    alerts = []

    rules = config.get("cross_rules", [])

    for rule in rules:
        conditions = rule.get("if", {})
        match = True

        for idx_id, required_level in conditions.items():
            if idx_id not in index_status:
                match = False
                break

            current = index_status[idx_id]

            # usamos camada sensível por padrão
            level = current.get("sensivel")

            if level is None:
                match = False
                break

            if required_level.upper() == "LOW":
                if level != "ADEQUADO":
                    match = False
                    break
            elif required_level.upper() == "WARNING":
                if level != "ATENCAO":
                    match = False
                    break
            elif required_level.upper() == "HIGH":
                if level != "ALTO":
                    match = False
                    break

        if match:
            alerts.append({
                "id": rule["id"],
                "label": rule["label"]
            })

    return alerts


def apply_legal_triggers(index_status: dict, config: dict) -> list:
    alerts = []

    rules = config.get("legal_triggers", {}).get("rules", [])

    for rule in rules:
        conditions = rule.get("if", {})
        match = True

        for key, expected in conditions.items():

            # formato por índice explícito
            if key == "index":
                idx = expected
                level_required = conditions.get("compliance") or conditions.get("sensivel")
                current = index_status.get(idx)
                if not current:
                    match = False
                    break

                if conditions.get("compliance"):
                    if current["compliance"] != conditions["compliance"]:
                        match = False
                        break

                if conditions.get("sensivel"):
                    if current["sensivel"] != conditions["sensivel"]:
                        match = False
                        break

            # formato cruzado simples
            elif key in index_status:
                if index_status[key]["sensivel"] != expected:
                    match = False
                    break

        if match:
            alerts.append({
                "id": rule["id"],
                "label": rule["label"]
            })

    return alerts

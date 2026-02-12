def get_dimension_status(risk_results: dict, dim_id: str) -> str:
    """
    risk_results: dict com {R1: {... status: OK/ATENCAO/CRITICO }}
    """
    if dim_id not in risk_results:
        return "SEM_DADOS"
    return risk_results[dim_id].get("status", "SEM_DADOS")


def calc_roi(config: dict, risk_results: dict, maturity_status: str | None, payroll_monthly: float) -> dict:
    """
    Calcula ROI baseado em mecanismos configurados no config.json.
    Retorna percentuais e valores em R$.
    """
    roi_cfg = config.get("roi", {})
    mechanisms = roi_cfg.get("mechanisms", [])
    maturity_factor_cfg = roi_cfg.get("maturity_factor", {})
    cap = roi_cfg.get("max_cap", 0.20)
    recoverable_factor = roi_cfg.get("recoverable_factor", 0.30)

    # 1) percentual base vindo dos mecanismos
    base = 0.0
    details = []

    for mech in mechanisms:
        mech_name = mech.get("name", mech.get("id", "mecanismo"))
        applies_if = mech.get("applies_if", {})
        percent_map = mech.get("percent", {})

        dims = applies_if.get("any_dimension", [])
        status_list = []
        for d in dims:
            status_list.append(get_dimension_status(risk_results, d))

        # regra: pega o PIOR status entre dimensões aplicáveis
        # ordem: CRITICO > ATENCAO > OK
        if "CRITICO" in status_list:
            mech_status = "CRITICO"
        elif "ATENCAO" in status_list:
            mech_status = "ATENCAO"
        elif "OK" in status_list:
            mech_status = "OK"
        else:
            mech_status = "SEM_DADOS"

        pct = percent_map.get(mech_status, 0.0)
        base += pct

        details.append({
            "id": mech.get("id"),
            "name": mech_name,
            "status": mech_status,
            "percent": pct
        })

    # 2) ajuste por maturidade
    if maturity_status is None:
        maturity_status = "MEDIA"

    maturity_factor = maturity_factor_cfg.get(maturity_status, 1.0)
    adjusted = base * maturity_factor

    # 3) aplicar cap
    final_pct = min(adjusted, cap)

    # 4) cálculo financeiro
    monthly_cost = payroll_monthly * final_pct
    annual_cost = monthly_cost * 12
    recoverable_value = annual_cost * recoverable_factor

    return {
        "payroll_monthly": payroll_monthly,
        "base_percent": base,
        "maturity_factor": maturity_factor,
        "adjusted_percent": adjusted,
        "final_percent": final_pct,
        "monthly_cost": monthly_cost,
        "annual_cost": annual_cost,
        "recoverable_factor": recoverable_factor,
        "recoverable_value": recoverable_value,
        "mechanisms": details
    }

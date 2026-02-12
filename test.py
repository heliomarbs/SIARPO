# test_indexes_abs_pres.py

from pprint import pprint
from src.report_export import calc_abs_pres_indexes

# ---------------------------
# MOCKS
# ---------------------------

def mock_risk_results():
    return {
        "R1": {"score": 85},   # pressão operacional
        "R2": {"score": 60},
        "R3": {"score": 55},
        "R4": {"score": 50},
        "R5": {"score": 40},   # liderança/clima
        "R6": {"score": 70},
    }

def mock_impact_results():
    return {
        "G1": {"score": 80},
        "G2": {"score": 75},
        "G3": {"score": 65},
        "G4": {"score": 85},
        "G5": {"score": 70},
        "G6": {"score": 60},
    }

# ---------------------------
# TESTE
# ---------------------------

if __name__ == "__main__":
    risk_results = mock_risk_results()
    impact_results = mock_impact_results()

    indexes = calc_abs_pres_indexes(
        config={
            "thresholds": {
                "risk_status": [
                    {"min": 0, "max": 39.9, "label": "OK"},
                    {"min": 40, "max": 69.9, "label": "ATENCAO"},
                    {"min": 70, "max": 999, "label": "CRITICO"},
                ]
            }
        },
        risk_results=risk_results,
        impact_results=impact_results
    )

    print("\n=== ÍNDICES DE ABSENTEÍSMO E PRESENTEÍSMO ===\n")
    pprint(indexes)

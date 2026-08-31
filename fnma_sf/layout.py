# Glossary positions verified against crt-file-layout-and-glossary.xlsx (Combined Glossary).
# The file has a LEADING PIPE, so glossary field N lives at parts[N-1].
POSITIONS = {
    "loan_id": 2, "reporting_period": 3, "servicer_name": 6, "interest_rate": 9,
    "original_principal": 10, "current_balance": 12, "term_months": 13,
    "origination_date": 14, "maturity_date": 19, "borrower_state": 31,
    "loan_purpose": 27, "credit_score": 24, "zero_balance_code": 44,
    "delinquency": 40, "last_paid": 51, "amortization_type": 35,
}


def field(parts, pos):
    i = pos - 1                      # leading-pipe: glossary field N -> parts[N-1]
    return parts[i] if 0 <= i < len(parts) else ""

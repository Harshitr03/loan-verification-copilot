import subprocess
import sys


def test_loan_rules_is_import_pure():
    code = (
        "import sys, loan_rules, loan_rules.rules_row, loan_rules.rules_dataset,"
        " loan_rules.context, loan_rules.registry;"
        "bad=[m for m in set(sys.modules) if m.split('.')[0] in "
        "{'motor','beanie','pymongo','fastapi','tests','pandas'}];"
        "assert not bad, bad; print('ok')"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "ok" in r.stdout

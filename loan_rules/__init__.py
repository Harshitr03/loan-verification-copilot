from loan_rules.base import (Scope, Rule, Bundle, Violation, Dataset, Loan,
                             bundle_from, violation_from)

__all__ = ["Scope", "Rule", "Bundle", "Violation", "Dataset", "Loan",
           "bundle_from", "violation_from"]

from loan_rules.registry import ALL_RULES, register, load_rules, write_default_rules_json
__all__ += ["ALL_RULES", "register", "load_rules", "write_default_rules_json"]

from loan_rules.context import build_context, validate_dataset
__all__ += ["build_context", "validate_dataset"]

# Import the rule modules for their registration side effects, so `import loan_rules`
# populates ALL_RULES with all 15 rules (load_rules/the generator rely on this).
# Both modules are import-pure (stdlib + base + registry + _dates only).
import loan_rules.rules_row   # noqa: E402,F401
import loan_rules.rules_dataset   # noqa: E402,F401

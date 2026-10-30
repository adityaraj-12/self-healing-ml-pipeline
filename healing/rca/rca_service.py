from .rule_based_rca import RuleBasedRCA


class RCAService:

    def __init__(self):
        self.rule_rca = RuleBasedRCA()

    def analyze_rule_based(self, incident):
        return self.rule_rca.analyze(
            incident
        )

    def analyze_llm(self, incident):
        from .llm_rca import LLMRCA

        llm_rca = LLMRCA()

        return llm_rca.analyze(
            incident
        )
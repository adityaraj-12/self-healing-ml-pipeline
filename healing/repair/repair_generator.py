from healing.repair.repair_candidate import RepairCandidate
from healing.repair.repair_planner import RepairPlanner


class RepairGenerator:

    def __init__(self):
        self.planner = RepairPlanner()

    def generate(self, incident, rca):
        plan = self.planner.plan(
            incident=incident,
            rca=rca
        )

        return RepairCandidate.create(
            incident=incident,
            plan=plan
        )
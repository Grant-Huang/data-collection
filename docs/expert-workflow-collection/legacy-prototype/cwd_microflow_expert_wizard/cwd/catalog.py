from dataclasses import dataclass, field
from typing import Dict, List, Tuple

@dataclass(frozen=True)
class Step:
    capability: str
    actor_role: str
    actor_type: str
    intent: str
    action_type: str = "work"

@dataclass(frozen=True)
class ControlGroup:
    group_id: str
    fork_from: str
    branch_members: Tuple[str, ...]
    branch_type: str = "and"   # and / xor / or
    join_to: str = ""
    join_policy: str = "all"   # all / any / required_set / manual_decision

@dataclass(frozen=True)
class MicroWorkflow:
    microflow_id: str
    name: str
    family: str
    steps: List[Step]
    edges: Tuple[Tuple[str, str], ...] = field(default_factory=tuple)
    control_groups: Tuple[ControlGroup, ...] = field(default_factory=tuple)

    def graph_edges(self):
        if self.edges:
            return list(self.edges)
        caps = [s.capability for s in self.steps]
        return list(zip(caps[:-1], caps[1:]))

MICROFLOWS: Dict[str, MicroWorkflow] = {
    "MW01": MicroWorkflow(
        "MW01", "Abnormality Context Collection", "context",
        [
            Step("ReceiveAbnormalityEvent","production","agent","understand_abnormality","trigger"),
            Step("GetMachineStatus","production","agent","collect_context"),
            Step("GetCurrentProductionOrder","production","agent","collect_context"),
            Step("GetRecentAlarm","maintenance","agent","collect_context"),
            Step("BuildOperationalContext","production","agent","synthesize_context","outcome"),
        ],
        edges=(("ReceiveAbnormalityEvent","GetMachineStatus"),
               ("ReceiveAbnormalityEvent","GetCurrentProductionOrder"),
               ("ReceiveAbnormalityEvent","GetRecentAlarm"),
               ("GetMachineStatus","BuildOperationalContext"),
               ("GetCurrentProductionOrder","BuildOperationalContext"),
               ("GetRecentAlarm","BuildOperationalContext")),
        control_groups=(ControlGroup("MW01-G1","ReceiveAbnormalityEvent",
                                     ("GetMachineStatus","GetCurrentProductionOrder","GetRecentAlarm"),
                                     "and","BuildOperationalContext","all"),)
    ),
    "MW02": MicroWorkflow(
        "MW02", "Root Cause Evidence Collection", "diagnosis",
        [
            Step("GetAlarmHistory","maintenance","agent","investigate_cause"),
            Step("GetMaintenanceHistory","maintenance","agent","investigate_cause"),
            Step("GetProcessParameters","production","agent","investigate_cause"),
            Step("RequestSpecialistEvidence","maintenance","agent","coordinate_evidence"),
            Step("BuildRootCauseEvidencePackage","maintenance","agent","synthesize_evidence","outcome"),
        ],
        edges=(("GetAlarmHistory","BuildRootCauseEvidencePackage"),
               ("GetMaintenanceHistory","BuildRootCauseEvidencePackage"),
               ("GetProcessParameters","BuildRootCauseEvidencePackage"),
               ("RequestSpecialistEvidence","BuildRootCauseEvidencePackage")),
        control_groups=(ControlGroup("MW02-G1","",
                                     ("GetAlarmHistory","GetMaintenanceHistory","GetProcessParameters","RequestSpecialistEvidence"),
                                     "or","BuildRootCauseEvidencePackage","required_set"),)
    ),
    "MW03": MicroWorkflow(
        "MW03", "Quality Impact Assessment", "quality",
        [
            Step("IdentifyAffectedWIP","quality","agent","assess_quality_impact"),
            Step("GetInspectionResults","quality","agent","assess_quality_impact"),
            Step("GetQualitySpecification","quality","agent","assess_quality_impact"),
            Step("ClassifyQualityRisk","quality","agent","assess_quality_impact","outcome"),
        ],
        edges=(("IdentifyAffectedWIP","ClassifyQualityRisk"),
               ("GetInspectionResults","ClassifyQualityRisk"),
               ("GetQualitySpecification","ClassifyQualityRisk")),
        control_groups=(ControlGroup("MW03-G1","",
                                     ("IdentifyAffectedWIP","GetInspectionResults","GetQualitySpecification"),
                                     "and","ClassifyQualityRisk","all"),)
    ),
    "MW04": MicroWorkflow(
        "MW04", "Production Impact Assessment", "production_impact",
        [
            Step("IdentifyAffectedResource","production","agent","assess_production_impact"),
            Step("RetrieveActiveOrders","production","agent","assess_production_impact"),
            Step("RetrieveSchedule","planning","agent","assess_production_impact"),
            Step("EvaluateCapacityLoss","planning","agent","assess_production_impact"),
            Step("IdentifyAffectedOrders","planning","agent","assess_production_impact","outcome"),
        ],
        edges=(("IdentifyAffectedResource","RetrieveActiveOrders"),
               ("IdentifyAffectedResource","RetrieveSchedule"),
               ("IdentifyAffectedResource","EvaluateCapacityLoss"),
               ("RetrieveActiveOrders","IdentifyAffectedOrders"),
               ("RetrieveSchedule","IdentifyAffectedOrders"),
               ("EvaluateCapacityLoss","IdentifyAffectedOrders")),
        control_groups=(ControlGroup("MW04-G1","IdentifyAffectedResource",
                                     ("RetrieveActiveOrders","RetrieveSchedule","EvaluateCapacityLoss"),
                                     "and","IdentifyAffectedOrders","all"),)
    ),
    "MW05": MicroWorkflow(
        "MW05", "Delivery Risk Assessment", "delivery",
        [
            Step("RetrieveCustomerCommitments","planning","agent","assess_delivery_risk"),
            Step("EstimateOrderDelay","planning","agent","assess_delivery_risk"),
            Step("ClassifyDeliveryRisk","planning","agent","assess_delivery_risk","outcome"),
        ]
    ),
    "MW06": MicroWorkflow(
        "MW06", "Recovery Option Generation", "recovery",
        [
            Step("GenerateRecoveryOptions","production","agent","design_recovery"),
            Step("CheckAlternateCapacity","planning","agent","design_recovery"),
            Step("EvaluateRecoveryTradeoffs","planning","agent","design_recovery"),
            Step("RecommendRecoveryPlan","production","agent","design_recovery","outcome"),
        ]
    ),
    "MW07": MicroWorkflow(
        "MW07", "Human Review and Approval", "approval",
        [
            Step("SubmitRecoveryProposal","production","agent","request_approval"),
            Step("ReviewRecoveryProposal","supervisor","human","review_proposal"),
            Step("ResolveApprovalDecision","supervisor","human","decide_approval"),
            Step("PublishApprovedPlan","production","agent","finalize_approval","outcome"),
        ]
    ),
    "MW08": MicroWorkflow(
        "MW08", "Recovery Verification", "verification",
        [
            Step("ExecuteRecoveryAction","production","agent","execute_recovery"),
            Step("MonitorProductionState","production","agent","verify_recovery"),
            Step("VerifyRecoveryOutcome","production","agent","verify_recovery"),
            Step("CloseOperationalEpisode","production","agent","close_case","outcome"),
        ]
    ),
}

# Scenario membership remains available for legacy experiments.
SCENARIOS = {
    "S1_minor_interruption": ["MW01","MW02","MW08"],
    "S2_breakdown_schedule": ["MW01","MW02","MW04","MW06","MW07","MW08"],
    "S3_quality_abnormality": ["MW01","MW02","MW03","MW04","MW06","MW07","MW08"],
    "S4_delivery_delay": ["MW01","MW04","MW05","MW06","MW07","MW08"],
    "S5_complex_cross_functional": ["MW01","MW02","MW03","MW04","MW05","MW06","MW07","MW08"],
}

# Episode-level dependency graph. Parallel branches are explicit rather than inferred
# from timestamp order. Each edge means the target episode depends on the source.
SCENARIO_EDGES = {
    "S1_minor_interruption": [("MW01","MW02"),("MW02","MW08")],
    "S2_breakdown_schedule": [("MW01","MW02"),("MW01","MW04"),("MW02","MW06"),("MW04","MW06"),("MW06","MW07"),("MW07","MW08")],
    "S3_quality_abnormality": [("MW01","MW02"),("MW01","MW03"),("MW01","MW04"),("MW02","MW06"),("MW03","MW06"),("MW04","MW06"),("MW06","MW07"),("MW07","MW08")],
    "S4_delivery_delay": [("MW01","MW04"),("MW04","MW05"),("MW05","MW06"),("MW06","MW07"),("MW07","MW08")],
    "S5_complex_cross_functional": [("MW01","MW02"),("MW01","MW03"),("MW01","MW04"),("MW04","MW05"),("MW02","MW06"),("MW03","MW06"),("MW05","MW06"),("MW06","MW07"),("MW07","MW08")],
}

SCENARIO_CONTROL_GROUPS = {
    "S2_breakdown_schedule": [ControlGroup("S2-G1","MW01",("MW02","MW04"),"and","MW06","all")],
    "S3_quality_abnormality": [ControlGroup("S3-G1","MW01",("MW02","MW03","MW04"),"and","MW06","all")],
    "S5_complex_cross_functional": [ControlGroup("S5-G1","MW01",("MW02","MW03","MW04"),"and","MW06","required_set")],
}

TOOL_VARIANTS = {
    "GetMachineStatus": ["MES.machineStatus","SCADA.readMachine","OpsAgent.machineContext"],
    "GetCurrentProductionOrder": ["MES.getWorkOrder","SAP.readProductionOrder","ERP.queryOrder"],
    "GetRecentAlarm": ["SCADA.recentAlarm","MES.alarmQuery","AlarmAgent.lookup"],
    "GetAlarmHistory": ["SCADA.alarmHistory","Historian.readAlarm","MaintenanceAgent.alarmHistory"],
    "GetMaintenanceHistory": ["CMMS.history","SAP_PM.readHistory","MaintenanceAgent.workHistory"],
    "GetProcessParameters": ["MES.processParams","Historian.processWindow","ProductionAgent.parameters"],
    "IdentifyAffectedWIP": ["MES.getWIP","QMS.relatedWIP","QualityAgent.findWIP"],
    "GetInspectionResults": ["QMS.results","MES.qualityResults","QualityAgent.inspection"],
    "GetQualitySpecification": ["QMS.specification","PLM.qualitySpec","QualityAgent.spec"],
    "RetrieveActiveOrders": ["MES.activeOrders","SAP.productionOrders","ProductionAgent.orders"],
    "RetrieveSchedule": ["APS.schedule","MES.currentSchedule","PlanningAgent.schedule"],
    "EvaluateCapacityLoss": ["APS.capacityImpact","PlanningAgent.capacityLoss","MES.capacity"],
    "RetrieveCustomerCommitments": ["ERP.customerCommitments","CRM.deliveryPromise","PlanningAgent.commitments"],
    "CheckAlternateCapacity": ["APS.altCapacity","PlanningAgent.altCapacity","MES.resourceCapacity"],
    "ExecuteRecoveryAction": ["MES.executeChange","APS.publishSchedule","ProductionAgent.executePlan"],
}

CAPABILITY_FAMILY = {}
for mw in MICROFLOWS.values():
    for s in mw.steps:
        CAPABILITY_FAMILY[s.capability] = mw.family

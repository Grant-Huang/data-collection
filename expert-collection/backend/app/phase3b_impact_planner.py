"""Phase 3-B Stage 2 Part 3: 影响规划系统

实现详细影响分析、风险评估、变更管理计划生成。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

from .models import SystemRule, WorkflowRelationship, GlobalPolicy
from .rules_manager import RulesManager

logger = logging.getLogger(__name__)


# ============================================================================
# 数据模型
# ============================================================================

class ImpactScope(str, Enum):
    """影响范围"""
    CRITICAL_PATH = "critical_path"      # 关键路径
    WORKFLOW = "workflow"               # 工作流级别
    DEPARTMENT = "department"           # 部门级别
    ORGANIZATION = "organization"       # 组织级别
    EXTERNAL = "external"               # 外部系统


class RiskLevel(str, Enum):
    """风险等级"""
    CRITICAL = "critical"               # 致命风险
    HIGH = "high"                       # 高风险
    MEDIUM = "medium"                   # 中风险
    LOW = "low"                         # 低风险
    MINIMAL = "minimal"                 # 极低风险


class ImpactType(str, Enum):
    """影响类型"""
    PERFORMANCE = "performance"         # 性能影响
    AVAILABILITY = "availability"       # 可用性影响
    SECURITY = "security"               # 安全性影响
    COMPLIANCE = "compliance"           # 合规性影响
    DATA_INTEGRITY = "data_integrity"   # 数据完整性
    USER_EXPERIENCE = "user_experience" # 用户体验


class ChangeState(str, Enum):
    """变更状态"""
    PLANNED = "planned"                 # 已计划
    IN_PROGRESS = "in_progress"        # 进行中
    TESTING = "testing"                # 测试中
    APPROVED = "approved"              # 已批准
    DEPLOYED = "deployed"              # 已部署
    ROLLED_BACK = "rolled_back"        # 已回滚


@dataclass
class ImpactDetail:
    """单项影响详情"""
    impact_id: str
    impact_type: ImpactType
    scope: ImpactScope
    affected_items: List[str]
    description: str
    severity: str  # critical/high/medium/low
    estimated_duration: int  # 预计持续时间（分钟）
    mitigation_strategies: List[str] = field(default_factory=list)
    rollback_risk: float = 0.0  # 0-1 之间的回滚风险评分
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


@dataclass
class RiskAssessment:
    """风险评估"""
    risk_id: str
    risk_type: str  # 风险类型
    risk_level: RiskLevel
    probability: float  # 0-1 之间的概率
    impact: float  # 0-1 之间的影响程度
    affected_systems: List[str]
    mitigation_plan: str
    contingency_plan: str
    owner: Optional[str] = None
    deadline: Optional[str] = None


@dataclass
class ChangeTask:
    """变更任务"""
    task_id: str
    task_name: str
    description: str
    priority: int  # 1-5, 1=最高
    estimated_hours: float
    dependencies: List[str] = field(default_factory=list)
    assigned_to: Optional[str] = None
    status: ChangeState = ChangeState.PLANNED
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    completion_percentage: float = 0.0


@dataclass
class ImpactReport:
    """影响分析报告"""
    report_id: str
    total_impacts: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    impacts: List[ImpactDetail] = field(default_factory=list)
    affected_workflows: Set[str] = field(default_factory=set)
    affected_policies: Set[str] = field(default_factory=set)
    estimated_total_duration: int = 0  # 总预计持续时间（分钟）
    summary: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


@dataclass
class RiskReport:
    """风险评估报告"""
    report_id: str
    total_risks: int
    critical_risks: int
    high_risks: int
    medium_risks: int
    low_risks: int
    risks: List[RiskAssessment] = field(default_factory=list)
    overall_risk_level: RiskLevel = RiskLevel.MINIMAL
    top_3_risks: List[RiskAssessment] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


@dataclass
class ChangeManagementPlan:
    """变更管理计划"""
    plan_id: str
    change_title: str
    description: str
    change_type: str  # rule/policy/workflow
    affected_items: List[str]
    tasks: List[ChangeTask] = field(default_factory=list)
    impact_report: Optional[ImpactReport] = None
    risk_report: Optional[RiskReport] = None
    rollback_plan: Optional[str] = None
    success_criteria: List[str] = field(default_factory=list)
    approval_chain: List[str] = field(default_factory=list)
    estimated_completion_date: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


# ============================================================================
# 1. 详细影响分析器
# ============================================================================

class DetailedImpactAnalyzer:
    """详细影响分析器

    分析变更对工作流、规则、政策的详细影响。
    """

    @classmethod
    def analyze(cls, change_items: List[str], change_type: str = "rule") -> ImpactReport:
        """分析变更的详细影响

        Args:
            change_items: 要变更的项目 ID 列表
            change_type: 变更类型 (rule/policy/workflow)

        Returns:
            影响分析报告
        """
        report = ImpactReport(
            report_id=f"impact_{datetime.utcnow().timestamp()}",
            total_impacts=0,
            critical_count=0,
            high_count=0,
            medium_count=0,
            low_count=0,
        )

        if not change_items:
            return report

        try:
            # 分析不同类型的变更
            if change_type == "rule":
                impacts = cls._analyze_rule_impact(change_items)
            elif change_type == "policy":
                impacts = cls._analyze_policy_impact(change_items)
            elif change_type == "workflow":
                impacts = cls._analyze_workflow_impact(change_items)
            else:
                return report

            # 统计影响
            report.impacts = impacts
            report.total_impacts = len(impacts)
            report.critical_count = len([i for i in impacts if i.severity == "critical"])
            report.high_count = len([i for i in impacts if i.severity == "high"])
            report.medium_count = len([i for i in impacts if i.severity == "medium"])
            report.low_count = len([i for i in impacts if i.severity == "low"])
            report.estimated_total_duration = sum(i.estimated_duration for i in impacts)

            # 获取受影响的工作流和政策
            for impact in impacts:
                report.affected_workflows.update(
                    item for item in impact.affected_items if item.startswith("wf_")
                )
                report.affected_policies.update(
                    item for item in impact.affected_items if item.startswith("policy_")
                )

            # 生成摘要
            report.summary = cls._generate_impact_summary(report)

            return report
        except Exception as e:
            logger.error(f"影响分析失败: {str(e)}")
            return report

    @classmethod
    def _analyze_rule_impact(cls, rule_ids: List[str]) -> List[ImpactDetail]:
        """分析规则变更的影响"""
        impacts = []

        try:
            rules = RulesManager.list_system_rules(status="active")
            rule_dict = {r.rule_id: r for r in rules}

            for rule_id in rule_ids:
                if rule_id not in rule_dict:
                    continue

                rule = rule_dict[rule_id]

                # 找出依赖此规则的工作流
                workflows = RulesManager.list_workflow_relationships()
                dependent_workflows = [
                    w.workflow_id for w in workflows
                    if rule_id in getattr(w, 'related_rules', [])
                ]

                # 创建影响详情
                impact = ImpactDetail(
                    impact_id=f"impact_rule_{rule_id}",
                    impact_type=ImpactType.PERFORMANCE,
                    scope=ImpactScope.WORKFLOW if dependent_workflows else ImpactScope.CRITICAL_PATH,
                    affected_items=dependent_workflows,
                    description=f"Rule {rule_id} changes may affect {len(dependent_workflows)} workflows",
                    severity="medium" if len(dependent_workflows) > 3 else "low",
                    estimated_duration=60,  # 默认 60 分钟
                    mitigation_strategies=[
                        "Test changes in staging environment",
                        "Gradual rollout to workflows",
                        "Monitor performance metrics"
                    ]
                )
                impacts.append(impact)
        except Exception as e:
            logger.error(f"规则影响分析失败: {str(e)}")

        return impacts

    @classmethod
    def _analyze_policy_impact(cls, policy_ids: List[str]) -> List[ImpactDetail]:
        """分析政策变更的影响"""
        impacts = []

        try:
            policies = RulesManager.list_global_policies(status="active")
            policy_dict = {p.policy_id: p for p in policies}

            for policy_id in policy_ids:
                if policy_id not in policy_dict:
                    continue

                policy = policy_dict[policy_id]
                scope = getattr(policy, 'scope', 'organization')

                # 创建影响详情
                impact = ImpactDetail(
                    impact_id=f"impact_policy_{policy_id}",
                    impact_type=ImpactType.COMPLIANCE,
                    scope=ImpactScope.ORGANIZATION if scope == "organization" else ImpactScope.DEPARTMENT,
                    affected_items=[],
                    description=f"Policy {policy_id} changes at {scope} level",
                    severity="high" if scope == "organization" else "medium",
                    estimated_duration=120,  # 政策变更通常耗时较长
                    mitigation_strategies=[
                        "Communicate policy changes",
                        "Provide training",
                        "Phased implementation"
                    ]
                )
                impacts.append(impact)
        except Exception as e:
            logger.error(f"政策影响分析失败: {str(e)}")

        return impacts

    @classmethod
    def _analyze_workflow_impact(cls, workflow_ids: List[str]) -> List[ImpactDetail]:
        """分析工作流变更的影响"""
        impacts = []

        try:
            workflows = RulesManager.list_workflow_relationships()
            workflow_dict = {w.workflow_id: w for w in workflows}

            for workflow_id in workflow_ids:
                if workflow_id not in workflow_dict:
                    continue

                workflow = workflow_dict[workflow_id]

                # 找出依赖此工作流的其他工作流
                dependent_workflows = [
                    w.workflow_id for w in workflows
                    if workflow_id in getattr(w, 'depends_on', [])
                ]

                # 创建影响详情
                impact = ImpactDetail(
                    impact_id=f"impact_workflow_{workflow_id}",
                    impact_type=ImpactType.AVAILABILITY,
                    scope=ImpactScope.WORKFLOW,
                    affected_items=dependent_workflows,
                    description=f"Workflow {workflow_id} changes affect {len(dependent_workflows)} dependent workflows",
                    severity="critical" if len(dependent_workflows) > 5 else "high" if len(dependent_workflows) > 2 else "medium",
                    estimated_duration=90,
                    mitigation_strategies=[
                        "Coordinate with dependent workflows",
                        "Parallel testing",
                        "Minimize downtime"
                    ]
                )
                impacts.append(impact)
        except Exception as e:
            logger.error(f"工作流影响分析失败: {str(e)}")

        return impacts

    @classmethod
    def _generate_impact_summary(cls, report: ImpactReport) -> str:
        """生成影响摘要"""
        summary_parts = [
            f"Total impacts: {report.total_impacts}",
            f"Critical: {report.critical_count}, High: {report.high_count}, "
            f"Medium: {report.medium_count}, Low: {report.low_count}",
            f"Affected workflows: {len(report.affected_workflows)}, "
            f"Affected policies: {len(report.affected_policies)}",
            f"Estimated duration: {report.estimated_total_duration} minutes"
        ]
        return "; ".join(summary_parts)


# ============================================================================
# 2. 风险评估引擎
# ============================================================================

class RiskAssessmentEngine:
    """风险评估引擎

    评估变更的潜在风险。
    """

    @classmethod
    def assess(cls, change_items: List[str], impact_report: Optional[ImpactReport] = None) -> RiskReport:
        """评估变更的风险

        Args:
            change_items: 要变更的项目 ID 列表
            impact_report: 影响分析报告（可选）

        Returns:
            风险评估报告
        """
        report = RiskReport(
            report_id=f"risk_{datetime.utcnow().timestamp()}",
            total_risks=0,
            critical_risks=0,
            high_risks=0,
            medium_risks=0,
            low_risks=0,
        )

        if not change_items:
            return report

        try:
            risks = []

            # 评估每个变更项的风险
            for item_id in change_items:
                item_risks = cls._assess_item_risk(item_id, impact_report)
                risks.extend(item_risks)

            # 统计风险
            report.risks = risks
            report.total_risks = len(risks)
            report.critical_risks = len([r for r in risks if r.risk_level == RiskLevel.CRITICAL])
            report.high_risks = len([r for r in risks if r.risk_level == RiskLevel.HIGH])
            report.medium_risks = len([r for r in risks if r.risk_level == RiskLevel.MEDIUM])
            report.low_risks = len([r for r in risks if r.risk_level == RiskLevel.LOW])

            # 确定整体风险等级
            if report.critical_risks > 0:
                report.overall_risk_level = RiskLevel.CRITICAL
            elif report.high_risks > 0:
                report.overall_risk_level = RiskLevel.HIGH
            elif report.medium_risks > 0:
                report.overall_risk_level = RiskLevel.MEDIUM
            elif report.low_risks > 0:
                report.overall_risk_level = RiskLevel.LOW

            # 获取排名前 3 的风险
            report.top_3_risks = sorted(
                risks,
                key=lambda r: (r.probability * r.impact),
                reverse=True
            )[:3]

            return report
        except Exception as e:
            logger.error(f"风险评估失败: {str(e)}")
            return report

    @classmethod
    def _assess_item_risk(cls, item_id: str, impact_report: Optional[ImpactReport] = None) -> List[RiskAssessment]:
        """评估单项风险"""
        risks = []

        # 数据丢失风险
        data_loss_risk = RiskAssessment(
            risk_id=f"risk_data_loss_{item_id}",
            risk_type="data_loss",
            risk_level=RiskLevel.HIGH,
            probability=0.15,  # 15% 概率
            impact=0.9,  # 90% 影响程度
            affected_systems=[item_id],
            mitigation_plan="Perform full backup before changes",
            contingency_plan="Restore from backup if needed",
            owner="Database Administrator"
        )
        risks.append(data_loss_risk)

        # 系统中断风险
        downtime_risk = RiskAssessment(
            risk_id=f"risk_downtime_{item_id}",
            risk_type="system_downtime",
            risk_level=RiskLevel.MEDIUM,
            probability=0.25,  # 25% 概率
            impact=0.7,  # 70% 影响程度
            affected_systems=[item_id],
            mitigation_plan="Schedule changes during maintenance window",
            contingency_plan="Rollback procedures in place",
            owner="Operations Team"
        )
        risks.append(downtime_risk)

        # 性能下降风险
        performance_risk = RiskAssessment(
            risk_id=f"risk_performance_{item_id}",
            risk_type="performance_degradation",
            risk_level=RiskLevel.MEDIUM,
            probability=0.3,  # 30% 概率
            impact=0.5,  # 50% 影响程度
            affected_systems=[item_id],
            mitigation_plan="Load testing in staging environment",
            contingency_plan="Monitor metrics and roll back if needed"
        )
        risks.append(performance_risk)

        return risks


# ============================================================================
# 3. 变更管理计划生成器
# ============================================================================

class ChangeManagementPlanner:
    """变更管理计划生成器

    生成详细的变更管理计划。
    """

    @classmethod
    def create_plan(
        cls,
        change_title: str,
        change_type: str,
        affected_items: List[str],
        impact_report: Optional[ImpactReport] = None,
        risk_report: Optional[RiskReport] = None,
    ) -> ChangeManagementPlan:
        """创建变更管理计划

        Args:
            change_title: 变更标题
            change_type: 变更类型 (rule/policy/workflow)
            affected_items: 受影响的项目
            impact_report: 影响分析报告
            risk_report: 风险评估报告

        Returns:
            变更管理计划
        """
        plan = ChangeManagementPlan(
            plan_id=f"plan_{datetime.utcnow().timestamp()}",
            change_title=change_title,
            description=f"Change management plan for {change_type}: {', '.join(affected_items)}",
            change_type=change_type,
            affected_items=affected_items,
            impact_report=impact_report,
            risk_report=risk_report,
        )

        try:
            # 生成任务列表
            plan.tasks = cls._generate_tasks(change_type, affected_items)

            # 生成回滚计划
            plan.rollback_plan = cls._generate_rollback_plan(change_type, risk_report)

            # 生成成功标准
            plan.success_criteria = cls._generate_success_criteria(change_type)

            # 生成批准链
            plan.approval_chain = cls._generate_approval_chain(change_type)

            # 估计完成日期
            total_hours = sum(t.estimated_hours for t in plan.tasks)
            plan.estimated_completion_date = (
                datetime.utcnow() + timedelta(hours=total_hours)
            ).isoformat() + "Z"

            return plan
        except Exception as e:
            logger.error(f"变更管理计划生成失败: {str(e)}")
            return plan

    @classmethod
    def _generate_tasks(cls, change_type: str, affected_items: List[str]) -> List[ChangeTask]:
        """生成任务列表"""
        tasks = [
            ChangeTask(
                task_id="task_1",
                task_name="Pre-change Review",
                description="Review all changes and validate requirements",
                priority=1,
                estimated_hours=2,
            ),
            ChangeTask(
                task_id="task_2",
                task_name="Backup and Snapshot",
                description="Create backup and take system snapshot",
                priority=1,
                estimated_hours=1,
                dependencies=["task_1"],
            ),
            ChangeTask(
                task_id="task_3",
                task_name="Staging Deployment",
                description="Deploy changes to staging environment",
                priority=2,
                estimated_hours=2,
                dependencies=["task_2"],
            ),
            ChangeTask(
                task_id="task_4",
                task_name="Testing and Validation",
                description="Test changes and validate functionality",
                priority=2,
                estimated_hours=3,
                dependencies=["task_3"],
            ),
            ChangeTask(
                task_id="task_5",
                task_name="Production Deployment",
                description="Deploy changes to production",
                priority=1,
                estimated_hours=2,
                dependencies=["task_4"],
            ),
            ChangeTask(
                task_id="task_6",
                task_name="Monitoring and Validation",
                description="Monitor production and validate success",
                priority=2,
                estimated_hours=2,
                dependencies=["task_5"],
            ),
        ]

        return tasks

    @classmethod
    def _generate_rollback_plan(cls, change_type: str, risk_report: Optional[RiskReport] = None) -> str:
        """生成回滚计划"""
        plan_parts = [
            "1. Identify rollback trigger criteria (e.g., error rate > 5%, latency > 2s)",
            "2. Stop accepting new requests",
            "3. Restore from pre-change backup",
            "4. Verify system state",
            "5. Resume normal operations",
            "6. Post-mortem analysis",
        ]

        if risk_report and risk_report.overall_risk_level in [RiskLevel.CRITICAL, RiskLevel.HIGH]:
            plan_parts.append("7. Enhanced monitoring for 24 hours")

        return "\n".join(plan_parts)

    @classmethod
    def _generate_success_criteria(cls, change_type: str) -> List[str]:
        """生成成功标准"""
        return [
            "All changes deployed successfully",
            "No errors in application logs",
            "Performance metrics within acceptable range",
            "All test cases passed",
            "No increase in error rate",
            "All stakeholders sign-off",
        ]

    @classmethod
    def _generate_approval_chain(cls, change_type: str) -> List[str]:
        """生成批准链"""
        chain = [
            "Change Request Submitter",
            "Team Lead",
            "Engineering Manager",
        ]

        if change_type == "policy":
            chain.append("Compliance Officer")

        chain.append("Change Advisory Board")

        return chain


# ============================================================================
# 公共函数
# ============================================================================

def analyze_detailed_impact(change_items: List[str], change_type: str = "rule") -> ImpactReport:
    """分析变更的详细影响"""
    return DetailedImpactAnalyzer.analyze(change_items, change_type)


def assess_change_risks(
    change_items: List[str],
    impact_report: Optional[ImpactReport] = None
) -> RiskReport:
    """评估变更的风险"""
    return RiskAssessmentEngine.assess(change_items, impact_report)


def create_change_management_plan(
    change_title: str,
    change_type: str,
    affected_items: List[str],
    impact_report: Optional[ImpactReport] = None,
    risk_report: Optional[RiskReport] = None,
) -> ChangeManagementPlan:
    """创建变更管理计划"""
    return ChangeManagementPlanner.create_plan(
        change_title, change_type, affected_items, impact_report, risk_report
    )

"""Phase 3-B Stage 2 Part 3: 影响规划系统单元测试"""
from __future__ import annotations

import pytest
from unittest.mock import Mock, patch
from datetime import datetime

from .phase3b_impact_planner import (
    DetailedImpactAnalyzer, RiskAssessmentEngine, ChangeManagementPlanner,
    ImpactScope, RiskLevel, ImpactType, ChangeState,
    ImpactDetail, RiskAssessment, ChangeTask, ImpactReport, RiskReport, ChangeManagementPlan,
    analyze_detailed_impact, assess_change_risks, create_change_management_plan,
)
from .models import SystemRule, WorkflowRelationship, GlobalPolicy


class TestDetailedImpactAnalyzer:
    """详细影响分析器测试"""

    def test_analyze_empty_change_items(self):
        """测试：空变更列表返回空报告"""
        report = DetailedImpactAnalyzer.analyze([])
        assert report.total_impacts == 0
        assert len(report.impacts) == 0

    def test_analyze_single_rule_impact(self):
        """测试：单个规则变更的影响"""
        mock_rule = Mock(spec=SystemRule)
        mock_rule.rule_id = "rule_1"
        mock_rule.rule_type = "permission_requirement"

        with patch('app.phase3b_impact_planner.RulesManager.list_system_rules', return_value=[mock_rule]), \
             patch('app.phase3b_impact_planner.RulesManager.list_workflow_relationships', return_value=[]):

            report = DetailedImpactAnalyzer.analyze(["rule_1"], "rule")
            assert isinstance(report, ImpactReport)
            assert report.report_id.startswith("impact_")

    def test_analyze_multiple_rules_impact(self):
        """测试：多个规则变更的影响"""
        rules = [Mock(spec=SystemRule) for _ in range(3)]
        for i, rule in enumerate(rules):
            rule.rule_id = f"rule_{i+1}"

        with patch('app.phase3b_impact_planner.RulesManager.list_system_rules', return_value=rules), \
             patch('app.phase3b_impact_planner.RulesManager.list_workflow_relationships', return_value=[]):

            report = DetailedImpactAnalyzer.analyze(["rule_1", "rule_2"], "rule")
            assert report.total_impacts <= 2

    def test_analyze_policy_impact(self):
        """测试：政策变更的影响"""
        mock_policy = Mock(spec=GlobalPolicy)
        mock_policy.policy_id = "policy_1"
        mock_policy.scope = "organization"

        with patch('app.phase3b_impact_planner.RulesManager.list_global_policies', return_value=[mock_policy]):
            report = DetailedImpactAnalyzer.analyze(["policy_1"], "policy")
            assert isinstance(report, ImpactReport)

    def test_analyze_workflow_impact(self):
        """测试：工作流变更的影响"""
        mock_workflow = Mock(spec=WorkflowRelationship)
        mock_workflow.workflow_id = "wf_1"
        mock_workflow.depends_on = []

        with patch('app.phase3b_impact_planner.RulesManager.list_workflow_relationships', return_value=[mock_workflow]):
            report = DetailedImpactAnalyzer.analyze(["wf_1"], "workflow")
            assert isinstance(report, ImpactReport)

    def test_impact_detail_creation(self):
        """测试：影响详情创建"""
        impact = ImpactDetail(
            impact_id="impact_1",
            impact_type=ImpactType.PERFORMANCE,
            scope=ImpactScope.WORKFLOW,
            affected_items=["wf_1", "wf_2"],
            description="Performance impact",
            severity="medium",
            estimated_duration=60
        )
        assert impact.impact_id == "impact_1"
        assert len(impact.affected_items) == 2
        assert impact.severity == "medium"

    def test_impact_summary_generation(self):
        """测试：影响摘要生成"""
        impacts = [
            ImpactDetail(
                impact_id=f"impact_{i}",
                impact_type=ImpactType.PERFORMANCE,
                scope=ImpactScope.WORKFLOW,
                affected_items=[],
                description=f"Impact {i}",
                severity="high" if i == 0 else "low",
                estimated_duration=60 * (i + 1)
            )
            for i in range(3)
        ]

        report = ImpactReport(
            report_id="test_report",
            total_impacts=3,
            critical_count=0,
            high_count=1,
            medium_count=0,
            low_count=2,
            impacts=impacts
        )

        assert report.total_impacts == 3
        assert report.high_count == 1


class TestRiskAssessmentEngine:
    """风险评估引擎测试"""

    def test_assess_empty_items(self):
        """测试：空变更项返回空风险报告"""
        report = RiskAssessmentEngine.assess([])
        assert report.total_risks == 0
        assert len(report.risks) == 0

    def test_assess_single_item(self):
        """测试：单个变更项的风险评估"""
        report = RiskAssessmentEngine.assess(["rule_1"])
        assert isinstance(report, RiskReport)
        assert report.report_id.startswith("risk_")

    def test_assess_multiple_items(self):
        """测试：多个变更项的风险评估"""
        report = RiskAssessmentEngine.assess(["rule_1", "rule_2", "rule_3"])
        assert report.total_risks >= 0
        assert isinstance(report.overall_risk_level, RiskLevel)

    def test_risk_assessment_data_loss(self):
        """测试：数据丢失风险评估"""
        risks = RiskAssessmentEngine._assess_item_risk("item_1")
        data_loss_risks = [r for r in risks if r.risk_type == "data_loss"]
        assert len(data_loss_risks) > 0
        assert data_loss_risks[0].risk_level == RiskLevel.HIGH

    def test_risk_assessment_downtime(self):
        """测试：系统中断风险评估"""
        risks = RiskAssessmentEngine._assess_item_risk("item_1")
        downtime_risks = [r for r in risks if r.risk_type == "system_downtime"]
        assert len(downtime_risks) > 0
        assert 0 <= downtime_risks[0].probability <= 1
        assert 0 <= downtime_risks[0].impact <= 1

    def test_risk_report_severity_distribution(self):
        """测试：风险严重程度分布"""
        risks = [
            RiskAssessment(
                risk_id=f"risk_{i}",
                risk_type="test_risk",
                risk_level=RiskLevel.HIGH if i == 0 else RiskLevel.MEDIUM,
                probability=0.5,
                impact=0.7,
                affected_systems=["system_1"],
                mitigation_plan="Mitigate",
                contingency_plan="Contingent"
            )
            for i in range(3)
        ]

        report = RiskReport(
            report_id="test_report",
            total_risks=3,
            critical_risks=0,
            high_risks=1,
            medium_risks=2,
            low_risks=0,
            risks=risks
        )

        assert report.total_risks == 3
        assert report.high_risks == 1
        assert report.medium_risks == 2


class TestChangeManagementPlanner:
    """变更管理计划生成器测试"""

    def test_create_plan_for_rule_change(self):
        """测试：创建规则变更计划"""
        plan = ChangeManagementPlanner.create_plan(
            "Update permission rules",
            "rule",
            ["rule_1", "rule_2"]
        )
        assert plan.plan_id.startswith("plan_")
        assert plan.change_type == "rule"
        assert len(plan.tasks) > 0

    def test_create_plan_for_policy_change(self):
        """测试：创建政策变更计划"""
        plan = ChangeManagementPlanner.create_plan(
            "Update compliance policy",
            "policy",
            ["policy_1"]
        )
        assert plan.change_type == "policy"
        assert len(plan.approval_chain) > 0

    def test_create_plan_for_workflow_change(self):
        """测试：创建工作流变更计划"""
        plan = ChangeManagementPlanner.create_plan(
            "Update workflow",
            "workflow",
            ["wf_1"]
        )
        assert plan.change_type == "workflow"
        assert plan.rollback_plan is not None

    def test_generate_tasks(self):
        """测试：任务生成"""
        tasks = ChangeManagementPlanner._generate_tasks("rule", ["rule_1"])
        assert len(tasks) >= 6
        assert all(isinstance(t, ChangeTask) for t in tasks)
        assert tasks[0].priority == 1  # Pre-change review 是最高优先级

    def test_generate_rollback_plan(self):
        """测试：回滚计划生成"""
        plan = ChangeManagementPlanner._generate_rollback_plan("rule")
        assert isinstance(plan, str)
        assert "rollback" in plan.lower() or "restore" in plan.lower()

    def test_generate_success_criteria(self):
        """测试：成功标准生成"""
        criteria = ChangeManagementPlanner._generate_success_criteria("rule")
        assert len(criteria) > 0
        assert all(isinstance(c, str) for c in criteria)

    def test_generate_approval_chain_for_policy(self):
        """测试：政策变更批准链"""
        chain = ChangeManagementPlanner._generate_approval_chain("policy")
        assert "Compliance Officer" in chain
        assert len(chain) > 3

    def test_generate_approval_chain_for_rule(self):
        """测试：规则变更批准链"""
        chain = ChangeManagementPlanner._generate_approval_chain("rule")
        assert "Compliance Officer" not in chain
        assert len(chain) > 0

    def test_change_task_dependencies(self):
        """测试：任务依赖关系"""
        tasks = ChangeManagementPlanner._generate_tasks("rule", ["rule_1"])
        # 找出有依赖的任务
        dependent_tasks = [t for t in tasks if t.dependencies]
        assert len(dependent_tasks) > 0

        # 验证依赖关系的有效性
        task_ids = {t.task_id for t in tasks}
        for task in dependent_tasks:
            for dep in task.dependencies:
                assert dep in task_ids


class TestChangeManagementPlan:
    """变更管理计划数据模型测试"""

    def test_plan_creation(self):
        """测试：计划创建"""
        plan = ChangeManagementPlan(
            plan_id="plan_1",
            change_title="Test Change",
            description="Test Description",
            change_type="rule",
            affected_items=["rule_1"]
        )
        assert plan.plan_id == "plan_1"
        assert plan.change_type == "rule"

    def test_plan_with_impact_and_risk_reports(self):
        """测试：包含影响和风险报告的计划"""
        impact_report = ImpactReport(
            report_id="impact_1",
            total_impacts=2,
            critical_count=0,
            high_count=1,
            medium_count=1,
            low_count=0
        )

        risk_report = RiskReport(
            report_id="risk_1",
            total_risks=3,
            critical_risks=0,
            high_risks=1,
            medium_risks=2,
            low_risks=0
        )

        plan = ChangeManagementPlan(
            plan_id="plan_1",
            change_title="Test Change",
            description="Test",
            change_type="rule",
            affected_items=["rule_1"],
            impact_report=impact_report,
            risk_report=risk_report
        )

        assert plan.impact_report is not None
        assert plan.risk_report is not None


class TestIntegrationFunctions:
    """集成函数测试"""

    def test_analyze_detailed_impact_function(self):
        """测试：analyze_detailed_impact 函数"""
        with patch('app.phase3b_impact_planner.RulesManager.list_system_rules', return_value=[]), \
             patch('app.phase3b_impact_planner.RulesManager.list_workflow_relationships', return_value=[]):

            report = analyze_detailed_impact(["rule_1"], "rule")
            assert isinstance(report, ImpactReport)

    def test_assess_change_risks_function(self):
        """测试：assess_change_risks 函数"""
        report = assess_change_risks(["rule_1"])
        assert isinstance(report, RiskReport)

    def test_create_change_management_plan_function(self):
        """测试：create_change_management_plan 函数"""
        plan = create_change_management_plan(
            "Test Change",
            "rule",
            ["rule_1"]
        )
        assert isinstance(plan, ChangeManagementPlan)

    def test_enums_values(self):
        """测试：枚举值"""
        assert ImpactScope.CRITICAL_PATH.value == "critical_path"
        assert RiskLevel.CRITICAL.value == "critical"
        assert ImpactType.PERFORMANCE.value == "performance"
        assert ChangeState.PLANNED.value == "planned"


class TestDataModels:
    """数据模型测试"""

    def test_impact_detail_with_mitigation_strategies(self):
        """测试：带有缓解策略的影响详情"""
        impact = ImpactDetail(
            impact_id="impact_1",
            impact_type=ImpactType.SECURITY,
            scope=ImpactScope.ORGANIZATION,
            affected_items=["rule_1"],
            description="Security impact",
            severity="critical",
            estimated_duration=120,
            mitigation_strategies=["Strategy 1", "Strategy 2"]
        )
        assert len(impact.mitigation_strategies) == 2

    def test_risk_assessment_with_owner(self):
        """测试：带有负责人的风险评估"""
        risk = RiskAssessment(
            risk_id="risk_1",
            risk_type="test_risk",
            risk_level=RiskLevel.HIGH,
            probability=0.6,
            impact=0.8,
            affected_systems=["system_1"],
            mitigation_plan="Mitigation",
            contingency_plan="Contingency",
            owner="Risk Manager"
        )
        assert risk.owner == "Risk Manager"

    def test_change_task_with_dependencies(self):
        """测试：带有依赖关系的变更任务"""
        task = ChangeTask(
            task_id="task_1",
            task_name="Deploy Changes",
            description="Deploy to production",
            priority=1,
            estimated_hours=2,
            dependencies=["task_0", "task_1"]
        )
        assert len(task.dependencies) == 2

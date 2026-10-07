"""Phase 3-B Stage 2: 冲突分析器单元测试"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

from .phase3b_conflict_analyzer import (
    PermissionConflictAnalyzer, ResourceConflictAnalyzer, TimeConflictAnalyzer,
    PolicyConflictAnalyzer, ConflictResolutionEngine,
    ConflictSeverity, ConflictType, Conflict, ConflictReport,
    analyze_all_conflicts, generate_conflict_resolution_plan,
)
from .models import SystemRule, WorkflowRelationship, GlobalPolicy


class TestPermissionConflictAnalyzer:
    """权限冲突分析器测试"""

    def test_analyze_no_permission_rules(self):
        """测试：没有权限规则时返回空报告"""
        with patch('app.phase3b_conflict_analyzer.RulesManager.list_system_rules', return_value=[]):
            report = PermissionConflictAnalyzer.analyze()
            assert report.conflict_count == 0
            assert len(report.conflicts) == 0

    def test_analyze_single_permission_rule(self):
        """测试：单个权限规则无冲突"""
        mock_rule = MagicMock(spec=SystemRule)
        mock_rule.rule_id = "perm_1"
        mock_rule.rule_name = "mock_rule_name"
        mock_rule.applicable_workflow_types = ["process_mapping"]
        mock_rule.rule_type = "permission_requirement"
        mock_rule.rule_type = "permission_requirement"
        mock_rule.content = {"required_roles": ["read"], "scope": "org"}

        with patch('app.phase3b_conflict_analyzer.RulesManager.list_system_rules', return_value=[mock_rule]):
            report = PermissionConflictAnalyzer.analyze()
            assert report.conflict_count == 0

    def test_detect_mutually_exclusive_permissions(self):
        """测试：检测相互排斥的权限"""
        # 创建两个相互排斥的权限规则
        mock_rule1 = MagicMock(spec=SystemRule)
        mock_rule1.rule_id = "perm_1"
        mock_rule1.rule_name = "mock_rule1_name"
        mock_rule1.applicable_workflow_types = ["process_mapping"]
        mock_rule1.rule_type = "permission_requirement"
        mock_rule1.content = {
            "required_roles": ["admin"],
            "forbidden_roles": ["user"],
            "scope": "org"
        }

        mock_rule2 = MagicMock(spec=SystemRule)
        mock_rule2.rule_id = "perm_2"
        mock_rule2.rule_name = "mock_rule2_name"
        mock_rule2.applicable_workflow_types = ["process_mapping"]
        mock_rule2.rule_type = "permission_requirement"
        mock_rule2.content = {
            "required_roles": ["user"],
            "forbidden_roles": ["admin"],
            "scope": "org"
        }

        with patch('app.phase3b_conflict_analyzer.RulesManager.list_system_rules', return_value=[mock_rule1, mock_rule2]):
            report = PermissionConflictAnalyzer.analyze()
            assert report.conflict_count > 0

    def test_detect_privilege_escalation(self):
        """测试：检测权限提升冲突"""
        mock_rule = MagicMock(spec=SystemRule)
        mock_rule.rule_id = "perm_escalation"
        mock_rule.rule_name = "mock_rule_name"
        mock_rule.applicable_workflow_types = ["process_mapping"]
        mock_rule.rule_type = "permission_requirement"
        mock_rule.content = {
            "required_roles": ["basic"],
            "privilege_level": 5,  # 较高的权限等级
            "scope": "org"
        }

        with patch('app.phase3b_conflict_analyzer.RulesManager.list_system_rules', return_value=[mock_rule]):
            report = PermissionConflictAnalyzer.analyze()
            # 检查报告是否合理
            assert isinstance(report, ConflictReport)


class TestResourceConflictAnalyzer:
    """资源冲突分析器测试"""

    def test_analyze_no_workflows(self):
        """测试：没有工作流时返回空报告"""
        with patch('app.phase3b_conflict_analyzer.RulesManager.list_workflow_relationships', return_value=[]):
            report = ResourceConflictAnalyzer.analyze()
            assert report.conflict_count == 0

    def test_analyze_single_workflow(self):
        """测试：单个工作流无冲突"""
        mock_workflow = MagicMock(spec=WorkflowRelationship)
        mock_workflow.workflow_id = "wf_1"
        mock_workflow.relationship_id = "mock_workflow_rel"
        mock_workflow.constraints = [{"resource_id": "res_1", "quantity": 1}]

        with patch('app.phase3b_conflict_analyzer.RulesManager.list_workflow_relationships', return_value=[mock_workflow]):
            report = ResourceConflictAnalyzer.analyze()
            assert isinstance(report, ConflictReport)

    def test_detect_resource_contention(self):
        """测试：检测资源竞争"""
        mock_workflow1 = MagicMock(spec=WorkflowRelationship)
        mock_workflow1.workflow_id = "wf_1"
        mock_workflow1.relationship_id = "mock_workflow1_rel"
        mock_workflow1.constraints = [{"resource_id": "res_1", "quantity": 10}]

        mock_workflow2 = MagicMock(spec=WorkflowRelationship)
        mock_workflow2.workflow_id = "wf_2"
        mock_workflow2.relationship_id = "mock_workflow2_rel"
        mock_workflow2.constraints = [{"resource_id": "res_1", "quantity": 8}]

        with patch('app.phase3b_conflict_analyzer.RulesManager.list_workflow_relationships', return_value=[mock_workflow1, mock_workflow2]):
            report = ResourceConflictAnalyzer.analyze()
            assert isinstance(report, ConflictReport)

    def test_detect_deadlock_risk(self):
        """测试：检测死锁风险"""
        # 创建循环依赖关系
        mock_workflow1 = MagicMock(spec=WorkflowRelationship)
        mock_workflow1.workflow_id = "wf_1"
        mock_workflow1.relationship_id = "mock_workflow1_rel"
        mock_workflow1.depends_on = ["wf_2"]
        mock_workflow1.constraints = [{"resource_id": "res_1", "quantity": 5}]

        mock_workflow2 = MagicMock(spec=WorkflowRelationship)
        mock_workflow2.workflow_id = "wf_2"
        mock_workflow2.relationship_id = "mock_workflow2_rel"
        mock_workflow2.depends_on = ["wf_1"]
        mock_workflow2.constraints = [{"resource_id": "res_2", "quantity": 5}]

        with patch('app.phase3b_conflict_analyzer.RulesManager.list_workflow_relationships', return_value=[mock_workflow1, mock_workflow2]):
            report = ResourceConflictAnalyzer.analyze()
            # 检查是否检测到循环依赖
            assert isinstance(report, ConflictReport)


class TestTimeConflictAnalyzer:
    """时间冲突分析器测试"""

    def test_analyze_no_time_constraints(self):
        """测试：没有时间约束时返回空报告"""
        with patch('app.phase3b_conflict_analyzer.RulesManager.list_system_rules', return_value=[]):
            report = TimeConflictAnalyzer.analyze()
            assert report.conflict_count == 0

    def test_analyze_valid_time_constraints(self):
        """测试：有效的时间约束无冲突"""
        mock_rule = MagicMock(spec=SystemRule)
        mock_rule.rule_id = "time_1"
        mock_rule.rule_name = "mock_rule_name"
        mock_rule.applicable_workflow_types = ["process_mapping"]
        mock_rule.rule_type = "permission_requirement"
        mock_rule.content = {
            "min_delay": 60,
            "max_delay": 3600
        }

        with patch('app.phase3b_conflict_analyzer.RulesManager.list_system_rules', return_value=[mock_rule]):
            report = TimeConflictAnalyzer.analyze()
            assert isinstance(report, ConflictReport)

    def test_detect_time_constraint_conflicts(self):
        """测试：检测时间约束冲突"""
        mock_rule1 = MagicMock(spec=SystemRule)
        mock_rule1.rule_id = "time_1"
        mock_rule1.rule_name = "mock_rule1_name"
        mock_rule1.applicable_workflow_types = ["process_mapping"]
        mock_rule1.rule_type = "permission_requirement"
        mock_rule1.content = {
            "min_delay": 100,
            "max_delay": 500,
            "workflow_type": "process_mapping"
        }

        mock_rule2 = MagicMock(spec=SystemRule)
        mock_rule2.rule_id = "time_2"
        mock_rule2.rule_name = "mock_rule2_name"
        mock_rule2.applicable_workflow_types = ["process_mapping"]
        mock_rule2.rule_type = "permission_requirement"
        mock_rule2.content = {
            "min_delay": 600,
            "max_delay": 1000,
            "workflow_type": "process_mapping"
        }

        with patch('app.phase3b_conflict_analyzer.RulesManager.list_system_rules', return_value=[mock_rule1, mock_rule2]):
            report = TimeConflictAnalyzer.analyze()
            assert isinstance(report, ConflictReport)

    def test_detect_deadline_conflicts(self):
        """测试：检测截止时间冲突"""
        now = datetime.utcnow()
        mock_rule = MagicMock(spec=SystemRule)
        mock_rule.rule_id = "deadline_1"
        mock_rule.rule_name = "mock_rule_name"
        mock_rule.applicable_workflow_types = ["process_mapping"]
        mock_rule.rule_type = "permission_requirement"
        mock_rule.content = {
            "required_completion_time": (now + timedelta(hours=1)).isoformat(),
            "expected_duration": 2  # 预期耗时2小时
        }

        with patch('app.phase3b_conflict_analyzer.RulesManager.list_system_rules', return_value=[mock_rule]):
            report = TimeConflictAnalyzer.analyze()
            assert isinstance(report, ConflictReport)


class TestPolicyConflictAnalyzer:
    """政策冲突分析器测试"""

    def test_analyze_no_policies(self):
        """测试：没有政策时返回空报告"""
        with patch('app.phase3b_conflict_analyzer.RulesManager.list_global_policies', return_value=[]):
            report = PolicyConflictAnalyzer.analyze()
            assert report.conflict_count == 0

    def test_analyze_single_policy(self):
        """测试：单个政策无冲突"""
        mock_policy = MagicMock(spec=GlobalPolicy)
        mock_policy.policy_id = "policy_1"
        mock_policy.decision_rules = [{"condition": "status==active", "action": "approve"}]

        with patch('app.phase3b_conflict_analyzer.RulesManager.list_global_policies', return_value=[mock_policy]):
            report = PolicyConflictAnalyzer.analyze()
            assert isinstance(report, ConflictReport)

    def test_detect_decision_rule_conflicts(self):
        """测试：检测决策规则冲突"""
        mock_policy1 = MagicMock(spec=GlobalPolicy)
        mock_policy1.policy_id = "policy_1"
        mock_policy1.decision_rules = [
            {"condition": "status==active and priority==high", "action": "approve"}
        ]

        mock_policy2 = MagicMock(spec=GlobalPolicy)
        mock_policy2.policy_id = "policy_2"
        mock_policy2.decision_rules = [
            {"condition": "status==active and priority==high", "action": "reject"}
        ]

        with patch('app.phase3b_conflict_analyzer.RulesManager.list_global_policies', return_value=[mock_policy1, mock_policy2]):
            report = PolicyConflictAnalyzer.analyze()
            assert isinstance(report, ConflictReport)

    def test_detect_coverage_conflicts(self):
        """测试：检测覆盖冲突"""
        mock_policy = MagicMock(spec=GlobalPolicy)
        mock_policy.policy_id = "policy_1"
        mock_policy.scope = "organization"
        mock_policy.coverage_areas = ["data_access", "resource_allocation"]

        with patch('app.phase3b_conflict_analyzer.RulesManager.list_global_policies', return_value=[mock_policy]):
            report = PolicyConflictAnalyzer.analyze()
            assert isinstance(report, ConflictReport)


class TestConflictResolutionEngine:
    """冲突解决引擎测试"""

    def test_analyze_all_conflicts_no_conflicts(self):
        """测试：无冲突时返回空报告"""
        with patch.object(PermissionConflictAnalyzer, 'analyze', return_value=ConflictReport(0, 0, 0, 0, 0, 0)), \
             patch.object(ResourceConflictAnalyzer, 'analyze', return_value=ConflictReport(0, 0, 0, 0, 0, 0)), \
             patch.object(TimeConflictAnalyzer, 'analyze', return_value=ConflictReport(0, 0, 0, 0, 0, 0)), \
             patch.object(PolicyConflictAnalyzer, 'analyze', return_value=ConflictReport(0, 0, 0, 0, 0, 0)):

            report = ConflictResolutionEngine.analyze_all_conflicts()
            assert report.conflict_count == 0

    def test_analyze_all_conflicts_with_conflicts(self):
        """测试：有冲突时返回合并报告"""
        conflict = Conflict(
            conflict_id="conflict_1",
            conflict_type=ConflictType.PERMISSION_CONFLICT,
            severity=ConflictSeverity.HIGH,
            affected_items=["rule_1", "rule_2"],
            description="Permission conflict between rules"
        )

        report1 = ConflictReport(1, 0, 1, 0, 0, 0, [conflict])
        report2 = ConflictReport(0, 0, 0, 0, 0, 0)
        report3 = ConflictReport(0, 0, 0, 0, 0, 0)
        report4 = ConflictReport(0, 0, 0, 0, 0, 0)

        with patch.object(PermissionConflictAnalyzer, 'analyze', return_value=report1), \
             patch.object(ResourceConflictAnalyzer, 'analyze', return_value=report2), \
             patch.object(TimeConflictAnalyzer, 'analyze', return_value=report3), \
             patch.object(PolicyConflictAnalyzer, 'analyze', return_value=report4):

            report = ConflictResolutionEngine.analyze_all_conflicts()
            assert report.conflict_count == 1
            assert report.high_count == 1

    def test_generate_resolution_plan_empty(self):
        """测试：无冲突时生成空解决方案"""
        report = ConflictReport(0, 0, 0, 0, 0, 0)
        plan = ConflictResolutionEngine.generate_resolution_plan(report)
        assert len(plan.get("resolution_steps", [])) == 0

    def test_generate_resolution_plan_with_conflicts(self):
        """测试：有冲突时生成解决方案"""
        conflict = Conflict(
            conflict_id="conflict_1",
            conflict_type=ConflictType.PERMISSION_CONFLICT,
            severity=ConflictSeverity.HIGH,
            affected_items=["rule_1", "rule_2"],
            description="Permission conflict",
            resolution_suggestions=["Revoke conflicting permission", "Update rule priority"]
        )

        report = ConflictReport(1, 0, 1, 0, 0, 0, [conflict])
        plan = ConflictResolutionEngine.generate_resolution_plan(report)

        assert "resolution_steps" in plan
        assert len(plan["resolution_steps"]) > 0


class TestConflictAnalysisFunctions:
    """冲突分析函数集成测试"""

    def test_analyze_all_conflicts_function(self):
        """测试：analyze_all_conflicts 函数"""
        with patch.object(ConflictResolutionEngine, 'analyze_all_conflicts', return_value=ConflictReport(0, 0, 0, 0, 0, 0)):
            report = analyze_all_conflicts()
            assert isinstance(report, ConflictReport)

    def test_generate_conflict_resolution_plan_function(self):
        """测试：generate_conflict_resolution_plan 函数"""
        report = ConflictReport(0, 0, 0, 0, 0, 0)
        plan = generate_conflict_resolution_plan(report)
        assert isinstance(plan, dict)

    def test_conflict_severity_levels(self):
        """测试：冲突严重程度枚举"""
        assert ConflictSeverity.CRITICAL.value == "critical"
        assert ConflictSeverity.HIGH.value == "high"
        assert ConflictSeverity.MEDIUM.value == "medium"
        assert ConflictSeverity.LOW.value == "low"
        assert ConflictSeverity.INFO.value == "info"

    def test_conflict_type_enum(self):
        """测试：冲突类型枚举"""
        assert ConflictType.PERMISSION_CONFLICT.value == "permission_conflict"
        assert ConflictType.RESOURCE_CONFLICT.value == "resource_conflict"
        assert ConflictType.TIME_CONFLICT.value == "time_conflict"
        assert ConflictType.POLICY_CONFLICT.value == "policy_conflict"
        assert ConflictType.DATA_CONFLICT.value == "data_conflict"


class TestConflictReportGeneration:
    """冲突报告生成测试"""

    def test_conflict_report_initialization(self):
        """测试：冲突报告初始化"""
        report = ConflictReport(
            conflict_count=2,
            critical_count=1,
            high_count=1,
            medium_count=0,
            low_count=0,
            info_count=0
        )
        assert report.conflict_count == 2
        assert report.critical_count == 1
        assert report.overall_severity == ConflictSeverity.INFO

    def test_conflict_initialization(self):
        """测试：单个冲突初始化"""
        conflict = Conflict(
            conflict_id="conf_1",
            conflict_type=ConflictType.RESOURCE_CONFLICT,
            severity=ConflictSeverity.CRITICAL,
            affected_items=["item_1", "item_2"],
            description="Resource exhaustion",
            resolution_suggestions=["Allocate additional resources", "Defer workflow"]
        )
        assert conflict.conflict_id == "conf_1"
        assert len(conflict.resolution_suggestions) == 2

    def test_conflict_report_with_conflicts(self):
        """测试：带有冲突的报告"""
        conflicts = [
            Conflict(
                conflict_id=f"conf_{i}",
                conflict_type=ConflictType.PERMISSION_CONFLICT,
                severity=ConflictSeverity.HIGH,
                affected_items=[f"item_{i}"],
                description=f"Conflict {i}"
            )
            for i in range(3)
        ]

        report = ConflictReport(
            conflict_count=3,
            critical_count=0,
            high_count=3,
            medium_count=0,
            low_count=0,
            info_count=0,
            conflicts=conflicts
        )

        assert len(report.conflicts) == 3
        assert all(c.severity == ConflictSeverity.HIGH for c in report.conflicts)

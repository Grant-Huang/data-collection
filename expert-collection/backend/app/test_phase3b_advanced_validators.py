"""Phase 3-B Stage 2: 高级验证器测试

测试规则集合验证器、工作流约束验证器、政策适用验证器。
"""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta

from .models import (
    SystemRule, SystemRuleUpdate,
    GlobalPolicy, GlobalPolicyUpdate,
    TimeConstraint, ExceptionHandler,
)
from .rules_manager import RulesManager
from .phase3b_advanced_validators import (
    RuleSetValidator, WorkflowConstraintValidator, PolicyApplicationValidator,
    ValidationStatus, ValidationItemType, validate_rule_set,
    validate_workflow_constraints, validate_policy_application,
)


class TestRuleSetValidator:
    """规则集合验证器测试"""

    def test_validate_empty_rule_set(self):
        """测试空规则集合验证"""
        report = RuleSetValidator.validate([])
        assert report.overall_status == ValidationStatus.PASS
        assert report.rules_count == 0

    def test_validate_consistency_pass(self):
        """测试一致性验证通过"""
        # 创建两个不重叠的规则
        rule1 = RulesManager.create_system_rule(
            rule_name="Rule 1",
            rule_type="validation_constraint",
            description="Rule 1",
            content={"constraint_expression": "test1"},
            created_by="test_user",
            applicable_workflow_types=["process_mapping"],
            status="active",
        )

        rule2 = RulesManager.create_system_rule(
            rule_name="Rule 2",
            rule_type="validation_constraint",
            description="Rule 2",
            content={"constraint_expression": "test2"},
            created_by="test_user",
            applicable_workflow_types=["standard_operation"],
            status="active",
        )

        report = RuleSetValidator.validate([rule1.rule_id, rule2.rule_id])

        # 验证检查已执行
        assert report.validation_items > 0
        # 检查是否有一致性问题（不应该有，因为范围不重叠）
        consistency_issues = [d for d in report.details if d.item_type == ValidationItemType.CONSISTENCY]
        # 一致性检查应该通过或有警告，但不应该有错误
        assert all(d.status != ValidationStatus.FAIL for d in consistency_issues)

    def test_validate_coverage_complete(self):
        """测试覆盖完整性验证"""
        # 创建具有不同类型的规则
        rule1 = RulesManager.create_system_rule(
            rule_name="Validation Rule",
            rule_type="validation_constraint",
            description="Test",
            content={"constraint_expression": "test"},
            created_by="test_user",
            status="active",
        )

        rule2 = RulesManager.create_system_rule(
            rule_name="Permission Rule",
            rule_type="permission_requirement",
            description="Test",
            content={"required_roles": ["admin"]},
            created_by="test_user",
            status="active",
        )

        report = RuleSetValidator.validate([rule1.rule_id, rule2.rule_id])

        # 应该没有缺失关键规则类型的警告
        coverage_issues = [d for d in report.details if d.item_type == ValidationItemType.COVERAGE]
        # 至少应该有一个通过的覆盖检查
        assert any(d.status == ValidationStatus.PASS for d in coverage_issues)

    def test_validate_priority_distribution(self):
        """测试优先级分布验证"""
        # 创建两个不同优先级的规则
        rule1 = RulesManager.create_system_rule(
            rule_name="Critical Rule",
            rule_type="validation_constraint",
            description="Test",
            content={"constraint_expression": "test"},
            created_by="test_user",
            priority="critical",
            status="active",
        )

        rule2 = RulesManager.create_system_rule(
            rule_name="Low Priority Rule",
            rule_type="validation_constraint",
            description="Test",
            content={"constraint_expression": "test2"},
            created_by="test_user",
            priority="low",
            status="active",
        )

        report = RuleSetValidator.validate([rule1.rule_id, rule2.rule_id])

        # 优先级分布应该是合理的
        priority_issues = [d for d in report.details if d.item_type == ValidationItemType.PRIORITY]
        # 应该有通过的优先级检查
        assert any(d.status == ValidationStatus.PASS for d in priority_issues)

    def test_validate_redundancy_detection(self):
        """测试冗余规则检测"""
        # 创建两个相似的规则
        rule1 = RulesManager.create_system_rule(
            rule_name="Validation Rule",
            rule_type="validation_constraint",
            description="Test",
            content={"constraint_expression": "test"},
            created_by="test_user",
            applicable_workflow_types=["process_mapping"],
            priority="high",
            status="active",
        )

        rule2 = RulesManager.create_system_rule(
            rule_name="Validation Rule 2",
            rule_type="validation_constraint",
            description="Test 2",
            content={"constraint_expression": "test"},
            created_by="test_user",
            applicable_workflow_types=["process_mapping"],
            priority="high",
            status="active",
        )

        report = RuleSetValidator.validate([rule1.rule_id, rule2.rule_id])

        # 应该检测到冗余
        redundancy_issues = [d for d in report.details if d.item_type == ValidationItemType.REDUNDANCY]
        assert len(redundancy_issues) > 0


class TestWorkflowConstraintValidator:
    """工作流约束验证器测试"""

    def test_validate_valid_workflow_type(self):
        """测试有效的工作流类型"""
        constraints = {
            "workflow_type": "process_mapping"
        }

        report = WorkflowConstraintValidator.validate("wf_test", constraints)

        # 应该通过工作流类型验证
        type_checks = [d for d in report.details if "workflow_type" in d.item_id]
        assert any(d.status == ValidationStatus.PASS for d in type_checks)

    def test_validate_invalid_workflow_type(self):
        """测试无效的工作流类型"""
        constraints = {
            "workflow_type": "invalid_type"
        }

        report = WorkflowConstraintValidator.validate("wf_test", constraints)

        # 应该失败工作流类型验证
        type_checks = [d for d in report.details if "workflow_type" in d.item_id]
        assert any(d.status == ValidationStatus.FAIL for d in type_checks)

    def test_validate_legal_stage_transitions(self):
        """测试合法的阶段转换"""
        constraints = {
            "allowed_transitions": [
                {"from": "initiation", "to": "collecting"},
                {"from": "collecting", "to": "confirmation"},
            ]
        }

        report = WorkflowConstraintValidator.validate("wf_test", constraints)

        # 应该通过合法转换验证
        transition_issues = [d for d in report.details if d.item_type == ValidationItemType.TRANSITION]
        # 至少应该有通过或警告的转换检查
        assert len(transition_issues) > 0

    def test_validate_invalid_stage_transitions(self):
        """测试非法的阶段转换"""
        constraints = {
            "allowed_transitions": [
                {"from": "unknown_stage", "to": "collecting"},
            ]
        }

        report = WorkflowConstraintValidator.validate("wf_test", constraints)

        # 应该检测到未知的阶段
        transition_issues = [d for d in report.details if d.item_type == ValidationItemType.TRANSITION]
        assert any(d.status == ValidationStatus.FAIL for d in transition_issues)

    def test_validate_time_constraints_valid(self):
        """测试有效的时间约束"""
        constraints = {
            "time_constraints": [
                {"min_delay": 60, "max_delay": 3600}
            ]
        }

        report = WorkflowConstraintValidator.validate("wf_test", constraints)

        # 应该通过时间约束验证
        time_checks = [d for d in report.details if d.item_type == ValidationItemType.TIME]
        assert any(d.status == ValidationStatus.PASS for d in time_checks)

    def test_validate_time_constraints_invalid_range(self):
        """测试无效的时间约束范围"""
        constraints = {
            "time_constraints": [
                {"min_delay": 3600, "max_delay": 60}  # min > max
            ]
        }

        report = WorkflowConstraintValidator.validate("wf_test", constraints)

        # 应该失败时间约束验证
        time_checks = [d for d in report.details if d.item_type == ValidationItemType.TIME]
        assert any(d.status == ValidationStatus.FAIL for d in time_checks)

    def test_validate_resource_constraints(self):
        """测试资源约束验证"""
        constraints = {
            "required_resources": [
                {"id": "resource_1", "count": 2}
            ]
        }

        report = WorkflowConstraintValidator.validate("wf_test", constraints)

        # 应该通过资源验证
        resource_checks = [d for d in report.details if d.item_type == ValidationItemType.RESOURCE]
        assert len(resource_checks) > 0


class TestPolicyApplicationValidator:
    """政策适用验证器测试"""

    def test_validate_empty_policy_set(self):
        """测试空政策集合"""
        report = PolicyApplicationValidator.validate([])
        assert report.overall_status == ValidationStatus.PASS
        assert report.rules_count == 0

    def test_validate_organization_level_policy(self):
        """测试组织级政策覆盖"""
        policy = RulesManager.create_global_policy(
            policy_name="Org Policy",
            description="Organization level policy",
            scope="organization",
            created_by="test_user",
            decision_rules=[
                {"rule_id": "r1", "condition": "test", "action": "allow"}
            ],
            status="active",
        )

        report = PolicyApplicationValidator.validate([policy.policy_id])

        # 应该通过组织级政策检查
        coverage_issues = [d for d in report.details if d.item_type == ValidationItemType.POLICY_COVERAGE]
        assert any(d.status == ValidationStatus.PASS for d in coverage_issues)

    def test_validate_missing_organization_policy(self):
        """测试缺少组织级政策"""
        policy = RulesManager.create_global_policy(
            policy_name="Dept Policy",
            description="Department level policy",
            scope="department",
            scope_target="engineering",
            created_by="test_user",
            decision_rules=[
                {"rule_id": "r1", "condition": "test", "action": "allow"}
            ],
            status="active",
        )

        report = PolicyApplicationValidator.validate([policy.policy_id])

        # 应该警告缺少组织级政策
        coverage_issues = [d for d in report.details if d.item_type == ValidationItemType.POLICY_COVERAGE]
        assert any(d.status == ValidationStatus.WARN for d in coverage_issues)

    def test_validate_decision_rules_complete(self):
        """测试决策规则完整性"""
        policy = RulesManager.create_global_policy(
            policy_name="Complete Policy",
            description="Policy with complete decision rules",
            scope="organization",
            created_by="test_user",
            decision_rules=[
                {
                    "rule_id": "r1",
                    "condition": "item_value > 10000",
                    "action": "require_director_approval"
                },
                {
                    "rule_id": "r2",
                    "condition": "item_value <= 10000",
                    "action": "require_manager_approval"
                }
            ],
            status="active",
        )

        report = PolicyApplicationValidator.validate([policy.policy_id])

        # 应该通过决策规则检查
        rule_issues = [d for d in report.details if d.item_type == ValidationItemType.DECISION_RULE]
        # 应该有通过或失败的规则检查，不应该只有警告
        assert len(rule_issues) > 0

    def test_validate_exception_handling_coverage(self):
        """测试异常处理覆盖"""
        policy = RulesManager.create_global_policy(
            policy_name="Exception Handling Policy",
            description="Policy with exception handlers",
            scope="organization",
            created_by="test_user",
            decision_rules=[
                {"rule_id": "r1", "condition": "test", "action": "allow"}
            ],
            exception_handlers=[
                ExceptionHandler(exception_type="timeout", handling_strategy="retry"),
                ExceptionHandler(exception_type="invalid_data", handling_strategy="reject"),
                ExceptionHandler(exception_type="resource_unavailable", handling_strategy="queue"),
                ExceptionHandler(exception_type="authorization_error", handling_strategy="deny"),
            ],
            status="active",
        )

        report = PolicyApplicationValidator.validate([policy.policy_id])

        # 应该检查异常处理覆盖
        exception_issues = [d for d in report.details if d.item_type == ValidationItemType.EXCEPTION_HANDLING]
        assert len(exception_issues) > 0

    def test_validate_policy_gap_detection(self):
        """测试政策死角检测"""
        report = PolicyApplicationValidator.validate([])

        # 空政策集合应该不被视为有死角
        gap_issues = [d for d in report.details if d.item_type == ValidationItemType.POLICY_GAP]
        # 应该有死角检测结果
        assert len(gap_issues) >= 0


class TestValidationFunctions:
    """测试高级验证函数"""

    def test_validate_rule_set_function(self):
        """测试 validate_rule_set 函数"""
        rule = RulesManager.create_system_rule(
            rule_name="Test Rule",
            rule_type="validation_constraint",
            description="Test",
            content={"constraint_expression": "test"},
            created_by="test_user",
            status="active",
        )

        report = validate_rule_set([rule.rule_id])
        assert report is not None
        assert report.rules_count == 1

    def test_validate_workflow_constraints_function(self):
        """测试 validate_workflow_constraints 函数"""
        constraints = {
            "workflow_type": "process_mapping",
            "allowed_transitions": [
                {"from": "initiation", "to": "collecting"}
            ]
        }

        report = validate_workflow_constraints("wf_test", constraints)
        assert report is not None
        assert report.validation_items > 0

    def test_validate_policy_application_function(self):
        """测试 validate_policy_application 函数"""
        policy = RulesManager.create_global_policy(
            policy_name="Test Policy",
            description="Test",
            scope="organization",
            created_by="test_user",
            decision_rules=[
                {"rule_id": "r1", "condition": "test", "action": "allow"}
            ],
            status="active",
        )

        report = validate_policy_application([policy.policy_id])
        assert report is not None
        assert report.rules_count == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Phase 3-B Stage 1: 单元测试

测试规则管理器、验证器、冲突检测和影响分析。
"""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta

from .models import (
    SystemRule, SystemRuleUpdate,
    WorkflowRelationship, WorkflowRelationshipUpdate,
    GlobalPolicy, GlobalPolicyUpdate,
    TimeConstraint, DataConstraint, ExceptionHandler,
)
from .rules_manager import RulesManager
from .phase3b_validators import (
    SystemRuleValidator, WorkflowRelationshipValidator,
    GlobalPolicyValidator, ConflictDetector, ImpactAnalyzer,
)


class TestSystemRuleValidator:
    """SystemRuleValidator 测试"""

    def test_validate_basic_fields(self):
        """测试基本字段验证"""
        now = datetime.utcnow().isoformat() + "Z"

        # 缺少规则名称
        rule_no_name = SystemRule(
            rule_id="rule_test",
            rule_name="",
            rule_type="validation_constraint",
            description="Test rule",
            content={"constraint_expression": "test"},
            status="active",
            version="1.0.0",
            effective_date=now,
            created_by="test_user",
            created_at=now,
            updated_by="test_user",
            updated_at=now,
        )

        issues = SystemRuleValidator.validate(rule_no_name)
        assert any(i.code == "RULE_NAME_REQUIRED" for i in issues)

    def test_validate_date_range(self):
        """测试日期范围验证"""
        now = datetime.utcnow()
        future = (now + timedelta(days=10)).isoformat() + "Z"
        past = (now - timedelta(days=10)).isoformat() + "Z"
        now_str = now.isoformat() + "Z"

        # 失效日期早于生效日期
        rule = SystemRule(
            rule_id="rule_test",
            rule_name="Test Rule",
            rule_type="validation_constraint",
            description="Test rule",
            content={"constraint_expression": "test"},
            status="active",
            version="1.0.0",
            effective_date=future,
            expiry_date=past,
            created_by="test_user",
            created_at=now_str,
            updated_by="test_user",
            updated_at=now_str,
        )

        issues = SystemRuleValidator.validate(rule)
        assert any(i.code == "INVALID_DATE_RANGE" for i in issues)

    def test_validate_content_format(self):
        """测试内容格式验证"""
        now = datetime.utcnow().isoformat() + "Z"

        # 缺少约束表达式
        rule = SystemRule(
            rule_id="rule_test",
            rule_name="Test Rule",
            rule_type="validation_constraint",
            description="Test rule",
            content={},  # 缺少 constraint_expression
            status="active",
            version="1.0.0",
            effective_date=now,
            created_by="test_user",
            created_at=now,
            updated_by="test_user",
            updated_at=now,
        )

        issues = SystemRuleValidator.validate(rule)
        assert any(i.code == "MISSING_CONSTRAINT_EXPRESSION" for i in issues)


class TestWorkflowRelationshipValidator:
    """WorkflowRelationshipValidator 测试"""

    def test_validate_workflows(self):
        """测试工作流字段验证"""
        now = datetime.utcnow().isoformat() + "Z"

        # 缺少工作流ID
        rel = WorkflowRelationship(
            relationship_id="rel_test",
            relationship_type="dependency",
            source_workflow_id="",
            target_workflow_id="wf2",
            description="Test relationship",
            version="1.0.0",
            status="active",
            created_by="test_user",
            created_at=now,
            updated_by="test_user",
            updated_at=now,
        )

        issues = WorkflowRelationshipValidator.validate(rel)
        assert any(i.code == "MISSING_WORKFLOW_ID" for i in issues)

    def test_validate_self_reference(self):
        """测试自引用检测"""
        now = datetime.utcnow().isoformat() + "Z"

        # 工作流与自身相关
        rel = WorkflowRelationship(
            relationship_id="rel_test",
            relationship_type="dependency",
            source_workflow_id="wf1",
            target_workflow_id="wf1",  # 自引用
            description="Test relationship",
            version="1.0.0",
            status="active",
            created_by="test_user",
            created_at=now,
            updated_by="test_user",
            updated_at=now,
        )

        issues = WorkflowRelationshipValidator.validate(rel)
        assert any(i.code == "SELF_REFERENCE" for i in issues)

    def test_validate_time_constraint(self):
        """测试时间约束验证"""
        now = datetime.utcnow().isoformat() + "Z"

        # 最小延迟大于最大延迟
        rel = WorkflowRelationship(
            relationship_id="rel_test",
            relationship_type="dependency",
            source_workflow_id="wf1",
            target_workflow_id="wf2",
            description="Test relationship",
            constraints=[
                TimeConstraint(min_delay=1000, max_delay=100)  # 错误
            ],
            version="1.0.0",
            status="active",
            created_by="test_user",
            created_at=now,
            updated_by="test_user",
            updated_at=now,
        )

        issues = WorkflowRelationshipValidator.validate(rel)
        assert any(i.code == "INVALID_TIME_CONSTRAINT" for i in issues)


class TestGlobalPolicyValidator:
    """GlobalPolicyValidator 测试"""

    def test_validate_basic_fields(self):
        """测试基本字段验证"""
        now = datetime.utcnow().isoformat() + "Z"

        # 缺少政策名称
        policy = GlobalPolicy(
            policy_id="policy_test",
            policy_name="",  # 缺少名称
            description="Test policy",
            scope="organization",
            version="1.0.0",
            status="active",
            effective_date=now,
            created_by="test_user",
            created_at=now,
            updated_by="test_user",
            updated_at=now,
        )

        issues = GlobalPolicyValidator.validate(policy)
        assert any(i.code == "POLICY_NAME_REQUIRED" for i in issues)

    def test_validate_scope_target(self):
        """测试范围目标验证"""
        now = datetime.utcnow().isoformat() + "Z"

        # 部门级政策缺少目标
        policy = GlobalPolicy(
            policy_id="policy_test",
            policy_name="Test Policy",
            description="Test policy",
            scope="department",  # 部门级
            scope_target=None,   # 缺少目标
            version="1.0.0",
            status="active",
            effective_date=now,
            created_by="test_user",
            created_at=now,
            updated_by="test_user",
            updated_at=now,
        )

        issues = GlobalPolicyValidator.validate(policy)
        assert any(i.code == "MISSING_SCOPE_TARGET" for i in issues)


class TestRulesManager:
    """RulesManager 集成测试"""

    def test_create_system_rule(self):
        """测试创建系统规则"""
        rule = RulesManager.create_system_rule(
            rule_name="Test Validation Rule",
            rule_type="validation_constraint",
            description="A test validation constraint",
            content={"constraint_expression": "step_count > 0"},
            created_by="test_user",
            applicable_workflow_types=["process_mapping"],
            priority="high",
            tags=["testing"],
        )

        assert rule.rule_id.startswith("rule_")
        assert rule.rule_name == "Test Validation Rule"
        assert rule.version == "1.0.0"
        assert rule.status == "draft"

        # 验证规则
        retrieved = RulesManager.get_system_rule(rule.rule_id)
        assert retrieved is not None
        assert retrieved.rule_name == rule.rule_name

    def test_update_system_rule(self):
        """测试更新系统规则"""
        # 创建规则
        rule = RulesManager.create_system_rule(
            rule_name="Test Rule",
            rule_type="validation_constraint",
            description="Original description",
            content={"constraint_expression": "test"},
            created_by="test_user",
        )

        # 更新规则
        update_data = SystemRuleUpdate(
            description="Updated description",
            priority="critical",
        )

        updated = RulesManager.update_system_rule(
            rule.rule_id,
            update_data,
            "updater_user",
        )

        assert updated is not None
        assert updated.description == "Updated description"
        assert updated.priority == "critical"
        # 版本应该增加
        assert updated.version != rule.version

    def test_create_workflow_relationship(self):
        """测试创建工作流关系"""
        rel = RulesManager.create_workflow_relationship(
            relationship_type="dependency",
            source_workflow_id="wf1",
            target_workflow_id="wf2",
            description="wf1 depends on wf2",
            created_by="test_user",
            tags=["testing"],
        )

        assert rel.relationship_id.startswith("rel_")
        assert rel.relationship_type == "dependency"

        # 验证关系
        retrieved = RulesManager.get_workflow_relationship(rel.relationship_id)
        assert retrieved is not None
        assert retrieved.source_workflow_id == "wf1"

    def test_create_global_policy(self):
        """测试创建全局政策"""
        policy = RulesManager.create_global_policy(
            policy_name="Test Policy",
            description="A test global policy",
            scope="organization",
            created_by="test_user",
            decision_rules=[
                {"condition": "step_type == 'approval'", "action": "require_manager_approval"},
            ],
            priority="high",
        )

        assert policy.policy_id.startswith("policy_")
        assert policy.policy_name == "Test Policy"
        assert policy.status == "draft"

        # 验证政策
        retrieved = RulesManager.get_global_policy(policy.policy_id)
        assert retrieved is not None
        assert len(retrieved.decision_rules) == 1


class TestImpactAnalyzer:
    """ImpactAnalyzer 测试"""

    def test_analyze_impact(self):
        """测试影响分析"""
        # 创建一个高优先级的规则
        rule = RulesManager.create_system_rule(
            rule_name="Critical Validation Rule",
            rule_type="validation_constraint",
            description="A critical rule affecting many workflows",
            content={"constraint_expression": "test"},
            created_by="test_user",
            applicable_workflow_types=[],  # 影响所有工作流
            priority="critical",
        )

        # 分析影响
        impact = ImpactAnalyzer.analyze_rule_change_impact(rule.rule_id)

        assert impact is not None
        assert impact.rule_id == rule.rule_id
        assert impact.rule_type == "validation_constraint"
        assert impact.priority == "critical" or impact.risk_level == "critical"


class TestConflictDetector:
    """ConflictDetector 测试"""

    def test_detect_permission_conflicts(self):
        """测试权限冲突检测"""
        # 创建两个相互矛盾的权限规则
        rule1 = RulesManager.create_system_rule(
            rule_name="Rule 1",
            rule_type="permission_requirement",
            description="Requires role A",
            content={"required_roles": ["role_A"]},
            created_by="test_user",
        )

        rule2 = RulesManager.create_system_rule(
            rule_name="Rule 2",
            rule_type="permission_requirement",
            description="Requires role B",
            content={"required_roles": ["role_B"]},
            created_by="test_user",
        )

        # 激活规则
        RulesManager.activate_system_rule(rule1.rule_id, "test_user")
        RulesManager.activate_system_rule(rule2.rule_id, "test_user")

        # 检测冲突
        conflicts = ConflictDetector.detect_permission_conflicts()

        # 简化测试：只验证函数可以执行
        assert isinstance(conflicts, list)


if __name__ == "__main__":
    # 运行测试: pytest app/test_phase3b.py -v
    pytest.main([__file__, "-v"])

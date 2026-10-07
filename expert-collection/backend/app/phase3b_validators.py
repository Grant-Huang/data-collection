"""Phase 3-B: 规则验证器、冲突检测和影响分析

实现系统规则、跨工作流关系、全局政策的验证和冲突检测。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional, Set, List, Tuple
from collections import defaultdict, deque

from .models import (
    SystemRule, WorkflowRelationship, GlobalPolicy,
    RuleValidationIssue, ImpactAnalysis,
)
from .rules_manager import RulesManager

logger = logging.getLogger(__name__)


class SystemRuleValidator:
    """系统规则验证器"""

    @classmethod
    def validate(cls, rule: SystemRule) -> List[RuleValidationIssue]:
        """验证系统规则的完整性和一致性"""
        issues = []

        # 验证基本字段
        issues.extend(cls._validate_basic_fields(rule))

        # 验证日期逻辑
        issues.extend(cls._validate_dates(rule))

        # 验证内容格式
        issues.extend(cls._validate_content(rule))

        # 验证权限
        issues.extend(cls._validate_permissions(rule))

        return issues

    @classmethod
    def _validate_basic_fields(cls, rule: SystemRule) -> List[RuleValidationIssue]:
        """验证基本字段"""
        issues = []

        # 检查唯一性（实际应查询数据库，这里简化）
        if not rule.rule_name or len(rule.rule_name.strip()) == 0:
            issues.append(RuleValidationIssue(
                issue_id="rule_no_name",
                issue_type="error",
                code="RULE_NAME_REQUIRED",
                message="规则名称不能为空",
                affected_rule_id=rule.rule_id,
            ))

        if not rule.rule_type:
            issues.append(RuleValidationIssue(
                issue_id="rule_no_type",
                issue_type="error",
                code="RULE_TYPE_REQUIRED",
                message="规则类型不能为空",
                affected_rule_id=rule.rule_id,
            ))

        return issues

    @classmethod
    def _validate_dates(cls, rule: SystemRule) -> List[RuleValidationIssue]:
        """验证日期逻辑"""
        issues = []

        try:
            effective = datetime.fromisoformat(rule.effective_date.replace("Z", "+00:00"))

            if rule.expiry_date:
                expiry = datetime.fromisoformat(rule.expiry_date.replace("Z", "+00:00"))
                if expiry <= effective:
                    issues.append(RuleValidationIssue(
                        issue_id="rule_invalid_dates",
                        issue_type="error",
                        code="INVALID_DATE_RANGE",
                        message="失效日期必须晚于生效日期",
                        affected_rule_id=rule.rule_id,
                    ))
        except (ValueError, AttributeError) as e:
            issues.append(RuleValidationIssue(
                issue_id="rule_date_format",
                issue_type="error",
                code="INVALID_DATE_FORMAT",
                message=f"日期格式错误: {e}",
                affected_rule_id=rule.rule_id,
            ))

        return issues

    @classmethod
    def _validate_content(cls, rule: SystemRule) -> List[RuleValidationIssue]:
        """验证规则内容格式"""
        issues = []

        if not rule.content:
            issues.append(RuleValidationIssue(
                issue_id="rule_no_content",
                issue_type="error",
                code="RULE_CONTENT_REQUIRED",
                message="规则内容不能为空",
                affected_rule_id=rule.rule_id,
            ))
            return issues

        # 根据规则类型验证内容结构
        content = rule.content

        if rule.rule_type == "validation_constraint":
            if "constraint_expression" not in content:
                issues.append(RuleValidationIssue(
                    issue_id="rule_missing_constraint",
                    issue_type="error",
                    code="MISSING_CONSTRAINT_EXPRESSION",
                    message="验证约束缺少表达式",
                    affected_rule_id=rule.rule_id,
                ))

        elif rule.rule_type == "permission_requirement":
            if "required_roles" not in content or not content["required_roles"]:
                issues.append(RuleValidationIssue(
                    issue_id="rule_missing_roles",
                    issue_type="error",
                    code="MISSING_REQUIRED_ROLES",
                    message="权限要求缺少角色定义",
                    affected_rule_id=rule.rule_id,
                ))

        return issues

    @classmethod
    def _validate_permissions(cls, rule: SystemRule) -> List[RuleValidationIssue]:
        """验证权限和审批"""
        issues = []

        if rule.requires_approval:
            if not rule.approved_by and rule.status == "active":
                issues.append(RuleValidationIssue(
                    issue_id="rule_not_approved",
                    issue_type="warning",
                    code="RULE_REQUIRES_APPROVAL",
                    message="规则需要审批但未被批准",
                    affected_rule_id=rule.rule_id,
                ))

        return issues


class WorkflowRelationshipValidator:
    """工作流关系验证器"""

    @classmethod
    def validate(cls, rel: WorkflowRelationship) -> List[RuleValidationIssue]:
        """验证工作流关系"""
        issues = []

        # 验证源和目标工作流
        issues.extend(cls._validate_workflows(rel))

        # 验证约束
        issues.extend(cls._validate_constraints(rel))

        return issues

    @classmethod
    def _validate_workflows(cls, rel: WorkflowRelationship) -> List[RuleValidationIssue]:
        """验证源和目标工作流"""
        issues = []

        if not rel.source_workflow_id or not rel.target_workflow_id:
            issues.append(RuleValidationIssue(
                issue_id="rel_missing_workflow",
                issue_type="error",
                code="MISSING_WORKFLOW_ID",
                message="源工作流或目标工作流缺失",
                affected_rule_id=rel.relationship_id,
            ))

        if rel.source_workflow_id == rel.target_workflow_id:
            issues.append(RuleValidationIssue(
                issue_id="rel_self_reference",
                issue_type="error",
                code="SELF_REFERENCE",
                message="工作流不能与自身相关联",
                affected_rule_id=rel.relationship_id,
            ))

        return issues

    @classmethod
    def _validate_constraints(cls, rel: WorkflowRelationship) -> List[RuleValidationIssue]:
        """验证约束条件"""
        issues = []

        for i, constraint in enumerate(rel.constraints):
            constraint_type = constraint.get("constraint_type") if isinstance(constraint, dict) else getattr(constraint, "constraint_type", None)

            if constraint_type == "time_constraint":
                if isinstance(constraint, dict):
                    min_delay = constraint.get("min_delay")
                    max_delay = constraint.get("max_delay")
                else:
                    min_delay = getattr(constraint, "min_delay", None)
                    max_delay = getattr(constraint, "max_delay", None)

                if min_delay and max_delay and min_delay > max_delay:
                    issues.append(RuleValidationIssue(
                        issue_id="rel_invalid_time_constraint",
                        issue_type="error",
                        code="INVALID_TIME_CONSTRAINT",
                        message=f"约束 {i}: 最小延迟不能大于最大延迟",
                        affected_rule_id=rel.relationship_id,
                    ))

        return issues

    @classmethod
    def detect_cycles(cls) -> dict[str, list[str]]:
        """检测工作流依赖中的循环"""
        all_rels = RulesManager.list_workflow_relationships()

        # 构建邻接表
        graph = defaultdict(list)
        workflows = set()

        for rel in all_rels:
            if rel.status != "active":
                continue
            graph[rel.source_workflow_id].append(rel.target_workflow_id)
            workflows.add(rel.source_workflow_id)
            workflows.add(rel.target_workflow_id)

        cycles = {}

        # DFS检测循环
        for workflow_id in workflows:
            visited = set()
            rec_stack = set()
            path = []

            if cls._has_cycle_dfs(workflow_id, graph, visited, rec_stack, path):
                cycles[workflow_id] = path

        return cycles

    @classmethod
    def _has_cycle_dfs(
        cls,
        node: str,
        graph: dict[str, list[str]],
        visited: Set[str],
        rec_stack: Set[str],
        path: List[str],
    ) -> bool:
        """DFS检测循环"""
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                if cls._has_cycle_dfs(neighbor, graph, visited, rec_stack, path):
                    return True
            elif neighbor in rec_stack:
                # 找到循环
                cycle_start = path.index(neighbor)
                path[cycle_start:] = path[cycle_start:] + [neighbor]
                return True

        path.pop()
        rec_stack.remove(node)
        return False


class GlobalPolicyValidator:
    """全局政策验证器"""

    @classmethod
    def validate(cls, policy: GlobalPolicy) -> List[RuleValidationIssue]:
        """验证全局政策"""
        issues = []

        # 验证基本字段
        issues.extend(cls._validate_basic_fields(policy))

        # 验证决策规则
        issues.extend(cls._validate_decision_rules(policy))

        # 验证适用范围
        issues.extend(cls._validate_scope(policy))

        return issues

    @classmethod
    def _validate_basic_fields(cls, policy: GlobalPolicy) -> List[RuleValidationIssue]:
        """验证基本字段"""
        issues = []

        if not policy.policy_name:
            issues.append(RuleValidationIssue(
                issue_id="policy_no_name",
                issue_type="error",
                code="POLICY_NAME_REQUIRED",
                message="政策名称不能为空",
                affected_rule_id=policy.policy_id,
            ))

        if not policy.scope:
            issues.append(RuleValidationIssue(
                issue_id="policy_no_scope",
                issue_type="error",
                code="POLICY_SCOPE_REQUIRED",
                message="政策适用范围不能为空",
                affected_rule_id=policy.policy_id,
            ))

        return issues

    @classmethod
    def _validate_decision_rules(cls, policy: GlobalPolicy) -> List[RuleValidationIssue]:
        """验证决策规则"""
        issues = []

        if not policy.decision_rules:
            issues.append(RuleValidationIssue(
                issue_id="policy_no_rules",
                issue_type="warning",
                code="POLICY_NO_DECISION_RULES",
                message="政策未定义决策规则",
                affected_rule_id=policy.policy_id,
            ))
            return issues

        for i, rule in enumerate(policy.decision_rules):
            if isinstance(rule, dict):
                if "condition" not in rule:
                    issues.append(RuleValidationIssue(
                        issue_id=f"policy_rule_no_condition_{i}",
                        issue_type="error",
                        code="DECISION_RULE_MISSING_CONDITION",
                        message=f"决策规则 {i}: 缺少条件表达式",
                        affected_rule_id=policy.policy_id,
                    ))
                if "action" not in rule:
                    issues.append(RuleValidationIssue(
                        issue_id=f"policy_rule_no_action_{i}",
                        issue_type="error",
                        code="DECISION_RULE_MISSING_ACTION",
                        message=f"决策规则 {i}: 缺少行动定义",
                        affected_rule_id=policy.policy_id,
                    ))

        return issues

    @classmethod
    def _validate_scope(cls, policy: GlobalPolicy) -> List[RuleValidationIssue]:
        """验证适用范围"""
        issues = []

        if policy.scope in ("department", "workflow_type"):
            if not policy.scope_target:
                issues.append(RuleValidationIssue(
                    issue_id="policy_missing_scope_target",
                    issue_type="error",
                    code="MISSING_SCOPE_TARGET",
                    message=f"政策范围为 {policy.scope} 时需要指定目标",
                    affected_rule_id=policy.policy_id,
                ))

        return issues


class ConflictDetector:
    """冲突检测器"""

    @classmethod
    def detect_permission_conflicts(cls) -> List[Tuple[str, str, str]]:
        """检测权限冲突（不同角色的权限矛盾）"""
        conflicts = []

        rules = RulesManager.list_system_rules(rule_type="permission_requirement", status="active")

        # 简化的冲突检测：查找相互矛盾的权限要求
        for i, rule1 in enumerate(rules):
            for rule2 in rules[i+1:]:
                if cls._rules_conflict(rule1, rule2):
                    conflicts.append((rule1.rule_id, rule2.rule_id, "Permission conflict"))

        return conflicts

    @classmethod
    def _rules_conflict(cls, rule1: SystemRule, rule2: SystemRule) -> bool:
        """检查两个规则是否冲突"""
        # 简化实现：检查内容是否互相排斥
        if rule1.content.get("required_roles") and rule2.content.get("required_roles"):
            roles1 = set(rule1.content["required_roles"])
            roles2 = set(rule2.content["required_roles"])

            # 如果两个规则要求完全不同的角色，可能冲突
            if roles1.isdisjoint(roles2):
                return True

        return False

    @classmethod
    def detect_policy_conflicts(cls) -> List[Tuple[str, str, str]]:
        """检测政策冲突"""
        conflicts = []

        policies = RulesManager.list_global_policies(status="active")

        for i, policy1 in enumerate(policies):
            for policy2 in policies[i+1:]:
                if policy1.scope == policy2.scope and policy1.scope_target == policy2.scope_target:
                    # 同范围的两个政策可能冲突
                    if cls._policies_conflict(policy1, policy2):
                        conflicts.append((policy1.policy_id, policy2.policy_id, "Scope overlap"))

        return conflicts

    @classmethod
    def _policies_conflict(cls, policy1: GlobalPolicy, policy2: GlobalPolicy) -> bool:
        """检查两个政策是否冲突"""
        # 简化实现：检查决策规则是否互相矛盾
        for rule1 in policy1.decision_rules:
            for rule2 in policy2.decision_rules:
                if isinstance(rule1, dict) and isinstance(rule2, dict):
                    if rule1.get("condition") == rule2.get("condition"):
                        # 同条件不同行动可能冲突
                        if rule1.get("action") != rule2.get("action"):
                            return True

        return False


class ImpactAnalyzer:
    """影响分析器"""

    @classmethod
    def analyze_rule_change_impact(cls, rule_id: str) -> Optional[ImpactAnalysis]:
        """分析规则变更的影响"""
        rule = RulesManager.get_system_rule(rule_id)
        if not rule:
            return None

        # 找到应用该规则的所有工作流
        affected_workflows = cls._find_affected_workflows(rule)

        # 评估风险等级
        risk_level = cls._evaluate_risk_level(rule, len(affected_workflows))

        # 生成建议
        recommendations = cls._generate_recommendations(rule, len(affected_workflows))

        return ImpactAnalysis(
            rule_id=rule_id,
            rule_type=rule.rule_type,
            affected_workflow_ids=affected_workflows,
            affected_workflow_count=len(affected_workflows),
            risk_level=risk_level,
            estimated_impact_percentage=min(100.0, (len(affected_workflows) / max(1, cls._get_total_workflows())) * 100),
            recommendations=recommendations,
            change_history=[],
        )

    @classmethod
    def _find_affected_workflows(cls, rule: SystemRule) -> List[str]:
        """找到受规则影响的工作流"""
        affected = []

        # 简化实现：根据applicable_workflow_types过滤
        if not rule.applicable_workflow_types:
            # 空列表表示全部工作流都受影响
            return ["all_workflows"]

        # 实际应从数据库查询匹配的工作流
        # 这里只返回示例
        return rule.applicable_workflow_types

    @classmethod
    def _evaluate_risk_level(cls, rule: SystemRule, affected_count: int) -> str:
        """评估风险等级"""
        if rule.rule_type == "compliance_requirement":
            return "high"

        if affected_count > 100:
            return "critical"
        elif affected_count > 50:
            return "high"
        elif affected_count > 10:
            return "medium"
        else:
            return "low"

    @classmethod
    def _generate_recommendations(cls, rule: SystemRule, affected_count: int) -> List[str]:
        """生成建议"""
        recommendations = []

        if affected_count > 50:
            recommendations.append("大范围影响，建议分阶段实施")

        if rule.requires_approval:
            recommendations.append("规则需要审批，确保已获得必要的批准")

        if rule.expiry_date:
            recommendations.append(f"规则将在 {rule.expiry_date} 失效，提前准备替代方案")

        recommendations.append("实施前进行充分的测试和验证")

        return recommendations

    @classmethod
    def _get_total_workflows(cls) -> int:
        """获取总工作流数（简化实现）"""
        return 1  # 实际应从数据库查询


# 导出验证器和检测器
__all__ = [
    "SystemRuleValidator",
    "WorkflowRelationshipValidator",
    "GlobalPolicyValidator",
    "ConflictDetector",
    "ImpactAnalyzer",
]

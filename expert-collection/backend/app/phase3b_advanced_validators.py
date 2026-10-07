"""Phase 3-B Stage 2: 高级验证系统

实现跨规则的高级验证、详细冲突分析、工作流影响规划。
包括规则集合验证、工作流约束验证、政策适用验证。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional, Set, List, Dict, Any, Tuple
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum

from .models import (
    SystemRule, WorkflowRelationship, GlobalPolicy,
    RuleValidationIssue, ImpactAnalysis,
    TimeConstraint, DataConstraint,
)
from .rules_manager import RulesManager

logger = logging.getLogger(__name__)


# ============================================================================
# 数据模型
# ============================================================================

class ValidationItemType(str, Enum):
    """验证项类型"""
    CONSISTENCY = "consistency"
    COVERAGE = "coverage"
    PRIORITY = "priority"
    REDUNDANCY = "redundancy"
    CONSTRAINT = "constraint"
    TRANSITION = "transition"
    RESOURCE = "resource"
    TIME = "time"
    POLICY_COVERAGE = "policy_coverage"
    DECISION_RULE = "decision_rule"
    EXCEPTION_HANDLING = "exception_handling"
    POLICY_GAP = "policy_gap"


class ValidationStatus(str, Enum):
    """验证状态"""
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass
class ValidationResult:
    """单项验证结果"""
    item_id: str
    item_type: ValidationItemType
    status: ValidationStatus
    message: str
    severity: str  # "critical", "high", "medium", "low", "info"
    affected_items: List[str] = field(default_factory=list)
    suggestion: Optional[str] = None


@dataclass
class ValidationReport:
    """验证报告"""
    overall_status: ValidationStatus
    rules_count: int
    validation_items: int
    passed: int
    warnings: int
    errors: int
    details: List[ValidationResult] = field(default_factory=list)
    summary: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


# ============================================================================
# 1. 规则集合验证器
# ============================================================================

class RuleSetValidator:
    """规则集合验证器

    验证一组规则的整体一致性、覆盖完整性、优先级合理性和冗余检测。
    """

    @classmethod
    def validate(cls, rule_ids: List[str]) -> ValidationReport:
        """验证规则集合"""
        rules = [RulesManager.get_system_rule(rid) for rid in rule_ids if RulesManager.get_system_rule(rid)]

        report = ValidationReport(
            overall_status=ValidationStatus.PASS,
            rules_count=len(rules),
            validation_items=0,
            passed=0,
            warnings=0,
            errors=0,
        )

        if not rules:
            return report

        # 执行各项验证
        report.details.extend(cls._validate_consistency(rules))
        report.details.extend(cls._validate_coverage(rules))
        report.details.extend(cls._validate_priority(rules))
        report.details.extend(cls._validate_redundancy(rules))

        # 统计结果
        report.validation_items = len(report.details)
        report.passed = sum(1 for d in report.details if d.status == ValidationStatus.PASS)
        report.warnings = sum(1 for d in report.details if d.status == ValidationStatus.WARN)
        report.errors = sum(1 for d in report.details if d.status == ValidationStatus.FAIL)

        # 确定整体状态
        if report.errors > 0:
            report.overall_status = ValidationStatus.FAIL
        elif report.warnings > 0:
            report.overall_status = ValidationStatus.WARN
        else:
            report.overall_status = ValidationStatus.PASS

        return report

    @classmethod
    def _validate_consistency(cls, rules: List[SystemRule]) -> List[ValidationResult]:
        """验证规则间的一致性"""
        results = []

        # 检查相同类型的规则是否有矛盾的约束
        rules_by_type = defaultdict(list)
        for rule in rules:
            rules_by_type[rule.rule_type].append(rule)

        for rule_type, typed_rules in rules_by_type.items():
            if len(typed_rules) <= 1:
                continue

            # 检查相同类型规则的约束一致性
            for i, rule1 in enumerate(typed_rules):
                for rule2 in typed_rules[i + 1:]:
                    # 检查是否应用范围重叠
                    overlap = cls._check_scope_overlap(rule1, rule2)

                    if overlap and rule1.status == "active" and rule2.status == "active":
                        # 如果范围重叠且都是活跃的，检查是否有矛盾
                        conflict = cls._check_rule_conflict(rule1, rule2)
                        if conflict:
                            results.append(ValidationResult(
                                item_id=f"consistency_{rule1.rule_id}_{rule2.rule_id}",
                                item_type=ValidationItemType.CONSISTENCY,
                                status=ValidationStatus.WARN,
                                message=f"规则 {rule1.rule_id} 和 {rule2.rule_id} 的应用范围重叠，可能存在矛盾",
                                severity="high",
                                affected_items=[rule1.rule_id, rule2.rule_id],
                                suggestion="检查两个规则的内容，确保它们在重叠范围内不相互矛盾"
                            ))

        if not results:
            results.append(ValidationResult(
                item_id="consistency_check",
                item_type=ValidationItemType.CONSISTENCY,
                status=ValidationStatus.PASS,
                message="规则间一致性检查通过",
                severity="info",
            ))

        return results

    @classmethod
    def _validate_coverage(cls, rules: List[SystemRule]) -> List[ValidationResult]:
        """验证规则覆盖完整性"""
        results = []

        # 统计不同规则类型的覆盖情况
        type_coverage = defaultdict(int)
        for rule in rules:
            if rule.status == "active":
                type_coverage[rule.rule_type] += 1

        # 检查是否有关键规则类型缺失
        critical_types = ["validation_constraint", "permission_requirement"]
        for ctype in critical_types:
            if type_coverage.get(ctype, 0) == 0:
                results.append(ValidationResult(
                    item_id=f"coverage_missing_{ctype}",
                    item_type=ValidationItemType.COVERAGE,
                    status=ValidationStatus.WARN,
                    message=f"缺少关键的 {ctype} 类型的活跃规则",
                    severity="high",
                    suggestion=f"建议添加至少一个 {ctype} 类型的规则"
                ))

        if not results:
            results.append(ValidationResult(
                item_id="coverage_check",
                item_type=ValidationItemType.COVERAGE,
                status=ValidationStatus.PASS,
                message="规则覆盖完整性检查通过",
                severity="info",
            ))

        return results

    @classmethod
    def _validate_priority(cls, rules: List[SystemRule]) -> List[ValidationResult]:
        """验证优先级设置的合理性"""
        results = []

        priority_levels = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        active_rules = [r for r in rules if r.status == "active"]

        if not active_rules:
            return [ValidationResult(
                item_id="priority_check",
                item_type=ValidationItemType.PRIORITY,
                status=ValidationStatus.PASS,
                message="没有活跃规则需要检查优先级",
                severity="info",
            )]

        # 检查优先级分布
        priority_dist = defaultdict(int)
        for rule in active_rules:
            priority = rule.priority or "medium"
            priority_dist[priority] += 1

        # 如果所有规则优先级相同，发出警告
        if len(priority_dist) == 1:
            results.append(ValidationResult(
                item_id="priority_uniform",
                item_type=ValidationItemType.PRIORITY,
                status=ValidationStatus.WARN,
                message="所有活跃规则的优先级都相同，建议进行分级",
                severity="medium",
                suggestion="根据业务重要性对规则进行优先级分级"
            ))

        if not results:
            results.append(ValidationResult(
                item_id="priority_check",
                item_type=ValidationItemType.PRIORITY,
                status=ValidationStatus.PASS,
                message="优先级设置合理",
                severity="info",
            ))

        return results

    @classmethod
    def _validate_redundancy(cls, rules: List[SystemRule]) -> List[ValidationResult]:
        """检测冗余规则"""
        results = []

        active_rules = [r for r in rules if r.status == "active"]

        for i, rule1 in enumerate(active_rules):
            for rule2 in active_rules[i + 1:]:
                # 检查两个规则是否高度相似
                similarity = cls._calculate_rule_similarity(rule1, rule2)

                if similarity > 0.8:  # 相似度超过80%
                    results.append(ValidationResult(
                        item_id=f"redundancy_{rule1.rule_id}_{rule2.rule_id}",
                        item_type=ValidationItemType.REDUNDANCY,
                        status=ValidationStatus.WARN,
                        message=f"规则 {rule1.rule_id} 和 {rule2.rule_id} 可能存在冗余 (相似度: {similarity:.1%})",
                        severity="medium",
                        affected_items=[rule1.rule_id, rule2.rule_id],
                        suggestion="检查两个规则的差异，考虑合并或删除其中一个"
                    ))

        if not results:
            results.append(ValidationResult(
                item_id="redundancy_check",
                item_type=ValidationItemType.REDUNDANCY,
                status=ValidationStatus.PASS,
                message="未检测到冗余规则",
                severity="info",
            ))

        return results

    # 辅助方法
    @staticmethod
    def _check_scope_overlap(rule1: SystemRule, rule2: SystemRule) -> bool:
        """检查两个规则的应用范围是否重叠"""
        # 如果任一规则的应用范围为空（表示全部），则重叠
        if not rule1.applicable_workflow_types or not rule2.applicable_workflow_types:
            return True

        # 检查是否有交集
        overlap = set(rule1.applicable_workflow_types) & set(rule2.applicable_workflow_types)
        return len(overlap) > 0

    @staticmethod
    def _check_rule_conflict(rule1: SystemRule, rule2: SystemRule) -> bool:
        """检查两个规则是否相互矛盾"""
        # 简化实现：检查内容是否完全不同
        if not rule1.content or not rule2.content:
            return False

        # 如果内容键完全不同，可能冲突
        keys1 = set(rule1.content.keys())
        keys2 = set(rule2.content.keys())

        return len(keys1 & keys2) == 0

    @staticmethod
    def _calculate_rule_similarity(rule1: SystemRule, rule2: SystemRule) -> float:
        """计算两个规则的相似度 (0-1)"""
        score = 0.0
        factors = 0

        # 比较规则类型
        if rule1.rule_type == rule2.rule_type:
            score += 1.0
        factors += 1

        # 比较适用范围
        if rule1.applicable_workflow_types == rule2.applicable_workflow_types:
            score += 1.0
        factors += 1

        # 比较优先级
        if rule1.priority == rule2.priority:
            score += 1.0
        factors += 1

        return score / factors if factors > 0 else 0.0


# ============================================================================
# 2. 工作流约束验证器
# ============================================================================

class WorkflowConstraintValidator:
    """工作流约束验证器

    验证工作流类型约束、阶段转换合法性、资源可用性、时间约束。
    """

    # 定义合法的阶段转换
    VALID_STAGE_TRANSITIONS = {
        "initiation": ["collecting", "confirmation"],
        "collecting": ["confirmation", "initiation"],
        "confirmation": ["execution", "revision"],
        "execution": ["completion", "revision"],
        "revision": ["collecting", "confirmation"],
        "completion": [],
    }

    WORKFLOW_TYPES = [
        "process_mapping",
        "standard_operation",
        "incident_response",
        "change_management",
        "audit",
    ]

    @classmethod
    def validate(cls, workflow_id: str, constraints: Dict[str, Any]) -> ValidationReport:
        """验证工作流约束"""
        report = ValidationReport(
            overall_status=ValidationStatus.PASS,
            rules_count=1,
            validation_items=0,
            passed=0,
            warnings=0,
            errors=0,
        )

        # 验证工作流类型约束
        report.details.extend(cls._validate_workflow_type_constraint(constraints))

        # 验证阶段转换
        report.details.extend(cls._validate_stage_transitions(constraints))

        # 验证资源约束
        report.details.extend(cls._validate_resource_constraints(constraints))

        # 验证时间约束
        report.details.extend(cls._validate_time_constraints(constraints))

        # 统计结果
        report.validation_items = len(report.details)
        report.passed = sum(1 for d in report.details if d.status == ValidationStatus.PASS)
        report.warnings = sum(1 for d in report.details if d.status == ValidationStatus.WARN)
        report.errors = sum(1 for d in report.details if d.status == ValidationStatus.FAIL)

        if report.errors > 0:
            report.overall_status = ValidationStatus.FAIL
        elif report.warnings > 0:
            report.overall_status = ValidationStatus.WARN

        return report

    @classmethod
    def _validate_workflow_type_constraint(cls, constraints: Dict[str, Any]) -> List[ValidationResult]:
        """验证工作流类型约束"""
        results = []

        workflow_type = constraints.get("workflow_type")
        if workflow_type and workflow_type not in cls.WORKFLOW_TYPES:
            results.append(ValidationResult(
                item_id="invalid_workflow_type",
                item_type=ValidationItemType.CONSTRAINT,
                status=ValidationStatus.FAIL,
                message=f"无效的工作流类型: {workflow_type}",
                severity="critical",
                suggestion=f"必须使用以下类型之一: {', '.join(cls.WORKFLOW_TYPES)}"
            ))
        else:
            results.append(ValidationResult(
                item_id="workflow_type_check",
                item_type=ValidationItemType.CONSTRAINT,
                status=ValidationStatus.PASS,
                message="工作流类型约束有效",
                severity="info",
            ))

        return results

    @classmethod
    def _validate_stage_transitions(cls, constraints: Dict[str, Any]) -> List[ValidationResult]:
        """验证阶段转换的合法性"""
        results = []

        transitions = constraints.get("allowed_transitions", [])

        for transition in transitions:
            from_stage = transition.get("from")
            to_stage = transition.get("to")

            if not from_stage or not to_stage:
                results.append(ValidationResult(
                    item_id=f"invalid_transition_{from_stage}_{to_stage}",
                    item_type=ValidationItemType.TRANSITION,
                    status=ValidationStatus.FAIL,
                    message=f"阶段转换缺少源或目标: {from_stage} -> {to_stage}",
                    severity="high",
                ))
                continue

            # 检查是否是合法的转换
            if from_stage not in cls.VALID_STAGE_TRANSITIONS:
                results.append(ValidationResult(
                    item_id=f"unknown_stage_{from_stage}",
                    item_type=ValidationItemType.TRANSITION,
                    status=ValidationStatus.FAIL,
                    message=f"未知的工作流阶段: {from_stage}",
                    severity="high",
                ))
                continue

            valid_targets = cls.VALID_STAGE_TRANSITIONS[from_stage]
            if to_stage not in valid_targets:
                results.append(ValidationResult(
                    item_id=f"illegal_transition_{from_stage}_{to_stage}",
                    item_type=ValidationItemType.TRANSITION,
                    status=ValidationStatus.WARN,
                    message=f"不推荐的阶段转换: {from_stage} -> {to_stage}",
                    severity="medium",
                    suggestion=f"从 {from_stage} 推荐的转换: {', '.join(valid_targets)}"
                ))

        if not transitions:
            results.append(ValidationResult(
                item_id="stage_transition_check",
                item_type=ValidationItemType.TRANSITION,
                status=ValidationStatus.PASS,
                message="没有阶段转换需要验证",
                severity="info",
            ))

        return results

    @classmethod
    def _validate_resource_constraints(cls, constraints: Dict[str, Any]) -> List[ValidationResult]:
        """验证资源可用性约束"""
        results = []

        resources = constraints.get("required_resources", [])

        if not resources:
            return [ValidationResult(
                item_id="resource_check",
                item_type=ValidationItemType.RESOURCE,
                status=ValidationStatus.PASS,
                message="没有资源约束需要验证",
                severity="info",
            )]

        for resource in resources:
            resource_id = resource.get("id")
            required_count = resource.get("count", 0)

            if not resource_id:
                results.append(ValidationResult(
                    item_id="missing_resource_id",
                    item_type=ValidationItemType.RESOURCE,
                    status=ValidationStatus.FAIL,
                    message="资源约束缺少 ID",
                    severity="high",
                ))
                continue

            if required_count <= 0:
                results.append(ValidationResult(
                    item_id=f"invalid_resource_count_{resource_id}",
                    item_type=ValidationItemType.RESOURCE,
                    status=ValidationStatus.WARN,
                    message=f"资源 {resource_id} 的需求数量无效: {required_count}",
                    severity="medium",
                ))

        if not results:
            results.append(ValidationResult(
                item_id="resource_check",
                item_type=ValidationItemType.RESOURCE,
                status=ValidationStatus.PASS,
                message="资源约束验证通过",
                severity="info",
            ))

        return results

    @classmethod
    def _validate_time_constraints(cls, constraints: Dict[str, Any]) -> List[ValidationResult]:
        """验证时间约束的可行性"""
        results = []

        time_constraints = constraints.get("time_constraints", [])

        if not time_constraints:
            return [ValidationResult(
                item_id="time_constraint_check",
                item_type=ValidationItemType.TIME,
                status=ValidationStatus.PASS,
                message="没有时间约束需要验证",
                severity="info",
            )]

        for tc in time_constraints:
            min_delay = tc.get("min_delay", 0)
            max_delay = tc.get("max_delay", float('inf'))

            if min_delay < 0 or max_delay < 0:
                results.append(ValidationResult(
                    item_id="negative_delay",
                    item_type=ValidationItemType.TIME,
                    status=ValidationStatus.FAIL,
                    message="延迟时间不能为负数",
                    severity="high",
                ))
                continue

            if min_delay > max_delay:
                results.append(ValidationResult(
                    item_id="invalid_delay_range",
                    item_type=ValidationItemType.TIME,
                    status=ValidationStatus.FAIL,
                    message=f"最小延迟 ({min_delay}) 不能大于最大延迟 ({max_delay})",
                    severity="high",
                    suggestion="调整延迟时间范围"
                ))

        if not results:
            results.append(ValidationResult(
                item_id="time_constraint_check",
                item_type=ValidationItemType.TIME,
                status=ValidationStatus.PASS,
                message="时间约束验证通过",
                severity="info",
            ))

        return results


# ============================================================================
# 3. 政策适用验证器
# ============================================================================

class PolicyApplicationValidator:
    """政策适用验证器

    验证政策覆盖范围、决策规则完整性、异常处理覆盖、政策死角检测。
    """

    @classmethod
    def validate(cls, policy_ids: List[str]) -> ValidationReport:
        """验证政策集合的适用性"""
        policies = [RulesManager.get_global_policy(pid) for pid in policy_ids if RulesManager.get_global_policy(pid)]

        report = ValidationReport(
            overall_status=ValidationStatus.PASS,
            rules_count=len(policies),
            validation_items=0,
            passed=0,
            warnings=0,
            errors=0,
        )

        if not policies:
            return report

        # 执行各项验证
        report.details.extend(cls._validate_coverage(policies))
        report.details.extend(cls._validate_decision_rules(policies))
        report.details.extend(cls._validate_exception_handling(policies))
        report.details.extend(cls._detect_policy_gaps(policies))

        # 统计结果
        report.validation_items = len(report.details)
        report.passed = sum(1 for d in report.details if d.status == ValidationStatus.PASS)
        report.warnings = sum(1 for d in report.details if d.status == ValidationStatus.WARN)
        report.errors = sum(1 for d in report.details if d.status == ValidationStatus.FAIL)

        if report.errors > 0:
            report.overall_status = ValidationStatus.FAIL
        elif report.warnings > 0:
            report.overall_status = ValidationStatus.WARN

        return report

    @classmethod
    def _validate_coverage(cls, policies: List[GlobalPolicy]) -> List[ValidationResult]:
        """验证政策覆盖范围"""
        results = []

        # 检查是否有组织级政策
        org_level_policies = [p for p in policies if p.scope == "organization" and p.status == "active"]

        if not org_level_policies:
            results.append(ValidationResult(
                item_id="missing_org_policy",
                item_type=ValidationItemType.POLICY_COVERAGE,
                status=ValidationStatus.WARN,
                message="缺少组织级政策",
                severity="high",
                suggestion="建议定义至少一个组织级政策作为基础"
            ))
        else:
            results.append(ValidationResult(
                item_id="org_policy_coverage",
                item_type=ValidationItemType.POLICY_COVERAGE,
                status=ValidationStatus.PASS,
                message=f"发现 {len(org_level_policies)} 个活跃的组织级政策",
                severity="info",
            ))

        return results

    @classmethod
    def _validate_decision_rules(cls, policies: List[GlobalPolicy]) -> List[ValidationResult]:
        """验证决策规则完整性"""
        results = []

        for policy in policies:
            if not policy.decision_rules:
                results.append(ValidationResult(
                    item_id=f"empty_rules_{policy.policy_id}",
                    item_type=ValidationItemType.DECISION_RULE,
                    status=ValidationStatus.WARN,
                    message=f"政策 {policy.policy_id} 没有定义决策规则",
                    severity="high",
                    suggestion="添加至少一个决策规则来定义政策行为"
                ))
                continue

            # 检查每个规则是否完整
            for rule in policy.decision_rules:
                rule_id = rule.get("rule_id", "unknown")
                condition = rule.get("condition")
                action = rule.get("action")

                if not condition or not action:
                    results.append(ValidationResult(
                        item_id=f"incomplete_rule_{policy.policy_id}_{rule_id}",
                        item_type=ValidationItemType.DECISION_RULE,
                        status=ValidationStatus.FAIL,
                        message=f"规则 {rule_id} 缺少条件或行动",
                        severity="high",
                        affected_items=[policy.policy_id],
                    ))

        if not results:
            results.append(ValidationResult(
                item_id="decision_rules_check",
                item_type=ValidationItemType.DECISION_RULE,
                status=ValidationStatus.PASS,
                message="决策规则完整性检查通过",
                severity="info",
            ))

        return results

    @classmethod
    def _validate_exception_handling(cls, policies: List[GlobalPolicy]) -> List[ValidationResult]:
        """验证异常处理覆盖"""
        results = []

        common_exceptions = ["timeout", "invalid_data", "resource_unavailable", "authorization_error"]

        for policy in policies:
            if policy.status != "active":
                continue

            handled_exceptions = {h.exception_type for h in (policy.exception_handlers or [])}

            # 检查是否覆盖了常见的异常类型
            missing = [e for e in common_exceptions if e not in handled_exceptions]

            if missing:
                results.append(ValidationResult(
                    item_id=f"missing_handlers_{policy.policy_id}",
                    item_type=ValidationItemType.EXCEPTION_HANDLING,
                    status=ValidationStatus.WARN,
                    message=f"政策 {policy.policy_id} 缺少对以下异常的处理: {', '.join(missing)}",
                    severity="medium",
                    suggestion="添加相应的异常处理规则"
                ))
            else:
                results.append(ValidationResult(
                    item_id=f"exception_coverage_{policy.policy_id}",
                    item_type=ValidationItemType.EXCEPTION_HANDLING,
                    status=ValidationStatus.PASS,
                    message=f"政策 {policy.policy_id} 覆盖了所有常见异常类型",
                    severity="info",
                ))

        return results

    @classmethod
    def _detect_policy_gaps(cls, policies: List[GlobalPolicy]) -> List[ValidationResult]:
        """检测政策死角"""
        results = []

        # 检查是否存在未被任何政策覆盖的场景
        active_policies = [p for p in policies if p.status == "active"]

        if not active_policies:
            results.append(ValidationResult(
                item_id="no_active_policies",
                item_type=ValidationItemType.POLICY_GAP,
                status=ValidationStatus.FAIL,
                message="没有活跃的政策",
                severity="critical",
                suggestion="激活至少一个政策以覆盖基本场景"
            ))
            return results

        # 检查政策覆盖的范围
        coverage_scopes = set()
        for policy in active_policies:
            coverage_scopes.add(policy.scope)

        # 检查是否有基础覆盖
        if "organization" not in coverage_scopes:
            results.append(ValidationResult(
                item_id="org_scope_gap",
                item_type=ValidationItemType.POLICY_GAP,
                status=ValidationStatus.WARN,
                message="缺少组织级别的政策覆盖",
                severity="high",
                suggestion="添加组织级政策以提供基础覆盖"
            ))

        if not results:
            results.append(ValidationResult(
                item_id="policy_gap_check",
                item_type=ValidationItemType.POLICY_GAP,
                status=ValidationStatus.PASS,
                message="政策覆盖完整，未检测到死角",
                severity="info",
            ))

        return results


# ============================================================================
# 辅助函数
# ============================================================================

def validate_rule_set(rule_ids: List[str]) -> ValidationReport:
    """验证规则集合"""
    return RuleSetValidator.validate(rule_ids)


def validate_workflow_constraints(workflow_id: str, constraints: Dict[str, Any]) -> ValidationReport:
    """验证工作流约束"""
    return WorkflowConstraintValidator.validate(workflow_id, constraints)


def validate_policy_application(policy_ids: List[str]) -> ValidationReport:
    """验证政策适用"""
    return PolicyApplicationValidator.validate(policy_ids)

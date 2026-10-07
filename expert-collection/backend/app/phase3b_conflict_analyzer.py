"""Phase 3-B Stage 2: 冲突分析引擎

实现冲突类型检测、解决建议生成、冲突严重程度评估。
包括权限冲突、资源冲突、时间冲突、政策冲突分析。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional, Set, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

from .models import (
    SystemRule, WorkflowRelationship, GlobalPolicy,
)
from .rules_manager import RulesManager

logger = logging.getLogger(__name__)


# ============================================================================
# 数据模型
# ============================================================================

class ConflictSeverity(str, Enum):
    """冲突严重程度"""
    CRITICAL = "critical"      # 系统无法继续
    HIGH = "high"              # 功能受阻
    MEDIUM = "medium"          # 部分功能受影响
    LOW = "low"                # 效率问题
    INFO = "info"              # 建议改进


class ConflictType(str, Enum):
    """冲突类型"""
    PERMISSION_CONFLICT = "permission_conflict"
    RESOURCE_CONFLICT = "resource_conflict"
    TIME_CONFLICT = "time_conflict"
    POLICY_CONFLICT = "policy_conflict"
    DATA_CONFLICT = "data_conflict"


@dataclass
class Conflict:
    """单个冲突"""
    conflict_id: str
    conflict_type: ConflictType
    severity: ConflictSeverity
    affected_items: List[str]
    description: str
    resolution_suggestions: List[str] = field(default_factory=list)
    impact_scope: str = ""  # 影响范围描述
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


@dataclass
class ConflictReport:
    """冲突报告"""
    conflict_count: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    info_count: int
    conflicts: List[Conflict] = field(default_factory=list)
    overall_severity: ConflictSeverity = ConflictSeverity.INFO
    summary: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


# ============================================================================
# 1. 权限冲突分析器
# ============================================================================

class PermissionConflictAnalyzer:
    """权限冲突分析器

    检测相互排斥的权限、权限提升矛盾、权限继承冲突、角色权限不一致。
    """

    @classmethod
    def analyze(cls) -> ConflictReport:
        """分析权限冲突"""
        report = ConflictReport(
            conflict_count=0,
            critical_count=0,
            high_count=0,
            medium_count=0,
            low_count=0,
            info_count=0,
        )

        # 获取所有权限相关的规则
        permission_rules = RulesManager.list_system_rules(rule_type="permission_requirement")

        if not permission_rules:
            return report

        # 检测相互排斥的权限
        report.conflicts.extend(cls._detect_mutually_exclusive_permissions(permission_rules))

        # 检测权限提升矛盾
        report.conflicts.extend(cls._detect_privilege_escalation_conflicts(permission_rules))

        # 检测权限继承冲突
        report.conflicts.extend(cls._detect_inheritance_conflicts(permission_rules))

        # 统计冲突
        cls._count_conflicts(report)

        return report

    @classmethod
    def _detect_mutually_exclusive_permissions(cls, rules: List[SystemRule]) -> List[Conflict]:
        """检测相互排斥的权限"""
        conflicts = []

        for i, rule1 in enumerate(rules):
            for rule2 in rules[i + 1:]:
                if not cls._are_roles_exclusive(rule1.content, rule2.content):
                    continue

                # 检查是否应用于相同的工作流
                if cls._check_scope_overlap(rule1, rule2):
                    conflicts.append(Conflict(
                        conflict_id=f"perm_exclusive_{rule1.rule_id}_{rule2.rule_id}",
                        conflict_type=ConflictType.PERMISSION_CONFLICT,
                        severity=ConflictSeverity.HIGH,
                        affected_items=[rule1.rule_id, rule2.rule_id],
                        description=f"规则 {rule1.rule_name} 和 {rule2.rule_name} 要求相互排斥的权限",
                        resolution_suggestions=[
                            "检查规则的适用范围，确保它们不重叠",
                            "考虑修改其中一个规则的权限要求",
                            "添加优先级来解决冲突",
                        ],
                        impact_scope="可能导致某些用户无法完成操作"
                    ))

        return conflicts

    @classmethod
    def _detect_privilege_escalation_conflicts(cls, rules: List[SystemRule]) -> List[Conflict]:
        """检测权限提升矛盾"""
        conflicts = []

        # 分析规则的权限要求
        for i, rule1 in enumerate(rules):
            for rule2 in rules[i + 1:]:
                # 检查rule1是否要求更高的权限
                if cls._is_higher_privilege(rule1.content, rule2.content):
                    # 检查条件是否相反
                    if cls._are_conditions_opposite(rule1, rule2):
                        conflicts.append(Conflict(
                            conflict_id=f"perm_escalation_{rule1.rule_id}_{rule2.rule_id}",
                            conflict_type=ConflictType.PERMISSION_CONFLICT,
                            severity=ConflictSeverity.MEDIUM,
                            affected_items=[rule1.rule_id, rule2.rule_id],
                            description=f"规则 {rule1.rule_name} 要求的权限高于 {rule2.rule_name}",
                            resolution_suggestions=[
                                "审查权限级别是否合理",
                                "确认条件是否应该不同",
                                "考虑统一权限要求",
                            ],
                            impact_scope="可能导致权限提升的不一致"
                        ))

        return conflicts

    @classmethod
    def _detect_inheritance_conflicts(cls, rules: List[SystemRule]) -> List[Conflict]:
        """检测权限继承冲突"""
        conflicts = []

        # 检查是否存在权限继承的循环
        inheritance_graph = defaultdict(set)

        for rule in rules:
            if "inherited_from" in rule.content:
                parent = rule.content.get("inherited_from")
                inheritance_graph[rule.rule_id].add(parent)

        # 检测循环
        for rule_id, parents in inheritance_graph.items():
            if cls._has_circular_inheritance(rule_id, parents, inheritance_graph):
                conflicts.append(Conflict(
                    conflict_id=f"perm_circular_{rule_id}",
                    conflict_type=ConflictType.PERMISSION_CONFLICT,
                    severity=ConflictSeverity.CRITICAL,
                    affected_items=[rule_id] + list(parents),
                    description=f"检测到权限继承的循环依赖",
                    resolution_suggestions=[
                        "移除循环的继承关系",
                        "重新设计权限层次结构",
                    ],
                    impact_scope="导致系统无法正确解析权限"
                ))

        return conflicts

    # 辅助方法
    @staticmethod
    def _are_roles_exclusive(content1: Dict, content2: Dict) -> bool:
        """检查两个权限要求是否相互排斥"""
        roles1 = set(content1.get("required_roles", []))
        roles2 = set(content2.get("required_roles", []))

        # 简化实现：如果角色集合完全不同，视为排斥
        return len(roles1 & roles2) == 0 and len(roles1) > 0 and len(roles2) > 0

    @staticmethod
    def _check_scope_overlap(rule1: SystemRule, rule2: SystemRule) -> bool:
        """检查两个规则的应用范围是否重叠"""
        if not rule1.applicable_workflow_types or not rule2.applicable_workflow_types:
            return True
        return len(set(rule1.applicable_workflow_types) & set(rule2.applicable_workflow_types)) > 0

    @staticmethod
    def _is_higher_privilege(content1: Dict, content2: Dict) -> bool:
        """检查content1是否要求更高的权限"""
        level1 = content1.get("privilege_level", 0)
        level2 = content2.get("privilege_level", 0)
        return level1 > level2

    @staticmethod
    def _are_conditions_opposite(rule1: SystemRule, rule2: SystemRule) -> bool:
        """检查两个规则的条件是否相反"""
        # 简化实现：如果描述中包含相反的关键词
        desc1 = (rule1.description or "").lower()
        desc2 = (rule2.description or "").lower()

        opposite_pairs = [("high", "low"), ("large", "small"), ("must", "must not")]
        for word1, word2 in opposite_pairs:
            if word1 in desc1 and word2 in desc2:
                return True
        return False

    @staticmethod
    def _has_circular_inheritance(node: str, parents: Set[str], graph: Dict[str, Set[str]]) -> bool:
        """检测循环继承"""
        visited = set()

        def dfs(current):
            if current in visited:
                return True
            visited.add(current)

            for parent in graph.get(current, set()):
                if parent == node:
                    return True
                if dfs(parent):
                    return True

            visited.remove(current)
            return False

        return dfs(node)


# ============================================================================
# 2. 资源冲突分析器
# ============================================================================

class ResourceConflictAnalyzer:
    """资源冲突分析器

    检测资源竞争、资源死锁风险、资源分配冲突、资源可用性验证。
    """

    @classmethod
    def analyze(cls) -> ConflictReport:
        """分析资源冲突"""
        report = ConflictReport(
            conflict_count=0,
            critical_count=0,
            high_count=0,
            medium_count=0,
            low_count=0,
            info_count=0,
        )

        # 获取所有工作流关系
        relationships = RulesManager.list_workflow_relationships()

        if not relationships:
            return report

        # 检测资源竞争
        report.conflicts.extend(cls._detect_resource_contention(relationships))

        # 检测死锁风险
        report.conflicts.extend(cls._detect_deadlock_risk(relationships))

        # 检测资源分配冲突
        report.conflicts.extend(cls._detect_allocation_conflicts(relationships))

        # 统计冲突
        cls._count_conflicts(report)

        return report

    @classmethod
    def _detect_resource_contention(cls, relationships: List[WorkflowRelationship]) -> List[Conflict]:
        """检测资源竞争"""
        conflicts = []

        # 统计每个资源的需求
        resource_usage = defaultdict(list)

        for rel in relationships:
            for constraint in (rel.constraints or []):
                if hasattr(constraint, 'resource_id'):
                    resource_id = constraint.resource_id
                    resource_usage[resource_id].append(rel.relationship_id)

        # 检测过度使用的资源
        for resource_id, users in resource_usage.items():
            if len(users) > 2:  # 超过2个工作流竞争同一资源
                conflicts.append(Conflict(
                    conflict_id=f"resource_contention_{resource_id}",
                    conflict_type=ConflictType.RESOURCE_CONFLICT,
                    severity=ConflictSeverity.MEDIUM,
                    affected_items=users[:3],  # 只列出前3个
                    description=f"资源 {resource_id} 被 {len(users)} 个工作流竞争",
                    resolution_suggestions=[
                        "增加资源的可用性",
                        "优化资源的使用时间",
                        "实现资源的分配策略",
                    ],
                    impact_scope="可能导致资源竞争和性能下降"
                ))

        return conflicts

    @classmethod
    def _detect_deadlock_risk(cls, relationships: List[WorkflowRelationship]) -> List[Conflict]:
        """检测死锁风险"""
        conflicts = []

        # 构建资源依赖图
        for i, rel1 in enumerate(relationships):
            for rel2 in relationships[i + 1:]:
                # 检查是否存在循环资源依赖
                if cls._has_circular_dependency(rel1, rel2):
                    conflicts.append(Conflict(
                        conflict_id=f"resource_deadlock_{rel1.relationship_id}_{rel2.relationship_id}",
                        conflict_type=ConflictType.RESOURCE_CONFLICT,
                        severity=ConflictSeverity.CRITICAL,
                        affected_items=[rel1.relationship_id, rel2.relationship_id],
                        description=f"工作流 {rel1.source_workflow_id} 和 {rel2.source_workflow_id} 之间存在死锁风险",
                        resolution_suggestions=[
                            "重新设计工作流的资源获取顺序",
                            "添加超时机制",
                            "实现死锁检测和恢复",
                        ],
                        impact_scope="导致系统挂起"
                    ))

        return conflicts

    @classmethod
    def _detect_allocation_conflicts(cls, relationships: List[WorkflowRelationship]) -> List[Conflict]:
        """检测资源分配冲突"""
        conflicts = []

        for rel in relationships:
            if not rel.constraints:
                continue

            for i, constraint1 in enumerate(rel.constraints):
                for constraint2 in rel.constraints[i + 1:]:
                    # 检查是否分配冲突（同一资源分配给两个不兼容的使用者）
                    if cls._are_allocations_conflicting(constraint1, constraint2):
                        conflicts.append(Conflict(
                            conflict_id=f"resource_alloc_{rel.relationship_id}",
                            conflict_type=ConflictType.RESOURCE_CONFLICT,
                            severity=ConflictSeverity.HIGH,
                            affected_items=[rel.relationship_id],
                            description=f"工作流 {rel.source_workflow_id} 的资源分配存在冲突",
                            resolution_suggestions=[
                                "检查资源分配策略",
                                "修改资源使用计划",
                                "添加资源隔离机制",
                            ],
                            impact_scope="可能导致资源冲突和操作失败"
                        ))

        return conflicts

    # 辅助方法
    @staticmethod
    def _has_circular_dependency(rel1: WorkflowRelationship, rel2: WorkflowRelationship) -> bool:
        """检查是否存在循环资源依赖"""
        # 简化实现：检查rel1的目标是否是rel2的源
        if rel1.target_workflow_id == rel2.source_workflow_id:
            if rel2.target_workflow_id == rel1.source_workflow_id:
                return True
        return False

    @staticmethod
    def _are_allocations_conflicting(constraint1: Any, constraint2: Any) -> bool:
        """检查两个资源分配是否冲突"""
        # 简化实现：检查是否有相同的资源但用途不同
        if hasattr(constraint1, 'resource_id') and hasattr(constraint2, 'resource_id'):
            if constraint1.resource_id == constraint2.resource_id:
                usage1 = getattr(constraint1, 'usage_type', '')
                usage2 = getattr(constraint2, 'usage_type', '')
                return usage1 != usage2 and usage1 and usage2
        return False


# ============================================================================
# 3. 时间冲突分析器
# ============================================================================

class TimeConflictAnalyzer:
    """时间冲突分析器

    检测时间约束冲突、死线冲突、延迟冲突、时间窗口验证。
    """

    @classmethod
    def analyze(cls) -> ConflictReport:
        """分析时间冲突"""
        report = ConflictReport(
            conflict_count=0,
            critical_count=0,
            high_count=0,
            medium_count=0,
            low_count=0,
            info_count=0,
        )

        # 获取所有工作流关系
        relationships = RulesManager.list_workflow_relationships()

        if not relationships:
            return report

        # 检测时间约束冲突
        report.conflicts.extend(cls._detect_time_constraint_conflicts(relationships))

        # 检测死线冲突
        report.conflicts.extend(cls._detect_deadline_conflicts(relationships))

        # 检测延迟冲突
        report.conflicts.extend(cls._detect_delay_conflicts(relationships))

        # 统计冲突
        cls._count_conflicts(report)

        return report

    @classmethod
    def _detect_time_constraint_conflicts(cls, relationships: List[WorkflowRelationship]) -> List[Conflict]:
        """检测时间约束冲突"""
        conflicts = []

        for rel in relationships:
            if not rel.constraints:
                continue

            time_constraints = [c for c in rel.constraints if hasattr(c, 'min_delay')]

            for i, tc1 in enumerate(time_constraints):
                for tc2 in time_constraints[i + 1:]:
                    if cls._are_time_constraints_conflicting(tc1, tc2):
                        conflicts.append(Conflict(
                            conflict_id=f"time_conflict_{rel.relationship_id}",
                            conflict_type=ConflictType.TIME_CONFLICT,
                            severity=ConflictSeverity.MEDIUM,
                            affected_items=[rel.relationship_id],
                            description=f"工作流关系 {rel.relationship_id} 的时间约束相互矛盾",
                            resolution_suggestions=[
                                "调整时间约束的范围",
                                "添加优先级来解决冲突",
                                "分离冲突的约束",
                            ],
                            impact_scope="可能导致工作流无法按时完成"
                        ))

        return conflicts

    @classmethod
    def _detect_deadline_conflicts(cls, relationships: List[WorkflowRelationship]) -> List[Conflict]:
        """检测死线冲突"""
        conflicts = []

        # 统计所有死线
        deadlines = {}
        for rel in relationships:
            for constraint in (rel.constraints or []):
                if hasattr(constraint, 'deadline'):
                    deadline = constraint.deadline
                    if deadline:
                        if deadline in deadlines:
                            deadlines[deadline].append(rel.relationship_id)
                        else:
                            deadlines[deadline] = [rel.relationship_id]

        # 检查多个工作流是否共享死线
        for deadline, relationships_list in deadlines.items():
            if len(relationships_list) > 1:
                conflicts.append(Conflict(
                    conflict_id=f"deadline_conflict_{deadline}",
                    conflict_type=ConflictType.TIME_CONFLICT,
                    severity=ConflictSeverity.MEDIUM,
                    affected_items=relationships_list,
                    description=f"多个工作流共享同一死线: {deadline}",
                    resolution_suggestions=[
                        "调整死线避免重叠",
                        "优先化工作流执行",
                        "增加资源以满足共同死线",
                    ],
                    impact_scope="可能导致死线冲突"
                ))

        return conflicts

    @classmethod
    def _detect_delay_conflicts(cls, relationships: List[WorkflowRelationship]) -> List[Conflict]:
        """检测延迟冲突"""
        conflicts = []

        for i, rel1 in enumerate(relationships):
            for rel2 in relationships[i + 1:]:
                # 检查是否是连续的关系
                if rel1.target_workflow_id == rel2.source_workflow_id:
                    delay1 = cls._get_total_delay(rel1)
                    delay2 = cls._get_total_delay(rel2)
                    total_delay = delay1 + delay2

                    # 检查总延迟是否超过合理范围
                    if total_delay > 86400:  # 超过24小时
                        conflicts.append(Conflict(
                            conflict_id=f"delay_conflict_{rel1.relationship_id}_{rel2.relationship_id}",
                            conflict_type=ConflictType.TIME_CONFLICT,
                            severity=ConflictSeverity.LOW,
                            affected_items=[rel1.relationship_id, rel2.relationship_id],
                            description=f"工作流链的总延迟超过24小时: {total_delay}秒",
                            resolution_suggestions=[
                                "优化工作流执行效率",
                                "并行化可并行的步骤",
                                "考虑重新设计工作流结构",
                            ],
                            impact_scope="可能导致端到端延迟过长"
                        ))

        return conflicts

    # 辅助方法
    @staticmethod
    def _are_time_constraints_conflicting(tc1: Any, tc2: Any) -> bool:
        """检查两个时间约束是否冲突"""
        min1 = getattr(tc1, 'min_delay', 0)
        max1 = getattr(tc1, 'max_delay', float('inf'))
        min2 = getattr(tc2, 'min_delay', 0)
        max2 = getattr(tc2, 'max_delay', float('inf'))

        # 检查范围是否不相交
        return max1 < min2 or max2 < min1

    @staticmethod
    def _get_total_delay(rel: WorkflowRelationship) -> float:
        """获取关系的总延迟"""
        total = 0
        for constraint in (rel.constraints or []):
            if hasattr(constraint, 'min_delay'):
                total += constraint.min_delay
        return total


# ============================================================================
# 4. 政策冲突分析器
# ============================================================================

class PolicyConflictAnalyzer:
    """政策冲突分析器

    检测决策规则冲突、政策覆盖冲突、异常处理冲突、政策优先级冲突。
    """

    @classmethod
    def analyze(cls) -> ConflictReport:
        """分析政策冲突"""
        report = ConflictReport(
            conflict_count=0,
            critical_count=0,
            high_count=0,
            medium_count=0,
            low_count=0,
            info_count=0,
        )

        # 获取所有活跃政策
        policies = RulesManager.list_global_policies(status="active")

        if not policies:
            return report

        # 检测决策规则冲突
        report.conflicts.extend(cls._detect_decision_rule_conflicts(policies))

        # 检测政策覆盖冲突
        report.conflicts.extend(cls._detect_coverage_conflicts(policies))

        # 检测异常处理冲突
        report.conflicts.extend(cls._detect_exception_handling_conflicts(policies))

        # 统计冲突
        cls._count_conflicts(report)

        return report

    @classmethod
    def _detect_decision_rule_conflicts(cls, policies: List[GlobalPolicy]) -> List[Conflict]:
        """检测决策规则冲突"""
        conflicts = []

        for policy in policies:
            if not policy.decision_rules:
                continue

            rules = policy.decision_rules
            for i, rule1 in enumerate(rules):
                for rule2 in rules[i + 1:]:
                    # 检查两个规则的条件是否重叠且行动不同
                    if cls._are_conditions_overlapping(rule1, rule2):
                        if rule1.get('action') != rule2.get('action'):
                            conflicts.append(Conflict(
                                conflict_id=f"policy_decision_{policy.policy_id}_{rule1.get('rule_id')}",
                                conflict_type=ConflictType.POLICY_CONFLICT,
                                severity=ConflictSeverity.HIGH,
                                affected_items=[policy.policy_id],
                                description=f"政策 {policy.policy_name} 中的规则条件重叠但行动冲突",
                                resolution_suggestions=[
                                    "调整规则的条件以避免重叠",
                                    "统一规则的行动",
                                    "添加优先级来解决冲突",
                                ],
                                impact_scope="导致决策结果不一致"
                            ))

        return conflicts

    @classmethod
    def _detect_coverage_conflicts(cls, policies: List[GlobalPolicy]) -> List[Conflict]:
        """检测政策覆盖冲突"""
        conflicts = []

        # 按范围分组政策
        policies_by_scope = defaultdict(list)
        for policy in policies:
            policies_by_scope[policy.scope].append(policy)

        # 检查同范围的政策是否有重叠
        for scope, scope_policies in policies_by_scope.items():
            if scope != "organization":
                continue

            if len(scope_policies) > 1:
                conflicts.append(Conflict(
                    conflict_id=f"policy_coverage_{scope}",
                    conflict_type=ConflictType.POLICY_CONFLICT,
                    severity=ConflictSeverity.MEDIUM,
                    affected_items=[p.policy_id for p in scope_policies],
                    description=f"存在 {len(scope_policies)} 个 {scope} 级别的政策，可能存在覆盖重叠",
                    resolution_suggestions=[
                        "整合重叠的政策",
                        "清晰定义每个政策的适用范围",
                        "建立政策优先级",
                    ],
                    impact_scope="可能导致政策应用的不确定性"
                ))

        return conflicts

    @classmethod
    def _detect_exception_handling_conflicts(cls, policies: List[GlobalPolicy]) -> List[Conflict]:
        """检测异常处理冲突"""
        conflicts = []

        for policy in policies:
            if not policy.exception_handlers:
                continue

            handlers = policy.exception_handlers
            handled_exceptions = {}

            for handler in handlers:
                exc_type = handler.exception_type
                if exc_type in handled_exceptions:
                    # 同一异常类型的多个处理器
                    conflicts.append(Conflict(
                        conflict_id=f"policy_exception_{policy.policy_id}_{exc_type}",
                        conflict_type=ConflictType.POLICY_CONFLICT,
                        severity=ConflictSeverity.MEDIUM,
                        affected_items=[policy.policy_id],
                        description=f"政策 {policy.policy_name} 对异常类型 {exc_type} 有多个处理器",
                        resolution_suggestions=[
                            "合并重复的异常处理器",
                            "明确定义处理器的优先级",
                            "分离不同条件下的处理",
                        ],
                        impact_scope="导致异常处理的不确定性"
                    ))
                else:
                    handled_exceptions[exc_type] = handler

        return conflicts

    # 辅助方法
    @staticmethod
    def _are_conditions_overlapping(rule1: Dict, rule2: Dict) -> bool:
        """检查两个规则的条件是否重叠"""
        cond1 = rule1.get('condition', '')
        cond2 = rule2.get('condition', '')

        # 简化实现：完全相同的条件视为重叠
        if cond1 == cond2:
            return True

        # 检查是否是包含关系（很简化的检查）
        if cond1 in cond2 or cond2 in cond1:
            return True

        return False


# ============================================================================
# 5. 冲突解决建议引擎
# ============================================================================

class ConflictResolutionEngine:
    """冲突解决建议引擎

    生成冲突解决建议、评估解决方案风险、提供优先级建议、生成变更计划。
    """

    @classmethod
    def analyze_all_conflicts(cls) -> ConflictReport:
        """执行全面的冲突分析"""
        logger.info("执行全面的冲突分析")

        # 执行所有分析器
        permission_report = PermissionConflictAnalyzer.analyze()
        resource_report = ResourceConflictAnalyzer.analyze()
        time_report = TimeConflictAnalyzer.analyze()
        policy_report = PolicyConflictAnalyzer.analyze()

        # 合并报告
        all_conflicts = (
            permission_report.conflicts +
            resource_report.conflicts +
            time_report.conflicts +
            policy_report.conflicts
        )

        # 按严重程度排序
        all_conflicts.sort(key=lambda c: cls._severity_score(c.severity), reverse=True)

        # 创建综合报告
        overall_report = ConflictReport(
            conflict_count=len(all_conflicts),
            critical_count=sum(1 for c in all_conflicts if c.severity == ConflictSeverity.CRITICAL),
            high_count=sum(1 for c in all_conflicts if c.severity == ConflictSeverity.HIGH),
            medium_count=sum(1 for c in all_conflicts if c.severity == ConflictSeverity.MEDIUM),
            low_count=sum(1 for c in all_conflicts if c.severity == ConflictSeverity.LOW),
            info_count=sum(1 for c in all_conflicts if c.severity == ConflictSeverity.INFO),
            conflicts=all_conflicts,
        )

        # 确定整体严重程度
        if overall_report.critical_count > 0:
            overall_report.overall_severity = ConflictSeverity.CRITICAL
        elif overall_report.high_count > 0:
            overall_report.overall_severity = ConflictSeverity.HIGH
        elif overall_report.medium_count > 0:
            overall_report.overall_severity = ConflictSeverity.MEDIUM
        elif overall_report.low_count > 0:
            overall_report.overall_severity = ConflictSeverity.LOW

        # 生成摘要
        overall_report.summary = cls._generate_summary(overall_report)

        return overall_report

    @classmethod
    def generate_resolution_plan(cls, conflicts: List[Conflict]) -> Dict[str, Any]:
        """生成冲突解决计划"""
        plan = {
            "total_conflicts": len(conflicts),
            "critical_items": [],
            "implementation_steps": [],
            "estimated_effort": 0,
            "risk_assessment": {},
        }

        # 优先处理严重冲突
        critical = [c for c in conflicts if c.severity == ConflictSeverity.CRITICAL]
        plan["critical_items"] = [c.conflict_id for c in critical]

        # 生成实施步骤
        for i, conflict in enumerate(sorted(conflicts, key=lambda c: cls._severity_score(c.severity), reverse=True)):
            step = {
                "step": i + 1,
                "conflict_id": conflict.conflict_id,
                "severity": conflict.severity.value,
                "actions": conflict.resolution_suggestions[:2],  # 前两个建议
                "estimated_hours": cls._estimate_effort(conflict),
            }
            plan["implementation_steps"].append(step)
            plan["estimated_effort"] += step["estimated_hours"]

        return plan

    # 辅助方法
    @staticmethod
    def _severity_score(severity: ConflictSeverity) -> int:
        """获取严重程度的数值分数"""
        scores = {
            ConflictSeverity.CRITICAL: 5,
            ConflictSeverity.HIGH: 4,
            ConflictSeverity.MEDIUM: 3,
            ConflictSeverity.LOW: 2,
            ConflictSeverity.INFO: 1,
        }
        return scores.get(severity, 0)

    @staticmethod
    def _generate_summary(report: ConflictReport) -> str:
        """生成冲突报告摘要"""
        return (
            f"发现 {report.conflict_count} 个冲突: "
            f"{report.critical_count} 个严重, {report.high_count} 个高危, "
            f"{report.medium_count} 个中等, {report.low_count} 个轻微"
        )

    @staticmethod
    def _estimate_effort(conflict: Conflict) -> float:
        """估计解决冲突的工作量（小时）"""
        severity_effort = {
            ConflictSeverity.CRITICAL: 8,
            ConflictSeverity.HIGH: 4,
            ConflictSeverity.MEDIUM: 2,
            ConflictSeverity.LOW: 1,
            ConflictSeverity.INFO: 0.5,
        }
        return severity_effort.get(conflict.severity, 1)


# ============================================================================
# 辅助函数
# ============================================================================

def _count_conflicts(report: ConflictReport):
    """统计冲突数量"""
    report.critical_count = sum(1 for c in report.conflicts if c.severity == ConflictSeverity.CRITICAL)
    report.high_count = sum(1 for c in report.conflicts if c.severity == ConflictSeverity.HIGH)
    report.medium_count = sum(1 for c in report.conflicts if c.severity == ConflictSeverity.MEDIUM)
    report.low_count = sum(1 for c in report.conflicts if c.severity == ConflictSeverity.LOW)
    report.info_count = sum(1 for c in report.conflicts if c.severity == ConflictSeverity.INFO)
    report.conflict_count = len(report.conflicts)


# 为分析器添加_count_conflicts方法
PermissionConflictAnalyzer._count_conflicts = staticmethod(_count_conflicts)
ResourceConflictAnalyzer._count_conflicts = staticmethod(_count_conflicts)
TimeConflictAnalyzer._count_conflicts = staticmethod(_count_conflicts)
PolicyConflictAnalyzer._count_conflicts = staticmethod(_count_conflicts)

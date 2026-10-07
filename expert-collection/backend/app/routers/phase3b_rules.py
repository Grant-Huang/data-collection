"""Phase 3-B: 系统规则、工作流关系、全局政策的REST API

提供规则、关系、政策的CRUD操作和查询接口。
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel

from .. import db
from ..models import (
    SystemRule, SystemRuleUpdate,
    WorkflowRelationship, WorkflowRelationshipUpdate,
    GlobalPolicy, GlobalPolicyUpdate,
    ValidationIssue, RuleValidationIssue,
)
from ..rules_manager import RulesManager
from ..phase3b_validators import (
    SystemRuleValidator, WorkflowRelationshipValidator,
    GlobalPolicyValidator, ConflictDetector, ImpactAnalyzer,
)

router = APIRouter(prefix="/api/phase3b", tags=["phase3b"])
logger = logging.getLogger(__name__)


# --- SystemRule 路由 ---

@router.post("/system-rules", response_model=SystemRule)
async def create_system_rule(
    rule_name: str,
    rule_type: str,
    description: str,
    content: dict,
    created_by: str,
    applicable_workflow_types: Optional[list[str]] = None,
    applicable_stages: Optional[list[str]] = None,
    requires_approval: bool = False,
    priority: str = "medium",
    tags: Optional[list[str]] = None,
):
    """创建系统规则"""
    try:
        rule = RulesManager.create_system_rule(
            rule_name=rule_name,
            rule_type=rule_type,
            description=description,
            content=content,
            created_by=created_by,
            applicable_workflow_types=applicable_workflow_types,
            applicable_stages=applicable_stages,
            requires_approval=requires_approval,
            priority=priority,
            tags=tags,
        )

        # 验证新创建的规则
        issues = SystemRuleValidator.validate(rule)
        if any(i.issue_type == "error" for i in issues):
            logger.warning(f"Validation issues for new rule {rule.rule_id}: {issues}")

        return rule
    except Exception as e:
        logger.error(f"Failed to create system rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/system-rules/{rule_id}", response_model=Optional[SystemRule])
async def get_system_rule(rule_id: str):
    """获取系统规则"""
    try:
        rule = RulesManager.get_system_rule(rule_id)
        if not rule:
            raise HTTPException(status_code=404, detail="Rule not found")
        return rule
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get system rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/system-rules", response_model=list[SystemRule])
async def list_system_rules(
    status: Optional[str] = Query(None),
    rule_type: Optional[str] = Query(None),
    workflow_type: Optional[str] = Query(None),
):
    """列表查询系统规则"""
    try:
        rules = RulesManager.list_system_rules(
            status=status,
            rule_type=rule_type,
            workflow_type=workflow_type,
        )
        return rules
    except Exception as e:
        logger.error(f"Failed to list system rules: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/system-rules/{rule_id}", response_model=Optional[SystemRule])
async def update_system_rule(
    rule_id: str,
    update_data: SystemRuleUpdate,
    updated_by: str,
):
    """更新系统规则"""
    try:
        rule = RulesManager.update_system_rule(rule_id, update_data, updated_by)
        if not rule:
            raise HTTPException(status_code=404, detail="Rule not found")

        # 验证更新后的规则
        issues = SystemRuleValidator.validate(rule)
        if any(i.issue_type == "error" for i in issues):
            logger.warning(f"Validation issues after update: {issues}")

        return rule
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update system rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/system-rules/{rule_id}/activate", response_model=Optional[SystemRule])
async def activate_system_rule(rule_id: str, activated_by: str):
    """激活系统规则"""
    try:
        rule = RulesManager.activate_system_rule(rule_id, activated_by)
        if not rule:
            raise HTTPException(status_code=404, detail="Rule not found or already active")

        # 分析激活这个规则的影响
        impact = ImpactAnalyzer.analyze_rule_change_impact(rule_id)
        if impact and impact.risk_level in ("high", "critical"):
            logger.warning(f"High/critical impact detected for rule {rule_id}: {impact}")

        return rule
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to activate system rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/system-rules/{rule_id}/validate", response_model=list[RuleValidationIssue])
async def validate_system_rule(rule_id: str):
    """验证系统规则"""
    try:
        rule = RulesManager.get_system_rule(rule_id)
        if not rule:
            raise HTTPException(status_code=404, detail="Rule not found")

        issues = SystemRuleValidator.validate(rule)
        return issues
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to validate system rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/system-rules/{rule_id}/impact", response_model=dict)
async def analyze_rule_impact(rule_id: str):
    """分析规则变更影响"""
    try:
        impact = ImpactAnalyzer.analyze_rule_change_impact(rule_id)
        if not impact:
            raise HTTPException(status_code=404, detail="Rule not found")

        return impact.model_dump()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to analyze rule impact: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- WorkflowRelationship 路由 ---

@router.post("/workflow-relationships", response_model=WorkflowRelationship)
async def create_workflow_relationship(
    relationship_type: str,
    source_workflow_id: str,
    target_workflow_id: str,
    description: str,
    created_by: str,
    condition: Optional[str] = None,
    constraints: Optional[list] = None,
    tags: Optional[list[str]] = None,
):
    """创建工作流关系"""
    try:
        rel = RulesManager.create_workflow_relationship(
            relationship_type=relationship_type,
            source_workflow_id=source_workflow_id,
            target_workflow_id=target_workflow_id,
            description=description,
            created_by=created_by,
            condition=condition,
            constraints=constraints,
            tags=tags,
        )

        # 验证新关系
        issues = WorkflowRelationshipValidator.validate(rel)
        if any(i.issue_type == "error" for i in issues):
            logger.warning(f"Validation issues for new relationship {rel.relationship_id}: {issues}")

        # 检测循环
        cycles = WorkflowRelationshipValidator.detect_cycles()
        if source_workflow_id in cycles:
            logger.warning(f"Circular dependency detected involving {source_workflow_id}")

        return rel
    except Exception as e:
        logger.error(f"Failed to create workflow relationship: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workflow-relationships/{rel_id}", response_model=Optional[WorkflowRelationship])
async def get_workflow_relationship(rel_id: str):
    """获取工作流关系"""
    try:
        rel = RulesManager.get_workflow_relationship(rel_id)
        if not rel:
            raise HTTPException(status_code=404, detail="Relationship not found")
        return rel
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get workflow relationship: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workflow-relationships", response_model=list[WorkflowRelationship])
async def list_workflow_relationships(
    source_workflow_id: Optional[str] = Query(None),
    target_workflow_id: Optional[str] = Query(None),
    relationship_type: Optional[str] = Query(None),
):
    """列表查询工作流关系"""
    try:
        rels = RulesManager.list_workflow_relationships(
            source_workflow_id=source_workflow_id,
            target_workflow_id=target_workflow_id,
            relationship_type=relationship_type,
        )
        return rels
    except Exception as e:
        logger.error(f"Failed to list workflow relationships: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/workflow-relationships/{rel_id}", response_model=Optional[WorkflowRelationship])
async def update_workflow_relationship(
    rel_id: str,
    update_data: WorkflowRelationshipUpdate,
    updated_by: str,
):
    """更新工作流关系"""
    try:
        rel = RulesManager.update_workflow_relationship(rel_id, update_data, updated_by)
        if not rel:
            raise HTTPException(status_code=404, detail="Relationship not found")

        # 验证更新
        issues = WorkflowRelationshipValidator.validate(rel)
        if any(i.issue_type == "error" for i in issues):
            logger.warning(f"Validation issues after relationship update: {issues}")

        return rel
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update workflow relationship: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workflow-relationships/detect-cycles", response_model=dict)
async def detect_cycles():
    """检测循环依赖"""
    try:
        cycles = WorkflowRelationshipValidator.detect_cycles()
        return {"cycles": cycles, "has_cycles": bool(cycles)}
    except Exception as e:
        logger.error(f"Failed to detect cycles: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- GlobalPolicy 路由 ---

@router.post("/global-policies", response_model=GlobalPolicy)
async def create_global_policy(
    policy_name: str,
    description: str,
    scope: str,
    created_by: str,
    scope_target: Optional[str] = None,
    decision_rules: Optional[list] = None,
    exception_handlers: Optional[list] = None,
    requires_approval: bool = False,
    priority: str = "medium",
    tags: Optional[list[str]] = None,
):
    """创建全局政策"""
    try:
        policy = RulesManager.create_global_policy(
            policy_name=policy_name,
            description=description,
            scope=scope,
            created_by=created_by,
            scope_target=scope_target,
            decision_rules=decision_rules,
            exception_handlers=exception_handlers,
            requires_approval=requires_approval,
            priority=priority,
            tags=tags,
        )

        # 验证政策
        issues = GlobalPolicyValidator.validate(policy)
        if any(i.issue_type == "error" for i in issues):
            logger.warning(f"Validation issues for new policy {policy.policy_id}: {issues}")

        return policy
    except Exception as e:
        logger.error(f"Failed to create global policy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/global-policies/{policy_id}", response_model=Optional[GlobalPolicy])
async def get_global_policy(policy_id: str):
    """获取全局政策"""
    try:
        policy = RulesManager.get_global_policy(policy_id)
        if not policy:
            raise HTTPException(status_code=404, detail="Policy not found")
        return policy
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get global policy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/global-policies", response_model=list[GlobalPolicy])
async def list_global_policies(
    scope: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    """列表查询全局政策"""
    try:
        policies = RulesManager.list_global_policies(scope=scope, status=status)
        return policies
    except Exception as e:
        logger.error(f"Failed to list global policies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/global-policies/{policy_id}", response_model=Optional[GlobalPolicy])
async def update_global_policy(
    policy_id: str,
    update_data: GlobalPolicyUpdate,
    updated_by: str,
):
    """更新全局政策"""
    try:
        policy = RulesManager.update_global_policy(policy_id, update_data, updated_by)
        if not policy:
            raise HTTPException(status_code=404, detail="Policy not found")

        # 验证更新
        issues = GlobalPolicyValidator.validate(policy)
        if any(i.issue_type == "error" for i in issues):
            logger.warning(f"Validation issues after policy update: {issues}")

        return policy
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update global policy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- 冲突检测和影响分析 ---

@router.get("/conflicts/permissions", response_model=dict)
async def detect_permission_conflicts():
    """检测权限冲突"""
    try:
        conflicts = ConflictDetector.detect_permission_conflicts()
        return {
            "conflict_count": len(conflicts),
            "conflicts": [
                {"rule1_id": r1, "rule2_id": r2, "conflict_type": ct}
                for r1, r2, ct in conflicts
            ]
        }
    except Exception as e:
        logger.error(f"Failed to detect permission conflicts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conflicts/policies", response_model=dict)
async def detect_policy_conflicts():
    """检测政策冲突"""
    try:
        conflicts = ConflictDetector.detect_policy_conflicts()
        return {
            "conflict_count": len(conflicts),
            "conflicts": [
                {"policy1_id": p1, "policy2_id": p2, "conflict_type": ct}
                for p1, p2, ct in conflicts
            ]
        }
    except Exception as e:
        logger.error(f"Failed to detect policy conflicts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health", response_model=dict)
async def health_check():
    """健康检查"""
    return {
        "status": "ok",
        "service": "phase3b_rules",
        "version": "1.0.0",
    }

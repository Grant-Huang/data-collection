"""Phase 3-B Stage 2: 高级验证系统 REST API

提供规则集合验证、工作流约束验证、政策适用验证的 REST 端点。
"""
from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from ..phase3b_advanced_validators import (
    RuleSetValidator, WorkflowConstraintValidator, PolicyApplicationValidator,
    ValidationReport, ValidationResult, ValidationStatus,
    validate_rule_set, validate_workflow_constraints, validate_policy_application,
)
from ..rules_manager import RulesManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/phase3b", tags=["phase3b-advanced"])


# ============================================================================
# 规则集合验证端点
# ============================================================================

@router.post("/validate/rule-set")
async def validate_rule_set_endpoint(rule_ids: List[str]) -> Dict[str, Any]:
    """验证规则集合的一致性、覆盖度、优先级和冗余性

    Args:
        rule_ids: 要验证的规则 ID 列表

    Returns:
        验证报告，包含详细的验证结果
    """
    try:
        logger.info(f"验证规则集合，包含 {len(rule_ids)} 个规则")
        report = validate_rule_set(rule_ids)

        return {
            "overall_status": report.overall_status.value,
            "rules_count": report.rules_count,
            "validation_items": report.validation_items,
            "passed": report.passed,
            "warnings": report.warnings,
            "errors": report.errors,
            "timestamp": report.timestamp,
            "details": [
                {
                    "item_id": d.item_id,
                    "item_type": d.item_type.value,
                    "status": d.status.value,
                    "message": d.message,
                    "severity": d.severity,
                    "affected_items": d.affected_items,
                    "suggestion": d.suggestion,
                }
                for d in report.details
            ]
        }
    except Exception as e:
        logger.error(f"规则集合验证失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"验证失败: {str(e)}")


@router.get("/validate/rule-set/summary")
async def get_rule_set_validation_summary(
    status: Optional[str] = Query(None, description="按状态过滤: active/draft/deprecated/archived"),
    rule_type: Optional[str] = Query(None, description="按规则类型过滤"),
) -> Dict[str, Any]:
    """获取规则集合验证摘要

    Args:
        status: 规则状态过滤
        rule_type: 规则类型过滤

    Returns:
        规则集合统计和验证摘要
    """
    try:
        # 获取所有规则
        all_rules = RulesManager.list_system_rules(status=status, rule_type=rule_type)
        rule_ids = [r.rule_id for r in all_rules]

        if not rule_ids:
            return {
                "rules_count": 0,
                "summary": "没有符合条件的规则",
                "recommendations": ["创建新的规则以完善系统规则库"]
            }

        # 验证规则集合
        report = validate_rule_set(rule_ids)

        # 生成摘要
        issues_by_type = {}
        for detail in report.details:
            item_type = detail.item_type.value
            if item_type not in issues_by_type:
                issues_by_type[item_type] = []
            issues_by_type[item_type].append({
                "message": detail.message,
                "severity": detail.severity,
            })

        return {
            "rules_count": report.rules_count,
            "overall_status": report.overall_status.value,
            "passed": report.passed,
            "warnings": report.warnings,
            "errors": report.errors,
            "issues_by_type": issues_by_type,
            "recommendations": [
                d.suggestion for d in report.details
                if d.suggestion and d.status != ValidationStatus.PASS
            ]
        }
    except Exception as e:
        logger.error(f"获取规则集合验证摘要失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取摘要失败: {str(e)}")


# ============================================================================
# 工作流约束验证端点
# ============================================================================

@router.post("/validate/workflow-constraints/{workflow_id}")
async def validate_workflow_constraints_endpoint(
    workflow_id: str,
    constraints: Dict[str, Any]
) -> Dict[str, Any]:
    """验证工作流约束的合法性和可行性

    Args:
        workflow_id: 工作流 ID
        constraints: 工作流约束定义

    Returns:
        验证报告
    """
    try:
        logger.info(f"验证工作流 {workflow_id} 的约束")
        report = validate_workflow_constraints(workflow_id, constraints)

        return {
            "workflow_id": workflow_id,
            "overall_status": report.overall_status.value,
            "validation_items": report.validation_items,
            "passed": report.passed,
            "warnings": report.warnings,
            "errors": report.errors,
            "timestamp": report.timestamp,
            "details": [
                {
                    "item_id": d.item_id,
                    "item_type": d.item_type.value,
                    "status": d.status.value,
                    "message": d.message,
                    "severity": d.severity,
                    "suggestion": d.suggestion,
                }
                for d in report.details
            ]
        }
    except Exception as e:
        logger.error(f"工作流约束验证失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"验证失败: {str(e)}")


@router.get("/validate/workflow-constraints/{workflow_id}/stages")
async def get_workflow_valid_transitions(workflow_id: str) -> Dict[str, Any]:
    """获取工作流的合法阶段转换

    Args:
        workflow_id: 工作流 ID

    Returns:
        工作流的合法阶段转换列表
    """
    return {
        "workflow_id": workflow_id,
        "valid_transitions": WorkflowConstraintValidator.VALID_STAGE_TRANSITIONS,
        "workflow_types": WorkflowConstraintValidator.WORKFLOW_TYPES,
    }


# ============================================================================
# 政策适用验证端点
# ============================================================================

@router.post("/validate/policy-application")
async def validate_policy_application_endpoint(policy_ids: List[str]) -> Dict[str, Any]:
    """验证政策集合的覆盖范围和完整性

    Args:
        policy_ids: 要验证的政策 ID 列表

    Returns:
        验证报告
    """
    try:
        logger.info(f"验证政策集合，包含 {len(policy_ids)} 个政策")
        report = validate_policy_application(policy_ids)

        return {
            "overall_status": report.overall_status.value,
            "policies_count": report.rules_count,
            "validation_items": report.validation_items,
            "passed": report.passed,
            "warnings": report.warnings,
            "errors": report.errors,
            "timestamp": report.timestamp,
            "details": [
                {
                    "item_id": d.item_id,
                    "item_type": d.item_type.value,
                    "status": d.status.value,
                    "message": d.message,
                    "severity": d.severity,
                    "affected_items": d.affected_items,
                    "suggestion": d.suggestion,
                }
                for d in report.details
            ]
        }
    except Exception as e:
        logger.error(f"政策适用验证失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"验证失败: {str(e)}")


@router.get("/validate/policy-application/summary")
async def get_policy_application_summary(
    scope: Optional[str] = Query(None, description="按范围过滤: organization/department/workflow_type"),
) -> Dict[str, Any]:
    """获取政策适用验证摘要

    Args:
        scope: 政策范围过滤

    Returns:
        政策集合统计和验证摘要
    """
    try:
        # 获取所有政策
        all_policies = RulesManager.list_global_policies(scope=scope)
        policy_ids = [p.policy_id for p in all_policies]

        if not policy_ids:
            return {
                "policies_count": 0,
                "summary": "没有符合条件的政策",
                "recommendations": ["创建新政策以建立治理框架"]
            }

        # 验证政策集合
        report = validate_policy_application(policy_ids)

        # 生成摘要
        issues_by_type = {}
        for detail in report.details:
            item_type = detail.item_type.value
            if item_type not in issues_by_type:
                issues_by_type[item_type] = []
            issues_by_type[item_type].append({
                "message": detail.message,
                "severity": detail.severity,
            })

        return {
            "policies_count": report.rules_count,
            "overall_status": report.overall_status.value,
            "passed": report.passed,
            "warnings": report.warnings,
            "errors": report.errors,
            "issues_by_type": issues_by_type,
            "recommendations": [
                d.suggestion for d in report.details
                if d.suggestion and d.status != ValidationStatus.PASS
            ]
        }
    except Exception as e:
        logger.error(f"获取政策适用验证摘要失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取摘要失败: {str(e)}")


# ============================================================================
# 健康检查
# ============================================================================

@router.get("/validate/health")
async def health_check() -> Dict[str, str]:
    """高级验证系统健康检查"""
    return {
        "status": "ok",
        "service": "phase3b_advanced_validators",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


# ============================================================================
# 批量验证端点
# ============================================================================

@router.post("/validate/all-systems")
async def validate_all_systems() -> Dict[str, Any]:
    """执行所有系统的全面验证

    包括规则集合、工作流约束、政策适用的全面检查。
    """
    try:
        logger.info("执行全面系统验证")

        # 获取所有活跃规则
        all_rules = RulesManager.list_system_rules(status="active")
        rule_ids = [r.rule_id for r in all_rules]

        # 获取所有活跃政策
        all_policies = RulesManager.list_global_policies(status="active")
        policy_ids = [p.policy_id for p in all_policies]

        # 执行验证
        rule_set_report = validate_rule_set(rule_ids) if rule_ids else ValidationReport(
            overall_status=ValidationStatus.PASS, rules_count=0, validation_items=0,
            passed=0, warnings=0, errors=0
        )

        policy_report = validate_policy_application(policy_ids) if policy_ids else ValidationReport(
            overall_status=ValidationStatus.PASS, rules_count=0, validation_items=0,
            passed=0, warnings=0, errors=0
        )

        # 确定整体系统状态
        overall_status = ValidationStatus.PASS
        if rule_set_report.overall_status == ValidationStatus.FAIL or policy_report.overall_status == ValidationStatus.FAIL:
            overall_status = ValidationStatus.FAIL
        elif rule_set_report.overall_status == ValidationStatus.WARN or policy_report.overall_status == ValidationStatus.WARN:
            overall_status = ValidationStatus.WARN

        return {
            "overall_status": overall_status.value,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "rule_set_validation": {
                "status": rule_set_report.overall_status.value,
                "rules_count": rule_set_report.rules_count,
                "passed": rule_set_report.passed,
                "warnings": rule_set_report.warnings,
                "errors": rule_set_report.errors,
            },
            "policy_application_validation": {
                "status": policy_report.overall_status.value,
                "policies_count": policy_report.rules_count,
                "passed": policy_report.passed,
                "warnings": policy_report.warnings,
                "errors": policy_report.errors,
            },
            "recommendations": [
                *[d.suggestion for d in rule_set_report.details if d.suggestion],
                *[d.suggestion for d in policy_report.details if d.suggestion],
            ]
        }
    except Exception as e:
        logger.error(f"全面系统验证失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"系统验证失败: {str(e)}")

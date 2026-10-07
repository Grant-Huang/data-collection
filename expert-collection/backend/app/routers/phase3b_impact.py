"""Phase 3-B Stage 2 Part 3: 影响规划系统 REST API

提供详细影响分析、风险评估、变更管理计划生成的 REST 端点。
"""
from __future__ import annotations

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from ..phase3b_impact_planner import (
    DetailedImpactAnalyzer, RiskAssessmentEngine, ChangeManagementPlanner,
    ImpactScope, RiskLevel, ImpactType,
    analyze_detailed_impact, assess_change_risks, create_change_management_plan,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/phase3b", tags=["phase3b-impact"])


# ============================================================================
# 详细影响分析端点
# ============================================================================

@router.post("/impact/analyze/detailed")
async def analyze_detailed_impact_endpoint(
    change_items: List[str],
    change_type: str = Query("rule", description="变更类型: rule/policy/workflow")
) -> Dict[str, Any]:
    """分析变更的详细影响

    Args:
        change_items: 要变更的项目 ID 列表
        change_type: 变更类型

    Returns:
        影响分析报告
    """
    try:
        logger.info(f"分析 {len(change_items)} 个 {change_type} 变更的影响")
        report = analyze_detailed_impact(change_items, change_type)

        return {
            "report_id": report.report_id,
            "total_impacts": report.total_impacts,
            "critical_count": report.critical_count,
            "high_count": report.high_count,
            "medium_count": report.medium_count,
            "low_count": report.low_count,
            "estimated_total_duration": report.estimated_total_duration,
            "affected_workflows": list(report.affected_workflows),
            "affected_policies": list(report.affected_policies),
            "summary": report.summary,
            "timestamp": report.timestamp,
            "impacts": [
                {
                    "impact_id": impact.impact_id,
                    "impact_type": impact.impact_type.value,
                    "scope": impact.scope.value,
                    "affected_items": impact.affected_items,
                    "description": impact.description,
                    "severity": impact.severity,
                    "estimated_duration": impact.estimated_duration,
                    "mitigation_strategies": impact.mitigation_strategies,
                    "rollback_risk": impact.rollback_risk,
                }
                for impact in report.impacts
            ]
        }
    except Exception as e:
        logger.error(f"详细影响分析失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")


@router.get("/impact/scopes")
async def get_impact_scopes() -> Dict[str, Any]:
    """获取所有影响范围"""
    return {
        "scopes": [
            {
                "id": scope.value,
                "name": scope.name,
                "description": f"Impact scope: {scope.value}"
            }
            for scope in ImpactScope
        ]
    }


@router.get("/impact/types")
async def get_impact_types() -> Dict[str, Any]:
    """获取所有影响类型"""
    return {
        "types": [
            {
                "id": impact_type.value,
                "name": impact_type.name,
                "description": f"Impact type: {impact_type.value}"
            }
            for impact_type in ImpactType
        ]
    }


# ============================================================================
# 风险评估端点
# ============================================================================

@router.post("/impact/assess-risks")
async def assess_risks_endpoint(
    change_items: List[str]
) -> Dict[str, Any]:
    """评估变更的风险

    Args:
        change_items: 要变更的项目 ID 列表

    Returns:
        风险评估报告
    """
    try:
        logger.info(f"评估 {len(change_items)} 个变更项的风险")
        report = assess_change_risks(change_items)

        return {
            "report_id": report.report_id,
            "total_risks": report.total_risks,
            "critical_risks": report.critical_risks,
            "high_risks": report.high_risks,
            "medium_risks": report.medium_risks,
            "low_risks": report.low_risks,
            "overall_risk_level": report.overall_risk_level.value,
            "timestamp": report.timestamp,
            "top_3_risks": [
                {
                    "risk_id": risk.risk_id,
                    "risk_type": risk.risk_type,
                    "risk_level": risk.risk_level.value,
                    "probability": risk.probability,
                    "impact": risk.impact,
                    "affected_systems": risk.affected_systems,
                    "mitigation_plan": risk.mitigation_plan,
                    "contingency_plan": risk.contingency_plan,
                    "owner": risk.owner,
                }
                for risk in report.top_3_risks
            ],
            "risks": [
                {
                    "risk_id": risk.risk_id,
                    "risk_type": risk.risk_type,
                    "risk_level": risk.risk_level.value,
                    "probability": risk.probability,
                    "impact": risk.impact,
                    "affected_systems": risk.affected_systems,
                    "mitigation_plan": risk.mitigation_plan,
                    "contingency_plan": risk.contingency_plan,
                }
                for risk in report.risks
            ]
        }
    except Exception as e:
        logger.error(f"风险评估失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"评估失败: {str(e)}")


@router.get("/impact/risk-levels")
async def get_risk_levels() -> Dict[str, Any]:
    """获取所有风险等级"""
    return {
        "risk_levels": [
            {
                "id": level.value,
                "name": level.name,
                "description": f"Risk level: {level.value}"
            }
            for level in RiskLevel
        ]
    }


# ============================================================================
# 变更管理计划端点
# ============================================================================

@router.post("/impact/create-change-plan")
async def create_change_plan_endpoint(
    change_title: str = Query(..., description="变更标题"),
    change_type: str = Query(..., description="变更类型: rule/policy/workflow"),
    change_items: List[str] = Query(..., description="受影响的项目 ID 列表")
) -> Dict[str, Any]:
    """创建变更管理计划

    Args:
        change_title: 变更标题
        change_type: 变更类型
        change_items: 受影响的项目 ID

    Returns:
        变更管理计划
    """
    try:
        logger.info(f"为 {change_type} 创建变更管理计划: {change_title}")

        # 先分析影响和风险
        impact_report = analyze_detailed_impact(change_items, change_type)
        risk_report = assess_change_risks(change_items, impact_report)

        # 创建变更管理计划
        plan = create_change_management_plan(
            change_title,
            change_type,
            change_items,
            impact_report,
            risk_report
        )

        return {
            "plan_id": plan.plan_id,
            "change_title": plan.change_title,
            "change_type": plan.change_type,
            "affected_items": plan.affected_items,
            "estimated_completion_date": plan.estimated_completion_date,
            "rollback_plan": plan.rollback_plan,
            "success_criteria": plan.success_criteria,
            "approval_chain": plan.approval_chain,
            "created_at": plan.created_at,
            "tasks": [
                {
                    "task_id": task.task_id,
                    "task_name": task.task_name,
                    "description": task.description,
                    "priority": task.priority,
                    "estimated_hours": task.estimated_hours,
                    "dependencies": task.dependencies,
                    "status": task.status.value,
                }
                for task in plan.tasks
            ],
            "impact_report": {
                "report_id": impact_report.report_id,
                "total_impacts": impact_report.total_impacts,
                "critical_count": impact_report.critical_count,
                "high_count": impact_report.high_count,
                "summary": impact_report.summary,
            },
            "risk_report": {
                "report_id": risk_report.report_id,
                "total_risks": risk_report.total_risks,
                "overall_risk_level": risk_report.overall_risk_level.value,
                "critical_risks": risk_report.critical_risks,
            }
        }
    except Exception as e:
        logger.error(f"变更管理计划创建失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建失败: {str(e)}")


@router.post("/impact/validate-plan")
async def validate_change_plan(
    plan_data: Dict[str, Any]
) -> Dict[str, Any]:
    """验证变更管理计划

    Args:
        plan_data: 变更管理计划数据

    Returns:
        验证结果
    """
    try:
        logger.info("验证变更管理计划")

        # 验证必要字段
        required_fields = ["change_title", "change_type", "affected_items", "tasks"]
        missing_fields = [f for f in required_fields if f not in plan_data]

        if missing_fields:
            return {
                "valid": False,
                "errors": [f"Missing required field: {f}" for f in missing_fields]
            }

        # 验证任务依赖关系
        tasks = plan_data.get("tasks", [])
        task_ids = {t.get("task_id") for t in tasks}

        dependency_errors = []
        for task in tasks:
            for dep in task.get("dependencies", []):
                if dep not in task_ids:
                    dependency_errors.append(f"Task {task.get('task_id')}: unknown dependency {dep}")

        if dependency_errors:
            return {
                "valid": False,
                "errors": dependency_errors
            }

        # 验证批准链
        approval_chain = plan_data.get("approval_chain", [])
        if len(approval_chain) < 2:
            return {
                "valid": False,
                "errors": ["Approval chain must have at least 2 approvers"]
            }

        return {
            "valid": True,
            "message": "Change plan is valid and ready for approval",
            "warnings": []
        }
    except Exception as e:
        logger.error(f"计划验证失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"验证失败: {str(e)}")


# ============================================================================
# 综合分析端点
# ============================================================================

@router.post("/impact/comprehensive-analysis")
async def comprehensive_analysis(
    change_items: List[str],
    change_type: str = Query("rule", description="变更类型: rule/policy/workflow")
) -> Dict[str, Any]:
    """执行综合影响和风险分析

    包括详细影响分析和风险评估的综合报告。
    """
    try:
        logger.info(f"执行综合分析: {len(change_items)} 项 {change_type}")

        impact_report = analyze_detailed_impact(change_items, change_type)
        risk_report = assess_change_risks(change_items, impact_report)

        # 计算综合风险分数
        total_items = len(change_items)
        impact_score = (impact_report.critical_count * 4 +
                       impact_report.high_count * 3 +
                       impact_report.medium_count * 2 +
                       impact_report.low_count * 1) / max(total_items, 1)

        risk_score = (risk_report.critical_risks * 4 +
                     risk_report.high_risks * 3 +
                     risk_report.medium_risks * 2 +
                     risk_report.low_risks * 1) / max(total_items, 1)

        overall_score = (impact_score + risk_score) / 2

        return {
            "analysis_type": "comprehensive",
            "change_type": change_type,
            "change_items_count": len(change_items),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "impact_analysis": {
                "report_id": impact_report.report_id,
                "total_impacts": impact_report.total_impacts,
                "critical_count": impact_report.critical_count,
                "high_count": impact_report.high_count,
                "medium_count": impact_report.medium_count,
                "low_count": impact_report.low_count,
                "estimated_duration_minutes": impact_report.estimated_total_duration,
            },
            "risk_analysis": {
                "report_id": risk_report.report_id,
                "total_risks": risk_report.total_risks,
                "critical_risks": risk_report.critical_risks,
                "high_risks": risk_report.high_risks,
                "medium_risks": risk_report.medium_risks,
                "overall_risk_level": risk_report.overall_risk_level.value,
            },
            "scores": {
                "impact_score": round(impact_score, 2),
                "risk_score": round(risk_score, 2),
                "overall_score": round(overall_score, 2),
                "recommendation": "Proceed with caution" if overall_score > 2 else "Safe to proceed"
            }
        }
    except Exception as e:
        logger.error(f"综合分析失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")


# ============================================================================
# 健康检查
# ============================================================================

@router.get("/impact/health")
async def health_check() -> Dict[str, str]:
    """影响规划系统健康检查"""
    return {
        "status": "ok",
        "service": "phase3b_impact_planner",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

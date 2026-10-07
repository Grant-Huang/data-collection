"""Phase 3-B Stage 2: 冲突分析引擎 REST API

提供权限冲突、资源冲突、时间冲突、政策冲突分析的 REST 端点。
"""
from __future__ import annotations

import logging
from typing import Dict, Any, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from ..phase3b_conflict_analyzer import (
    PermissionConflictAnalyzer, ResourceConflictAnalyzer, TimeConflictAnalyzer,
    PolicyConflictAnalyzer, ConflictResolutionEngine,
    ConflictSeverity, ConflictType,
    analyze_all_conflicts, generate_conflict_resolution_plan,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/phase3b", tags=["phase3b-conflict"])


# ============================================================================
# 权限冲突分析端点
# ============================================================================

@router.post("/analyze/conflicts/permissions")
async def analyze_permission_conflicts() -> Dict[str, Any]:
    """分析权限冲突

    检测相互排斥的权限、权限提升矛盾、权限继承冲突。

    Returns:
        冲突分析报告
    """
    try:
        logger.info("执行权限冲突分析")
        report = PermissionConflictAnalyzer.analyze()

        return {
            "analyzer_type": "permission",
            "conflict_count": report.conflict_count,
            "critical_count": report.critical_count,
            "high_count": report.high_count,
            "medium_count": report.medium_count,
            "low_count": report.low_count,
            "info_count": report.info_count,
            "overall_severity": report.overall_severity.value,
            "timestamp": report.timestamp,
            "conflicts": [
                {
                    "conflict_id": c.conflict_id,
                    "conflict_type": c.conflict_type.value,
                    "severity": c.severity.value,
                    "affected_items": c.affected_items,
                    "description": c.description,
                    "resolution_suggestions": c.resolution_suggestions,
                    "impact_scope": c.impact_scope,
                }
                for c in report.conflicts
            ]
        }
    except Exception as e:
        logger.error(f"权限冲突分析失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")


# ============================================================================
# 资源冲突分析端点
# ============================================================================

@router.post("/analyze/conflicts/resources")
async def analyze_resource_conflicts() -> Dict[str, Any]:
    """分析资源冲突

    检测资源竞争、死锁风险、资源分配冲突。

    Returns:
        冲突分析报告
    """
    try:
        logger.info("执行资源冲突分析")
        report = ResourceConflictAnalyzer.analyze()

        return {
            "analyzer_type": "resource",
            "conflict_count": report.conflict_count,
            "critical_count": report.critical_count,
            "high_count": report.high_count,
            "medium_count": report.medium_count,
            "low_count": report.low_count,
            "info_count": report.info_count,
            "overall_severity": report.overall_severity.value,
            "timestamp": report.timestamp,
            "conflicts": [
                {
                    "conflict_id": c.conflict_id,
                    "conflict_type": c.conflict_type.value,
                    "severity": c.severity.value,
                    "affected_items": c.affected_items,
                    "description": c.description,
                    "resolution_suggestions": c.resolution_suggestions,
                    "impact_scope": c.impact_scope,
                }
                for c in report.conflicts
            ]
        }
    except Exception as e:
        logger.error(f"资源冲突分析失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")


# ============================================================================
# 时间冲突分析端点
# ============================================================================

@router.post("/analyze/conflicts/time")
async def analyze_time_conflicts() -> Dict[str, Any]:
    """分析时间冲突

    检测时间约束冲突、截止时间冲突、延迟冲突。

    Returns:
        冲突分析报告
    """
    try:
        logger.info("执行时间冲突分析")
        report = TimeConflictAnalyzer.analyze()

        return {
            "analyzer_type": "time",
            "conflict_count": report.conflict_count,
            "critical_count": report.critical_count,
            "high_count": report.high_count,
            "medium_count": report.medium_count,
            "low_count": report.low_count,
            "info_count": report.info_count,
            "overall_severity": report.overall_severity.value,
            "timestamp": report.timestamp,
            "conflicts": [
                {
                    "conflict_id": c.conflict_id,
                    "conflict_type": c.conflict_type.value,
                    "severity": c.severity.value,
                    "affected_items": c.affected_items,
                    "description": c.description,
                    "resolution_suggestions": c.resolution_suggestions,
                    "impact_scope": c.impact_scope,
                }
                for c in report.conflicts
            ]
        }
    except Exception as e:
        logger.error(f"时间冲突分析失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")


# ============================================================================
# 政策冲突分析端点
# ============================================================================

@router.post("/analyze/conflicts/policies")
async def analyze_policy_conflicts() -> Dict[str, Any]:
    """分析政策冲突

    检测决策规则冲突、覆盖冲突、异常处理冲突。

    Returns:
        冲突分析报告
    """
    try:
        logger.info("执行政策冲突分析")
        report = PolicyConflictAnalyzer.analyze()

        return {
            "analyzer_type": "policy",
            "conflict_count": report.conflict_count,
            "critical_count": report.critical_count,
            "high_count": report.high_count,
            "medium_count": report.medium_count,
            "low_count": report.low_count,
            "info_count": report.info_count,
            "overall_severity": report.overall_severity.value,
            "timestamp": report.timestamp,
            "conflicts": [
                {
                    "conflict_id": c.conflict_id,
                    "conflict_type": c.conflict_type.value,
                    "severity": c.severity.value,
                    "affected_items": c.affected_items,
                    "description": c.description,
                    "resolution_suggestions": c.resolution_suggestions,
                    "impact_scope": c.impact_scope,
                }
                for c in report.conflicts
            ]
        }
    except Exception as e:
        logger.error(f"政策冲突分析失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")


# ============================================================================
# 综合分析端点
# ============================================================================

@router.post("/analyze/conflicts/all")
async def analyze_all_conflicts_endpoint() -> Dict[str, Any]:
    """执行所有冲突类型的综合分析

    包括权限、资源、时间、政策的全面冲突检测。

    Returns:
        综合冲突分析报告
    """
    try:
        logger.info("执行综合冲突分析")
        report = analyze_all_conflicts()

        # 确定整体严重程度
        overall_severity = ConflictSeverity.INFO
        if report.critical_count > 0:
            overall_severity = ConflictSeverity.CRITICAL
        elif report.high_count > 0:
            overall_severity = ConflictSeverity.HIGH
        elif report.medium_count > 0:
            overall_severity = ConflictSeverity.MEDIUM
        elif report.low_count > 0:
            overall_severity = ConflictSeverity.LOW

        return {
            "overall_severity": overall_severity.value,
            "conflict_count": report.conflict_count,
            "critical_count": report.critical_count,
            "high_count": report.high_count,
            "medium_count": report.medium_count,
            "low_count": report.low_count,
            "info_count": report.info_count,
            "timestamp": report.timestamp,
            "summary": report.summary or f"检测到 {report.conflict_count} 个冲突",
            "conflicts_by_type": _group_conflicts_by_type(report.conflicts),
            "conflicts": [
                {
                    "conflict_id": c.conflict_id,
                    "conflict_type": c.conflict_type.value,
                    "severity": c.severity.value,
                    "affected_items": c.affected_items,
                    "description": c.description,
                    "resolution_suggestions": c.resolution_suggestions,
                    "impact_scope": c.impact_scope,
                }
                for c in report.conflicts
            ]
        }
    except Exception as e:
        logger.error(f"综合冲突分析失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")


@router.post("/analyze/conflicts/resolution-plan")
async def generate_resolution_plan_endpoint() -> Dict[str, Any]:
    """生成冲突解决方案

    基于检测到的冲突，生成优先级排序的解决建议。

    Returns:
        解决方案计划
    """
    try:
        logger.info("生成冲突解决方案")

        # 执行冲突分析
        report = analyze_all_conflicts()

        # 生成解决方案
        plan = generate_conflict_resolution_plan(report)

        return {
            "total_conflicts": report.conflict_count,
            "total_resolution_steps": len(plan.get("resolution_steps", [])),
            "total_effort_hours": sum(s.get("estimated_effort_hours", 0) for s in plan.get("resolution_steps", [])),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "resolution_plan": plan
        }
    except Exception as e:
        logger.error(f"生成解决方案失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"生成失败: {str(e)}")


# ============================================================================
# 冲突统计端点
# ============================================================================

@router.get("/analyze/conflicts/summary")
async def get_conflict_summary(
    severity: Optional[str] = Query(None, description="按严重程度过滤: critical/high/medium/low/info"),
    conflict_type: Optional[str] = Query(None, description="按冲突类型过滤"),
) -> Dict[str, Any]:
    """获取冲突汇总统计

    Args:
        severity: 严重程度过滤
        conflict_type: 冲突类型过滤

    Returns:
        冲突统计汇总
    """
    try:
        logger.info("获取冲突汇总统计")
        report = analyze_all_conflicts()

        # 过滤冲突
        filtered_conflicts = report.conflicts
        if severity:
            filtered_conflicts = [c for c in filtered_conflicts if c.severity.value == severity]
        if conflict_type:
            filtered_conflicts = [c for c in filtered_conflicts if c.conflict_type.value == conflict_type]

        # 计算统计
        severity_distribution = {}
        for conflict in filtered_conflicts:
            severity_distribution[conflict.severity.value] = severity_distribution.get(conflict.severity.value, 0) + 1

        type_distribution = {}
        for conflict in filtered_conflicts:
            type_distribution[conflict.conflict_type.value] = type_distribution.get(conflict.conflict_type.value, 0) + 1

        return {
            "total_conflicts": len(filtered_conflicts),
            "severity_distribution": severity_distribution,
            "type_distribution": type_distribution,
            "top_affected_items": _get_top_affected_items(filtered_conflicts),
            "recommendations": _get_recommendations(filtered_conflicts),
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    except Exception as e:
        logger.error(f"获取冲突汇总失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


# ============================================================================
# 健康检查
# ============================================================================

@router.get("/analyze/conflicts/health")
async def health_check() -> Dict[str, str]:
    """冲突分析系统健康检查"""
    return {
        "status": "ok",
        "service": "phase3b_conflict_analyzer",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


# ============================================================================
# 辅助函数
# ============================================================================

def _group_conflicts_by_type(conflicts: list) -> Dict[str, int]:
    """按冲突类型分组统计"""
    result = {}
    for conflict in conflicts:
        conflict_type = conflict.conflict_type.value
        result[conflict_type] = result.get(conflict_type, 0) + 1
    return result


def _get_top_affected_items(conflicts: list, limit: int = 5) -> list:
    """获取最受影响的项"""
    from collections import Counter
    affected_counter = Counter()
    for conflict in conflicts:
        affected_counter.update(conflict.affected_items)

    return [
        {"item": item, "conflict_count": count}
        for item, count in affected_counter.most_common(limit)
    ]


def _get_recommendations(conflicts: list, limit: int = 5) -> list:
    """获取建议"""
    recommendations = []
    seen = set()

    for conflict in sorted(conflicts, key=lambda c: _severity_to_priority(c.severity)):
        for suggestion in conflict.resolution_suggestions:
            if suggestion not in seen and len(recommendations) < limit:
                recommendations.append({
                    "priority": _severity_to_priority(conflict.severity),
                    "suggestion": suggestion,
                    "related_conflicts": len([c for c in conflicts if suggestion in c.resolution_suggestions])
                })
                seen.add(suggestion)

    return recommendations


def _severity_to_priority(severity: ConflictSeverity) -> int:
    """将严重程度转换为优先级数字"""
    priority_map = {
        ConflictSeverity.CRITICAL: 1,
        ConflictSeverity.HIGH: 2,
        ConflictSeverity.MEDIUM: 3,
        ConflictSeverity.LOW: 4,
        ConflictSeverity.INFO: 5,
    }
    return priority_map.get(severity, 5)

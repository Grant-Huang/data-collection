"""Phase 3-A 集成模块 - 将 Validator、LLM 采集、隔离范围等新功能集成到主应用

此模块作为适配层，连接 Phase 3-A 的新功能与现有的 expert-collection 系统。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# 动态导入 Phase 3-A 模块（支持不同的安装位置）
def _import_phase3a_modules():
    """尝试导入 Phase 3-A 模块，支持多种目录结构"""
    try:
        # 尝试从项目根目录导入
        sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
        from src.validators.phase3a_validator import SchemaValidator, Phase3AValidator, ValidationSeverity
        from src.collection.phase3a_llm_prompts import Phase3ACollectionPipeline
        return SchemaValidator, Phase3AValidator, ValidationSeverity, Phase3ACollectionPipeline
    except ImportError:
        raise ImportError(
            "无法导入 Phase 3-A 模块。请确保 src/validators 和 src/collection 模块已正确安装"
        )


# 延迟导入，仅在需要时加载
_phase3a_modules = None


def _get_phase3a_modules():
    """获取 Phase 3-A 模块（延迟加载）"""
    global _phase3a_modules
    if _phase3a_modules is None:
        _phase3a_modules = _import_phase3a_modules()
    return _phase3a_modules


class Phase3AValidator:
    """Phase 3-A 验证器的包装类，用于与 expert-collection 系统集成"""

    def __init__(self):
        """初始化验证器"""
        self.schema_validator, _, _, _ = _get_phase3a_modules()
        self.validator = self.schema_validator()

    def validate_workflow_graph(self, graph: Dict[str, Any]) -> Dict[str, Any]:
        """
        验证工作流 DAG 中的 Phase 3-A 新维度

        Args:
            graph: 工作流 DAG 对象，包含 nodes 和 edges

        Returns:
            {
                'valid': bool,
                'errors': [...],  # 包含所有错误（ERROR、WARNING、INFO）
                'error_count': int,
                'warning_count': int,
                'summary': str
            }
        """
        return self.validator.validate_graph(graph)

    def convert_to_legacy_issues(self, validation_result: Dict[str, Any]) -> List[Dict[str, str]]:
        """
        将 Phase 3-A 验证结果转换为现有系统的 issue 格式

        Args:
            validation_result: Phase 3-A 验证结果

        Returns:
            兼容现有 graph_validator 的 issue 列表
        """
        issues = []
        for error in validation_result.get('errors', []):
            issue = {
                'level': 'error' if error['severity'] == 'error' else 'warning',
                'code': f"phase3a_{error['code']}",
                'message': error['message'],
                'field': error['field'],
            }

            # 如果有修复建议，添加到消息中
            if error.get('suggestion'):
                issue['message'] += f" [建议：{error['suggestion']}]"

            # 尝试提取 node_id 或 edge_id
            if '[' in error['field'] and ']' in error['field']:
                # 格式如 approval_matrix[0].required_roles
                try:
                    field_part = error['field'].split('[')[0]
                    # 对于嵌套字段，使用 node_id 作为标识
                    issue['field_type'] = field_part
                except Exception:
                    pass

            issues.append(issue)

        return issues


class Phase3ACollectionIntegration:
    """Phase 3-A LLM 采集的集成模块"""

    def __init__(self):
        """初始化采集集成"""
        _, _, _, pipeline_class = _get_phase3a_modules()
        self.pipeline = pipeline_class()

    def create_collection_plan(self, expert_name: str, workflow_name: str) -> Dict[str, Any]:
        """
        创建采集计划

        Args:
            expert_name: 专家名字
            workflow_name: 工作流名称

        Returns:
            采集计划，包含 5 个阶段的问题和时间估计
        """
        return self.pipeline.create_collection_plan(expert_name, workflow_name)

    def get_collection_questions_for_phase(self, phase_num: int) -> List[Dict[str, str]]:
        """
        获取指定阶段的采集问题

        Args:
            phase_num: 阶段号（1-5）

        Returns:
            该阶段的问题列表
        """
        plan = self.pipeline.question_set.get_all_questions()
        if phase_num < 1 or phase_num > 5:
            raise ValueError(f"无效的阶段号：{phase_num}，应该是 1-5")

        # 按分类获取问题
        categories = list(plan.keys())
        if phase_num <= len(categories):
            category = categories[phase_num - 1]
            return [
                {
                    'id': q.id,
                    'text': q.text,
                    'context': q.context,
                    'example': q.example,
                    'follow_up': q.follow_up or []
                }
                for q in plan[category]
            ]
        return []

    def get_quality_checklist(self) -> List[str]:
        """获取采集质量检查清单"""
        return self.pipeline.quality_checklist()


class Phase3ADataExtractor:
    """从结构化数据中提取 Phase 3-A 新维度"""

    @staticmethod
    def extract_approval_matrix(node: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """提取权限矩阵"""
        return node.get('approval_matrix')

    @staticmethod
    def extract_aggregation_conditions(node: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """提取聚合条件"""
        conditions = []
        for criterion in node.get('evaluation_criteria', []):
            if 'aggregation' in criterion:
                conditions.append({
                    'criterion_id': criterion.get('id'),
                    'criterion_name': criterion.get('name'),
                    'aggregation': criterion['aggregation']
                })
        return conditions if conditions else None

    @staticmethod
    def extract_temporary_measures(node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """提取临时措施"""
        retry = node.get('retry_semantics')
        if retry and retry.get('is_temporary'):
            return {
                'enabled': retry.get('enabled'),
                'max_retries': retry.get('max_retries_per_phase'),
                'expiration': retry.get('expiration'),
                'revocation': retry.get('revocation_trigger'),
                'escalation': retry.get('escalation_on_repeat')
            }
        return None

    @staticmethod
    def extract_containment_scope(node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """提取隔离范围"""
        return node.get('containment_scope')

    @staticmethod
    def summarize_phase3a_features(graph: Dict[str, Any]) -> Dict[str, Any]:
        """
        为整个 DAG 总结 Phase 3-A 新维度的使用情况

        Returns:
            {
                'has_approval_matrix': bool,
                'has_aggregation': bool,
                'has_temporary_measures': bool,
                'has_containment': bool,
                'approval_matrix_nodes': int,
                'aggregation_nodes': int,
                'temporary_measure_nodes': int,
                'containment_nodes': int,
                'summary': str
            }
        """
        summary = {
            'approval_matrix_nodes': 0,
            'aggregation_nodes': 0,
            'temporary_measure_nodes': 0,
            'containment_nodes': 0,
        }

        for node in graph.get('nodes', []):
            if node.get('approval_matrix'):
                summary['approval_matrix_nodes'] += 1

            if any(c.get('aggregation') for c in node.get('evaluation_criteria', [])):
                summary['aggregation_nodes'] += 1

            if node.get('retry_semantics', {}).get('is_temporary'):
                summary['temporary_measure_nodes'] += 1

            if node.get('containment_scope'):
                summary['containment_nodes'] += 1

        # 生成摘要
        features = []
        if summary['approval_matrix_nodes'] > 0:
            features.append(f"权限矩阵（{summary['approval_matrix_nodes']} 个节点）")
        if summary['aggregation_nodes'] > 0:
            features.append(f"聚合条件（{summary['aggregation_nodes']} 个节点）")
        if summary['temporary_measure_nodes'] > 0:
            features.append(f"临时措施（{summary['temporary_measure_nodes']} 个节点）")
        if summary['containment_nodes'] > 0:
            features.append(f"隔离范围（{summary['containment_nodes']} 个节点）")

        summary['has_approval_matrix'] = summary['approval_matrix_nodes'] > 0
        summary['has_aggregation'] = summary['aggregation_nodes'] > 0
        summary['has_temporary_measures'] = summary['temporary_measure_nodes'] > 0
        summary['has_containment'] = summary['containment_nodes'] > 0
        summary['summary'] = '、'.join(features) if features else '无 Phase 3-A 新维度'

        return summary


class Phase3AValidationConfig:
    """Phase 3-A 验证配置"""

    # 可配置的验证规则
    RULES_CONFIG = {
        'approval_matrix': {
            'enabled': True,
            'strict': False,  # False 时只检查关键字段
            'allow_missing_escalation': False
        },
        'aggregation': {
            'enabled': True,
            'strict': False,
            'max_window_size': 100
        },
        'temporary_measures': {
            'enabled': True,
            'strict': False,
            'require_revocation_trigger': False
        },
        'containment_scope': {
            'enabled': True,
            'strict': False,
            'allow_any_dimension': False
        }
    }

    @classmethod
    def set_rule_enabled(cls, rule: str, enabled: bool):
        """启用/禁用特定规则"""
        if rule in cls.RULES_CONFIG:
            cls.RULES_CONFIG[rule]['enabled'] = enabled

    @classmethod
    def set_strict_mode(cls, rule: str, strict: bool):
        """设置特定规则的严格模式"""
        if rule in cls.RULES_CONFIG:
            cls.RULES_CONFIG[rule]['strict'] = strict


# 全局实例（单例）
_phase3a_validator = None
_phase3a_collection = None


def get_validator() -> Phase3AValidator:
    """获取全局 Phase 3-A 验证器实例"""
    global _phase3a_validator
    if _phase3a_validator is None:
        _phase3a_validator = Phase3AValidator()
    return _phase3a_validator


def get_collection() -> Phase3ACollectionIntegration:
    """获取全局 Phase 3-A 采集实例"""
    global _phase3a_collection
    if _phase3a_collection is None:
        _phase3a_collection = Phase3ACollectionIntegration()
    return _phase3a_collection


def validate_and_enrich_graph(graph: Dict[str, Any]) -> Dict[str, Any]:
    """
    验证并增强图数据

    进行以下操作：
    1. 运行 Phase 3-A 验证
    2. 提取 Phase 3-A 新维度的信息
    3. 生成特征摘要

    Args:
        graph: 工作流 DAG

    Returns:
        增强后的图数据（包含验证结果和特征摘要）
    """
    validator = get_validator()

    # 验证
    validation_result = validator.validate_workflow_graph(graph)

    # 提取特征
    extractor = Phase3ADataExtractor()
    features_summary = extractor.summarize_phase3a_features(graph)

    # 转换为兼容的 issues 格式
    issues = validator.convert_to_legacy_issues(validation_result)

    # 返回增强的数据
    return {
        'validation': {
            'phase3a': validation_result,
            'issues': issues,
        },
        'features': features_summary,
    }

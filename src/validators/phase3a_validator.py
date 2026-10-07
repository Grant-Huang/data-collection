"""Phase 3-A 验证器 - 验证新维度字段的数据完整性和逻辑一致性"""

from enum import Enum
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass
from datetime import datetime
import re


class ValidationSeverity(str, Enum):
    """验证错误的严重级别"""
    ERROR = "error"  # 阻止保存
    WARNING = "warning"  # 应该修复但可继续
    INFO = "info"  # 建议信息


@dataclass
class ValidationError:
    """单个验证错误的表示"""
    object_id: str  # 节点或边的 ID
    field: str  # 出错字段的路径 (e.g., 'approval_matrix[0].required_roles')
    code: str  # 错误代码 (e.g., 'invalid_role')
    message: str  # 用户可读的错误信息
    suggestion: Optional[str] = None  # 如何修复的建议
    severity: ValidationSeverity = ValidationSeverity.ERROR  # 严重级别
    object_kind: str = 'node'  # object_id 指向的对象类型：'node' 或 'edge'

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典用于 JSON 序列化"""
        return {
            'object_id': self.object_id,
            'object_kind': self.object_kind,
            'field': self.field,
            'code': self.code,
            'message': self.message,
            'suggestion': self.suggestion,
            'severity': self.severity.value
        }


class Phase3AValidator:
    """Phase 3-A 新维度验证器"""

    # 有效值配置
    VALID_ROLES = {
        'equipment_engineer', 'process_engineer', 'quality_engineer',
        'production_manager', 'production_director', 'executive', 'other'
    }

    VALID_SEQUENCES = {'parallel', 'sequential'}

    VALID_AGG_METHODS = {'trend', 'pattern', 'continuous', 'statistical'}

    VALID_AGG_OPERATORS = {
        'all_increasing', 'all_decreasing', 'two_exceeding',
        'variance_above', 'mean_shift', 'cycle_detected'
    }

    VALID_DIMENSIONS = {
        'equipment_id', 'lot_id', 'material_id', 'line_id', 'mold_id', 'shift_id'
    }

    # —— 本体维度（阈值 / escalation / 证据）——
    # 需要数值阈值与单位的评估标准类型（schema: evaluation_criterion.type）
    NUMERIC_CRITERION_TYPES = {'metric', 'numeric_range'}

    # 隐含"升级给某人"的 escalation_on_repeat.action；create_capa / stop_production 是动作而非移交
    ESCALATE_ACTIONS = {'escalate_to_manager', 'escalate_to_executive'}

    # 结构性节点：不承载专家陈述的内容，不要求证据来源
    STRUCTURAL_NODE_TYPES = {'start', 'end'}

    # "裸数字"阈值：只由数字、比较符、区间符号构成（如 "3"、"< 40"、"40-50"、"≥0.5"），不含任何单位
    _BARE_NUMBER_RE = re.compile(r'^[\s<>=≤≥±~+\-–—.,\d]+$')

    def __init__(self):
        """初始化验证器"""
        self.errors: List[ValidationError] = []

    def validate_node(self, node: Dict[str, Any]) -> List[ValidationError]:
        """
        验证单个节点的所有 Phase 3-A 字段

        Args:
            node: 节点对象，包含 ID 和所有字段

        Returns:
            验证错误列表
        """
        self.errors = []
        # 主应用的图节点使用 node_id；早期 Phase 3-A 示例使用 id，两者都兼容
        node_id = node.get('node_id') or node.get('id', 'unknown')

        # 验证权限矩阵
        if node.get('approval_matrix'):
            self._validate_approval_matrix(node_id, node['approval_matrix'])

        # 验证评估条件中的聚合
        if node.get('evaluation_criteria'):
            self._validate_evaluation_criteria(node_id, node['evaluation_criteria'])

        # 验证临时措施
        if node.get('retry_semantics'):
            self._validate_temporary_measures(node_id, node['retry_semantics'])

        # 验证隔离范围
        if node.get('containment_scope'):
            self._validate_containment_scope(node_id, node['containment_scope'])

        # —— 本体维度 ——
        # 阈值缺单位 / 数值型标准缺阈值
        if isinstance(node.get('evaluation_criteria'), list):
            self._validate_threshold_units(node_id, node['evaluation_criteria'])

        # escalation 缺接收角色（SLA 超期升级 / 重复出现升级）
        self._validate_escalation_receivers(node_id, node)

        return self.errors

    def validate_evidence(self, obj: Dict[str, Any], kind: str = 'node') -> List[ValidationError]:
        """
        验证节点或边的证据维度：证据来源（source_turn_ids）与 confidence。

        PRD：每个节点/边必须保留 source_turn_ids（证据可追溯）、confidence、expert_confirmed，
        模型抽取结果不等于已确认事实。该检查放在图级（SchemaValidator）调用，
        因为它针对的是图中每个对象，而不是某个 Phase 3-A 字段。

        Args:
            obj: 节点或边对象
            kind: 'node' 或 'edge'

        Returns:
            验证错误列表
        """
        errors: List[ValidationError] = []
        if not isinstance(obj, dict):
            return errors

        if kind == 'edge':
            object_id = obj.get('edge_id') or obj.get('id', 'unknown')
        else:
            object_id = obj.get('node_id') or obj.get('id', 'unknown')
            # start/end 是结构性节点，不需要证据来源
            if obj.get('node_type') in self.STRUCTURAL_NODE_TYPES:
                return errors

        # 证据缺来源：既没有对话证据，也没有专家确认 → 无法追溯这条事实从哪里来
        source_turn_ids = obj.get('source_turn_ids')
        if not source_turn_ids and not obj.get('expert_confirmed'):
            errors.append(ValidationError(
                object_id,
                'source_turn_ids',
                'evidence_missing_source',
                f'{"边" if kind == "edge" else "节点"}缺少证据来源：既没有 source_turn_ids，也未经专家确认',
                suggestion='关联提出该内容的对话轮次（source_turn_ids），或请专家确认（expert_confirmed）',
                severity=ValidationSeverity.WARNING,
                object_kind=kind,
            ))
        elif source_turn_ids is not None and not isinstance(source_turn_ids, list):
            errors.append(ValidationError(
                object_id,
                'source_turn_ids',
                'type_error',
                'source_turn_ids 必须是数组',
                severity=ValidationSeverity.ERROR,
                object_kind=kind,
            ))

        # confidence 必须是 [0, 1] 区间内的数（schema: minimum 0, maximum 1）
        confidence = obj.get('confidence')
        if confidence is not None:
            # bool 是 int 的子类，需要单独排除
            is_number = isinstance(confidence, (int, float)) and not isinstance(confidence, bool)
            if not is_number or not 0 <= confidence <= 1:
                errors.append(ValidationError(
                    object_id,
                    'confidence',
                    'invalid_confidence',
                    f'confidence 必须是 0 到 1 之间的数，当前为：{confidence!r}',
                    severity=ValidationSeverity.ERROR,
                    object_kind=kind,
                ))

        return errors

    def _validate_threshold_units(self, node_id: str, criteria_list: List[Any]) -> None:
        """
        验证评估标准的阈值维度：
        - 阈值（thresholds 或 aggregation.threshold）是裸数字且没有 unit → WARNING threshold_missing_unit
        - 数值型标准（metric / numeric_range）既没有阈值也没有聚合条件 → WARNING metric_missing_threshold
        """
        for i, criterion in enumerate(criteria_list):
            if not isinstance(criterion, dict):
                continue
            path = f'evaluation_criteria[{i}]'
            label = criterion.get('name') or criterion.get('id') or f'第 {i+1} 项'

            # 收集本条标准里所有非空阈值（分级阈值 + 聚合阈值）
            thresholds = criterion.get('thresholds')
            level_values = [
                str(v).strip() for v in thresholds.values()
                if v is not None and str(v).strip()
            ] if isinstance(thresholds, dict) else []
            agg = criterion.get('aggregation')
            agg_value = str(agg.get('threshold') or '').strip() if isinstance(agg, dict) else ''
            threshold_values = level_values + ([agg_value] if agg_value else [])

            unit = criterion.get('unit')
            has_unit = isinstance(unit, str) and bool(unit.strip())

            # 阈值值里已自带单位（如 "3°C"、"< 85%"）时视为自描述；只有出现裸数字才算缺单位
            bare_values = [v for v in threshold_values if self._BARE_NUMBER_RE.match(v)]
            if bare_values and not has_unit:
                self.errors.append(ValidationError(
                    node_id,
                    f'{path}.unit',
                    'threshold_missing_unit',
                    f'评估标准「{label}」的阈值 {", ".join(bare_values)} 缺少单位',
                    suggestion='补充 unit（如 %、mm、℃、ppm、defects/mm²），无量纲指标也请写明（如 "ratio"）',
                    severity=ValidationSeverity.WARNING,
                ))

            if (criterion.get('type') in self.NUMERIC_CRITERION_TYPES
                    and not level_values and not isinstance(agg, dict)):
                self.errors.append(ValidationError(
                    node_id,
                    f'{path}.thresholds',
                    'metric_missing_threshold',
                    f'数值型评估标准「{label}」没有定义阈值或预期值',
                    suggestion='补充 thresholds（normal / warning / critical）或 aggregation 条件',
                    severity=ValidationSeverity.WARNING,
                ))

    def _validate_escalation_receivers(self, node_id: str, node: Dict[str, Any]) -> None:
        """
        验证 escalation 的接收角色（escalate_to_roles）：
        - sla_config.violation_action == 'escalate' 但没有接收角色 → ERROR（超期后无人接手）
        - retry_semantics.escalation_on_repeat 启用但没有 action → ERROR
        - escalation_on_repeat.action 为 escalate_to_* 但没有接收角色 → WARNING（action 只给了级别）
        - escalate_to_roles 中出现未知角色 → ERROR（与 approval_matrix 的 invalid_role 一致）
        """
        # SLA 超期升级
        sla = node.get('sla_config')
        if isinstance(sla, dict) and sla.get('violation_action') == 'escalate':
            roles = sla.get('escalate_to_roles')
            if not roles:
                self.errors.append(ValidationError(
                    node_id,
                    'sla_config.escalate_to_roles',
                    'escalation_missing_receiver',
                    'SLA 超期处理为 escalate，但没有指定升级接收角色',
                    suggestion=f'在 escalate_to_roles 中指定接收角色：{", ".join(sorted(self.VALID_ROLES))}',
                    severity=ValidationSeverity.ERROR,
                ))
            else:
                self._check_roles(node_id, 'sla_config.escalate_to_roles', roles)

        # 重复出现时升级
        retry = node.get('retry_semantics')
        repeat = retry.get('escalation_on_repeat') if isinstance(retry, dict) else None
        if isinstance(repeat, dict) and repeat.get('enabled'):
            field = 'retry_semantics.escalation_on_repeat'
            action = repeat.get('action')
            roles = repeat.get('escalate_to_roles')
            if not action:
                self.errors.append(ValidationError(
                    node_id,
                    f'{field}.action',
                    'required_field',
                    '已启用重复升级，但没有指定升级动作 action',
                    severity=ValidationSeverity.ERROR,
                ))
            elif action in self.ESCALATE_ACTIONS and not roles:
                self.errors.append(ValidationError(
                    node_id,
                    f'{field}.escalate_to_roles',
                    'escalation_missing_receiver',
                    f'升级动作为 {action}，但没有指定具体接收角色',
                    suggestion=f'在 escalate_to_roles 中指定接收角色：{", ".join(sorted(self.VALID_ROLES))}',
                    severity=ValidationSeverity.WARNING,
                ))
            if roles:
                self._check_roles(node_id, f'{field}.escalate_to_roles', roles)

    def _check_roles(self, node_id: str, field: str, roles: Any) -> None:
        """校验角色列表：必须是数组且每个角色都在 VALID_ROLES 中"""
        if not isinstance(roles, list):
            self.errors.append(ValidationError(
                node_id, field, 'type_error', f'{field} 必须是数组',
                severity=ValidationSeverity.ERROR,
            ))
            return
        for role in roles:
            if role not in self.VALID_ROLES:
                self.errors.append(ValidationError(
                    node_id, field, 'invalid_role', f'不认可的角色：{role}',
                    suggestion=f'使用以下角色之一：{", ".join(sorted(self.VALID_ROLES))}',
                    severity=ValidationSeverity.ERROR,
                ))

    def _validate_approval_matrix(self, node_id: str, approval_matrix: Any) -> None:
        """验证权限矩阵的完整性"""
        if not isinstance(approval_matrix, list):
            self.errors.append(ValidationError(
                node_id,
                'approval_matrix',
                'type_error',
                'approval_matrix 必须是数组',
                suggestion='检查数据类型是否正确',
                severity=ValidationSeverity.ERROR
            ))
            return

        if not approval_matrix:
            self.errors.append(ValidationError(
                node_id,
                'approval_matrix',
                'empty_array',
                'approval_matrix 不能为空',
                suggestion='至少添加一项批准规则',
                severity=ValidationSeverity.WARNING
            ))
            return

        seen_types = set()

        for i, approval in enumerate(approval_matrix):
            if not isinstance(approval, dict):
                self.errors.append(ValidationError(
                    node_id,
                    f'approval_matrix[{i}]',
                    'type_error',
                    f'第 {i+1} 项批准必须是对象',
                    severity=ValidationSeverity.ERROR
                ))
                continue

            # 检查 approval_type
            approval_type = approval.get('approval_type')
            if not approval_type:
                self.errors.append(ValidationError(
                    node_id,
                    f'approval_matrix[{i}].approval_type',
                    'required_field',
                    f'第 {i+1} 项的 approval_type 不能为空',
                    severity=ValidationSeverity.ERROR
                ))
            else:
                if approval_type in seen_types:
                    self.errors.append(ValidationError(
                        node_id,
                        f'approval_matrix[{i}].approval_type',
                        'duplicate_type',
                        f'approval_type "{approval_type}" 重复出现',
                        severity=ValidationSeverity.WARNING
                    ))
                seen_types.add(approval_type)

            # 检查 required_roles
            roles = approval.get('required_roles')
            if not roles:
                self.errors.append(ValidationError(
                    node_id,
                    f'approval_matrix[{i}].required_roles',
                    'required_field',
                    f'第 {i+1} 项的 required_roles 不能为空',
                    severity=ValidationSeverity.ERROR
                ))
            else:
                if not isinstance(roles, list):
                    self.errors.append(ValidationError(
                        node_id,
                        f'approval_matrix[{i}].required_roles',
                        'type_error',
                        f'required_roles 必须是数组',
                        severity=ValidationSeverity.ERROR
                    ))
                else:
                    for role in roles:
                        if role not in self.VALID_ROLES:
                            self.errors.append(ValidationError(
                                node_id,
                                f'approval_matrix[{i}].required_roles',
                                'invalid_role',
                                f'不认可的角色：{role}',
                                suggestion=f'使用以下角色之一：{", ".join(self.VALID_ROLES)}',
                                severity=ValidationSeverity.ERROR
                            ))

            # 检查 sequence
            sequence = approval.get('sequence')
            if sequence and sequence not in self.VALID_SEQUENCES:
                self.errors.append(ValidationError(
                    node_id,
                    f'approval_matrix[{i}].sequence',
                    'invalid_value',
                    f'sequence 必须是 parallel 或 sequential',
                    severity=ValidationSeverity.ERROR
                ))

            # 检查 criteria
            criteria = approval.get('criteria')
            if not criteria:
                self.errors.append(ValidationError(
                    node_id,
                    f'approval_matrix[{i}].criteria',
                    'required_field',
                    f'第 {i+1} 项的 criteria（批准标准）不能为空',
                    suggestion='添加具体的批准条件描述',
                    severity=ValidationSeverity.ERROR
                ))

            # 检查 escalation_level
            escalation = approval.get('escalation_level')
            if escalation is not None:
                if not isinstance(escalation, int) or escalation < 0:
                    self.errors.append(ValidationError(
                        node_id,
                        f'approval_matrix[{i}].escalation_level',
                        'type_error',
                        f'escalation_level 必须是非负整数',
                        severity=ValidationSeverity.ERROR
                    ))

    def _validate_evaluation_criteria(self, node_id: str, criteria_list: Any) -> None:
        """验证评估条件中的聚合条件"""
        if not isinstance(criteria_list, list):
            self.errors.append(ValidationError(
                node_id,
                'evaluation_criteria',
                'type_error',
                'evaluation_criteria 必须是数组',
                severity=ValidationSeverity.ERROR
            ))
            return

        for i, criterion in enumerate(criteria_list):
            if not isinstance(criterion, dict):
                continue

            # 仅验证包含聚合的条件
            if not criterion.get('aggregation'):
                continue

            agg = criterion['aggregation']
            criterion_path = f'evaluation_criteria[{i}].aggregation'

            # 检查聚合方法
            method = agg.get('method')
            if not method:
                self.errors.append(ValidationError(
                    node_id,
                    f'{criterion_path}.method',
                    'required_field',
                    f'第 {i+1} 项聚合条件的 method 不能为空',
                    severity=ValidationSeverity.ERROR
                ))
            elif method not in self.VALID_AGG_METHODS:
                self.errors.append(ValidationError(
                    node_id,
                    f'{criterion_path}.method',
                    'invalid_value',
                    f'不认可的聚合方法：{method}',
                    suggestion=f'使用以下之一：{", ".join(self.VALID_AGG_METHODS)}',
                    severity=ValidationSeverity.ERROR
                ))

            # 检查窗口大小
            window_size = agg.get('window_size')
            if window_size is not None:
                if not isinstance(window_size, int) or window_size < 2:
                    self.errors.append(ValidationError(
                        node_id,
                        f'{criterion_path}.window_size',
                        'invalid_value',
                        f'window_size 必须是大于等于 2 的整数',
                        severity=ValidationSeverity.ERROR
                    ))
                elif window_size > 100:
                    self.errors.append(ValidationError(
                        node_id,
                        f'{criterion_path}.window_size',
                        'value_too_large',
                        f'window_size 过大：{window_size}（建议不超过 100）',
                        severity=ValidationSeverity.WARNING
                    ))

            # 检查操作符
            operator = agg.get('operator')
            if operator and operator not in self.VALID_AGG_OPERATORS:
                self.errors.append(ValidationError(
                    node_id,
                    f'{criterion_path}.operator',
                    'invalid_value',
                    f'不认可的操作符：{operator}',
                    severity=ValidationSeverity.ERROR
                ))

            # 检查最小样本数
            min_samples = agg.get('min_samples')
            if min_samples is not None:
                if not isinstance(min_samples, int) or min_samples < 1:
                    self.errors.append(ValidationError(
                        node_id,
                        f'{criterion_path}.min_samples',
                        'invalid_value',
                        f'min_samples 必须是正整数',
                        severity=ValidationSeverity.ERROR
                    ))
                elif window_size and min_samples > window_size:
                    self.errors.append(ValidationError(
                        node_id,
                        f'{criterion_path}.min_samples',
                        'logic_error',
                        f'min_samples ({min_samples}) 不能大于 window_size ({window_size})',
                        severity=ValidationSeverity.ERROR
                    ))

            # 检查描述
            if not agg.get('description'):
                self.errors.append(ValidationError(
                    node_id,
                    f'{criterion_path}.description',
                    'required_field',
                    f'聚合条件的描述不能为空',
                    severity=ValidationSeverity.WARNING
                ))

    def _validate_temporary_measures(self, node_id: str, retry: Any) -> None:
        """验证临时措施的生命周期字段"""
        if not isinstance(retry, dict):
            return

        if not retry.get('is_temporary'):
            return  # 不是临时措施，跳过验证

        # 检查 expiration 字段
        expiration = retry.get('expiration')
        if not expiration:
            self.errors.append(ValidationError(
                node_id,
                'retry_semantics.expiration',
                'required_field',
                '临时措施必须定义 expiration',
                severity=ValidationSeverity.ERROR
            ))
        else:
            self._validate_expiration(node_id, expiration)

        # 检查 revocation_trigger
        revocation = retry.get('revocation_trigger')
        if not revocation:
            self.errors.append(ValidationError(
                node_id,
                'retry_semantics.revocation_trigger',
                'required_field',
                '临时措施必须定义 revocation_trigger',
                severity=ValidationSeverity.WARNING
            ))
        else:
            self._validate_revocation_trigger(node_id, revocation)

        # 检查 max_retries_per_phase
        max_retries = retry.get('max_retries_per_phase')
        if max_retries is not None:
            if not isinstance(max_retries, int) or max_retries <= 0:
                self.errors.append(ValidationError(
                    node_id,
                    'retry_semantics.max_retries_per_phase',
                    'invalid_value',
                    'max_retries_per_phase 必须是正整数',
                    severity=ValidationSeverity.ERROR
                ))

    def _validate_expiration(self, node_id: str, expiration: Any) -> None:
        """验证过期配置"""
        if not isinstance(expiration, dict):
            self.errors.append(ValidationError(
                node_id,
                'retry_semantics.expiration',
                'type_error',
                'expiration 必须是对象',
                severity=ValidationSeverity.ERROR
            ))
            return

        # 检查 duration（ISO 8601 格式）
        duration = expiration.get('duration')
        if duration:
            if not self._is_valid_iso8601_duration(duration):
                self.errors.append(ValidationError(
                    node_id,
                    'retry_semantics.expiration.duration',
                    'invalid_format',
                    f'duration 格式无效：{duration}（需要 ISO 8601 格式，如 PT72H）',
                    severity=ValidationSeverity.ERROR
                ))

        # 检查 lot_count
        lot_count = expiration.get('lot_count')
        if lot_count is not None:
            if not isinstance(lot_count, int) or lot_count <= 0:
                self.errors.append(ValidationError(
                    node_id,
                    'retry_semantics.expiration.lot_count',
                    'invalid_value',
                    'lot_count 必须是正整数',
                    severity=ValidationSeverity.ERROR
                ))

        # 检查 expiration_trigger
        trigger = expiration.get('expiration_trigger')
        if trigger not in ['duration_or_count', 'duration_and_count', None]:
            self.errors.append(ValidationError(
                node_id,
                'retry_semantics.expiration.expiration_trigger',
                'invalid_value',
                f'expiration_trigger 必须是 duration_or_count 或 duration_and_count',
                severity=ValidationSeverity.ERROR
            ))

    def _validate_revocation_trigger(self, node_id: str, revocation: Any) -> None:
        """验证撤销触发器配置"""
        if not isinstance(revocation, dict):
            self.errors.append(ValidationError(
                node_id,
                'retry_semantics.revocation_trigger',
                'type_error',
                'revocation_trigger 必须是对象',
                severity=ValidationSeverity.ERROR
            ))
            return

        # 检查 type
        revocation_type = revocation.get('type')
        if revocation_type not in ['time_passed', 'reoccurrence', 'condition_met', None]:
            self.errors.append(ValidationError(
                node_id,
                'retry_semantics.revocation_trigger.type',
                'invalid_value',
                f'type 必须是 time_passed、reoccurrence 或 condition_met',
                severity=ValidationSeverity.ERROR
            ))

        # 如果是 time_passed 或 reoccurrence，检查 days
        if revocation_type in ['time_passed', 'reoccurrence']:
            days = revocation.get('days')
            if not days:
                self.errors.append(ValidationError(
                    node_id,
                    'retry_semantics.revocation_trigger.days',
                    'required_field',
                    f'revocation_type 为 {revocation_type} 时，days 不能为空',
                    severity=ValidationSeverity.ERROR
                ))
            elif not isinstance(days, int) or days <= 0:
                self.errors.append(ValidationError(
                    node_id,
                    'retry_semantics.revocation_trigger.days',
                    'invalid_value',
                    'days 必须是正整数',
                    severity=ValidationSeverity.ERROR
                ))

    def _validate_containment_scope(self, node_id: str, containment: Any) -> None:
        """验证隔离范围配置"""
        if not isinstance(containment, dict):
            self.errors.append(ValidationError(
                node_id,
                'containment_scope',
                'type_error',
                'containment_scope 必须是对象',
                severity=ValidationSeverity.ERROR
            ))
            return

        # 检查 dimension
        dimension = containment.get('dimension')
        if not dimension:
            self.errors.append(ValidationError(
                node_id,
                'containment_scope.dimension',
                'required_field',
                'containment_scope 的 dimension 不能为空',
                severity=ValidationSeverity.ERROR
            ))
        elif dimension not in self.VALID_DIMENSIONS:
            self.errors.append(ValidationError(
                node_id,
                'containment_scope.dimension',
                'invalid_value',
                f'不认可的隔离维度：{dimension}',
                suggestion=f'使用以下之一：{", ".join(self.VALID_DIMENSIONS)}',
                severity=ValidationSeverity.ERROR
            ))

        # 检查 rule
        rule = containment.get('rule')
        if not rule:
            self.errors.append(ValidationError(
                node_id,
                'containment_scope.rule',
                'required_field',
                'containment_scope 的 rule 不能为空',
                severity=ValidationSeverity.ERROR
            ))

        # 检查 applicable_conditions
        conditions = containment.get('applicable_conditions')
        if conditions is not None:
            if not isinstance(conditions, list):
                self.errors.append(ValidationError(
                    node_id,
                    'containment_scope.applicable_conditions',
                    'type_error',
                    'applicable_conditions 必须是数组',
                    severity=ValidationSeverity.ERROR
                ))

    def _is_valid_iso8601_duration(self, duration_str: str) -> bool:
        """
        检查是否为有效的 ISO 8601 duration 格式
        例如：PT72H, P3D, PT30M, PT1H30M
        """
        pattern = r'^P(?:\d+Y)?(?:\d+M)?(?:\d+W)?(?:\d+D)?(?:T(?:\d+H)?(?:\d+M)?(?:\d+(?:\.\d+)?S)?)?$'
        return bool(re.match(pattern, duration_str)) if duration_str else True


class SchemaValidator:
    """高级验证器，整合所有验证规则"""

    def __init__(self):
        self.phase3a_validator = Phase3AValidator()

    def validate_graph(self, workflow_graph: Dict[str, Any]) -> Dict[str, Any]:
        """
        验证完整的工作流 DAG

        Args:
            workflow_graph: 工作流 DAG 对象

        Returns:
            {
                'valid': bool,
                'errors': List[ValidationError],
                'error_count': int,
                'warning_count': int,
                'summary': str
            }
        """
        all_errors = []

        # 验证所有节点（Phase 3-A 字段 + 证据维度）
        for node in workflow_graph.get('nodes') or []:
            all_errors.extend(self.phase3a_validator.validate_node(node))
            all_errors.extend(self.phase3a_validator.validate_evidence(node, 'node'))

        # 验证所有边（证据维度）
        for edge in workflow_graph.get('edges') or []:
            all_errors.extend(self.phase3a_validator.validate_evidence(edge, 'edge'))

        # 统计错误
        error_count = sum(1 for e in all_errors if e.severity == ValidationSeverity.ERROR)
        warning_count = sum(1 for e in all_errors if e.severity == ValidationSeverity.WARNING)

        return {
            'valid': error_count == 0,
            'errors': [e.to_dict() for e in all_errors],
            'error_count': error_count,
            'warning_count': warning_count,
            'summary': self._generate_summary(error_count, warning_count)
        }

    def _generate_summary(self, error_count: int, warning_count: int) -> str:
        """生成验证摘要"""
        if error_count == 0 and warning_count == 0:
            return '✅ 验证通过，无错误或警告'

        parts = []
        if error_count > 0:
            parts.append(f'❌ {error_count} 个错误')
        if warning_count > 0:
            parts.append(f'⚠️  {warning_count} 个警告')

        return '，'.join(parts)

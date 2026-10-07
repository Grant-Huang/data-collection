"""Phase 3-A Validator 的完整测试套件"""

import unittest
from phase3a_validator import (
    Phase3AValidator, SchemaValidator, ValidationError, ValidationSeverity
)


class TestApprovalMatrixValidation(unittest.TestCase):
    """权限矩阵验证的测试用例"""

    def setUp(self):
        self.validator = Phase3AValidator()

    def test_valid_approval_matrix(self):
        """测试有效的权限矩阵"""
        node = {
            'id': 'n1',
            'approval_matrix': [
                {
                    'approval_type': 'equipment_release',
                    'required_roles': ['equipment_engineer'],
                    'sequence': 'sequential',
                    'criteria': '设备状态正常，无报警',
                    'escalation_level': 1
                },
                {
                    'approval_type': 'process_release',
                    'required_roles': ['process_engineer'],
                    'sequence': 'sequential',
                    'criteria': '工艺参数在范围内',
                    'escalation_level': 1
                }
            ]
        }
        errors = self.validator.validate_node(node)
        self.assertEqual(len(errors), 0, f'预期无错误，但得到：{errors}')

    def test_missing_approval_type(self):
        """测试缺少 approval_type"""
        node = {
            'id': 'n2',
            'approval_matrix': [
                {
                    'required_roles': ['equipment_engineer'],
                    'sequence': 'sequential',
                    'criteria': '设备状态正常'
                }
            ]
        }
        errors = self.validator.validate_node(node)
        self.assertTrue(any(e.code == 'required_field' and 'approval_type' in e.field
                           for e in errors), '应该报告缺少 approval_type')

    def test_invalid_role(self):
        """测试无效的角色"""
        node = {
            'id': 'n3',
            'approval_matrix': [
                {
                    'approval_type': 'test_release',
                    'required_roles': ['invalid_role_name'],
                    'sequence': 'sequential',
                    'criteria': '测试标准'
                }
            ]
        }
        errors = self.validator.validate_node(node)
        self.assertTrue(any(e.code == 'invalid_role' for e in errors),
                       '应该报告无效角色')

    def test_invalid_sequence(self):
        """测试无效的 sequence 值"""
        node = {
            'id': 'n4',
            'approval_matrix': [
                {
                    'approval_type': 'test_release',
                    'required_roles': ['equipment_engineer'],
                    'sequence': 'invalid_sequence',
                    'criteria': '测试标准'
                }
            ]
        }
        errors = self.validator.validate_node(node)
        self.assertTrue(any(e.code == 'invalid_value' and 'sequence' in e.field
                           for e in errors), '应该报告无效的 sequence')

    def test_missing_criteria(self):
        """测试缺少 criteria"""
        node = {
            'id': 'n5',
            'approval_matrix': [
                {
                    'approval_type': 'test_release',
                    'required_roles': ['equipment_engineer'],
                    'sequence': 'sequential'
                }
            ]
        }
        errors = self.validator.validate_node(node)
        self.assertTrue(any(e.code == 'required_field' and 'criteria' in e.field
                           for e in errors), '应该报告缺少 criteria')

    def test_duplicate_approval_type(self):
        """测试重复的 approval_type"""
        node = {
            'id': 'n6',
            'approval_matrix': [
                {
                    'approval_type': 'equipment_release',
                    'required_roles': ['equipment_engineer'],
                    'sequence': 'sequential',
                    'criteria': '条件 1'
                },
                {
                    'approval_type': 'equipment_release',
                    'required_roles': ['process_engineer'],
                    'sequence': 'sequential',
                    'criteria': '条件 2'
                }
            ]
        }
        errors = self.validator.validate_node(node)
        self.assertTrue(any(e.code == 'duplicate_type' for e in errors),
                       '应该报告重复的 approval_type')


class TestAggregationValidation(unittest.TestCase):
    """聚合条件验证的测试用例"""

    def setUp(self):
        self.validator = Phase3AValidator()

    def test_valid_aggregation(self):
        """测试有效的聚合条件"""
        node = {
            'id': 'n1',
            'evaluation_criteria': [
                {
                    'id': 'temp_trend',
                    'name': '温度趋势',
                    'aggregation': {
                        'method': 'trend',
                        'window_size': 7,
                        'operator': 'all_increasing',
                        'threshold': '3',
                        'min_samples': 5,
                        'description': '过去 7 个点持续上升'
                    }
                }
            ]
        }
        errors = self.validator.validate_node(node)
        self.assertEqual(len(errors), 0, f'预期无错误，但得到：{errors}')

    def test_invalid_aggregation_method(self):
        """测试无效的聚合方法"""
        node = {
            'id': 'n2',
            'evaluation_criteria': [
                {
                    'id': 'test',
                    'aggregation': {
                        'method': 'invalid_method',
                        'window_size': 7,
                        'operator': 'all_increasing',
                        'min_samples': 5,
                        'description': '测试'
                    }
                }
            ]
        }
        errors = self.validator.validate_node(node)
        self.assertTrue(any(e.code == 'invalid_value' and 'method' in e.field
                           for e in errors), '应该报告无效的聚合方法')

    def test_invalid_window_size(self):
        """测试无效的窗口大小"""
        node = {
            'id': 'n3',
            'evaluation_criteria': [
                {
                    'id': 'test',
                    'aggregation': {
                        'method': 'trend',
                        'window_size': 1,  # 应该 >= 2
                        'operator': 'all_increasing',
                        'min_samples': 1,
                        'description': '测试'
                    }
                }
            ]
        }
        errors = self.validator.validate_node(node)
        self.assertTrue(any(e.code == 'invalid_value' and 'window_size' in e.field
                           for e in errors), '应该报告无效的窗口大小')

    def test_min_samples_exceeds_window(self):
        """测试最小样本数超过窗口大小"""
        node = {
            'id': 'n4',
            'evaluation_criteria': [
                {
                    'id': 'test',
                    'aggregation': {
                        'method': 'trend',
                        'window_size': 5,
                        'operator': 'all_increasing',
                        'min_samples': 10,  # 大于 window_size
                        'description': '测试'
                    }
                }
            ]
        }
        errors = self.validator.validate_node(node)
        self.assertTrue(any(e.code == 'logic_error' for e in errors),
                       '应该报告逻辑错误：min_samples > window_size')

    def test_missing_description(self):
        """测试缺少描述"""
        node = {
            'id': 'n5',
            'evaluation_criteria': [
                {
                    'id': 'test',
                    'aggregation': {
                        'method': 'trend',
                        'window_size': 7,
                        'operator': 'all_increasing',
                        'min_samples': 5
                    }
                }
            ]
        }
        errors = self.validator.validate_node(node)
        warnings = [e for e in errors if e.severity == ValidationSeverity.WARNING]
        self.assertTrue(any(w.code == 'required_field' and 'description' in w.field
                           for w in warnings), '应该报告缺少描述的警告')


class TestTemporaryMeasuresValidation(unittest.TestCase):
    """临时措施验证的测试用例"""

    def setUp(self):
        self.validator = Phase3AValidator()

    def test_valid_temporary_measure(self):
        """测试有效的临时措施"""
        node = {
            'id': 'n1',
            'retry_semantics': {
                'enabled': True,
                'is_temporary': True,
                'max_retries_per_phase': 1,
                'expiration': {
                    'duration': 'PT72H',
                    'lot_count': 3,
                    'expiration_trigger': 'duration_or_count'
                },
                'revocation_trigger': {
                    'type': 'reoccurrence',
                    'days': 30,
                    'description': '30 天内同一故障再次出现则失效'
                }
            }
        }
        errors = self.validator.validate_node(node)
        self.assertEqual(len(errors), 0, f'预期无错误，但得到：{errors}')

    def test_invalid_duration_format(self):
        """测试无效的 duration 格式"""
        node = {
            'id': 'n2',
            'retry_semantics': {
                'is_temporary': True,
                'expiration': {
                    'duration': 'invalid_duration',
                    'lot_count': 3,
                    'expiration_trigger': 'duration_or_count'
                },
                'revocation_trigger': {
                    'type': 'time_passed',
                    'days': 30
                }
            }
        }
        errors = self.validator.validate_node(node)
        self.assertTrue(any(e.code == 'invalid_format' and 'duration' in e.field
                           for e in errors), '应该报告无效的 duration 格式')

    def test_missing_revocation_trigger(self):
        """测试缺少 revocation_trigger"""
        node = {
            'id': 'n3',
            'retry_semantics': {
                'is_temporary': True,
                'expiration': {
                    'duration': 'PT72H',
                    'lot_count': 3
                }
            }
        }
        errors = self.validator.validate_node(node)
        warnings = [e for e in errors if e.severity == ValidationSeverity.WARNING]
        self.assertTrue(any(w.code == 'required_field' and 'revocation_trigger' in w.field
                           for w in warnings), '应该报告缺少 revocation_trigger')

    def test_invalid_revocation_type(self):
        """测试无效的 revocation 类型"""
        node = {
            'id': 'n4',
            'retry_semantics': {
                'is_temporary': True,
                'expiration': {
                    'duration': 'PT72H',
                    'lot_count': 3
                },
                'revocation_trigger': {
                    'type': 'invalid_type',
                    'days': 30
                }
            }
        }
        errors = self.validator.validate_node(node)
        self.assertTrue(any(e.code == 'invalid_value' and 'revocation_trigger' in e.field
                           for e in errors), '应该报告无效的 revocation 类型')

    def test_missing_days_for_time_passed(self):
        """测试 time_passed 类型缺少 days"""
        node = {
            'id': 'n5',
            'retry_semantics': {
                'is_temporary': True,
                'expiration': {
                    'duration': 'PT72H'
                },
                'revocation_trigger': {
                    'type': 'time_passed'
                }
            }
        }
        errors = self.validator.validate_node(node)
        self.assertTrue(any(e.code == 'required_field' and 'days' in e.field
                           for e in errors), '应该报告缺少 days')


class TestContainmentScopeValidation(unittest.TestCase):
    """隔离范围验证的测试用例"""

    def setUp(self):
        self.validator = Phase3AValidator()

    def test_valid_containment_scope(self):
        """测试有效的隔离范围"""
        node = {
            'id': 'n1',
            'containment_scope': {
                'dimension': 'equipment_id',
                'rule': 'all_products_on_same_equipment',
                'applicable_conditions': ['equipment_failure']
            }
        }
        errors = self.validator.validate_node(node)
        self.assertEqual(len(errors), 0, f'预期无错误，但得到：{errors}')

    def test_invalid_dimension(self):
        """测试无效的隔离维度"""
        node = {
            'id': 'n2',
            'containment_scope': {
                'dimension': 'invalid_dimension',
                'rule': 'isolation_rule'
            }
        }
        errors = self.validator.validate_node(node)
        self.assertTrue(any(e.code == 'invalid_value' and 'dimension' in e.field
                           for e in errors), '应该报告无效的隔离维度')

    def test_missing_dimension(self):
        """测试缺少 dimension"""
        node = {
            'id': 'n3',
            'containment_scope': {
                'rule': 'isolation_rule'
            }
        }
        errors = self.validator.validate_node(node)
        self.assertTrue(any(e.code == 'required_field' and 'dimension' in e.field
                           for e in errors), '应该报告缺少 dimension')

    def test_missing_rule(self):
        """测试缺少 rule"""
        node = {
            'id': 'n4',
            'containment_scope': {
                'dimension': 'lot_id'
            }
        }
        errors = self.validator.validate_node(node)
        self.assertTrue(any(e.code == 'required_field' and 'rule' in e.field
                           for e in errors), '应该报告缺少 rule')

    def test_invalid_applicable_conditions_type(self):
        """测试无效的 applicable_conditions 类型"""
        node = {
            'id': 'n5',
            'containment_scope': {
                'dimension': 'equipment_id',
                'rule': 'isolation_rule',
                'applicable_conditions': 'not_an_array'
            }
        }
        errors = self.validator.validate_node(node)
        self.assertTrue(any(e.code == 'type_error' and 'applicable_conditions' in e.field
                           for e in errors), '应该报告类型错误')


class TestSchemaValidator(unittest.TestCase):
    """高级 SchemaValidator 的测试用例"""

    def setUp(self):
        self.validator = SchemaValidator()

    def test_validate_complete_graph(self):
        """测试验证完整的工作流 DAG"""
        graph = {
            'nodes': [
                {
                    'id': 'n1',
                    'approval_matrix': [
                        {
                            'approval_type': 'test_release',
                            'required_roles': ['equipment_engineer'],
                            'sequence': 'sequential',
                            'criteria': '设备状态正常'
                        }
                    ]
                },
                {
                    'id': 'n2',
                    'containment_scope': {
                        'dimension': 'equipment_id',
                        'rule': 'isolation_rule'
                    }
                }
            ]
        }
        result = self.validator.validate_graph(graph)
        self.assertTrue(result['valid'], '应该验证通过')
        self.assertEqual(result['error_count'], 0, '应该没有错误')

    def test_validate_graph_with_errors(self):
        """测试包含错误的工作流 DAG"""
        graph = {
            'nodes': [
                {
                    'id': 'n1',
                    'approval_matrix': [
                        {
                            'approval_type': 'test',
                            'required_roles': ['invalid_role'],
                            'sequence': 'sequential',
                            'criteria': '标准'
                        }
                    ]
                }
            ]
        }
        result = self.validator.validate_graph(graph)
        self.assertFalse(result['valid'], '应该验证失败')
        self.assertGreater(result['error_count'], 0, '应该有错误')

    def test_summary_generation(self):
        """测试摘要生成"""
        graph = {
            'nodes': [
                {
                    'id': 'n1',
                    'approval_matrix': [
                        {
                            'approval_type': 'test',
                            'required_roles': ['invalid_role'],
                            'sequence': 'sequential',
                            'criteria': '标准'
                        }
                    ]
                }
            ]
        }
        result = self.validator.validate_graph(graph)
        self.assertIsNotNone(result['summary'], '应该生成摘要')
        self.assertIn('错误', result['summary'], '摘要应该包含错误信息')


if __name__ == '__main__':
    unittest.main()

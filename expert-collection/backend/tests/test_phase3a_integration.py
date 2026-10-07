"""Phase 3-A 集成测试 - 验证 Phase 3-A 功能在主应用中的正确集成"""

import sys
import unittest
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import phase3a_integration


class TestPhase3AIntegration(unittest.TestCase):
    """测试 Phase 3-A 与主应用的集成"""

    def setUp(self):
        """设置测试环境"""
        self.validator = phase3a_integration.Phase3AValidator()
        self.collection = phase3a_integration.Phase3ACollectionIntegration()

    def test_validator_initialization(self):
        """测试验证器初始化"""
        self.assertIsNotNone(self.validator)
        self.assertIsNotNone(self.validator.validator)

    def test_validate_simple_graph(self):
        """测试验证简单的工作流 DAG"""
        graph = {
            'nodes': [
                {
                    'id': 'n1',
                    'approval_matrix': [
                        {
                            'approval_type': 'test',
                            'required_roles': ['equipment_engineer'],
                            'sequence': 'sequential',
                            'criteria': '标准'
                        }
                    ]
                }
            ]
        }

        result = self.validator.validate_workflow_graph(graph)

        self.assertIsNotNone(result)
        self.assertIn('valid', result)
        self.assertIn('errors', result)
        self.assertIn('error_count', result)
        self.assertIn('warning_count', result)
        self.assertIn('summary', result)

    def test_validate_and_enrich_graph(self):
        """测试验证并增强图数据"""
        graph = {
            'nodes': [
                {
                    'id': 'n1',
                    'approval_matrix': [
                        {
                            'approval_type': 'approval1',
                            'required_roles': ['equipment_engineer'],
                            'sequence': 'sequential',
                            'criteria': '设备状态正常'
                        }
                    ],
                    'evaluation_criteria': [
                        {
                            'id': 'agg1',
                            'name': '聚合条件',
                            'aggregation': {
                                'method': 'trend',
                                'window_size': 7,
                                'operator': 'all_increasing',
                                'min_samples': 5,
                                'description': '趋势上升'
                            }
                        }
                    ]
                },
                {
                    'id': 'n2',
                    'retry_semantics': {
                        'enabled': True,
                        'is_temporary': True,
                        'expiration': {
                            'duration': 'PT72H',
                            'lot_count': 3
                        },
                        'revocation_trigger': {
                            'type': 'reoccurrence',
                            'days': 30
                        }
                    }
                },
                {
                    'id': 'n3',
                    'containment_scope': {
                        'dimension': 'equipment_id',
                        'rule': 'all_products_on_same_equipment'
                    }
                }
            ]
        }

        result = phase3a_integration.validate_and_enrich_graph(graph)

        # 检查结构
        self.assertIn('validation', result)
        self.assertIn('features', result)

        # 检查特性检测
        features = result['features']
        self.assertTrue(features['has_approval_matrix'])
        self.assertTrue(features['has_aggregation'])
        self.assertTrue(features['has_temporary_measures'])
        self.assertTrue(features['has_containment'])

        # 检查节点计数
        self.assertEqual(features['approval_matrix_nodes'], 1)
        self.assertEqual(features['aggregation_nodes'], 1)
        self.assertEqual(features['temporary_measure_nodes'], 1)
        self.assertEqual(features['containment_nodes'], 1)

    def test_conversion_to_legacy_issues(self):
        """测试转换为旧版 issue 格式"""
        validation_result = {
            'valid': False,
            'errors': [
                {
                    'severity': 'error',
                    'field': 'approval_matrix[0].required_roles',
                    'code': 'invalid_role',
                    'message': '不认可的角色',
                    'suggestion': '使用有效的角色'
                }
            ],
            'error_count': 1,
            'warning_count': 0,
            'summary': '❌ 1 个错误'
        }

        issues = self.validator.convert_to_legacy_issues(validation_result)

        self.assertEqual(len(issues), 1)
        issue = issues[0]
        self.assertEqual(issue['level'], 'error')
        self.assertIn('phase3a_', issue['code'])
        self.assertIn('不认可的角色', issue['message'])

    def test_collection_plan_creation(self):
        """测试采集计划创建"""
        plan = self.collection.create_collection_plan('李工程师', 'Release 批准流程')

        self.assertIsNotNone(plan)
        self.assertEqual(plan['expert_name'], '李工程师')
        self.assertEqual(plan['workflow_name'], 'Release 批准流程')
        self.assertIn('phases', plan)
        self.assertEqual(len(plan['phases']), 5)
        self.assertIn('success_criteria', plan)
        self.assertIn('total_estimated_time_minutes', plan)

    def test_collection_plan_phases(self):
        """测试采集计划的各个阶段"""
        plan = self.collection.create_collection_plan('test', 'test_workflow')

        # 检查每个阶段
        for i, phase_info in enumerate(plan['phases'], 1):
            self.assertEqual(phase_info['phase'], i)
            self.assertIn('dimension', phase_info)
            self.assertIn('questions', phase_info)
            self.assertIn('estimated_time_minutes', phase_info)

            # 检查问题不为空
            self.assertGreater(len(phase_info['questions']), 0)

            # 检查每个问题有必要的字段
            for question in phase_info['questions']:
                self.assertIsNotNone(question)

    def test_quality_checklist(self):
        """测试质量检查清单"""
        checklist = self.collection.get_quality_checklist()

        self.assertIsNotNone(checklist)
        self.assertGreater(len(checklist), 0)

        # 检查清单项都是字符串
        for item in checklist:
            self.assertIsInstance(item, str)

    def test_data_extraction(self):
        """测试数据提取功能"""
        node = {
            'id': 'n1',
            'approval_matrix': [
                {
                    'approval_type': 'type1',
                    'required_roles': ['engineer'],
                    'sequence': 'sequential',
                    'criteria': 'test'
                }
            ],
            'evaluation_criteria': [
                {
                    'id': 'crit1',
                    'name': 'test',
                    'aggregation': {
                        'method': 'trend',
                        'window_size': 7
                    }
                }
            ],
            'retry_semantics': {
                'enabled': True,
                'is_temporary': True,
                'expiration': {'duration': 'PT72H'}
            },
            'containment_scope': {
                'dimension': 'equipment_id',
                'rule': 'test'
            }
        }

        extractor = phase3a_integration.Phase3ADataExtractor()

        # 测试每个提取器
        approval = extractor.extract_approval_matrix(node)
        self.assertIsNotNone(approval)
        self.assertEqual(len(approval), 1)

        agg = extractor.extract_aggregation_conditions(node)
        self.assertIsNotNone(agg)
        self.assertEqual(len(agg), 1)

        temp = extractor.extract_temporary_measures(node)
        self.assertIsNotNone(temp)
        self.assertTrue(temp['enabled'])

        contain = extractor.extract_containment_scope(node)
        self.assertIsNotNone(contain)
        self.assertEqual(contain['dimension'], 'equipment_id')

    def test_features_summary(self):
        """测试特性摘要"""
        graph = {
            'nodes': [
                {
                    'id': 'n1',
                    'approval_matrix': [{'approval_type': 't1', 'required_roles': ['r1'], 'sequence': 's', 'criteria': 'c'}],
                    'evaluation_criteria': [{'id': 'c1', 'aggregation': {'method': 'trend', 'window_size': 7, 'operator': 'op', 'min_samples': 5, 'description': 'd'}}],
                },
                {
                    'id': 'n2',
                    'retry_semantics': {'is_temporary': True, 'expiration': {'duration': 'P1D'}},
                },
                {
                    'id': 'n3',
                    'containment_scope': {'dimension': 'lot_id', 'rule': 'r'},
                }
            ]
        }

        extractor = phase3a_integration.Phase3ADataExtractor()
        summary = extractor.summarize_phase3a_features(graph)

        self.assertTrue(summary['has_approval_matrix'])
        self.assertTrue(summary['has_aggregation'])
        self.assertTrue(summary['has_temporary_measures'])
        self.assertTrue(summary['has_containment'])

        self.assertEqual(summary['approval_matrix_nodes'], 1)
        self.assertEqual(summary['aggregation_nodes'], 1)
        self.assertEqual(summary['temporary_measure_nodes'], 1)
        self.assertEqual(summary['containment_nodes'], 1)

    def test_global_instances(self):
        """测试全局实例获取"""
        validator = phase3a_integration.get_validator()
        self.assertIsNotNone(validator)

        collection = phase3a_integration.get_collection()
        self.assertIsNotNone(collection)

        # 再次获取应该返回同一个实例
        validator2 = phase3a_integration.get_validator()
        self.assertIs(validator, validator2)

        collection2 = phase3a_integration.get_collection()
        self.assertIs(collection, collection2)


class TestPhase3AValidationConfig(unittest.TestCase):
    """测试 Phase 3-A 验证配置"""

    def test_config_modification(self):
        """测试配置修改"""
        config = phase3a_integration.Phase3AValidationConfig

        # 测试启用/禁用规则
        original_state = config.RULES_CONFIG['approval_matrix']['enabled']
        config.set_rule_enabled('approval_matrix', False)
        self.assertFalse(config.RULES_CONFIG['approval_matrix']['enabled'])

        # 恢复原状态
        config.set_rule_enabled('approval_matrix', original_state)
        self.assertEqual(config.RULES_CONFIG['approval_matrix']['enabled'], original_state)

    def test_strict_mode(self):
        """测试严格模式"""
        config = phase3a_integration.Phase3AValidationConfig

        original_state = config.RULES_CONFIG['aggregation']['strict']
        config.set_strict_mode('aggregation', True)
        self.assertTrue(config.RULES_CONFIG['aggregation']['strict'])

        config.set_strict_mode('aggregation', original_state)
        self.assertEqual(config.RULES_CONFIG['aggregation']['strict'], original_state)


class TestPhase3AErrorHandling(unittest.TestCase):
    """测试 Phase 3-A 错误处理"""

    def test_invalid_graph_structure(self):
        """测试无效的图结构"""
        validator = phase3a_integration.Phase3AValidator()

        # 缺少必要字段
        invalid_graph = {
            'nodes': [
                {
                    'id': 'n1',
                    'approval_matrix': [
                        {
                            'required_roles': ['engineer'],
                            'sequence': 'sequential'
                            # 缺少 approval_type 和 criteria
                        }
                    ]
                }
            ]
        }

        result = validator.validate_workflow_graph(invalid_graph)
        self.assertFalse(result['valid'])
        self.assertGreater(result['error_count'], 0)

    def test_missing_module_handling(self):
        """测试缺失模块的处理"""
        # 这个测试验证了如果 Phase 3-A 模块不可用，系统能够正常处理
        # 实际测试应该在移除依赖时进行
        graph = {'nodes': []}

        try:
            result = phase3a_integration.validate_and_enrich_graph(graph)
            # 即使没有 Phase 3-A 特性，应该仍然返回有效结果
            self.assertIsNotNone(result)
        except Exception as e:
            self.fail(f"验证不应该抛出异常：{e}")


if __name__ == '__main__':
    unittest.main()

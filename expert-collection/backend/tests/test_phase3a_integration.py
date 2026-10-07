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


class TestOntologyDimensionIntegration(unittest.TestCase):
    """Phase 3-A 证据维度规则在主应用中的集成（阈值/升级角色由 ontology_validator 负责）"""

    # 主应用真实形态的图：节点用 node_id，边用 edge_id + from/to
    GRAPH = {
        'nodes': [
            {'node_id': 'start', 'node_type': 'start', 'label': '开始', 'source_turn_ids': []},
            {'node_id': 'n1', 'node_type': 'activity', 'label': '初评', 'source_turn_ids': ['t1'],
             'confidence': 1.5,
             'retry_semantics': {'escalation_on_repeat': {'enabled': True}}},
            {'node_id': 'n2', 'node_type': 'activity', 'label': '测温', 'source_turn_ids': ['t2'],
             'sla_config': {'duration': 'PT2H', 'violation_action': 'escalate'}},
            {'node_id': 'end', 'node_type': 'end', 'label': '结束', 'source_turn_ids': []},
        ],
        'edges': [
            {'edge_id': 'e1', 'from': 'start', 'to': 'n1', 'edge_type': 'normal', 'source_turn_ids': []},
            {'edge_id': 'e2', 'from': 'n1', 'to': 'n2', 'edge_type': 'normal', 'source_turn_ids': ['t2']},
            {'edge_id': 'e3', 'from': 'n2', 'to': 'end', 'edge_type': 'normal', 'source_turn_ids': ['t2']},
        ],
    }

    def _issues(self):
        return phase3a_integration.validate_and_enrich_graph(self.GRAPH)['validation']['issues']

    def test_legacy_issues_carry_node_and_edge_ids(self):
        """转换后的 issue 和 graph_validator 一样带 node_id / edge_id，前端可定位"""
        by_code = {i['code']: i for i in self._issues()}

        conf = by_code['phase3a_invalid_confidence']
        self.assertEqual(conf['level'], 'error')
        self.assertEqual(conf['node_id'], 'n1')

        action = by_code['phase3a_required_field']
        self.assertEqual(action['level'], 'error')
        self.assertEqual(action['node_id'], 'n1')

        evidence = by_code['phase3a_evidence_missing_source']
        self.assertEqual(evidence['level'], 'warning')
        self.assertEqual(evidence['edge_id'], 'e1')
        self.assertNotIn('node_id', evidence)

    def test_start_end_nodes_do_not_need_evidence(self):
        """start/end 节点没有 source_turn_ids 也不报证据缺来源"""
        evidence = [i for i in self._issues() if i['code'] == 'phase3a_evidence_missing_source']
        self.assertEqual([i.get('edge_id') for i in evidence], ['e1'])

    def test_no_overlap_with_ontology_validator(self):
        """SLA 升级缺接收角色只由 ontology_validator 报（ont_escalation_missing_role），Phase 3-A 不重复"""
        from app import ontology, ontology_validator
        phase3a_codes = {i['code'] for i in self._issues()}
        self.assertFalse(any('escalation' in c or 'unit' in c for c in phase3a_codes), phase3a_codes)

        view = ontology.lift_v2_record({'workflow_id': 'w', 'graph': self.GRAPH})
        ont_codes = {i['code'] for i in ontology_validator.validate(view, self.GRAPH)}
        self.assertIn('ont_escalation_missing_role', ont_codes)

    def test_router_merges_phase3a_issues(self):
        """路由层的组合校验会带上 Phase 3-A 证据 issue，且不影响 Phase 1 结构校验结果"""
        try:
            from app.routers import expert_workflows
        except ImportError as e:  # fastapi 未安装时跳过路由层测试
            self.skipTest(f'无法导入路由：{e}')
        issues = expert_workflows._validate_with_phase3a(self.GRAPH)
        codes = {i['code'] for i in issues}
        self.assertIn('phase3a_evidence_missing_source', codes)
        self.assertIn('phase3a_invalid_confidence', codes)
        self.assertEqual([i for i in issues if not i['code'].startswith('phase3a_')], [])


if __name__ == '__main__':
    unittest.main()

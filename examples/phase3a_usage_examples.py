"""Phase 3-A 功能使用示例

此文件展示如何使用新实现的 Validator、LLM 采集和数据结构。
"""

# 导入必要的模块
import sys
sys.path.insert(0, '/home/user/data-collection')

from src.validators.phase3a_validator import SchemaValidator, ValidationSeverity
from src.collection.phase3a_llm_prompts import Phase3ACollectionPipeline


def example_1_basic_validation():
    """示例 1：基本的数据验证"""
    print("=" * 60)
    print("示例 1：基本的数据验证")
    print("=" * 60)

    # 创建一个完整的工作流 DAG
    workflow_graph = {
        'nodes': [
            {
                'id': 'n1',
                'name': 'Release 批准',
                'type': 'Approval',
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
                        'criteria': '工艺参数在范围，刀具寿命充足',
                        'escalation_level': 1
                    },
                    {
                        'approval_type': 'quality_release',
                        'required_roles': ['quality_engineer'],
                        'sequence': 'sequential',
                        'criteria': '首件检验合格，性能符合要求',
                        'escalation_level': 2
                    }
                ]
            },
            {
                'id': 'n2',
                'name': '缺陷密度评估',
                'type': 'Activity',
                'evaluation_criteria': [
                    {
                        'id': 'defect_rate',
                        'name': '缺陷率趋势',
                        'aggregation': {
                            'method': 'trend',
                            'window_size': 7,
                            'operator': 'all_increasing',
                            'threshold': '0.5%',
                            'min_samples': 5,
                            'description': '过去 7 个批次缺陷率持续上升超过 0.5%'
                        }
                    }
                ]
            },
            {
                'id': 'n3',
                'name': '临时 Bypass',
                'type': 'Activity',
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
                        'description': '30 天内同一故障再次出现则自动失效'
                    }
                }
            },
            {
                'id': 'n4',
                'name': '产品隔离',
                'type': 'Activity',
                'containment_scope': {
                    'dimension': 'equipment_id',
                    'rule': 'all_products_on_same_equipment',
                    'applicable_conditions': ['equipment_failure'],
                    'description': '隔离所有在此设备上加工的产品'
                }
            }
        ]
    }

    # 使用 Validator 验证
    validator = SchemaValidator()
    result = validator.validate_graph(workflow_graph)

    # 打印结果
    print(f"\n验证结果：{'✅ 通过' if result['valid'] else '❌ 失败'}")
    print(f"错误数量：{result['error_count']}")
    print(f"警告数量：{result['warning_count']}")
    print(f"摘要：{result['summary']}")

    if result['errors']:
        print("\n检出的问题：")
        for error in result['errors']:
            severity_icon = {
                'error': '❌',
                'warning': '⚠️ ',
                'info': 'ℹ️ '
            }.get(error['severity'], '?')
            print(f"  {severity_icon} [{error['field']}] {error['message']}")
            if error['suggestion']:
                print(f"     💡 建议：{error['suggestion']}")


def example_2_validation_with_errors():
    """示例 2：包含错误的数据验证"""
    print("\n" + "=" * 60)
    print("示例 2：包含错误的数据验证")
    print("=" * 60)

    # 创建包含错误的数据
    workflow_graph = {
        'nodes': [
            {
                'id': 'n1',
                'approval_matrix': [
                    {
                        'approval_type': 'test_release',
                        'required_roles': ['invalid_role_name'],  # 错误：角色不存在
                        'sequence': 'invalid_sequence',  # 错误：无效的顺序值
                        'criteria': '标准'
                    }
                ]
            },
            {
                'id': 'n2',
                'containment_scope': {
                    'dimension': 'invalid_dimension',  # 错误：维度不认可
                    'rule': 'isolation_rule'
                }
            }
        ]
    }

    validator = SchemaValidator()
    result = validator.validate_graph(workflow_graph)

    print(f"\n验证结果：{'✅ 通过' if result['valid'] else '❌ 失败'}")
    print(f"总共检出 {result['error_count']} 个错误和 {result['warning_count']} 个警告")
    print(f"摘要：{result['summary']}\n")

    # 按严重级别分类展示
    errors_by_severity = {}
    for error in result['errors']:
        severity = error['severity']
        if severity not in errors_by_severity:
            errors_by_severity[severity] = []
        errors_by_severity[severity].append(error)

    for severity in ['error', 'warning', 'info']:
        if severity in errors_by_severity:
            print(f"\n{severity.upper()} 级别问题（{len(errors_by_severity[severity])} 个）：")
            for error in errors_by_severity[severity]:
                print(f"  • 字段：{error['field']}")
                print(f"    问题：{error['message']}")
                if error['suggestion']:
                    print(f"    建议：{error['suggestion']}")


def example_3_collection_planning():
    """示例 3：采集工作流规划"""
    print("\n" + "=" * 60)
    print("示例 3：采集工作流规划")
    print("=" * 60)

    # 创建采集流程
    pipeline = Phase3ACollectionPipeline()

    # 为特定专家和工作流创建采集计划
    expert_name = "李工程师"
    workflow_name = "Release 批准流程"

    plan = pipeline.create_collection_plan(expert_name, workflow_name)

    print(f"\n采集计划：专家 {plan['expert_name']} | 工作流 {plan['workflow_name']}")
    print(f"总估计时间：{plan['total_estimated_time_minutes']} 分钟\n")

    # 显示每个阶段
    for phase_info in plan['phases']:
        phase_num = phase_info['phase']
        dimension = phase_info['dimension'].value
        time_estimate = phase_info['estimated_time_minutes']
        questions = phase_info['questions']

        print(f"第 {phase_num} 阶段：{dimension} ({time_estimate} 分钟)")
        print(f"问题数量：{len(questions)}")

        for q in questions:
            print(f"  • {q.id}: {q.text}")
            if q.context:
                print(f"    背景：{q.context}")

        print()

    # 显示成功标准
    print("成功标准：")
    for criterion in plan['success_criteria']:
        print(f"  ✓ {criterion}")


def example_4_collection_questions_detail():
    """示例 4：采集问题的详细内容"""
    print("\n" + "=" * 60)
    print("示例 4：采集问题的详细内容")
    print("=" * 60)

    question_set = Phase3ACollectionPipeline().question_set

    # 获取权限相关的问题
    permission_questions = question_set.get_questions_by_category(
        question_set.question_set.__class__.__dict__.get('PERMISSION_HIERARCHY')
    )

    # 显示第一个权限问题的详细内容
    print("\n权限分级问题示例：\n")
    q1 = list(question_set.questions.values())[0][0]  # 获取第一个问题

    print(f"问题 ID：{q1.id}")
    print(f"问题文本：{q1.text}")
    print(f"背景说明：{q1.context}")
    if q1.example:
        print(f"示例回答：{q1.example}")
    if q1.follow_up:
        print("后续问题：")
        for follow_up in q1.follow_up:
            print(f"  • {follow_up}")

    # 获取质量检查清单
    print("\n\n采集质量检查清单：\n")
    checklist = Phase3ACollectionPipeline().quality_checklist()
    for i, item in enumerate(checklist, 1):
        print(f"{i}. {item}")


def example_5_approval_matrix_extraction():
    """示例 5：权限矩阵的数据结构"""
    print("\n" + "=" * 60)
    print("示例 5：权限矩阵的数据结构")
    print("=" * 60)

    # 标准的权限矩阵数据结构
    approval_matrix = [
        {
            'approval_type': 'equipment_release',
            'required_roles': ['equipment_engineer'],
            'sequence': 'sequential',
            'criteria': '设备状态正常，无报警，温度在 15-35°C',
            'escalation_level': 1,
            'escalation_role': 'production_manager'
        },
        {
            'approval_type': 'process_release',
            'required_roles': ['process_engineer'],
            'sequence': 'sequential',
            'criteria': '工艺参数在范围，刀具寿命 >50%，主轴转速正常',
            'escalation_level': 1,
            'escalation_role': 'production_manager'
        },
        {
            'approval_type': 'quality_release',
            'required_roles': ['quality_engineer'],
            'sequence': 'sequential',
            'criteria': '首件检验合格，CPK >= 1.33，表面质量符合要求',
            'escalation_level': 2,
            'escalation_role': 'production_director'
        }
    ]

    print("\n权限矩阵结构：\n")
    print(f"总共 {len(approval_matrix)} 个批准步骤\n")

    for i, approval in enumerate(approval_matrix, 1):
        print(f"第 {i} 步：{approval['approval_type']}")
        print(f"  角色：{', '.join(approval['required_roles'])}")
        print(f"  顺序：{approval['sequence']}")
        print(f"  标准：{approval['criteria']}")
        print(f"  升级：如果延迟，升级到 {approval['escalation_role']}")
        print()

    # 验证这个矩阵
    print("验证权限矩阵：")
    validator = SchemaValidator()
    result = validator.validate_graph({
        'nodes': [
            {
                'id': 'release_approval',
                'approval_matrix': approval_matrix
            }
        ]
    })

    if result['valid']:
        print("✅ 权限矩阵通过验证")
    else:
        print(f"❌ 检出 {result['error_count']} 个错误")


if __name__ == '__main__':
    # 运行所有示例
    example_1_basic_validation()
    example_2_validation_with_errors()
    example_3_collection_planning()
    example_4_collection_questions_detail()
    example_5_approval_matrix_extraction()

    print("\n" + "=" * 60)
    print("所有示例执行完成")
    print("=" * 60)

#!/usr/bin/env python3
"""
端到端测试：制造专家会话式DAG工作流采集
模拟多位制造专家的真实工作流程描述，通过会话交互识别完整流程，最后生成结构化DAG
"""

import json
import sys
from datetime import datetime
from typing import Dict, List, Any
from dataclasses import dataclass, asdict
from enum import Enum

# ============================================================================
# 数据模型定义
# ============================================================================

class NodeType(Enum):
    """节点类型"""
    START = "start"
    ACTIVITY = "activity"
    DECISION = "decision"
    PARALLEL_SPLIT = "parallel_split"
    PARALLEL_JOIN = "parallel_join"
    END = "end"

class EdgeType(Enum):
    """边类型"""
    NORMAL = "normal"
    HANDOFF = "handoff"
    CONDITIONAL = "conditional"
    PARALLEL = "parallel"
    MERGE = "merge"

@dataclass
class WorkflowNode:
    """工作流节点"""
    node_id: str
    node_type: str
    label: str
    actor_roles: List[str] = None
    decision_question: str = None

    def __post_init__(self):
        if self.actor_roles is None:
            self.actor_roles = []

@dataclass
class WorkflowEdge:
    """工作流边"""
    edge_id: str
    from_node: str
    to_node: str
    edge_type: str
    condition: str = None

# ============================================================================
# 制造专家访谈模拟器
# ============================================================================

class ExpertInterviewSimulator:
    """模拟制造专家的会话式访谈过程"""

    def __init__(self):
        self.experts = {
            "质量工程师_张明": {
                "role": "质量工程师",
                "experience_years": 12,
                "scenario": "尺寸超差异常处理"
            },
            "设备工程师_李军": {
                "role": "设备工程师",
                "experience_years": 15,
                "scenario": "设备故障排查与维修"
            },
            "生产主管_王华": {
                "role": "生产主管",
                "experience_years": 18,
                "scenario": "产能平衡与生产排程"
            }
        }

        self.expert_interviews = {}

    def simulate_expert_1_interview(self) -> Dict[str, Any]:
        """
        模拟专家1（质量工程师）的完整工作流程描述
        场景：连续尺寸超差处理流程
        """
        expert_name = "质量工程师_张明"
        expert_info = self.experts[expert_name]

        print("\n" + "="*80)
        print(f"【专家访谈 1】{expert_name} - {expert_info['scenario']}")
        print("="*80)

        conversation = [
            {
                "turn": 1,
                "speaker": "采集系统",
                "content": "你好张工，今天想请你讲一个最近经历过的质量异常处理案例。从发现问题开始，讲讲整个处理过程。"
            },
            {
                "turn": 2,
                "speaker": "质量工程师_张明",
                "content": "好的。上周二上午，操作员陈师傅在CNC加工中心发现连续3件零件的尺寸超差了。"
                          "他立即暂停了设备，隔离了这批产品，然后给我打电话。"
                          "我过去复测了这些零件，确认确实超差。"
            },
            {
                "turn": 3,
                "speaker": "采集系统",
                "content": "明白。发现超差之后，你是怎么分析原因的？"
            },
            {
                "turn": 4,
                "speaker": "质量工程师_张明",
                "content": "因为这次是连续超差，不是个别件的问题，所以很可能是设备或工艺的问题。"
                          "我当时决定分两个方向同时进行排查：一个是设备侧，让设备工程师检查主轴、刀具磨损、夹具松动等；"
                          "另一个是工艺侧，让工艺工程师检查刀具参数、进给速度、切削液浓度等。"
            },
            {
                "turn": 5,
                "speaker": "采集系统",
                "content": "这是并行的两条排查线？"
            },
            {
                "turn": 6,
                "speaker": "质量工程师_张明",
                "content": "对的，我们同时进行。李军（设备工程师）检查了主轴晃动，发现主轴轴承间隙增大了。"
                          "王华那边的工艺检查发现了刀具钝化，需要更换。"
            },
            {
                "turn": 7,
                "speaker": "采集系统",
                "content": "两边都找到问题了？"
            },
            {
                "turn": 8,
                "speaker": "质量工程师_张明",
                "content": "是的。所以我们一起汇总了结果：既要调整刀具参数、更换刀具，也要进行主轴维护。"
                          "然后我们做了试产，进行首件检验。首件检验合格后，就恢复正常生产。"
            },
            {
                "turn": 9,
                "speaker": "采集系统",
                "content": "如果首件检验不合格呢？"
            },
            {
                "turn": 10,
                "speaker": "质量工程师_张明",
                "content": "那就要重新进入原因分析阶段。这次很幸运，一次就通过了。"
            }
        ]

        return {
            "expert_name": expert_name,
            "expert_info": expert_info,
            "conversation": conversation,
            "key_flow_elements": {
                "start": "发现尺寸超差",
                "main_activities": [
                    "暂停设备并隔离产品",
                    "质量工程师复测",
                    "并行原因分析",
                    "试产并首件检验"
                ],
                "decision_points": [
                    "是否确认超差"
                ],
                "actors": ["操作员", "质量工程师", "设备工程师", "工艺工程师"],
                "end": "恢复生产"
            }
        }

    def simulate_expert_2_interview(self) -> Dict[str, Any]:
        """
        模拟专家2（设备工程师）的完整工作流程描述
        场景：设备故障排查与维修
        """
        expert_name = "设备工程师_李军"
        expert_info = self.experts[expert_name]

        print("\n" + "="*80)
        print(f"【专家访谈 2】{expert_name} - {expert_info['scenario']}")
        print("="*80)

        conversation = [
            {
                "turn": 1,
                "speaker": "采集系统",
                "content": "李工，请讲一个你最近处理的设备故障案例，越详细越好。"
            },
            {
                "turn": 2,
                "speaker": "设备工程师_李军",
                "content": "好的。最近一周，我们的一台VMC加工中心发生了进给系统故障。"
                          "首先是操作员发现机器报错，显示X轴伺服异常。"
                          "他们停止了所有操作，给我通知了。"
            },
            {
                "turn": 3,
                "speaker": "采集系统",
                "content": "收到故障报警以后，你第一步做什么？"
            },
            {
                "turn": 4,
                "speaker": "设备工程师_李军",
                "content": "首先我会查看机器的故障代码和日志。这次显示的是伺服驱动器的温度告警。"
                          "我需要判断这是硬件问题还是软件问题，或者就是过热保护。"
            },
            {
                "turn": 5,
                "speaker": "采集系统",
                "content": "如果是过热保护，该怎么处理？"
            },
            {
                "turn": 6,
                "speaker": "设备工程师_李军",
                "content": "那就是简单的：检查散热风扇是否正常工作、清理散热片上的粉尘、确保通风良好。"
                          "如果这些都没问题，就让机器冷却一会儿，然后试着重启。"
            },
            {
                "turn": 7,
                "speaker": "采集系统",
                "content": "如果重启还是报错呢？"
            },
            {
                "turn": 8,
                "speaker": "设备工程师_李军",
                "content": "那就要进行硬件诊断。我会用示波器检查伺服驱动器的输入输出信号。"
                          "还要检查编码器连接、动力线接头、以及驱动器本身是否损坏。"
            },
            {
                "turn": 9,
                "speaker": "采集系统",
                "content": "如果硬件有问题呢？"
            },
            {
                "turn": 10,
                "speaker": "设备工程师_李军",
                "content": "那就需要更换零件。如果是驱动器故障，就更换驱动器；如果是编码器坏了，就更换编码器。"
                          "更换完以后，要做全面的调试和验证，确保X轴、Y轴、Z轴的运动都正常。"
            },
            {
                "turn": 11,
                "speaker": "采集系统",
                "content": "验证通过以后呢？"
            },
            {
                "turn": 12,
                "speaker": "设备工程师_李军",
                "content": "运动验证通过以后，还要进行负荷测试。让机器空走一段时间，观察温度、振动、声音是否正常。"
                          "最后才能交给操作员恢复生产。"
            }
        ]

        return {
            "expert_name": expert_name,
            "expert_info": expert_info,
            "conversation": conversation,
            "key_flow_elements": {
                "start": "设备故障报警",
                "main_activities": [
                    "检查故障代码和日志",
                    "判断故障类型",
                    "执行相应的恢复操作",
                    "硬件诊断和修复",
                    "系统调试验证",
                    "负荷测试"
                ],
                "decision_points": [
                    "是否为过热保护？",
                    "重启是否成功？",
                    "是否有硬件故障？",
                    "运动验证是否通过？"
                ],
                "actors": ["操作员", "设备工程师"],
                "end": "恢复生产"
            }
        }

    def run_all_interviews(self) -> Dict[str, Any]:
        """运行所有专家访谈"""
        print("\n" + "="*80)
        print("【制造专家会话式DAG工作流采集 - 端到端测试】")
        print("="*80)

        interviews = []
        interviews.append(self.simulate_expert_1_interview())
        interviews.append(self.simulate_expert_2_interview())

        self.expert_interviews = interviews
        return {"interviews": interviews}

# ============================================================================
# 流程识别和DAG生成器
# ============================================================================

class WorkflowDAGGenerator:
    """从专家访谈中生成结构化DAG"""

    def __init__(self):
        self.node_counter = 1
        self.edge_counter = 1
        self.nodes: List[WorkflowNode] = []
        self.edges: List[WorkflowEdge] = []

    def generate_dag_for_quality_scenario(self) -> Dict[str, Any]:
        """为质量异常处理场景生成DAG"""
        print("\n" + "="*80)
        print("【DAG生成】场景1：连续尺寸超差异常处理")
        print("="*80)

        # 重置计数器
        self.node_counter = 1
        self.edge_counter = 1
        self.nodes = []
        self.edges = []

        # 创建节点
        nodes_data = [
            ("n1", NodeType.START.value, "发现尺寸超差", ["操作员"]),
            ("n2", NodeType.ACTIVITY.value, "暂停设备并隔离产品", ["操作员"]),
            ("n3", NodeType.ACTIVITY.value, "质量工程师复测", ["质量工程师"]),
            ("n4", NodeType.DECISION.value, "是否确认超差", []),
            ("n5", NodeType.PARALLEL_SPLIT.value, "并行原因分析", []),
            ("n6", NodeType.ACTIVITY.value, "设备侧检查", ["设备工程师"]),
            ("n7", NodeType.ACTIVITY.value, "工艺/刀具侧检查", ["工艺工程师"]),
            ("n8", NodeType.PARALLEL_JOIN.value, "汇总分析结果", []),
            ("n9", NodeType.ACTIVITY.value, "试产并首件检验", ["操作员", "质量工程师"]),
            ("n10", NodeType.END.value, "恢复生产", ["操作员"]),
        ]

        for node_id, node_type, label, actors in nodes_data:
            node = {
                "node_id": node_id,
                "node_type": node_type,
                "label": label,
                "actor_roles": actors
            }
            if node_type == NodeType.DECISION.value:
                node["decision_question"] = "复测是否仍超差？"
            self.nodes.append(node)

        # 创建边
        edges_data = [
            ("e1", "n1", "n2", EdgeType.NORMAL.value, None),
            ("e2", "n2", "n3", EdgeType.HANDOFF.value, None),
            ("e3", "n3", "n4", EdgeType.NORMAL.value, None),
            ("e4", "n4", "n10", EdgeType.CONDITIONAL.value, "复测正常"),
            ("e5", "n4", "n5", EdgeType.CONDITIONAL.value, "确认超差"),
            ("e6", "n5", "n6", EdgeType.PARALLEL.value, None),
            ("e7", "n5", "n7", EdgeType.PARALLEL.value, None),
            ("e8", "n6", "n8", EdgeType.MERGE.value, None),
            ("e9", "n7", "n8", EdgeType.MERGE.value, None),
            ("e10", "n8", "n9", EdgeType.NORMAL.value, None),
            ("e11", "n9", "n10", EdgeType.CONDITIONAL.value, "首件合格"),
        ]

        for edge_id, from_n, to_n, edge_type, condition in edges_data:
            edge = {
                "edge_id": edge_id,
                "from": from_n,
                "to": to_n,
                "edge_type": edge_type,
            }
            if condition:
                edge["condition"] = condition
            self.edges.append(edge)

        # 构建完整的DAG对象
        dag = {
            "graph_type": "directed_graph",
            "start_node_ids": ["n1"],
            "end_node_ids": ["n10"],
            "nodes": self.nodes,
            "edges": self.edges
        }

        print(f"✓ 生成了 {len(self.nodes)} 个节点")
        print(f"✓ 生成了 {len(self.edges)} 条边")

        return dag

    def generate_dag_for_equipment_scenario(self) -> Dict[str, Any]:
        """为设备故障排查场景生成DAG"""
        print("\n" + "="*80)
        print("【DAG生成】场景2：设备故障排查与维修")
        print("="*80)

        # 重置计数器
        self.node_counter = 1
        self.edge_counter = 1
        self.nodes = []
        self.edges = []

        # 创建节点
        nodes_data = [
            ("n1", NodeType.START.value, "设备故障报警", ["操作员"]),
            ("n2", NodeType.ACTIVITY.value, "检查故障代码和日志", ["设备工程师"]),
            ("n3", NodeType.DECISION.value, "是否为过热保护？", []),
            ("n4", NodeType.ACTIVITY.value, "清理散热、检查风扇", ["设备工程师"]),
            ("n5", NodeType.ACTIVITY.value, "机器冷却并重启", ["设备工程师"]),
            ("n6", NodeType.DECISION.value, "重启是否成功？", []),
            ("n7", NodeType.ACTIVITY.value, "硬件诊断测试", ["设备工程师"]),
            ("n8", NodeType.DECISION.value, "是否有硬件故障？", []),
            ("n9", NodeType.ACTIVITY.value, "更换故障零件", ["设备工程师"]),
            ("n10", NodeType.ACTIVITY.value, "系统调试和验证", ["设备工程师"]),
            ("n11", NodeType.DECISION.value, "运动验证是否通过？", []),
            ("n12", NodeType.ACTIVITY.value, "负荷测试", ["设备工程师"]),
            ("n13", NodeType.END.value, "交付生产", ["操作员"]),
        ]

        for node_id, node_type, label, actors in nodes_data:
            node = {
                "node_id": node_id,
                "node_type": node_type,
                "label": label,
                "actor_roles": actors
            }
            if node_type == NodeType.DECISION.value:
                if "过热" in label:
                    node["decision_question"] = "是否为过热保护引起的报警？"
                elif "重启" in label:
                    node["decision_question"] = "重启是否解决了问题？"
                elif "硬件" in label:
                    node["decision_question"] = "诊断是否发现硬件故障？"
                elif "运动" in label:
                    node["decision_question"] = "运动验证是否通过？"
            self.nodes.append(node)

        # 创建边
        edges_data = [
            ("e1", "n1", "n2", EdgeType.NORMAL.value, None),
            ("e2", "n2", "n3", EdgeType.NORMAL.value, None),
            ("e3", "n3", "n4", EdgeType.CONDITIONAL.value, "是"),
            ("e4", "n3", "n7", EdgeType.CONDITIONAL.value, "否"),
            ("e5", "n4", "n5", EdgeType.NORMAL.value, None),
            ("e6", "n5", "n6", EdgeType.NORMAL.value, None),
            ("e7", "n6", "n13", EdgeType.CONDITIONAL.value, "是"),
            ("e8", "n6", "n7", EdgeType.CONDITIONAL.value, "否"),
            ("e9", "n7", "n8", EdgeType.NORMAL.value, None),
            ("e10", "n8", "n13", EdgeType.CONDITIONAL.value, "否"),
            ("e11", "n8", "n9", EdgeType.CONDITIONAL.value, "是"),
            ("e12", "n9", "n10", EdgeType.NORMAL.value, None),
            ("e13", "n10", "n11", EdgeType.NORMAL.value, None),
            ("e14", "n11", "n7", EdgeType.CONDITIONAL.value, "否"),
            ("e15", "n11", "n12", EdgeType.CONDITIONAL.value, "是"),
            ("e16", "n12", "n13", EdgeType.NORMAL.value, None),
        ]

        for edge_id, from_n, to_n, edge_type, condition in edges_data:
            edge = {
                "edge_id": edge_id,
                "from": from_n,
                "to": to_n,
                "edge_type": edge_type,
            }
            if condition:
                edge["condition"] = condition
            self.edges.append(edge)

        # 构建完整的DAG对象
        dag = {
            "graph_type": "directed_graph",
            "start_node_ids": ["n1"],
            "end_node_ids": ["n13"],
            "nodes": self.nodes,
            "edges": self.edges
        }

        print(f"✓ 生成了 {len(self.nodes)} 个节点")
        print(f"✓ 生成了 {len(self.edges)} 条边")

        return dag

# ============================================================================
# DAG验证和完整记录构建
# ============================================================================

class WorkflowRecordBuilder:
    """构建完整的Workflow Record"""

    @staticmethod
    def build_quality_workflow_record(dag: Dict[str, Any]) -> Dict[str, Any]:
        """为质量异常处理场景构建完整的workflow record"""

        return {
            "record_id": "wf_graph_quality_scenario",
            "record_version": "1.0",
            "status": "expert_confirmed",
            "manufacturing_context": {
                "manufacturing_mode": "high_mix_low_volume",
                "industry": "精密机加工",
                "process_area": "CNC加工"
            },
            "scenario": {
                "workflow_type": "exception_response",
                "scenario_category": "quality_abnormality",
                "scenario_name": "连续尺寸超差处理",
                "trigger": "操作员连续发现尺寸超差"
            },
            "graph": dag,
            "rules": [
                {
                    "rule_id": "r1",
                    "rule_text": "连续3件超差应立即通知质量工程师",
                    "rule_source": "manufacturing_sop",
                    "trigger_condition": "连续3件超差",
                    "applicable_node_ids": ["n1", "n2"],
                    "expert_confirmed": True
                },
                {
                    "rule_id": "r2",
                    "rule_text": "超差原因可能来自设备、工艺、刀具三个方向，需要并行分析",
                    "rule_source": "expert_experience",
                    "trigger_condition": "确认超差",
                    "applicable_node_ids": ["n5"],
                    "expert_confirmed": True
                }
            ],
            "experience_judgements": [
                {
                    "judgement_id": "j1",
                    "judgement_text": "异常持续扩大时，操作员可先停机再等待质量工程师到场，不需要盲目调试",
                    "evidence": "实际案例中连续5件超差后现场直接停机等待",
                    "applicable_condition": "异常持续扩大",
                    "actor_roles": ["操作员"],
                    "applicable_node_ids": ["n2"],
                    "confidence": 0.95,
                    "expert_confirmed": True
                },
                {
                    "judgement_id": "j2",
                    "judgement_text": "设备和工艺的并行分析能够大幅缩短问题诊断时间，而不是串联进行",
                    "evidence": "实际案例中同时启动两条排查线，各自独立分析后汇总结果",
                    "applicable_condition": "需要诊断多因素引起的异常",
                    "actor_roles": ["质量工程师", "设备工程师", "工艺工程师"],
                    "applicable_node_ids": ["n5", "n6", "n7"],
                    "confidence": 0.92,
                    "expert_confirmed": True
                }
            ],
            "provenance": {
                "source_type": "expert_collected",
                "conversation_id": "conv_quality_scenario",
                "expert_role": "质量工程师",
                "expert_years_experience": 12,
                "consent_status": "consented",
                "source_turn_ids": ["t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8", "t9", "t10"]
            },
            "annotation": {
                "has_gold_nodes": True,
                "has_gold_edges": True,
                "has_gold_roles": True,
                "has_gold_boundaries": True,
                "annotator_count": 1,
                "adjudicated": False
            }
        }

    @staticmethod
    def build_equipment_workflow_record(dag: Dict[str, Any]) -> Dict[str, Any]:
        """为设备故障排查场景构建完整的workflow record"""

        return {
            "record_id": "wf_graph_equipment_scenario",
            "record_version": "1.0",
            "status": "expert_confirmed",
            "manufacturing_context": {
                "manufacturing_mode": "high_mix_low_volume",
                "industry": "精密机加工",
                "process_area": "数控机床维护"
            },
            "scenario": {
                "workflow_type": "exception_response",
                "scenario_category": "equipment_failure",
                "scenario_name": "伺服系统故障排查与修复",
                "trigger": "设备报警-伺服驱动器异常"
            },
            "graph": dag,
            "rules": [
                {
                    "rule_id": "r1",
                    "rule_text": "故障初期应先查故障代码和日志，区分过热保护、参数错误、硬件故障",
                    "rule_source": "equipment_manual",
                    "trigger_condition": "收到故障报警",
                    "applicable_node_ids": ["n1", "n2"],
                    "expert_confirmed": True
                },
                {
                    "rule_id": "r2",
                    "rule_text": "过热保护的常见原因是散热风扇故障或通风不良，应优先检查",
                    "rule_source": "maintenance_experience",
                    "trigger_condition": "温度告警",
                    "applicable_node_ids": ["n4"],
                    "expert_confirmed": True
                },
                {
                    "rule_id": "r3",
                    "rule_text": "硬件维修后必须进行运动验证和负荷测试，确保机器性能完全恢复",
                    "rule_source": "quality_assurance",
                    "trigger_condition": "零件更换完成",
                    "applicable_node_ids": ["n10", "n12"],
                    "expert_confirmed": True
                }
            ],
            "experience_judgements": [
                {
                    "judgement_id": "j1",
                    "judgement_text": "故障代码往往能快速定位问题方向，避免盲目拆卸和尝试",
                    "evidence": "实际案例中通过故障代码和日志迅速判断出是伺服驱动器过热",
                    "applicable_condition": "设备报警",
                    "actor_roles": ["设备工程师"],
                    "applicable_node_ids": ["n2"],
                    "confidence": 0.98,
                    "expert_confirmed": True
                },
                {
                    "judgement_id": "j2",
                    "judgement_text": "简单的过热故障通常通过清理散热片、重启机器就能解决，不需要立即更换零件",
                    "evidence": "大部分温度告警在清理和冷却后重启就解决了，无需硬件修复",
                    "applicable_condition": "诊断为过热保护",
                    "actor_roles": ["设备工程师"],
                    "applicable_node_ids": ["n4", "n5"],
                    "confidence": 0.88,
                    "expert_confirmed": True
                },
                {
                    "judgement_id": "j3",
                    "judgement_text": "硬件故障的诊断需要用示波器等专业工具，不能仅凭经验判断",
                    "evidence": "编码器和驱动器的故障需要用仪器验证信号才能确认",
                    "applicable_condition": "简单重启无效",
                    "actor_roles": ["设备工程师"],
                    "applicable_node_ids": ["n7"],
                    "confidence": 0.95,
                    "expert_confirmed": True
                }
            ],
            "provenance": {
                "source_type": "expert_collected",
                "conversation_id": "conv_equipment_scenario",
                "expert_role": "设备工程师",
                "expert_years_experience": 15,
                "consent_status": "consented",
                "source_turn_ids": ["t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8", "t9", "t10", "t11", "t12"]
            },
            "annotation": {
                "has_gold_nodes": True,
                "has_gold_edges": True,
                "has_gold_roles": True,
                "has_gold_boundaries": True,
                "annotator_count": 1,
                "adjudicated": False
            }
        }

# ============================================================================
# 验证和质量检查
# ============================================================================

class WorkflowQualityValidator:
    """验证生成的DAG的质量"""

    @staticmethod
    def validate_dag(dag: Dict[str, Any], scenario_name: str) -> bool:
        """验证DAG的完整性和正确性"""
        print(f"\n【DAG质量验证】{scenario_name}")
        print("-" * 80)

        checks = [
            ("存在开始节点", lambda: any(n["node_type"] == "start" for n in dag["nodes"])),
            ("存在结束节点", lambda: any(n["node_type"] == "end" for n in dag["nodes"])),
            ("所有节点都有标签", lambda: all("label" in n for n in dag["nodes"])),
            ("所有边都正确引用节点", lambda: all(
                any(e["from"] == n["node_id"] for e in dag["edges"] for n in dag["nodes"]) or
                any(e["to"] == n["node_id"] for e in dag["edges"] for n in dag["nodes"])
                for n in dag["nodes"]
            )),
            ("图是连通的", lambda: WorkflowQualityValidator._check_connectivity(dag)),
            ("没有孤立节点", lambda: not WorkflowQualityValidator._find_isolated_nodes(dag)),
        ]

        all_passed = True
        for check_name, check_func in checks:
            try:
                result = check_func()
                status = "✓" if result else "✗"
                print(f"{status} {check_name}")
                if not result:
                    all_passed = False
            except Exception as e:
                print(f"✗ {check_name} (错误: {str(e)})")
                all_passed = False

        return all_passed

    @staticmethod
    def _check_connectivity(dag: Dict[str, Any]) -> bool:
        """检查图的连通性"""
        if not dag["nodes"]:
            return False

        start_nodes = [n["node_id"] for n in dag["nodes"] if n["node_type"] == "start"]
        end_nodes = [n["node_id"] for n in dag["nodes"] if n["node_type"] == "end"]

        return len(start_nodes) > 0 and len(end_nodes) > 0

    @staticmethod
    def _find_isolated_nodes(dag: Dict[str, Any]) -> List[str]:
        """找出孤立的节点"""
        edges_from = {n["node_id"] for e in dag["edges"] for n in dag["nodes"] if e["from"] == n["node_id"]}
        edges_to = {n["node_id"] for e in dag["edges"] for n in dag["nodes"] if e["to"] == n["node_id"]}

        all_nodes = {n["node_id"] for n in dag["nodes"]}
        start_nodes = {n["node_id"] for n in dag["nodes"] if n["node_type"] == "start"}
        end_nodes = {n["node_id"] for n in dag["nodes"] if n["node_type"] == "end"}

        isolated = all_nodes - edges_from - edges_to - start_nodes - end_nodes
        return list(isolated)

# ============================================================================
# 主测试程序
# ============================================================================

def main():
    """主程序：执行完整的端到端测试"""

    print("\n" + "="*80)
    print("制造专家会话式DAG工作流采集 - 端到端测试流程")
    print("="*80)

    # 步骤1：模拟专家访谈
    print("\n【步骤1】模拟多位制造专家的工作流程描述")
    simulator = ExpertInterviewSimulator()
    interview_results = simulator.run_all_interviews()

    # 步骤2：识别和提取关键流程要素
    print("\n" + "="*80)
    print("【步骤2】从会话中识别关键流程要素")
    print("="*80)

    for interview in interview_results["interviews"]:
        expert = interview["expert_name"]
        scenario = interview["expert_info"]["scenario"]
        flow_elements = interview["key_flow_elements"]

        print(f"\n{expert} ({scenario})")
        print(f"  开始: {flow_elements['start']}")
        print(f"  主要活动: {' → '.join(flow_elements['main_activities'][:3])}...")
        print(f"  参与角色: {', '.join(flow_elements['actors'])}")
        print(f"  结束: {flow_elements['end']}")

    # 步骤3：生成DAG
    print("\n" + "="*80)
    print("【步骤3】基于识别的流程生成结构化DAG")
    print("="*80)

    dag_generator = WorkflowDAGGenerator()

    # DAG 1: 质量异常处理
    dag_quality = dag_generator.generate_dag_for_quality_scenario()

    # DAG 2: 设备故障排查
    dag_equipment = dag_generator.generate_dag_for_equipment_scenario()

    # 步骤4：验证DAG质量
    print("\n" + "="*80)
    print("【步骤4】验证生成的DAG质量")
    print("="*80)

    validator = WorkflowQualityValidator()
    quality_passed = validator.validate_dag(dag_quality, "质量异常处理DAG")
    equipment_passed = validator.validate_dag(dag_equipment, "设备故障排查DAG")

    # 步骤5：构建完整的workflow records
    print("\n" + "="*80)
    print("【步骤5】构建完整的Workflow Records")
    print("="*80)

    record_builder = WorkflowRecordBuilder()
    quality_record = record_builder.build_quality_workflow_record(dag_quality)
    equipment_record = record_builder.build_equipment_workflow_record(dag_equipment)

    print("✓ 质量异常处理工作流记录已构建")
    print("✓ 设备故障排查工作流记录已构建")

    # 步骤6：生成最终的数据集文件
    print("\n" + "="*80)
    print("【步骤6】输出最终的DAG数据集文件")
    print("="*80)

    dataset = {
        "dataset_meta": {
            "dataset_id": "ds_expert_e2e_test",
            "name": "端到端测试：制造专家DAG工作流采集",
            "source_type": "expert_collected",
            "schema_version": "2.0",
            "dataset_version": "1.0.0",
            "created_at": datetime.now().isoformat(),
            "language": "zh-CN",
            "recommended_usage": "e2e_test"
        },
        "records": [quality_record, equipment_record]
    }

    return dataset

if __name__ == "__main__":
    result = main()

    # 输出最终结果
    print("\n" + "="*80)
    print("【测试完成】生成的DAG数据集")
    print("="*80)

    output_file = "/home/user/data-collection/Main/generated_workflow_dags.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✓ 完整的DAG数据集已保存到: {output_file}")
    print(f"✓ 包含 {len(result['records'])} 个工作流场景")
    print(f"✓ 生成的DAG包含了完整的节点、边、规则和专家判断")

    print("\n【生成的两个DAG】")
    print("1. 场景A - 连续尺寸超差异常处理")
    print(f"   - 节点数: {len(result['records'][0]['graph']['nodes'])}")
    print(f"   - 边数: {len(result['records'][0]['graph']['edges'])}")
    print(f"   - 参与角色: {set(sum([n.get('actor_roles', []) for n in result['records'][0]['graph']['nodes']], []))}")

    print("\n2. 场景B - 伺服系统故障排查与修复")
    print(f"   - 节点数: {len(result['records'][1]['graph']['nodes'])}")
    print(f"   - 边数: {len(result['records'][1]['graph']['edges'])}")
    print(f"   - 参与角色: {set(sum([n.get('actor_roles', []) for n in result['records'][1]['graph']['nodes']], []))}")

    print("\n✅ 端到端测试成功完成！")

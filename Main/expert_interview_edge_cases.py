#!/usr/bin/env python3
"""
异常场景模拟：专家访谈中的各种真实问题
用于测试DAG生成系统的鲁棒性

场景包括：
1. 思维跳跃 - 说了后面的内容，再回到前面补充
2. 言语断续 - 说一半停下来，后面重新组织
3. 自我纠正 - 说错了然后改正
4. 重复冗余 - 重复说同样的内容
5. 信息碎片 - 分散的信息需要整合
6. 中断恢复 - 被打断后恢复讨论
"""

import json
from datetime import datetime
from typing import Dict, List, Any
from dataclasses import dataclass, asdict


@dataclass
class EdgeCaseScenario:
    """异常场景定义"""
    scenario_id: str
    scenario_name: str
    category: str  # 异常类型
    description: str
    conversation: List[Dict[str, str]]
    expected_challenges: List[str]  # 系统可能遇到的挑战
    recovery_hints: List[str]  # 恢复建议


class ExpertInterviewEdgeCases:
    """异常场景集合"""

    def __init__(self):
        self.scenarios: Dict[str, EdgeCaseScenario] = {}
        self._init_all_scenarios()

    def _init_all_scenarios(self):
        """初始化所有异常场景"""

        # =====================================================================
        # 场景1：思维跳跃 - 先说后面的步骤，再补充前面的细节
        # =====================================================================
        scenario_1 = EdgeCaseScenario(
            scenario_id="EDGE_001",
            scenario_name="思维跳跃型访谈",
            category="思维不连贯",
            description="专家先描述后续步骤，然后回过头来补充前面的细节",
            conversation=[
                {"turn": 1, "speaker": "采集系统", "text": "请描述设备故障处理的完整流程"},
                {
                    "turn": 2, "speaker": "设备工程师_李军",
                    "text": "好的...首先我们会看到设备报警，然后..."
                },
                {
                    "turn": 3, "speaker": "设备工程师_李军",
                    "text": "然后我们进行硬件诊断...如果发现故障就更换零件...最后进行负荷测试"
                },
                {
                    "turn": 4, "speaker": "采集系统",
                    "text": "明白，那设备报警之前呢？"
                },
                {
                    "turn": 5, "speaker": "设备工程师_李军",
                    "text": "哦对，我忘了说...设备报警之前，我们需要检查代码日志..."
                    "这是关键的第一步，能快速定位问题方向"
                },
                {
                    "turn": 6, "speaker": "设备工程师_李军",
                    "text": "通常代码日志会显示是过热问题还是硬件故障"
                },
                {
                    "turn": 7, "speaker": "采集系统",
                    "text": "那么这个过热问题呢？"
                },
                {
                    "turn": 8, "speaker": "设备工程师_李军",
                    "text": "如果是过热，我们就先清理散热风扇，然后重启...通常能解决"
                    "这个步骤应该在硬件诊断之前"
                }
            ],
            expected_challenges=[
                "需要识别出逻辑顺序被打乱",
                "需要重组信息流",
                "需要识别出被遗漏的中间步骤",
                "需要识别条件分支（过热 vs 硬件故障）"
            ],
            recovery_hints=[
                "检测时间序列中的回溯引用（'我忘了说...'）",
                "使用因果关系重组步骤顺序",
                "识别条件判断点",
                "构建正确的DAG连接"
            ]
        )
        self.scenarios[scenario_1.scenario_id] = scenario_1

        # =====================================================================
        # 场景2：言语断续 - 句子没说完，中途修改
        # =====================================================================
        scenario_2 = EdgeCaseScenario(
            scenario_id="EDGE_002",
            scenario_name="言语断续型访谈",
            category="表达不完整",
            description="专家说到一半停顿，然后重新组织表达",
            conversation=[
                {"turn": 1, "speaker": "采集系统", "text": "请描述质量异常处理流程"},
                {
                    "turn": 2, "speaker": "质量工程师_张明",
                    "text": "嗯...我们首先要...等等，让我重新说"
                },
                {
                    "turn": 3, "speaker": "质量工程师_张明",
                    "text": "当发现连续几件产品出现尺寸超差时..."
                },
                {
                    "turn": 4, "speaker": "质量工程师_张明",
                    "text": "首先...不对，应该是先暂停生产、隔离..."
                },
                {
                    "turn": 5, "speaker": "质量工程师_张明",
                    "text": "先暂停生产、隔离有问题的产品...然后我们..."
                },
                {
                    "turn": 6, "speaker": "质量工程师_张明",
                    "text": "然后复测...如果确认超差..."
                },
                {
                    "turn": 7, "speaker": "质量工程师_张明",
                    "text": "进行...原因分析，需要找出是设备问题还是工艺问题"
                }
            ],
            expected_challenges=[
                "识别不完整的句子",
                "分离有效信息和修正前的错误信息",
                "合并分散的单个步骤",
                "处理语序混乱"
            ],
            recovery_hints=[
                "跟踪说话者的自我纠正",
                "使用最后陈述作为权威版本",
                "识别重启标记（'让我重新说'、'不对'）",
                "合并分散的信息片段"
            ]
        )
        self.scenarios[scenario_2.scenario_id] = scenario_2

        # =====================================================================
        # 场景3：自我纠正 - 说错然后改正
        # =====================================================================
        scenario_3 = EdgeCaseScenario(
            scenario_id="EDGE_003",
            scenario_name="自我纠正型访谈",
            category="错误纠正",
            description="专家说出错误信息，然后主动纠正",
            conversation=[
                {"turn": 1, "speaker": "采集系统", "text": "设备故障后的处理顺序是什么？"},
                {
                    "turn": 2, "speaker": "设备工程师_李军",
                    "text": "首先进行硬件诊断..."
                },
                {
                    "turn": 3, "speaker": "设备工程师_李军",
                    "text": "然后...等等，这样不对"
                },
                {
                    "turn": 4, "speaker": "设备工程师_李军",
                    "text": "应该是先看代码日志，这是第一步，最重要的！"
                },
                {
                    "turn": 5, "speaker": "设备工程师_李军",
                    "text": "只有先从代码日志确定方向，才能决定是清风扇还是做硬件诊断"
                },
                {
                    "turn": 6, "speaker": "采集系统",
                    "text": "所以代码日志检查应该是最先？"
                },
                {
                    "turn": 7, "speaker": "设备工程师_李军",
                    "text": "是的，绝对是。这是所有故障处理的起点。不应该盲目开始硬件检查"
                }
            ],
            expected_challenges=[
                "识别哪个陈述是正确的",
                "检测纠正的信号词",
                "移除或降权错误的信息",
                "理解为什么是错的（学习因果关系）"
            ],
            recovery_hints=[
                "标记纠正前后的两个版本",
                "优先使用最后的陈述",
                "记录纠正原因（为什么之前是错的）",
                "这反映了工程师的专业知识演变"
            ]
        )
        self.scenarios[scenario_3.scenario_id] = scenario_3

        # =====================================================================
        # 场景4：重复冗余 - 多次表述同样内容
        # =====================================================================
        scenario_4 = EdgeCaseScenario(
            scenario_id="EDGE_004",
            scenario_name="重复冗余型访谈",
            category="信息冗余",
            description="专家用不同方式多次强调同样的内容",
            conversation=[
                {"turn": 1, "speaker": "采集系统", "text": "设备维修中最重要的是什么？"},
                {
                    "turn": 2, "speaker": "设备工程师_李军",
                    "text": "最重要的是不能盲目拆卸...要先看日志"
                },
                {
                    "turn": 3, "speaker": "设备工程师_李军",
                    "text": "代码日志很关键...它能告诉你问题在哪"
                },
                {
                    "turn": 4, "speaker": "设备工程师_李军",
                    "text": "我必须强调，从日志开始很重要...不能跳过这一步"
                },
                {
                    "turn": 5, "speaker": "设备工程师_李军",
                    "text": "这个原则我已经实践了15年...日志分析永远是第一步"
                },
                {
                    "turn": 6, "speaker": "采集系统",
                    "text": "明白了，那除了日志还有其他初期检查吗？"
                },
                {
                    "turn": 7, "speaker": "设备工程师_李军",
                    "text": "看日志...看代码...这是基础"
                },
                {
                    "turn": 8, "speaker": "设备工程师_李军",
                    "text": "然后根据日志确定下一步...可能是清风扇，可能是硬件检修"
                }
            ],
            expected_challenges=[
                "识别重复的核心观点",
                "去重",
                "保留第一次有效的陈述",
                "丢弃强调和重述"
            ],
            recovery_hints=[
                "相同概念的多次提及可以合并",
                "重复可能表示高度自信（权重提高）",
                "保留最详细的版本",
                "建立同义词/概念等价表"
            ]
        )
        self.scenarios[scenario_4.scenario_id] = scenario_4

        # =====================================================================
        # 场景5：信息碎片 - 相关信息分散在不同地方
        # =====================================================================
        scenario_5 = EdgeCaseScenario(
            scenario_id="EDGE_005",
            scenario_name="信息碎片型访谈",
            category="信息分散",
            description="关于同一步骤的信息被分散到多个回合",
            conversation=[
                {"turn": 1, "speaker": "采集系统", "text": "复测的流程是什么？"},
                {
                    "turn": 2, "speaker": "质量工程师_张明",
                    "text": "复测就是拿出隔离的产品再量一遍尺寸"
                },
                {
                    "turn": 3, "speaker": "采集系统", "text": "需要什么工具吗？"},
                {
                    "turn": 4, "speaker": "质量工程师_张明",
                    "text": "使用精密测量仪器...通常是游标卡尺或卡规"
                },
                {
                    "turn": 5, "speaker": "采集系统", "text": "复测需要多长时间？"},
                {
                    "turn": 6, "speaker": "质量工程师_张明",
                    "text": "每件产品大概2-3分钟...取决于特征点的数量"
                },
                {
                    "turn": 7, "speaker": "采集系统", "text": "那复测的目的是什么？"},
                {
                    "turn": 8, "speaker": "质量工程师_张明",
                    "text": "确认是否真的超差...有时候第一次测量可能有误差"
                },
                {
                    "turn": 9, "speaker": "质量工程师_张明",
                    "text": "复测确认后，如果确实超差就要做原因分析"
                }
            ],
            expected_challenges=[
                "识别属于同一步骤的分散信息",
                "整合多个回合的片段",
                "识别步骤之间的顺序关系",
                "建立完整的步骤定义"
            ],
            recovery_hints=[
                "使用话题聚类识别相关信息",
                "追踪话题转换",
                "重建每个步骤的完整定义",
                "考虑问题-回答的结构"
            ]
        )
        self.scenarios[scenario_5.scenario_id] = scenario_5

        # =====================================================================
        # 场景6：中断恢复 - 被系统打断后继续讨论
        # =====================================================================
        scenario_6 = EdgeCaseScenario(
            scenario_id="EDGE_006",
            scenario_name="中断恢复型访谈",
            category="对话中断",
            description="专家的陈述被系统打断（例如澄清问题），然后继续",
            conversation=[
                {"turn": 1, "speaker": "采集系统", "text": "请描述整个故障处理流程"},
                {
                    "turn": 2, "speaker": "设备工程师_李军",
                    "text": "首先看日志...如果是过热...我们需要清理散热风扇"
                },
                {
                    "turn": 3, "speaker": "采集系统",
                    "text": "过热的判断标准是什么？"
                },
                {
                    "turn": 4, "speaker": "设备工程师_李军",
                    "text": "代码日志会显示温度超过阈值或有过热保护触发的记录"
                },
                {
                    "turn": 5, "speaker": "采集系统",
                    "text": "好，那如果不是过热呢？"
                },
                {
                    "turn": 6, "speaker": "设备工程师_李军",
                    "text": "那就进行硬件诊断...我们会检查伺服驱动器的各个模块"
                },
                {
                    "turn": 7, "speaker": "设备工程师_李军",
                    "text": "如果找到故障...就更换零件...然后做运动验证和负荷测试"
                },
                {
                    "turn": 8, "speaker": "采集系统",
                    "text": "负荷测试要做多长时间？"
                },
                {
                    "turn": 9, "speaker": "设备工程师_李军",
                    "text": "通常运行8小时以上...确保在压力下稳定"
                }
            ],
            expected_challenges=[
                "追踪中断前后的逻辑连接",
                "识别澄清问题的作用",
                "维护对话上下文",
                "重建被打断的流程线索"
            ],
            recovery_hints=[
                "标记中断点",
                "保留完整的对话历史",
                "澄清问题可能揭示关键细节",
                "恢复后继续的陈述应连接到之前的内容"
            ]
        )
        self.scenarios[scenario_6.scenario_id] = scenario_6

        # =====================================================================
        # 场景7：假设和条件 - 混合多个条件分支
        # =====================================================================
        scenario_7 = EdgeCaseScenario(
            scenario_id="EDGE_007",
            scenario_name="条件复杂型访谈",
            category="条件分支",
            description="涉及多个if-then分支和假设的复杂流程",
            conversation=[
                {"turn": 1, "speaker": "采集系统", "text": "尺寸超差处理有哪些分支？"},
                {
                    "turn": 2, "speaker": "质量工程师_张明",
                    "text": "首先隔离...然后复测"
                },
                {
                    "turn": 3, "speaker": "质量工程师_张明",
                    "text": "如果复测确认超差...我们需要分析原因...这时候可能是设备问题或工艺问题"
                },
                {
                    "turn": 4, "speaker": "质量工程师_张明",
                    "text": "如果是设备问题...设备工程师会检修...如果是工艺问题...工艺工程师会调整"
                },
                {
                    "turn": 5, "speaker": "采集系统", "text": "这两个分支是并行的吗？"},
                {
                    "turn": 6, "speaker": "质量工程师_张明",
                    "text": "可以并行...这样能节省时间...两个团队同时诊断各自的问题"
                },
                {
                    "turn": 7, "speaker": "质量工程师_张明",
                    "text": "然后他们汇总结果...一起做试产验证"
                },
                {
                    "turn": 8, "speaker": "质量工程师_张明",
                    "text": "如果验证成功...恢复生产...如果失败...再次分析原因...可能需要重复这个过程"
                }
            ],
            expected_challenges=[
                "识别所有的条件判断点",
                "区分顺序执行 vs 并行执行",
                "处理递归或重试循环",
                "建立完整的决策树"
            ],
            recovery_hints=[
                "寻找条件关键词（'如果'、'或者'、'可能'）",
                "明确问同步/异步问题",
                "建立状态转移图",
                "识别反馈循环"
            ]
        )
        self.scenarios[scenario_7.scenario_id] = scenario_7

        # =====================================================================
        # 场景8：情绪和经验表达 - 混合主观评价
        # =====================================================================
        scenario_8 = EdgeCaseScenario(
            scenario_id="EDGE_008",
            scenario_name="经验融合型访谈",
            category="主观评价",
            description="专家混合客观步骤和主观经验、感受、建议",
            conversation=[
                {"turn": 1, "speaker": "采集系统", "text": "故障处理中最常见的错误是什么？"},
                {
                    "turn": 2, "speaker": "设备工程师_李军",
                    "text": "最糟糕的就是不看日志就开始拆...很多年轻工程师都这样做"
                },
                {
                    "turn": 3, "speaker": "设备工程师_李军",
                    "text": "这是一个教训...我见过太多这样的失败"
                },
                {
                    "turn": 4, "speaker": "设备工程师_李军",
                    "text": "所以流程必须是：看日志→判断方向→然后才能采取行动"
                },
                {
                    "turn": 5, "speaker": "采集系统", "text": "那么经验在这里的作用是什么？"},
                {
                    "turn": 6, "speaker": "设备工程师_李军",
                    "text": "经验帮助我们快速识别日志中的关键信息...我能在30秒内看出问题方向"
                },
                {
                    "turn": 7, "speaker": "设备工程师_李军",
                    "text": "新手可能需要几分钟...但基本步骤是一样的...区别只是速度"
                }
            ],
            expected_challenges=[
                "分离过程步骤和主观评价",
                "识别'教训'和'规则'",
                "处理效率改进信息",
                "识别隐含的规则"
            ],
            recovery_hints=[
                "标记主观评价（'最糟糕的'、'见过'、'教训'）",
                "提取隐含的因果规则",
                "区分'基本步骤'和'优化'",
                "记录经验信息作为额外的知识"
            ]
        )
        self.scenarios[scenario_8.scenario_id] = scenario_8

    def get_scenario(self, scenario_id: str) -> EdgeCaseScenario:
        """获取指定场景"""
        return self.scenarios.get(scenario_id)

    def list_all_scenarios(self) -> List[EdgeCaseScenario]:
        """列出所有场景"""
        return list(self.scenarios.values())

    def export_to_json(self, output_file: str):
        """导出所有场景到JSON文件"""
        export_data = {
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "version": "1.0",
                "description": "异常场景测试数据集"
            },
            "scenarios": [
                {
                    **asdict(scenario),
                    "scenario": scenario
                }
                for scenario in self.scenarios.values()
            ]
        }

        # 处理dataclass序列化
        scenarios_data = []
        for scenario in self.scenarios.values():
            scenario_dict = {
                "scenario_id": scenario.scenario_id,
                "scenario_name": scenario.scenario_name,
                "category": scenario.category,
                "description": scenario.description,
                "conversation": scenario.conversation,
                "expected_challenges": scenario.expected_challenges,
                "recovery_hints": scenario.recovery_hints
            }
            scenarios_data.append(scenario_dict)

        export_data["scenarios"] = scenarios_data

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

        print(f"✅ 已导出 {len(self.scenarios)} 个异常场景到 {output_file}")

    def print_summary(self):
        """打印场景总结"""
        print("\n" + "="*80)
        print("📋 异常场景测试数据集总结")
        print("="*80)
        print(f"\n总场景数: {len(self.scenarios)}\n")

        for scenario in self.scenarios.values():
            print(f"🔷 {scenario.scenario_id}: {scenario.scenario_name}")
            print(f"   类别: {scenario.category}")
            print(f"   描述: {scenario.description}")
            print(f"   对话轮数: {len(scenario.conversation)}")
            print(f"   预期挑战数: {len(scenario.expected_challenges)}")
            print()


# ============================================================================
# 测试函数
# ============================================================================

def test_edge_cases():
    """测试异常场景"""
    edge_cases = ExpertInterviewEdgeCases()

    # 打印总结
    edge_cases.print_summary()

    # 导出到JSON
    edge_cases.export_to_json("expert_interview_edge_cases.json")

    # 显示第一个场景的详细信息
    scenario = edge_cases.list_all_scenarios()[0]
    print("\n" + "="*80)
    print(f"📌 示例场景详解: {scenario.scenario_id}")
    print("="*80)
    print(f"名称: {scenario.scenario_name}")
    print(f"类别: {scenario.category}\n")
    print(f"描述:\n{scenario.description}\n")

    print("对话内容:")
    for turn in scenario.conversation:
        speaker = turn["speaker"]
        text = turn["text"]
        print(f"  {speaker}: {text}")

    print(f"\n预期挑战:")
    for i, challenge in enumerate(scenario.expected_challenges, 1):
        print(f"  {i}. {challenge}")

    print(f"\n恢复建议:")
    for i, hint in enumerate(scenario.recovery_hints, 1):
        print(f"  {i}. {hint}")


if __name__ == "__main__":
    test_edge_cases()

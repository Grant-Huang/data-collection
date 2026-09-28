#!/usr/bin/env python3
"""
高级异常场景：扩展的边界情况和复杂场景
包含6个新的异常场景 + 长流程测试数据

新增场景：
1. 多语言混合 - 中英文混合表述
2. 术语混乱 - 同一概念用不同术语
3. 极端长度 - 非常长或非常短的输入
4. 深度回溯 - 多层思维跳跃
5. 假设嵌套 - if-then-if 嵌套结构
6. 并发修正 - 多个问题同时纠正

扩展：
- 长流程数据集（节点>30个）
- 改进的因果链分析
- 信息完整性检查
- 置信度评分系统
"""

import json
from datetime import datetime
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum


class ConfidenceLevel(Enum):
    """置信度级别"""
    VERY_HIGH = 0.9    # 90%+ 置信度
    HIGH = 0.75        # 75-90% 置信度
    MEDIUM = 0.6       # 60-75% 置信度
    LOW = 0.4          # 40-60% 置信度
    VERY_LOW = 0.2     # <40% 置信度


@dataclass
class CausalChain:
    """因果链"""
    from_node: str
    to_node: str
    causality: str      # 因果关系描述
    strength: float     # 因果强度 (0-1)
    explanation: str


@dataclass
class AdvancedEdgeCaseScenario:
    """高级异常场景定义"""
    scenario_id: str
    scenario_name: str
    category: str
    description: str
    complexity_level: str  # SIMPLE, INTERMEDIATE, ADVANCED, EXPERT
    conversation: List[Dict[str, str]]
    expected_challenges: List[str]
    recovery_hints: List[str]
    expected_causal_chains: int  # 预期的因果链数量
    expected_completeness: float  # 预期的完整性评分 (0-1)
    expected_confidence: float    # 预期的置信度 (0-1)


class AdvancedEdgeCaseGenerator:
    """高级异常场景生成器"""

    def __init__(self):
        self.scenarios: Dict[str, AdvancedEdgeCaseScenario] = {}
        self._init_all_scenarios()

    def _init_all_scenarios(self):
        """初始化所有高级异常场景"""

        # =====================================================================
        # 场景1：多语言混合 - 中英文交织
        # =====================================================================
        scenario_1 = AdvancedEdgeCaseScenario(
            scenario_id="ADVANCED_001",
            scenario_name="多语言混合型访谈",
            category="语言混合",
            description="专家在中英文之间切换，有时混合使用",
            complexity_level="INTERMEDIATE",
            conversation=[
                {"turn": 1, "speaker": "采集系统", "text": "Please describe the quality control process"},
                {
                    "turn": 2, "speaker": "质量工程师_张明",
                    "text": "首先我们要进行incoming inspection检查...然后在线monitoring"
                },
                {
                    "turn": 3, "speaker": "质量工程师_张明",
                    "text": "如果发现defect就需要进行root cause analysis...RCA"
                },
                {
                    "turn": 4, "speaker": "质量工程师_张明",
                    "text": "之后我们会采取corrective action...纠正措施，防止再发生"
                },
                {
                    "turn": 5, "speaker": "采集系统",
                    "text": "What about the verification step?"
                },
                {
                    "turn": 6, "speaker": "质量工程师_张明",
                    "text": "verification是在CA执行后进行的...我们需要confirm问题已解决"
                },
                {
                    "turn": 7, "speaker": "质量工程师_张明",
                    "text": "最后进行effectiveness check...effectiveness evaluation来确保方案有效"
                }
            ],
            expected_challenges=[
                "处理中英文混合",
                "识别同义的中英概念",
                "统一术语表示",
                "保持流程逻辑清晰"
            ],
            recovery_hints=[
                "建立中英术语映射表",
                "检测语言切换点",
                "规范术语表示",
                "验证逻辑连贯性"
            ],
            expected_causal_chains=6,
            expected_completeness=0.85,
            expected_confidence=0.70
        )
        self.scenarios[scenario_1.scenario_id] = scenario_1

        # =====================================================================
        # 场景2：术语混乱 - 同一概念多个术语
        # =====================================================================
        scenario_2 = AdvancedEdgeCaseScenario(
            scenario_id="ADVANCED_002",
            scenario_name="术语混乱型访谈",
            category="术语不一致",
            description="同一概念用多个不同的术语表示",
            complexity_level="INTERMEDIATE",
            conversation=[
                {"turn": 1, "speaker": "采集系统", "text": "请描述设备维修流程"},
                {
                    "turn": 2, "speaker": "设备工程师_李军",
                    "text": "首先我们要检查equipment log...或者叫device code log"
                },
                {
                    "turn": 3, "speaker": "设备工程师_李军",
                    "text": "然后进行hardware diagnostic...或者称为hardware check/inspection"
                },
                {
                    "turn": 4, "speaker": "设备工程师_李军",
                    "text": "如果找到部件故障...零件故障...component failure...就要replacement"
                },
                {
                    "turn": 5, "speaker": "采集系统",
                    "text": "那repair之后呢？"
                },
                {
                    "turn": 6, "speaker": "设备工程师_李军",
                    "text": "修复后我们要进行verification testing...性能验证...或者叫performance validation"
                },
                {
                    "turn": 7, "speaker": "设备工程师_李军",
                    "text": "最后的load test...负载测试...stress test用来确保stability稳定性"
                }
            ],
            expected_challenges=[
                "识别同义的多个术语",
                "建立术语之间的映射",
                "处理中英术语混用",
                "规范术语表示"
            ],
            recovery_hints=[
                "自动建立术语同义集合",
                "使用文本相似度匹配",
                "创建术语标准化映射",
                "验证流程语义一致性"
            ],
            expected_causal_chains=6,
            expected_completeness=0.80,
            expected_confidence=0.65
        )
        self.scenarios[scenario_2.scenario_id] = scenario_2

        # =====================================================================
        # 场景3：极端长度 - 超长流程说明
        # =====================================================================
        scenario_3 = AdvancedEdgeCaseScenario(
            scenario_id="ADVANCED_003",
            scenario_name="极端长度型访谈",
            category="表达极端",
            description="单个回合包含非常长的流程说明（多个步骤）",
            complexity_level="ADVANCED",
            conversation=[
                {"turn": 1, "speaker": "采集系统", "text": "请描述完整的生产流程"},
                {
                    "turn": 2, "speaker": "生产主管_王华",
                    "text": "完整流程是这样的：首先在仓库pick原料...然后运送到生产线...进行预热处理...然后装配...接着进行初级检验...如果通过...进入下一工序...如果不通过...进行返工...返工后再检验...通过后进入喷涂工序...喷涂完成后进行干燥...干燥后进行二级检验...检验包括外观检查和尺寸检查...外观检查用目视法...尺寸检查用精密测量仪器...两项都通过才能进入包装工序...包装时要放入说明书和保修卡...包装后进行称重验证...最后进行二维码标签贴附...贴完标签后进入仓库准备出货"
                },
                {
                    "turn": 3, "speaker": "采集系统",
                    "text": "这个流程中有多少个检验点？"
                },
                {
                    "turn": 4, "speaker": "生产主管_王华",
                    "text": "三个检验点：初级检验在装配后...二级检验在干燥后...第三个是称重验证在包装后...如果在任何检验点发现问题...都要进行相应的纠正措施...初级检验发现问题进行返工...二级检验发现问题进行返工或报废处理...称重验证发现问题要检查包装内容物是否正确"
                }
            ],
            expected_challenges=[
                "分解超长句子为独立步骤",
                "识别嵌入的决策点",
                "解析复杂的流程链",
                "处理多个并发的信息",
                "保持整体结构清晰"
            ],
            recovery_hints=[
                "使用分句和分段处理",
                "识别关键词作为步骤分界",
                "建立层级结构（main steps -> sub steps）",
                "标记决策和条件",
                "生成流程树而不是线性链"
            ],
            expected_causal_chains=12,
            expected_completeness=0.75,
            expected_confidence=0.60
        )
        self.scenarios[scenario_3.scenario_id] = scenario_3

        # =====================================================================
        # 场景4：深度回溯 - 多层思维跳跃
        # =====================================================================
        scenario_4 = AdvancedEdgeCaseScenario(
            scenario_id="ADVANCED_004",
            scenario_name="深度回溯型访谈",
            category="思维跳跃",
            description="多层次的思维回溯和补充",
            complexity_level="ADVANCED",
            conversation=[
                {"turn": 1, "speaker": "采集系统", "text": "请描述故障处理流程"},
                {
                    "turn": 2, "speaker": "设备工程师_李军",
                    "text": "首先报警...然后硬件诊断...最后维修"
                },
                {
                    "turn": 3, "speaker": "采集系统", "text": "报警前呢？"},
                {
                    "turn": 4, "speaker": "设备工程师_李军",
                    "text": "报警前...哦，对...需要正常运行monitoring...还有日志记录"
                },
                {
                    "turn": 5, "speaker": "采集系统", "text": "日志记录怎么做？"},
                {
                    "turn": 6, "speaker": "设备工程师_李军",
                    "text": "日志是自动的...系统每秒记录一次...关键参数是温度、电压、电流...等等...还有运行时间和cycle count"
                },
                {
                    "turn": 7, "speaker": "采集系统", "text": "硬件诊断具体包括什么？"},
                {
                    "turn": 8, "speaker": "设备工程师_李军",
                    "text": "硬件诊断...嗯...包括多个子步骤...首先self-test...然后component check...然后connection verify...然后signal test...等等...我忘了最重要的...还要看之前的日志...因为报警前可能有异常信号...这些信号在日志里有记录"
                },
                {
                    "turn": 9, "speaker": "采集系统", "text": "所以日志很重要？"},
                {
                    "turn": 10, "speaker": "设备工程师_李军",
                    "text": "是的...关键是要追踪日志...从报警往前回溯...找出最早出现异常的时间点...以及当时的参数值...这样能判断是什么故障...然后在硬件诊断时就能有针对性地检查...而不是盲目的全面检查"
                }
            ],
            expected_challenges=[
                "追踪多层回溯的逻辑关系",
                "识别后期发现的关键信息",
                "重建正确的因果链",
                "处理循环依赖关系",
                "建立前置和后置关系"
            ],
            recovery_hints=[
                "记录每个回溯点和补充内容",
                "分析信息之间的依赖关系",
                "使用拓扑排序建立正确顺序",
                "识别关键决策节点",
                "验证因果链的完整性"
            ],
            expected_causal_chains=10,
            expected_completeness=0.70,
            expected_confidence=0.55
        )
        self.scenarios[scenario_4.scenario_id] = scenario_4

        # =====================================================================
        # 场景5：假设嵌套 - 多层条件嵌套
        # =====================================================================
        scenario_5 = AdvancedEdgeCaseScenario(
            scenario_id="ADVANCED_005",
            scenario_name="假设嵌套型访谈",
            category="嵌套条件",
            description="复杂的嵌套条件结构 (if-then-if-then)",
            complexity_level="EXPERT",
            conversation=[
                {"turn": 1, "speaker": "采集系统", "text": "异常处理的完整逻辑是什么？"},
                {
                    "turn": 2, "speaker": "质量工程师_张明",
                    "text": "首先检查是否真的异常...如果确认异常...就要判断异常类型...如果是尺寸异常...我们进行测量分析...如果是材料异常...我们进行材料分析"
                },
                {
                    "turn": 3, "speaker": "质量工程师_张明",
                    "text": "然后对于尺寸异常...还要判断是超大还是超小...如果超大...可能是模具磨损...需要更换模具或调整参数...如果超小...可能是工艺不稳定...需要重新校准"
                },
                {
                    "turn": 4, "speaker": "质量工程师_张明",
                    "text": "对于材料异常...还要检查是表面异常还是内部异常...如果是表面异常...清洁后重新检验...如果是内部异常...需要报废或降级使用"
                },
                {
                    "turn": 5, "speaker": "质量工程师_张明",
                    "text": "而且...如果采取措施后...还要再做验证...验证成功...进行根本原因分析...制定预防措施...验证失败...则进行二次诊断...二次诊断时可能需要专家参与"
                },
                {
                    "turn": 6, "speaker": "采集系统", "text": "如果二次诊断还是失败呢？"},
                {
                    "turn": 7, "speaker": "质量工程师_张明",
                    "text": "如果二次诊断失败...那就要升级...可能需要停线调查...或者送样到外部实验室...当然...前提是问题的严重程度足够...如果只是个别产品...可能就直接处理...但如果是批量问题...就必须根本解决"
                }
            ],
            expected_challenges=[
                "解析多层嵌套的if-then结构",
                "识别所有的分支路径",
                "建立完整的决策树",
                "处理跨层级的依赖关系",
                "处理递归性的验证流程"
            ],
            recovery_hints=[
                "使用树形结构表示嵌套条件",
                "标记每个条件的层级和范围",
                "枚举所有可能的路径",
                "验证条件的互斥性和完整性",
                "使用临界点标记决策重要性"
            ],
            expected_causal_chains=15,
            expected_completeness=0.65,
            expected_confidence=0.50
        )
        self.scenarios[scenario_5.scenario_id] = scenario_5

        # =====================================================================
        # 场景6：并发修正 - 多个问题同时修正
        # =====================================================================
        scenario_6 = AdvancedEdgeCaseScenario(
            scenario_id="ADVANCED_006",
            scenario_name="并发修正型访谈",
            category="并发修正",
            description="多个错误或不清楚的地方同时被纠正",
            complexity_level="ADVANCED",
            conversation=[
                {"turn": 1, "speaker": "采集系统", "text": "请描述检验流程"},
                {
                    "turn": 2, "speaker": "质量工程师_张明",
                    "text": "检验包括外观检查和功能测试...不对，应该还有尺寸测量...嗯...其实检验有三部分"
                },
                {
                    "turn": 3, "speaker": "质量工程师_张明",
                    "text": "外观检查...等等，我之前说的顺序不对...应该是先做功能测试...确保功能正常...然后再做外观检查...因为功能测试可能会有振动"
                },
                {
                    "turn": 4, "speaker": "质量工程师_张明",
                    "text": "哦还有...尺寸测量应该在功能测试之前...因为功能测试会产生热...可能影响尺寸...所以顺序应该是：尺寸→功能→外观"
                },
                {
                    "turn": 5, "speaker": "采集系统", "text": "每个检验需要多长时间？"},
                {
                    "turn": 6, "speaker": "质量工程师_张明",
                    "text": "尺寸测量...不对，我刚才说需要10分钟，其实不对...有些产品5分钟就够...有些需要15分钟...取决于特征点的数量...功能测试是2小时...不对，通常是30分钟...除非有问题需要延长...外观检查是10分钟左右"
                }
            ],
            expected_challenges=[
                "识别同时发生的多个纠正",
                "追踪哪些陈述被更新了",
                "处理相互关联的修正",
                "识别修正之间的依赖关系",
                "确定最终的正确版本"
            ],
            recovery_hints=[
                "标记所有的纠正点",
                "为每个修正建立版本号",
                "识别修正之间的优先级",
                "合并相关的修正",
                "验证修正后的一致性"
            ],
            expected_causal_chains=7,
            expected_completeness=0.72,
            expected_confidence=0.58
        )
        self.scenarios[scenario_6.scenario_id] = scenario_6

    def get_scenario(self, scenario_id: str) -> AdvancedEdgeCaseScenario:
        """获取指定场景"""
        return self.scenarios.get(scenario_id)

    def list_all_scenarios(self) -> List[AdvancedEdgeCaseScenario]:
        """列出所有场景"""
        return list(self.scenarios.values())

    def export_to_json(self, output_file: str = "advanced_edge_cases.json"):
        """导出所有场景到JSON文件"""
        scenarios_data = []
        for scenario in self.scenarios.values():
            scenario_dict = {
                "scenario_id": scenario.scenario_id,
                "scenario_name": scenario.scenario_name,
                "category": scenario.category,
                "description": scenario.description,
                "complexity_level": scenario.complexity_level,
                "conversation": scenario.conversation,
                "expected_challenges": scenario.expected_challenges,
                "recovery_hints": scenario.recovery_hints,
                "expected_causal_chains": scenario.expected_causal_chains,
                "expected_completeness": scenario.expected_completeness,
                "expected_confidence": scenario.expected_confidence
            }
            scenarios_data.append(scenario_dict)

        export_data = {
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "version": "2.0",
                "description": "高级异常场景测试数据集 - 扩展版本",
                "total_scenarios": len(scenarios_data),
                "categories": list(set(s["category"] for s in scenarios_data))
            },
            "scenarios": scenarios_data
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

        print(f"✅ 已导出 {len(scenarios_data)} 个高级异常场景到 {output_file}")

    def print_summary(self):
        """打印场景总结"""
        print("\n" + "="*80)
        print("📋 高级异常场景测试数据集总结")
        print("="*80)
        print(f"\n总场景数: {len(self.scenarios)}\n")

        by_complexity = {}
        for scenario in self.scenarios.values():
            level = scenario.complexity_level
            if level not in by_complexity:
                by_complexity[level] = []
            by_complexity[level].append(scenario)

        for level in ["INTERMEDIATE", "ADVANCED", "EXPERT"]:
            if level in by_complexity:
                print(f"\n【{level}】 ({len(by_complexity[level])} 个场景)")
                for scenario in by_complexity[level]:
                    print(f"  🔷 {scenario.scenario_id}: {scenario.scenario_name}")
                    print(f"     类别: {scenario.category}")
                    print(f"     对话轮数: {len(scenario.conversation)}")
                    print(f"     因果链: {scenario.expected_causal_chains}")
                    print(f"     完整性: {scenario.expected_completeness:.0%}, 置信度: {scenario.expected_confidence:.0%}")


class LongProcessGenerator:
    """长流程数据集生成器（节点>30个）"""

    @staticmethod
    def generate_semiconductor_manufacturing_process() -> Dict[str, Any]:
        """生成半导体制造完整流程（40+节点）"""
        return {
            "scenario_id": "LONG_001",
            "scenario_name": "半导体制造完整流程",
            "category": "长流程测试",
            "description": "半导体制造的完整工艺流程，包含40个以上的步骤",
            "conversation": [
                {
                    "turn": 1,
                    "speaker": "工艺工程师",
                    "text": """完整的半导体制造流程包括以下步骤：

第一阶段（硅片准备）：
1. 硅片切割 - 从晶棒中切割硅片
2. 硅片清洗 - 去除表面杂质
3. 硅片检验 - 检查硅片质量

第二阶段（氧化层制作）：
4. 湿法氧化 - 在炉子中氧化硅片
5. 干法氧化 - 添加额外的氧化层
6. 氧化层厚度检测 - 使用椭圆偏振仪检测

第三阶段（光刻工艺）：
7. 涂布光刻胶 - 均匀涂布光刻胶
8. 软烤 - 去除光刻胶中的溶剂
9. 光刻曝光 - 使用掩膜进行曝光
10. 焦距调整 - 调整焦距确保清晰度
11. 显影 - 显影光刻胶
12. 硬烤 - 固化光刻胶

第四阶段（刻蚀工艺）：
13. 等离子刻蚀 - 使用等离子刻蚀图案
14. 湿法刻蚀 - 化学刻蚀
15. 刻蚀后清洗 - 清除刻蚀副产物
16. 光刻胶脱除 - 去除剩余光刻胶

第五阶段（掺杂工艺）：
17. 离子植入 - 高能离子植入
18. 快速热退火 - 固化掺杂原子
19. 掺杂浓度检测 - 使用二次离子质谱仪

第六阶段（薄膜沉积）：
20. 化学气相沉积 - 沉积二氧化硅
21. 金属化沉积 - 沉积金属层
22. 膜厚检测 - 使用椭圆偏振仪

第七阶段（互连制作）：
23. 金属互连光刻 - 定义金属互连图案
24. 金属刻蚀 - 刻蚀金属层
25. 绝缘层沉积 - 沉积层间绝缘层
26. 化学机械抛光 - 平坦化表面

第八阶段（多层互连）：
27. 孔洞刻蚀 - 刻蚀接触孔
28. 钨填充 - 填充钨
29. 第二层金属沉积 - 沉积第二层金属
30. 第二层刻蚀 - 刻蚀第二层

第九阶段（后续工艺）：
31. 钝化层沉积 - 沉积钝化层
32. 焊盘打开 - 打开芯片焊盘
33. 最终检测 - 进行最终电气测试
34. 晶圆切割 - 将晶圆切成单个芯片

第十阶段（封装测试）：
35. 芯片挑选 - 选择合格芯片
36. 芯片粘贴 - 粘贴到封装基体
37. 焊线连接 - 进行焊线连接
38. 模压成型 - 进行模压
39. 去毛刺 - 处理毛刺
40. 最终标记 - 进行激光标记
41. 最终检测 - 进行最终功能检测
42. 包装 - 进行防静电包装
                    """
                },
                {
                    "turn": 2,
                    "speaker": "采集系统",
                    "text": "关键质量控制点在哪些步骤？"
                },
                {
                    "turn": 3,
                    "speaker": "工艺工程师",
                    "text": """关键控制点包括：
- 第3步：硅片检验 - 初始质量把控
- 第6步：厚度检测 - 氧化层质量
- 第10步：焦距检测 - 光刻精度
- 第14步：刻蚀检测 - 图案清晰度
- 第22步：膜厚检测 - 膜层质量
- 第33步：电气测试 - 功能验证
- 第41步：最终检测 - 成品质量

这些点的检测失败都会导致整个批次报废。
                    """
                }
            ],
            "expected_nodes": 42,
            "expected_edges": 41,
            "complexity": "EXPERT"
        }

    @staticmethod
    def generate_long_process_report() -> Dict[str, Any]:
        """生成长流程测试报告"""
        process_data = LongProcessGenerator.generate_semiconductor_manufacturing_process()

        return {
            "process_id": process_data["scenario_id"],
            "process_name": process_data["scenario_name"],
            "total_steps": process_data["expected_nodes"],
            "total_transitions": process_data["expected_edges"],
            "conversation_length": sum(len(turn.get("text", "").split())
                                       for turn in process_data["conversation"]),
            "quality_control_points": 7,
            "critical_transitions": [
                "硅片检验 → 湿法氧化",
                "光刻曝光 → 显影",
                "等离子刻蚀 → 刻蚀后清洗",
                "化学机械抛光 → 孔洞刻蚀",
                "钝化层沉积 → 焦盘打开",
                "最终标记 → 最终检测"
            ],
            "sequential_dependencies": {
                "high": 35,  # 强制顺序依赖
                "medium": 4, # 可选顺序依赖
                "low": 2     # 弱依赖
            }
        }


# ============================================================================
# 测试函数
# ============================================================================

def test_advanced_edge_cases():
    """测试高级异常场景"""
    generator = AdvancedEdgeCaseGenerator()

    # 打印总结
    generator.print_summary()

    # 导出到JSON
    generator.export_to_json()

    # 生成长流程测试数据
    print("\n" + "="*80)
    print("📊 长流程测试数据")
    print("="*80)

    long_process = LongProcessGenerator.generate_semiconductor_manufacturing_process()
    long_report = LongProcessGenerator.generate_long_process_report()

    print(f"\n流程名称: {long_process['scenario_name']}")
    print(f"总步骤数: {long_report['total_steps']}")
    print(f"总转换数: {long_report['total_transitions']}")
    print(f"对话字数: {long_report['conversation_length']}")
    print(f"质量控制点: {long_report['quality_control_points']}")
    print(f"\n顺序依赖:")
    print(f"  强依赖: {long_report['sequential_dependencies']['high']}")
    print(f"  中依赖: {long_report['sequential_dependencies']['medium']}")
    print(f"  弱依赖: {long_report['sequential_dependencies']['low']}")

    # 保存长流程数据
    with open("long_process_test_data.json", 'w', encoding='utf-8') as f:
        json.dump(long_process, f, ensure_ascii=False, indent=2)

    with open("long_process_analysis.json", 'w', encoding='utf-8') as f:
        json.dump(long_report, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 已保存长流程数据到 long_process_test_data.json")
    print(f"✅ 已保存流程分析到 long_process_analysis.json")


if __name__ == "__main__":
    test_advanced_edge_cases()

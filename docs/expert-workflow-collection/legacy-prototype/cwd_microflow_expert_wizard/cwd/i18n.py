TEXT = {
"zh":{
"title":"协作工作流蒸馏 — 论文实验平台",
"caption":"制造协作轨迹 → 语义抽象 → Episode 分段 → Process Mining → Micro-workflow 恢复",
"single":"单组实验","compare":"多组对比","paper":"论文 Baseline 套件",
"data":"数据参数","cases":"Cases 数量","bv":"业务变体率","ed":"执行偏差率","le":"日志错误率",
"hetero":"工具异构度","human":"额外人工介入率","seed":"随机种子",
"method":"方法","semantic":"语义能力归一化","seg":"Episode 分段","miner":"Workflow Miner",
"backend":"Embedding 后端","run":"运行","runpaper":"运行论文 Baseline 套件",
"none":"不分段","rule":"Rule-based","embed":"Embedding Change-Point","oracle":"Oracle 上限",
"consensus":"Consensus DFG","inductive":"PM4Py Inductive Miner","heuristics":"PM4Py Heuristics Miner",
"f1":"Micro-workflow F1","bf1":"Boundary F1","status":"状态","explain":"结果解释",
"pmnote":"PM4Py 是正式 baseline。若本机尚未安装，会显示 unavailable；安装 requirements.txt 后即可运行。",
"embnote":"Embedding Change-Point 优先使用 sentence-transformers；若模型不可用则自动回退到 TF-IDF+SVD dense embedding，以保证实验可复现。",
"oraclewarn":"Oracle 直接读取 synthetic ground-truth episode 边界，仅作为 upper bound。",
},
"en":{
"title":"Collaborative Workflow Distillation — Paper Experiment Platform",
"caption":"Manufacturing collaborative traces → semantic abstraction → episode segmentation → process mining → micro-workflow recovery",
"single":"Single Run","compare":"Multi-Run Comparison","paper":"Paper Baseline Suite",
"data":"Data Parameters","cases":"Number of Cases","bv":"Business Variation Rate","ed":"Execution Deviation Rate","le":"Logging Error Rate",
"hetero":"Tool Heterogeneity","human":"Additional Human Intervention Rate","seed":"Random Seed",
"method":"Method","semantic":"Semantic Capability Normalization","seg":"Episode Segmentation","miner":"Workflow Miner",
"backend":"Embedding Backend","run":"Run","runpaper":"Run Paper Baseline Suite",
"none":"No Segmentation","rule":"Rule-based","embed":"Embedding Change-Point","oracle":"Oracle Upper Bound",
"consensus":"Consensus DFG","inductive":"PM4Py Inductive Miner","heuristics":"PM4Py Heuristics Miner",
"f1":"Micro-workflow F1","bf1":"Boundary F1","status":"Status","explain":"Result Interpretation",
"pmnote":"PM4Py is a formal process-mining baseline. If it is not installed locally the run is marked unavailable; install requirements.txt to enable it.",
"embnote":"Embedding Change-Point prefers sentence-transformers and falls back to deterministic TF-IDF+SVD dense embeddings when the model is unavailable.",
"oraclewarn":"Oracle directly reads synthetic ground-truth episode boundaries and is only an upper bound.",
}}
TIPS={
"zh":{
"bv":"合理业务变体，例如可选步骤、合法局部重排、不同角色参与；不是日志错误。",
"ed":"实际执行失败、重试、补偿等偏离标准路径的情况。",
"le":"平台观测层面的漏记、重复、时间戳扰动等。",
"semantic":"将 MES/SAP/Agent 等不同工具映射到同一业务能力。",
"seg":"把长协作 case 切成目标较一致的工作 episode。",
"embed":"把每个 event 的 activity、intent、actor、object 编码成向量，通过左右窗口语义变化检测边界。",
"f1":"发现的 micro-workflow 类别与 ground truth 的 Macro F1。",
"bf1":"预测 episode 边界与真实边界的 F1。",
},
"en":{
"bv":"Legitimate business variants such as optional steps, local reordering, or role substitution.",
"ed":"Execution failures, retries, compensation, or other deviations from the normative path.",
"le":"Observation errors such as missing, duplicate, or timestamp-perturbed records.",
"semantic":"Maps implementation-specific tools from MES/SAP/agents into shared business capabilities.",
"seg":"Splits a long collaborative case into semantically coherent work episodes.",
"embed":"Encodes event activity, intent, actor, and object into vectors and detects semantic changes between left/right windows.",
"f1":"Macro F1 between recovered micro-workflow labels and ground truth.",
"bf1":"F1 between predicted and true episode boundaries.",
}}
def tr(lang,key): return TEXT[lang].get(key,key)
def tip(lang,key): return TIPS[lang].get(key)

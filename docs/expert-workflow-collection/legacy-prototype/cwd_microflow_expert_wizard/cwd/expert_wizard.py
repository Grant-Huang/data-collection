import json
import uuid
from datetime import datetime
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


def _blank_trace(n=15):
    return pd.DataFrame([
        {
            "步骤序号": i+1,
            "大致时间": "",
            "执行人": "",
            "角色": "",
            "做了什么": "",
            "为什么做": "",
            "使用的系统/工具": "",
            "输入/依据": "",
            "输出/决定": "",
            "工作对象": "",
            "是否重试/异常": "否",
        }
        for i in range(n)
    ])


def _full_example_trace():
    rows = [
        [1,"09:12","张工","生产主管","收到3号线停机报警并确认产线已停止","先确认异常是否真实、影响是否仍在持续","MES","设备报警、线体状态","确认3号线停机","3号线/设备M3","否"],
        [2,"09:15","张工","生产主管","查看当前正在生产的工单和在制数量","确认停机时正在做什么、影响了多少在制品","MES","工单、WIP","确认O1048正在生产，WIP 420件","工单O1048","否"],
        [3,"09:18","维护Agent","设备维护助手","查询最近7天同设备报警历史","寻找重复故障和异常模式","维护系统","报警历史","发现同类伺服报警出现2次","设备M3","否"],
        [4,"09:21","刘工","维修工程师","查看上次维修记录和更换部件","判断本次是否与上次故障有关","CMMS","维修历史","上次更换过编码器接头","设备M3","否"],
        [5,"09:25","维护Agent","设备维护助手","调取停机前30分钟关键参数趋势","寻找故障发生前的参数变化","设备数据平台","电流、温度、速度趋势","发现停机前电流波动异常","设备M3","否"],
        [6,"09:31","刘工","维修工程师","现场检查编码器连接和伺服驱动","验证历史证据对应的可能原因","现场检查","接口、驱动器状态","确认编码器接头松动","设备M3","否"],
        [7,"09:36","李工","计划员","查询3号线未来8小时排产和订单优先级","判断停机对生产计划影响多大","APS","排产、订单优先级","识别3个受影响订单","订单O1048/O1052/O1057","否"],
        [8,"09:40","李工","计划员","查询受影响订单承诺交期","判断哪些订单可能影响客户交付","ERP","订单交期","O1052当天16:00必须完成","订单O1052","否"],
        [9,"09:44","计划Agent","计划助手","计算若3号线停机2小时的预计延误","量化停机持续时间对应的风险","APS","产能、WIP、节拍","O1052预计延误70分钟","订单O1052","否"],
        [10,"09:49","王工","质量工程师","确认停机瞬间在制品是否需要隔离","避免异常停机造成质量风险","QMS","批次、停机时间","建议隔离当前420件WIP待复检","批次B2208","否"],
        [11,"09:54","计划Agent","计划助手","查询2号线可用产能和换线条件","寻找替代生产资源","APS","2号线产能、换线时间","2号线10:20后可释放45%产能","2号线","否"],
        [12,"09:58","李工","计划员","生成两个恢复方案：等待维修或转移O1052到2号线","比较不同恢复选择","APS","维修预估、产能、交期","形成方案A/B","订单O1052","否"],
        [13,"10:04","刘工","维修工程师","给出预计30分钟可恢复的维修判断","为恢复方案提供维修时间依据","现场/CMMS","检查结果","预计10:35前恢复","设备M3","否"],
        [14,"10:08","张工","生产主管","组织计划、维修、质量快速确认恢复方案","避免单部门决策遗漏约束","现场会议","方案A/B、质量隔离要求","决定O1052先转2号线，其余等待3号线","跨部门决策","否"],
        [15,"10:12","李工","计划员","调整O1052排产并锁定2号线时间窗","把已批准方案转成可执行计划","APS","批准方案","新排产已发布","订单O1052/2号线","否"],
        [16,"10:18","刘工","维修工程师","重新固定编码器接头并完成设备试运行","恢复3号线设备能力","现场维修","故障原因","设备试运行正常","设备M3","否"],
        [17,"10:23","王工","质量工程师","完成隔离WIP快速复检并解除隔离","确认异常期间产品可以继续使用","QMS","抽检结果","420件WIP复检合格","批次B2208","否"],
        [18,"10:28","张工","生产主管","确认3号线恢复、2号线转产完成且订单风险解除","验证恢复措施是否真正解决问题","MES/APS","设备状态、排产、订单风险","事件关闭，O1052预计按时完成","整个事件","否"],
    ]
    return pd.DataFrame(rows, columns=["步骤序号","大致时间","执行人","角色","做了什么","为什么做","使用的系统/工具","输入/依据","输出/决定","工作对象","是否重试/异常"])


def _example_groups(trace_df):
    phase_map = {
        1:(1,"确认现场与上下文"), 2:(1,"确认现场与上下文"),
        3:(2,"原因证据收集"),4:(2,"原因证据收集"),5:(2,"原因证据收集"),6:(2,"原因证据收集"),
        7:(3,"生产与交付影响评估"),8:(3,"生产与交付影响评估"),9:(3,"生产与交付影响评估"),10:(3,"生产与交付影响评估"),
        11:(4,"恢复方案生成"),12:(4,"恢复方案生成"),13:(4,"恢复方案生成"),
        14:(5,"跨部门评审与批准"),
        15:(6,"恢复方案执行"),16:(6,"恢复方案执行"),17:(6,"恢复方案执行"),
        18:(7,"恢复验证与关闭"),
    }
    out = trace_df[["步骤序号","做了什么","为什么做"]].copy()
    out["小目标编号"] = out["步骤序号"].map(lambda x: phase_map.get(int(x),(1,"待命名"))[0])
    out["小目标名称"] = out["步骤序号"].map(lambda x: phase_map.get(int(x),(1,"待命名"))[1])
    out["这个边界拿不准"] = "否"
    return out



def _default_dependencies(trace_df):
    trace=_clean_trace(trace_df) if "_clean_trace" in globals() else trace_df.copy()
    rows=[]
    for i,r in trace.reset_index(drop=True).iterrows():
        step=int(r["步骤序号"])
        rows.append({
            "步骤序号":step,
            "做了什么":r.get("做了什么",""),
            "开始前必须完成哪些步骤":"" if i==0 else str(int(trace.iloc[i-1]["步骤序号"])),
            "关系备注":"",
        })
    return pd.DataFrame(rows)


def _example_dependencies(trace_df):
    pred={1:"",2:"1",3:"2",4:"2",5:"2",6:"3,4,5",7:"6",8:"7",9:"8",10:"6",11:"9,10",12:"11",13:"12",14:"13",15:"14",16:"14",17:"16",18:"15,17"}
    out=trace_df[["步骤序号","做了什么"]].copy()
    out["开始前必须完成哪些步骤"]=out["步骤序号"].map(lambda x: pred.get(int(x),""))
    out["关系备注"]=""
    return out


def _blank_branch_table():
    return pd.DataFrame(columns=["分叉点步骤","分支起始步骤","这些分支是什么关系","汇合步骤","什么时候可以继续","说明"])


def _example_branch_table():
    return pd.DataFrame([
        {"分叉点步骤":2,"分支起始步骤":"3,4,5","这些分支是什么关系":"同时都要做","汇合步骤":6,"什么时候可以继续":"全部完成后","说明":"报警、维修记录、参数趋势可以并行收集，现场检查汇总证据。"},
        {"分叉点步骤":6,"分支起始步骤":"7,10","这些分支是什么关系":"同时都要做","汇合步骤":11,"什么时候可以继续":"全部完成后","说明":"计划影响评估与质量风险检查并行。"},
        {"分叉点步骤":14,"分支起始步骤":"15,16","这些分支是什么关系":"同时都要做","汇合步骤":18,"什么时候可以继续":"全部完成后","说明":"排产调整与设备维修并行，最终在恢复确认处汇合。"},
    ])

def _intro_animation():
    components.html(r'''
    <div style="font-family:Arial,'Microsoft YaHei',sans-serif;background:#f7fafc;border:1px solid #dfe7ef;border-radius:16px;padding:20px 24px;overflow:hidden;">
      <div style="font-size:20px;font-weight:700;margin-bottom:5px;color:#16324f;">你只需要讲清楚“一件真实事情是怎么处理的”</div>
      <div style="color:#66788a;margin-bottom:18px;">系统负责把完整案例转换成可分析的工作轨迹，你不需要懂 AI 或流程挖掘。</div>
      <div id="flow" style="display:flex;gap:12px;align-items:stretch;min-width:780px;">
        <div class="box active"><b>① 完整业务事件</b><span>例如：产线停机导致交付风险</span></div>
        <div class="arrow">→</div>
        <div class="box"><b>② 按时间写动作</b><span>谁做了什么、为什么做</span></div>
        <div class="arrow">→</div>
        <div class="box"><b>③ 按“小目标”分段</b><span>哪些连续步骤在解决同一件小事</span></div>
        <div class="arrow">→</div>
        <div class="box"><b>④ 系统发现可复用套路</b><span>例如：原因证据收集、影响评估</span></div>
      </div>
    </div>
    <style>
      .box{width:190px;min-height:92px;border-radius:12px;padding:14px;background:white;border:2px solid #dfe7ef;transition:.45s;box-sizing:border-box;box-shadow:0 2px 8px rgba(20,50,80,.05)}
      .box b{display:block;color:#16324f;margin-bottom:8px}.box span{font-size:13px;color:#6c7f90;line-height:1.45}
      .box.active{border-color:#2d7ff9;transform:translateY(-5px);box-shadow:0 8px 20px rgba(45,127,249,.18);background:#f2f7ff}
      .arrow{font-size:25px;color:#93a4b5;display:flex;align-items:center}
    </style>
    <script>
      const boxes=[...document.querySelectorAll('.box')]; let i=0;
      setInterval(()=>{boxes.forEach(x=>x.classList.remove('active')); i=(i+1)%boxes.length; boxes[i].classList.add('active');},1700);
    </script>
    ''', height=180)


def _ensure_state():
    if "expert_wizard_step" not in st.session_state:
        st.session_state.expert_wizard_step = 0
    if "expert_case_meta" not in st.session_state:
        st.session_state.expert_case_meta = {
            "dataset_name":"ManufacturingExpertBatch-01",
            "annotator_id":"Expert-01",
            "case_id":f"CASE-{uuid.uuid4().hex[:6].upper()}",
            "case_title":"",
            "factory_or_line":"",
            "problem_type":"设备异常",
            "business_goal":"",
            "final_result":"",
            "result_quality":"成功",
            "case_date":str(datetime.now().date()),
        }
    if "expert_trace_df" not in st.session_state:
        st.session_state.expert_trace_df = _blank_trace(15)
    if "expert_dependency_df" not in st.session_state:
        st.session_state.expert_dependency_df = pd.DataFrame()
    if "expert_branch_df" not in st.session_state:
        st.session_state.expert_branch_df = _blank_branch_table()
    if "expert_group_df" not in st.session_state:
        st.session_state.expert_group_df = pd.DataFrame()
    if "expert_reuse_df" not in st.session_state:
        st.session_state.expert_reuse_df = pd.DataFrame()
    if "expert_datasets" not in st.session_state:
        st.session_state.expert_datasets = {}


def _progress(step):
    names=["说明","案例背景","工作过程","分叉与汇合","工作单元归组","复用性确认","检查并保存"]
    cols=st.columns(len(names))
    for i,(c,n) in enumerate(zip(cols,names)):
        if i<step:
            c.success(f"✓ {n}")
        elif i==step:
            c.info(f"● {n}")
        else:
            c.caption(f"○ {n}")


def _nav(show_back=True, next_label="下一步 →", allow_next=True):
    c1,c2,_=st.columns([1,1,5])
    if show_back and c1.button("← 上一步", use_container_width=True):
        st.session_state.expert_wizard_step=max(0,st.session_state.expert_wizard_step-1)
        st.rerun()
    if c2.button(next_label, type="primary", use_container_width=True, disabled=not allow_next):
        st.session_state.expert_wizard_step=min(6,st.session_state.expert_wizard_step+1)
        st.rerun()


def _clean_trace(df):
    out=df.copy()
    out=out[out["做了什么"].fillna("").astype(str).str.strip()!=""].copy()
    out["步骤序号"]=range(1,len(out)+1)
    return out.reset_index(drop=True)


def _derive_reuse_df(group_df):
    if group_df.empty:
        return pd.DataFrame(columns=["小目标名称","以后类似问题还会用到吗","换个人/Agent还能用吗","换系统/工具还能用吗","复用价值(1-5)","补充说明"])
    names=[]
    for x in group_df["小目标名称"].fillna("").astype(str):
        x=x.strip()
        if x and x not in names: names.append(x)
    return pd.DataFrame([{
        "小目标名称":n,
        "以后类似问题还会用到吗":"是",
        "换个人/Agent还能用吗":"是",
        "换系统/工具还能用吗":"是",
        "复用价值(1-5)":4,
        "补充说明":"",
    } for n in names])


def _to_canonical(meta, trace, groups, dependencies=None, branches=None):
    trace=_clean_trace(trace)
    dependencies = dependencies if dependencies is not None else _default_dependencies(trace)
    branches = branches if branches is not None else _blank_branch_table()

    gmap={}; ambiguity={}
    for _,r in groups.iterrows():
        try: step=int(r["步骤序号"])
        except Exception: continue
        no=r.get("小目标编号",""); name=str(r.get("小目标名称","") or "").strip()
        gmap[step]=(no,name); ambiguity[step]=str(r.get("这个边界拿不准","否"))

    # Allocate event IDs before resolving dependency references.
    step_to_event={int(r["步骤序号"]):str(uuid.uuid4()) for _,r in trace.iterrows()}
    pred_map={}
    for _,r in dependencies.iterrows():
        try: step=int(r["步骤序号"])
        except Exception: continue
        raw=str(r.get("开始前必须完成哪些步骤","") or "")
        vals=[]
        for x in raw.replace(";",",").split(","):
            x=x.strip()
            if not x: continue
            try: vals.append(int(float(x)))
            except Exception: pass
        pred_map[step]=[step_to_event[x] for x in vals if x in step_to_event]

    branch_meta={step:{"branch_group_id":"","branch_type":"","join_policy":"","control_role":""} for step in step_to_event}
    relation_map={"同时都要做":"and","根据情况选一条":"xor","根据情况做一条或多条":"or"}
    join_map={"全部完成后":"all","任意一个完成后":"any","达到必要结果后":"required_set","由负责人判断":"manual_decision"}
    branch_records=[]
    for i,r in branches.dropna(how="all").iterrows():
        try: fork=int(r.get("分叉点步骤"))
        except Exception: continue
        raw=str(r.get("分支起始步骤","") or "")
        members=[]
        for x in raw.replace(";",",").split(","):
            try: members.append(int(float(x.strip())))
            except Exception: pass
        try: join=int(r.get("汇合步骤"))
        except Exception: join=None
        btype=relation_map.get(str(r.get("这些分支是什么关系","") or ""),"")
        jpolicy=join_map.get(str(r.get("什么时候可以继续","") or ""),"")
        gid=f"{meta['case_id']}_BG{i+1:02d}"
        if fork in branch_meta: branch_meta[fork].update(branch_group_id=gid,branch_type=btype,control_role="fork")
        for m in members:
            if m in branch_meta: branch_meta[m].update(branch_group_id=gid,branch_type=btype,control_role="branch")
        if join in branch_meta: branch_meta[join].update(branch_group_id=gid,branch_type=btype,join_policy=jpolicy,control_role="join")
        branch_records.append({"branch_group_id":gid,"fork_step":fork,"branch_steps":members,"branch_type":btype,
                               "join_step":join,"join_policy":jpolicy,"note":str(r.get("说明","") or "")})

    rows=[]
    for _,r in trace.iterrows():
        step=int(r["步骤序号"]); eno,ename=gmap.get(step,(None,"")); bm=branch_meta.get(step,{})
        rows.append({
            "source_type":"expert_wizard","dataset_name":meta["dataset_name"],"annotator_id":meta["annotator_id"],
            "case_id":meta["case_id"],"case_title":meta["case_title"],"factory_or_line":meta["factory_or_line"],
            "problem_type":meta["problem_type"],"business_goal":meta["business_goal"],"final_result":meta["final_result"],
            "result_quality":meta["result_quality"],"event_id":step_to_event[step],"step_no":step,
            "timestamp_raw":str(r.get("大致时间","") or ""),"actor_raw":str(r.get("执行人","") or ""),
            "role_raw":str(r.get("角色","") or ""),"raw_action_text":str(r.get("做了什么","") or ""),
            "raw_intent_text":str(r.get("为什么做","") or ""),"raw_tool_text":str(r.get("使用的系统/工具","") or ""),
            "raw_input_text":str(r.get("输入/依据","") or ""),"raw_output_text":str(r.get("输出/决定","") or ""),
            "raw_object_text":str(r.get("工作对象","") or ""),"execution_flag":str(r.get("是否重试/异常","否") or "否"),
            "predecessor_event_ids":";".join(pred_map.get(step,[])),"dependency_source":"expert",
            "branch_group_id":bm.get("branch_group_id",""),"branch_type":bm.get("branch_type",""),
            "join_policy":bm.get("join_policy",""),"control_role":bm.get("control_role",""),
            "episode_id_expert":f"{meta['case_id']}_E{int(eno):02d}" if pd.notna(eno) and str(eno)!="" else "",
            "episode_name_expert":ename,"episode_reference_source":"expert","soft_boundary_flag":ambiguity.get(step,"否"),
            "semantic_capability":"","intent_normalized":"","actor_type":"","actor_role":"","object_type":"",
        })
    return pd.DataFrame(rows), pd.DataFrame(branch_records)


def render_expert_wizard():
    _ensure_state()
    st.title("🧭 制造专家数据采集 Wizard")
    st.caption("不需要懂 AI、IT 或流程挖掘。每次只讲清楚一个真实业务事件，系统负责转换成研究数据。")
    _progress(st.session_state.expert_wizard_step)
    st.divider()
    step=st.session_state.expert_wizard_step

    if step==0:
        _intro_animation()
        st.markdown("### 什么样的案例最合适？")
        c1,c2,c3=st.columns(3)
        c1.info("**选完整事件**\n\n例如：设备停机 → 调查 → 判断影响 → 形成方案 → 执行 → 验证。")
        c2.warning("**不要只填3个步骤**\n\n3步往往已经接近一个微工作流，无法观察多个可复用工作单元如何组合。")
        c3.success("**推荐 10–30 个动作**\n\n通常包含 3–7 个不同的小目标，是最适合研究的粒度。")
        st.markdown("#### 完整案例 ≠ 微工作流")
        st.write("一个完整案例应该包含多个小阶段。例如：**确认现场 → 原因证据收集 → 影响评估 → 恢复方案 → 审批 → 执行 → 验证**。系统研究的正是能否从这些完整案例里重新发现可复用的小套路。")
        if st.button("▶ 看一个18步完整样例并开始填写", type="primary"):
            st.session_state.expert_trace_df=_full_example_trace()
            st.session_state.expert_dependency_df=_example_dependencies(st.session_state.expert_trace_df)
            st.session_state.expert_branch_df=_example_branch_table()
            st.session_state.expert_group_df=_example_groups(st.session_state.expert_trace_df)
            st.session_state.expert_case_meta.update({
                "case_id":"CASE-DEMO-001",
                "case_title":"3号线设备停机导致交付风险",
                "factory_or_line":"A工厂-3号线",
                "problem_type":"设备异常",
                "business_goal":"判断故障原因、评估订单风险并形成可执行恢复方案",
                "final_result":"修复3号线，同时将高风险订单临时转移到2号线，交付风险解除",
                "result_quality":"成功",
            })
            st.session_state.expert_wizard_step=1
            st.rerun()
        if st.button("从空白案例开始"):
            st.session_state.expert_trace_df=_blank_trace(15)
            st.session_state.expert_dependency_df=pd.DataFrame()
            st.session_state.expert_branch_df=_blank_branch_table()
            st.session_state.expert_group_df=pd.DataFrame()
            st.session_state.expert_wizard_step=1
            st.rerun()

    elif step==1:
        st.markdown("### 第1步：先讲清楚这是一件什么事")
        st.info("把它当成一次事后复盘：发生了什么？当时想解决什么？最后结果怎样？这里不要写具体操作步骤，下一页再写。")
        m=st.session_state.expert_case_meta
        c1,c2=st.columns(2)
        m["dataset_name"]=c1.text_input("数据批次名",m["dataset_name"],help="同一批专家采集的数据建议使用同一个批次名，例如 PlantA-August-ExpertStudy。")
        m["annotator_id"]=c2.text_input("填写人/专家编号",m["annotator_id"],help="可以使用匿名编号，例如 Expert-01，不必填写真实姓名。")
        c1,c2=st.columns(2)
        m["case_id"]=c1.text_input("案例编号",m["case_id"],help="同一批次内不要重复。系统会用它把后面的步骤、分段和这个案例关联起来。")
        m["case_title"]=c2.text_input("案例标题",m["case_title"],placeholder="例：3号线设备停机导致交付风险")
        c1,c2,c3=st.columns(3)
        m["factory_or_line"]=c1.text_input("工厂 / 产线 / 部门",m["factory_or_line"],placeholder="例：A工厂-3号线")
        m["problem_type"]=c2.selectbox("问题类型",["设备异常","质量异常","物料异常","计划异常","交付风险","工艺异常","其他"],index=max(0,["设备异常","质量异常","物料异常","计划异常","交付风险","工艺异常","其他"].index(m["problem_type"]) if m["problem_type"] in ["设备异常","质量异常","物料异常","计划异常","交付风险","工艺异常","其他"] else 0))
        m["result_quality"]=c3.selectbox("最后结果",["成功","部分成功","失败","仍在处理中"],index=["成功","部分成功","失败","仍在处理中"].index(m["result_quality"]) if m["result_quality"] in ["成功","部分成功","失败","仍在处理中"] else 0)
        m["business_goal"]=st.text_area("当时最主要想解决什么？",m["business_goal"],placeholder="例：尽快确认停机原因，同时判断会不会影响当天高优先级订单。",help="写业务目标，不要写技术方案。")
        m["final_result"]=st.text_area("最后实际结果怎样？",m["final_result"],placeholder="例：设备恢复，高风险订单转到2号线生产，最终没有延期。")
        allow=bool(m["case_id"].strip() and m["case_title"].strip() and m["business_goal"].strip())
        _nav(True,"下一步：写工作过程 →",allow)

    elif step==2:
        st.markdown("### 第2步：按时间顺序写“实际做了什么”")
        st.info("**一行只写一个动作。** 不要先替系统总结流程。按照真实发生顺序写：谁做了什么、为什么做、参考了什么、得到了什么。一般完整案例建议 **10–30步**。")
        with st.expander("💡 怎么判断要不要拆成两步？",expanded=False):
            st.write("如果两个动作的执行人不同、目的不同，或者中间产生了一个明确结果后才继续下一件事，通常应该拆成两步。例如“查报警记录并调整排产”应拆成“查报警记录”和“调整排产”。")
        edited=st.data_editor(
            st.session_state.expert_trace_df,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config={
                "步骤序号":st.column_config.NumberColumn("步骤",help="系统最终会自动重新编号。",width="small"),
                "大致时间":st.column_config.TextColumn("时间",help="不用精确到秒，不知道可以留空。",width="small"),
                "执行人":st.column_config.TextColumn("谁做的",help="可以填姓名、岗位或Agent名称。"),
                "角色":st.column_config.TextColumn("角色",help="例：生产主管、维修工程师、计划员、质量Agent。"),
                "做了什么":st.column_config.TextColumn("做了什么 *",help="每行一个动作，用业务语言。例如“查询受影响订单和交期”。",width="large"),
                "为什么做":st.column_config.TextColumn("为什么做",help="这一列很重要：写当时希望通过这个动作回答什么问题。",width="large"),
                "使用的系统/工具":st.column_config.TextColumn("系统/工具",help="MES、ERP、QMS、电话、会议、Excel、现场检查都可以。"),
                "输入/依据":st.column_config.TextColumn("参考了什么",help="例如报警、订单、维修记录、检测数据。"),
                "输出/决定":st.column_config.TextColumn("得到什么",help="例如“发现2个高风险订单”“确认接头松动”。"),
                "工作对象":st.column_config.TextColumn("针对什么",help="例如设备M3、订单O1048、批次B2208。"),
                "是否重试/异常":st.column_config.SelectboxColumn("重试/异常",options=["否","是","不确定"],help="如果这一步是失败后的重试、补救或异常处理，请选择“是”。"),
            },
            key="expert_trace_editor",
        )
        st.session_state.expert_trace_df=edited
        clean=_clean_trace(edited)
        c1,c2,c3=st.columns(3)
        c1.metric("已填写动作",len(clean))
        c2.metric("建议最少",10)
        c3.metric("建议范围","10–30")
        if 0 < len(clean) < 10:
            st.warning("当前案例只有不到10个动作。它可能仍然是有效案例，但很可能只覆盖1–2个微工作流。建议确认是否遗漏了调查、判断影响、协作决策、执行或验证等步骤。")
        if st.button("重新载入18步完整样例"):
            st.session_state.expert_trace_df=_full_example_trace(); st.rerun()
        allow=len(clean)>=3
        if allow and (st.session_state.expert_dependency_df.empty or len(st.session_state.expert_dependency_df)!=len(clean)):
            st.session_state.expert_dependency_df=_default_dependencies(clean)
        if allow and st.session_state.expert_group_df.empty:
            st.session_state.expert_group_df=clean[["步骤序号","做了什么","为什么做"]].copy()
            st.session_state.expert_group_df["小目标编号"]=1
            st.session_state.expert_group_df["小目标名称"]=""
            st.session_state.expert_group_df["这个边界拿不准"]="否"
        _nav(True,"下一步：标记分叉与汇合 →",allow)

    elif step==3:
        trace=_clean_trace(st.session_state.expert_trace_df)
        if st.session_state.expert_dependency_df.empty or len(st.session_state.expert_dependency_df)!=len(trace):
            st.session_state.expert_dependency_df=_default_dependencies(trace)
        st.markdown("### 第3步：有没有并行、分叉或重新汇合？")
        st.info("大多数步骤系统已经按‘上一件做完再做下一件’自动填好。你只需要修改真正存在并行或依赖的地方。核心问题只有一个：**这一步开始前，必须等哪些步骤先完成？**")
        st.caption("例如步骤6需要等步骤3、4、5都完成，就填 `3,4,5`。如果步骤7和步骤10都只依赖步骤6，它们就可以并行，而不是因为时间先后被误认为串行。")
        dep=st.data_editor(st.session_state.expert_dependency_df,use_container_width=True,hide_index=True,
            disabled=["步骤序号","做了什么"],
            column_config={
                "步骤序号":st.column_config.NumberColumn("步骤",width="small"),
                "做了什么":st.column_config.TextColumn("做了什么",width="large"),
                "开始前必须完成哪些步骤":st.column_config.TextColumn("前置步骤",help="填步骤号，多个用逗号分隔。第一步通常留空。",width="medium"),
                "关系备注":st.column_config.TextColumn("备注",help="不确定时可以写‘大概需要等设备和质量结果都回来’。",width="large"),
            },key="expert_dependency_editor")
        st.session_state.expert_dependency_df=dep
        st.markdown("#### 如果存在明显的分叉/汇合，再补充下面这张小表（没有可留空）")
        st.caption("这里记录的是业务含义：是‘同时都做’，还是‘根据情况选一条/多条’。系统会把这些信息转换成 AND / XOR / OR，但你不需要记这些术语。")
        branches=st.data_editor(st.session_state.expert_branch_df,num_rows="dynamic",use_container_width=True,hide_index=True,
            column_config={
                "分叉点步骤":st.column_config.NumberColumn("从哪一步分开",min_value=1,step=1),
                "分支起始步骤":st.column_config.TextColumn("后面哪些步骤分别开始",help="多个步骤号用逗号分隔，例如 7,10"),
                "这些分支是什么关系":st.column_config.SelectboxColumn("关系",options=["同时都要做","根据情况选一条","根据情况做一条或多条"]),
                "汇合步骤":st.column_config.NumberColumn("在哪一步重新汇合",min_value=1,step=1),
                "什么时候可以继续":st.column_config.SelectboxColumn("继续条件",options=["全部完成后","任意一个完成后","达到必要结果后","由负责人判断"]),
                "说明":st.column_config.TextColumn("说明",width="large"),
            },key="expert_branch_editor")
        st.session_state.expert_branch_df=branches
        if st.button("载入示例中的3个并行关系"):
            st.session_state.expert_dependency_df=_example_dependencies(trace); st.session_state.expert_branch_df=_example_branch_table(); st.rerun()
        _nav(True,"下一步：归纳工作单元 →",True)

    elif step==4:
        trace=_clean_trace(st.session_state.expert_trace_df)
        if st.session_state.expert_group_df.empty or len(st.session_state.expert_group_df)!=len(trace):
            st.session_state.expert_group_df=trace[["步骤序号","做了什么","为什么做"]].copy()
            st.session_state.expert_group_df["小目标编号"]=1
            st.session_state.expert_group_df["小目标名称"]=""
            st.session_state.expert_group_df["这个边界拿不准"]="否"
        st.markdown("### 第4步：哪些步骤属于同一个“工作单元”？")
        st.info("这里不是让你画流程图。只需要给连续步骤分组。例如步骤3–6都在“收集原因证据”，就都填小目标编号2、名称“原因证据收集”。当工作目的明显改变时，再开始下一组。")
        st.warning("**边界拿不准是正常的。** 如果某一步既可以算上一段的最后一步，也可以算下一段的第一步，请把“这个边界拿不准”选为“是”。这对我们的研究非常重要，不需要强行给唯一答案。")
        g=st.data_editor(
            st.session_state.expert_group_df,
            use_container_width=True,hide_index=True,
            disabled=["步骤序号","做了什么","为什么做"],
            column_config={
                "步骤序号":st.column_config.NumberColumn("步骤",width="small"),
                "做了什么":st.column_config.TextColumn("做了什么",width="large"),
                "为什么做":st.column_config.TextColumn("为什么做",width="large"),
                "小目标编号":st.column_config.NumberColumn("小目标编号 *",min_value=1,step=1,help="属于同一个工作单元就填相同编号，不要求在时间线上连续。",width="small"),
                "小目标名称":st.column_config.TextColumn("这个小目标叫什么 *",help="用你们日常业务语言，例如“原因证据收集”“生产影响评估”。",width="medium"),
                "这个边界拿不准":st.column_config.SelectboxColumn("边界拿不准？",options=["否","是","不确定"],help="通常只需在新小目标开始的第一步考虑这个问题。"),
            },key="expert_group_editor")
        st.session_state.expert_group_df=g
        named=g["小目标名称"].fillna("").astype(str).str.strip()
        n_groups=g.loc[named!="","小目标编号"].nunique()
        st.metric("当前分成的小目标",int(n_groups))
        if n_groups<=1:
            st.warning("目前只有1个小目标。对于完整业务案例，通常会有3–7个小目标。请确认这个案例是不是仍然太短，或是否还没有完成分段。")
        elif n_groups>10:
            st.warning("当前分段超过10个，可能切得太碎。请问自己：相邻两段是不是其实在解决同一个小问题？")
        allow=bool((named!="").all() and g["小目标编号"].notna().all())
        if allow:
            st.session_state.expert_reuse_df=_derive_reuse_df(g) if st.session_state.expert_reuse_df.empty else st.session_state.expert_reuse_df
        _nav(True,"下一步：判断哪些套路可复用 →",allow)

    elif step==5:
        st.markdown("### 第5步：这些“工作单元”以后还能不能重复使用？")
        st.info("这里不要求你判断算法对不对。只凭制造经验回答：下次遇到类似问题，这套做法还会不会用？即使换了人、换了Agent、换了MES/QMS，只要工作目的和核心做法仍一样，也可以认为是可复用。")
        current=_derive_reuse_df(st.session_state.expert_group_df)
        # Preserve edited values by name when possible
        if not st.session_state.expert_reuse_df.empty:
            old=st.session_state.expert_reuse_df.set_index("小目标名称").to_dict("index")
            for i,r in current.iterrows():
                if r["小目标名称"] in old:
                    for c,v in old[r["小目标名称"]].items(): current.at[i,c]=v
        r=st.data_editor(current,use_container_width=True,hide_index=True,
            disabled=["小目标名称"],
            column_config={
                "小目标名称":st.column_config.TextColumn("小目标",width="medium"),
                "以后类似问题还会用到吗":st.column_config.SelectboxColumn("下次还会用？",options=["是","可能","否","不确定"],help="不一定要步骤完全一样，只要这套处理思路仍值得复用。"),
                "换个人/Agent还能用吗":st.column_config.SelectboxColumn("换人还能用？",options=["是","大致可以","否","不确定"]),
                "换系统/工具还能用吗":st.column_config.SelectboxColumn("换工具还能用？",options=["是","大致可以","否","不确定"]),
                "复用价值(1-5)":st.column_config.NumberColumn("复用价值",min_value=1,max_value=5,step=1,help="1=几乎只适用于本案例；5=在很多类似问题中都值得作为标准套路。"),
                "补充说明":st.column_config.TextColumn("为什么",width="large"),
            },key="expert_reuse_editor")
        st.session_state.expert_reuse_df=r
        _nav(True,"下一步：检查并保存 →",True)

    elif step==6:
        meta=st.session_state.expert_case_meta
        trace=_clean_trace(st.session_state.expert_trace_df)
        groups=st.session_state.expert_group_df
        canonical, branch_records=_to_canonical(meta,trace,groups,st.session_state.expert_dependency_df,st.session_state.expert_branch_df)
        st.markdown("### 第6步：检查，然后直接保存到实验系统")
        c1,c2,c3,c4=st.columns(4)
        c1.metric("完整案例",1)
        c2.metric("工作动作",len(trace))
        c3.metric("小目标",groups["小目标编号"].nunique())
        c4.metric("可复用候选",sum(st.session_state.expert_reuse_df["以后类似问题还会用到吗"].isin(["是","可能"])) if not st.session_state.expert_reuse_df.empty else 0)
        st.markdown(f"**{meta['case_id']} — {meta['case_title']}**")
        st.caption(f"目标：{meta['business_goal']}  ·  结果：{meta['final_result']}")
        with st.expander("查看系统将要导入的标准 Work Trace",expanded=False):
            st.dataframe(canonical,use_container_width=True,hide_index=True)
        with st.expander("查看分叉/汇合与专家工作单元",expanded=False):
            st.dataframe(st.session_state.expert_dependency_df,use_container_width=True,hide_index=True)
            if not branch_records.empty: st.dataframe(branch_records,use_container_width=True,hide_index=True)
            st.dataframe(st.session_state.expert_group_df,use_container_width=True,hide_index=True)
        with st.expander("查看复用性评价",expanded=False):
            st.dataframe(st.session_state.expert_reuse_df,use_container_width=True,hide_index=True)

        package={
            "metadata":meta,
            "events":canonical.to_dict("records"),
            "expert_segments":groups.to_dict("records"),
            "dependencies":st.session_state.expert_dependency_df.to_dict("records"),
            "control_groups":branch_records.to_dict("records"),
            "reuse_review":st.session_state.expert_reuse_df.to_dict("records"),
            "schema_version":"expert-wizard-v2-dag",
        }
        st.download_button("⬇ 下载本案例 JSON 备份",json.dumps(package,ensure_ascii=False,indent=2).encode("utf-8"),file_name=f"{meta['case_id']}_expert_package.json",mime="application/json")
        c1,c2=st.columns([1.4,1])
        if c1.button("✅ 保存到实验系统数据集",type="primary",use_container_width=True):
            name=meta["dataset_name"]
            ds=st.session_state.expert_datasets.setdefault(name,{"cases":{},"schema_version":"expert-wizard-v2-dag"})
            ds["cases"][meta["case_id"]]=package
            st.success(f"已保存到数据集 **{name}**。当前共有 {len(ds['cases'])} 个专家案例。")
        if c2.button("＋ 继续填写下一个案例",use_container_width=True):
            batch=meta["dataset_name"]; annotator=meta["annotator_id"]
            st.session_state.expert_case_meta={
                "dataset_name":batch,"annotator_id":annotator,
                "case_id":f"CASE-{uuid.uuid4().hex[:6].upper()}","case_title":"","factory_or_line":"","problem_type":"设备异常","business_goal":"","final_result":"","result_quality":"成功","case_date":str(datetime.now().date())}
            st.session_state.expert_trace_df=_blank_trace(15)
            st.session_state.expert_dependency_df=pd.DataFrame(); st.session_state.expert_branch_df=_blank_branch_table()
            st.session_state.expert_group_df=pd.DataFrame(); st.session_state.expert_reuse_df=pd.DataFrame(); st.session_state.expert_wizard_step=1
            st.rerun()
        st.markdown("---")
        st.markdown("#### 已在当前会话保存的数据集")
        if st.session_state.expert_datasets:
            rows=[]
            for n,d in st.session_state.expert_datasets.items():
                events=sum(len(c["events"]) for c in d["cases"].values())
                rows.append({"数据集":n,"案例数":len(d["cases"]),"事件数":events})
            st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
        else:
            st.caption("还没有保存的专家数据集。")
        _nav(True,"完成",False)

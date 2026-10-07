# Phase 3-A HTML 原型实现指南

本文档说明如何更新现有的 `dag-sla-evaluation-redesign.html` 原型，添加 Phase 3-A 新维度的 UI 展示。

## 数据结构扩展

### 1. nodeData 结构的扩展

在现有的节点数据结构基础上，添加以下可选字段：

```javascript
const nodeData = {
    n5: {
        name: 'Release 批准',  // 新节点示例
        type: 'Approval',
        role: '设备/工艺/质量工程师',
        desc: '产品 release 的多角色批准流程',
        
        // Phase 1/2: 现有字段
        hasSLA: true,
        sla: { /* ... */ },
        hasEval: true,
        eval: [ /* ... */ ],
        
        // Phase 3-A: 新增字段
        
        // 1. 权限分级和多层签字
        hasApprovalMatrix: true,
        approvalMatrix: [
            {
                type: 'equipment_release',
                roles: ['设备工程师'],
                sequence: 'sequential',
                criteria: '设备状态正常，无报警',
                escalation: '生产主管'
            },
            {
                type: 'process_release',
                roles: ['工艺工程师'],
                sequence: 'sequential',
                criteria: '工艺参数在范围，刀具寿命充足',
                escalation: '生产主管'
            },
            {
                type: 'quality_release',
                roles: ['质量工程师'],
                sequence: 'sequential',
                criteria: '首件检验合格，性能符合要求',
                escalation: '生产副总'
            }
        ],
        
        // 2. 聚合和趋势条件（在 eval 中添加 aggregation 字段）
        // eval: [
        //     {
        //         id: 'temperature_trend',
        //         name: '设备温度趋势',
        //         hasAggregation: true,
        //         aggregation: {
        //             method: 'trend',      // trend | pattern | continuous | statistical
        //             windowSize: 7,
        //             operator: 'all_increasing',
        //             threshold: '3°C',
        //             minSamples: 5,
        //             description: '过去 7 个测量点持续上升，每次 > 3°C'
        //         }
        //     }
        // ],
    },
    
    n6: {
        name: '临时 Bypass',
        type: 'Activity',
        role: '设备/质量工程师',
        desc: '设备故障期间的临时检测 bypass',
        
        // 3. 临时措施生命周期
        hasRetry: true,
        retry: {
            enabled: true,
            isTemporary: true,
            maxRetries: 1,
            expiration: {
                duration: 'PT72H',
                lotCount: 3,
                trigger: 'duration_or_count',
                description: '72 小时或 3 个 lot，先达到任一条件失效'
            },
            revocation: {
                type: 'reoccurrence',
                days: 30,
                description: '30 天内同一故障再次出现则自动失效'
            },
            escalationOnRepeat: {
                enabled: true,
                trigger: 'same_condition',
                action: 'create_capa'
            }
        }
    },
    
    n7: {
        name: '产品隔离',
        type: 'Activity',
        role: '质量工程师',
        desc: '根据根因隔离受影响的产品',
        
        // 4. 多维追溯和隔离
        hasContainment: true,
        containment: {
            dimension: 'equipment_id',  // equipment_id | lot_id | material_id | line_id
            rule: 'all_products_on_same_equipment',
            affectedProducts: 847,
            description: '隔离所有在此设备上加工的产品'
        }
    }
};
```

## UI 组件实现

### 1. 权限和签字小节（新增）

在 HTML 模板的详情面板中添加新小节：

```html
<div id="approvalSection" class="panel-section" style="display: none;">
    <div class="section-title">权限和签字 🔐</div>
    <div id="approvalContent"></div>
</div>
```

对应的 JavaScript 渲染逻辑：

```javascript
// 权限部分渲染
if (data.hasApprovalMatrix) {
    document.getElementById('approvalSection').style.display = 'block';
    const approvalContent = document.getElementById('approvalContent');
    
    let html = '<div class="approval-matrix">';
    data.approvalMatrix.forEach((approval, index) => {
        html += `
            <div class="approval-item">
                <div class="approval-step">
                    <span class="step-number">${index + 1}</span>
                    <span class="approval-type">${approval.type}</span>
                </div>
                <div class="approval-detail">
                    <strong>角色：</strong> ${approval.roles.join(', ')}<br>
                    <strong>顺序：</strong> ${approval.sequence === 'sequential' ? '顺序批准' : '并行批准'}<br>
                    <strong>标准：</strong> ${approval.criteria}<br>
                    <strong>升级：</strong> ${approval.escalation}
                </div>
            </div>
        `;
    });
    html += '</div>';
    approvalContent.innerHTML = html;
} else {
    document.getElementById('approvalSection').style.display = 'none';
}
```

### 2. 聚合条件的可视化

在评估规则卡片中添加聚合条件支持：

```html
<div class="evaluation-item">
    <!-- 现有内容 -->
    
    <!-- 新增聚合条件部分 -->
    <div id="aggregationInfo-${criterion.id}" class="aggregation-info" style="display: none;">
        <div class="subsection-title">📈 聚合条件</div>
        <div class="aggregation-detail">
            <div><strong>方法：</strong> <span id="aggMethod"></span></div>
            <div><strong>窗口：</strong> <span id="aggWindow"></span> 个数据点</div>
            <div><strong>判断：</strong> <span id="aggOperator"></span></div>
            <div class="mini-chart">
                <!-- 简化的趋势图表 -->
                <svg width="100%" height="60">
                    <polyline points="0,50 10,40 20,30 30,35 40,25 50,15 60,5" 
                              fill="none" stroke="#3B82F6" stroke-width="2"/>
                </svg>
            </div>
        </div>
    </div>
</div>
```

对应的 JavaScript 逻辑：

```javascript
if (criterion.hasAggregation) {
    const aggInfo = criterion.aggregation;
    document.getElementById(`aggregationInfo-${criterion.id}`).style.display = 'block';
    document.getElementById('aggMethod').textContent = getAggregationMethodLabel(aggInfo.method);
    document.getElementById('aggWindow').textContent = aggInfo.windowSize;
    document.getElementById('aggOperator').textContent = aggInfo.description;
}
```

### 3. 临时措施信息小节（新增）

```html
<div id="temporarySection" class="panel-section" style="display: none;">
    <div class="section-title">临时措施信息 ⏳</div>
    <div id="temporaryContent"></div>
</div>
```

JavaScript 实现：

```javascript
if (data.hasRetry && data.retry.isTemporary) {
    document.getElementById('temporarySection').style.display = 'block';
    const tempContent = document.getElementById('temporaryContent');
    
    const retry = data.retry;
    const expirationInfo = retry.expiration;
    
    tempContent.innerHTML = `
        <div class="temporary-info">
            <div class="info-item">
                <strong>状态：</strong> 
                <span class="badge">临时措施</span>
            </div>
            <div class="info-item">
                <strong>有效期：</strong> 
                ${expirationInfo.duration} ${expirationInfo.trigger === 'duration_or_count' ? 'OR' : 'AND'} 
                ${expirationInfo.lotCount} 个 lot
            </div>
            <div class="info-item">
                <strong>失效条件：</strong> 
                ${retry.revocation.description}
            </div>
            <div class="info-item">
                <strong>重复升级：</strong> 
                ${retry.escalationOnRepeat.enabled ? 
                    `${retry.escalationOnRepeat.action} (${retry.escalationOnRepeat.trigger})` : 
                    '禁用'}
            </div>
            
            <div class="countdown-display">
                <div class="countdown-row">
                    <span>已使用时长：</span>
                    <progress value="33" max="100"></progress>
                    <span>24h / 72h</span>
                </div>
                <div class="countdown-row">
                    <span>已加工产品：</span>
                    <progress value="33" max="100"></progress>
                    <span>1 / 3 lot</span>
                </div>
            </div>
        </div>
    `;
}
```

### 4. 隔离范围小节（新增）

```html
<div id="containmentSection" class="panel-section" style="display: none;">
    <div class="section-title">隔离和追溯 📍</div>
    <div id="containmentContent"></div>
</div>
```

JavaScript 实现：

```javascript
if (data.hasContainment) {
    document.getElementById('containmentSection').style.display = 'block';
    const containContent = document.getElementById('containmentContent');
    
    const containment = data.containment;
    containContent.innerHTML = `
        <div class="containment-info">
            <div class="info-item">
                <strong>隔离维度：</strong> ${getDimensionLabel(containment.dimension)}
            </div>
            <div class="info-item">
                <strong>隔离规则：</strong> ${containment.rule}
            </div>
            <div class="info-item">
                <strong>受影响产品数：</strong> 
                <span class="highlight">${containment.affectedProducts} 件</span>
            </div>
            <div class="info-item">
                <strong>说明：</strong> ${containment.description}
            </div>
        </div>
    `;
}
```

## CSS 样式扩展

添加以下 CSS 类以支持新的 UI 部分：

```css
/* 权限矩阵样式 */
.approval-matrix {
    display: flex;
    flex-direction: column;
    gap: 10px;
}

.approval-item {
    padding: 8px;
    border: 1px solid #E5E7EB;
    border-radius: 4px;
    background: #FAFAFA;
}

.approval-step {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 6px;
    font-size: 11px;
    font-weight: 600;
    color: #1F2937;
}

.step-number {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 18px;
    height: 18px;
    border-radius: 50%;
    background: #3B82F6;
    color: white;
    font-size: 10px;
}

/* 聚合条件样式 */
.aggregation-info {
    margin-top: 8px;
    padding: 8px;
    background: #F0F4F8;
    border-left: 3px solid #3B82F6;
    border-radius: 4px;
}

.subsection-title {
    font-size: 10px;
    font-weight: 600;
    color: #3B82F6;
    margin-bottom: 6px;
}

.mini-chart {
    margin-top: 6px;
    padding: 6px 0;
}

/* 临时措施样式 */
.temporary-info {
    padding: 8px;
    background: #FEF3C7;
    border-left: 3px solid #F59E0B;
    border-radius: 4px;
}

.countdown-display {
    margin-top: 8px;
    display: flex;
    flex-direction: column;
    gap: 6px;
}

.countdown-row {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 11px;
}

progress {
    flex: 1;
    height: 6px;
    border-radius: 3px;
}

/* 隔离范围样式 */
.containment-info {
    padding: 8px;
    background: #F0F4F8;
    border-left: 3px solid #10B981;
    border-radius: 4px;
}

.highlight {
    color: #DC2626;
    font-weight: 600;
}

.badge {
    display: inline-block;
    padding: 2px 6px;
    background: #FEE2E2;
    color: #DC2626;
    border-radius: 3px;
    font-size: 10px;
    font-weight: 600;
}
```

## DAG 图层的节点扩展

在 SVG 渲染中添加 Phase 3-A 维度的图标：

```javascript
// 在节点内添加维度指示图标
function renderNodeDimensionIndicators(nodeData, yOffset) {
    let indicators = [];
    
    if (nodeData.hasApprovalMatrix) {
        indicators.push({ icon: '🔐', label: '权限', x: 0 });
    }
    
    if (nodeData.hasEval && nodeData.eval.some(e => e.hasAggregation)) {
        indicators.push({ icon: '📊', label: '趋势', x: 20 });
    }
    
    if (nodeData.hasRetry && nodeData.retry.isTemporary) {
        indicators.push({ icon: '⏳', label: '临时', x: 40 });
    }
    
    if (nodeData.hasContainment) {
        indicators.push({ icon: '📍', label: '隔离', x: 60 });
    }
    
    return indicators;
    // 在 SVG 中渲染这些图标
}
```

## 实现步骤

1. **数据结构扩展**（1-2h）
   - 在 `nodeData` 中添加新的节点
   - 扩展现有节点的数据结构，支持新字段

2. **HTML 模板扩展**（1-2h）
   - 在详情面板中添加新的小节
   - 添加相应的容器和 ID

3. **JavaScript 逻辑**（2-3h）
   - 实现新小节的渲染逻辑
   - 添加交互事件处理（展开/折叠、倒计时更新）
   - DAG 图层的图标渲染

4. **CSS 样式**（1h）
   - 添加新组件的样式
   - 确保响应式设计

5. **测试和调试**（1-2h）
   - 验证所有新维度的显示
   - 测试交互功能
   - 检查移动端响应式

## 预期工作量

- 总计：8-12 小时
- 可在 2-3 天内完成

## 参考文件

- `UI-DESIGN-SLA-EVALUATION.md` - UI 规范
- `PHASE3A_EXAMPLES.md` - 数据示例
- 当前的 `dag-sla-evaluation-redesign.html` 原型

## 关键设计原则

1. **渐进呈现**：主图显示摘要，详情留给面板
2. **颜色编码**：不同维度用不同的颜色和图标区分
3. **交互一致性**：保持现有的"点击查看详情"模式
4. **采集友好**：字段名称与采集提示词对齐

---

**文档版本**：1.0  
**日期**：2026-10-07  
**状态**：实现指南（可直接用于编码）

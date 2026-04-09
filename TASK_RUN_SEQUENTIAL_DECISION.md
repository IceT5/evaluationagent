# TASK: 决定run_sequential修改方案

> 创建时间：2026-04-07
> 状态：待决策
> 优先级：高
> 阻塞：删除_run_sequential()的实施

## 背景

已完成Trace增强和修复trace调用遗漏，现在需要决定如何处理_run_sequential()方法。

## 当前状态

**_run_sequential()存在于：**
- `src/evaluator/agents/cicd/orchestrator.py`
- `src/evaluator/agents/intelligence_pipeline.py`

**用户已决策：**
- ✅ Retry模式改用LangGraph
- ✅ 移除fallback，LangGraph不可用时直接报错
- ✅ 希望完全删除_run_sequential()

## 待决策问题

### 问题1：Supplement模式的触发频率

**关键信息：**
- Supplement模式由用户选择（ReportFixAgent._ask_user_choice）
- 用户发现问题后选择"补充模式"
- 会重复执行extract、plan、invoke

**需要回答：**
- [ ] Supplement模式是高频还是低频？
- [ ] 如果低频，可以接受方案C的重复执行

---

### 问题2：对性能的要求

**方案C的影响：**
- extract：~1秒（文件读取）
- plan：~1秒（生成prompt）
- invoke：**10-30秒**（LLM调用）

**需要回答：**
- [ ] 对性能的要求是极致还是一般？
- [ ] 是否可以接受额外的LLM调用？

---

### 问题3：retry模式的语义

**当前实现：**
- ❌ 没有重新extract
- ❌ 没有重新plan
- ⚠️ 只重新invoke

**需要回答：**
- [ ] retry模式应该是"完全重做"还是"部分重做"？
- [ ] 当前实现是否符合预期？

---

### 问题4：架构一致性vs实现成本

**权衡：**
- 方案B：架构完美，~40行新增代码
- 方案C：最简单，但有重复执行

**需要回答：**
- [ ] 更看重架构一致性还是快速实现？

---

## 三个方案对比

### 方案A：混合执行（不推荐❌）

**实现：** Supplement手动调用，其他用LangGraph

**弊端：**
- 执行方式不统一
- 代码重复
- 违反设计理念
- Trace不完整
- 缺少高级特性

---

### 方案B：条件入口点（推荐✅）

**实现：** LangGraph条件入口点，supplement从retry开始

**优点：**
- ✅ 执行方式统一
- ✅ 无代码重复
- ✅ Trace完整
- ✅ 支持所有特性

**缺点：**
- ⚠️ 实现难度中等（~40行）
- ⚠️ 需处理前置数据依赖

**改动量：** 净减少28行代码

---

### 方案C：接受重复执行（可选⚠️）

**实现：** 所有模式统一用LangGraph，接受supplement重复执行

**优点：**
- ✅ 最简单
- ✅ 执行方式统一
- ✅ Trace完整

**缺点：**
- ❌ Supplement模式重复执行extract/plan/invoke
- ❌ 浪费资源（主要影响：额外LLM调用）

---

## 决策矩阵

| 维度 | 方案A | 方案B | 方案C |
|------|------|------|------|
| 执行统一性 | ❌ | ✅ | ✅ |
| 代码重复 | ❌ | ✅ | ✅ |
| Trace完整性 | ⚠️ | ✅ | ✅ |
| 实现难度 | ✅ | ⚠️ | ✅ |
| 性能影响 | ✅ | ✅ | ❌ |
| 维护成本 | ❌ | ✅ | ✅ |

---

## 决策流程

**Step 1：回答4个关键问题**
- Supplement频率？
- 性能要求？
- retry语义？
- 架构vs成本？

**Step 2：根据回答选择方案**
- 追求架构完美 → 方案B
- 快速实现且supplement低频 → 方案C
- 不选方案A

**Step 3：实施选定方案**
- 修改代码
- 运行测试
- 验证trace
- Git提交

---

## 实施后的影响

**删除_run_sequential()后：**
- ✅ 所有模式统一使用LangGraph
- ✅ 代码简化（减少~28行）
- ✅ 维护成本降低
- ✅ Trace增强完全生效

---

## 相关文件

**需要修改：**
- `src/evaluator/agents/cicd/orchestrator.py`
- `src/evaluator/agents/intelligence_pipeline.py`

**相关参考：**
- `src/evaluator/core/graphs/main_graph.py` - 用户选择逻辑
- `src/evaluator/agents/report_fix_agent.py` - 用户选择入口
- `AGENTS.md` - Trace统一要求

---

## Git历史

**前置提交：**
- `e1334b4` - feat: 增强LangSmith Trace支持
- `9fb95c7` - fix: 修复trace调用遗漏

---

## 下一步

**在新session中：**
1. 回答4个关键问题
2. 选择方案
3. 开始实施

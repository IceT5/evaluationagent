# TASK: 决定runnable.py的处理方式

> 创建时间：2026-04-07
> 状态：待决策
> 优先级：中
> 依赖：无

## 背景

runnable.py定义了AnalyzeRunnable和CompareRunnable，提供Runnable接口，但当前未被使用。需要决定如何处理。

## 当前状态

**文件：** `src/evaluator/core/runnable.py`（131行）

**定义内容：**
- AnalyzeRunnable类
- CompareRunnable类
- analyze_runnable实例
- compare_runnable实例

**特性：**
- ✅ 支持invoke、ainvoke、pipe等Runnable接口
- ✅ 支持LangSmith trace
- ✅ 已在core/__init__.py导出
- ❌ **未被实际使用**

---

## 使用情况分析

### 当前执行路径

**CLI：**
```python
# cli/app.py
final_state = self.graph.invoke(initial_state)
```
- 直接使用graph.invoke()
- 不使用runnable

**analyze_project()：**
```python
# core/analyze.py
graph = create_main_graph()
final_state = graph.invoke(initial_state)
```
- 函数式接口
- 内部使用graph.invoke()

**compare_projects()：**
```python
# core/compare.py
graph = create_main_graph()
final_state = graph.invoke(initial_state)
```
- 函数式接口
- 内部使用graph.invoke()

**runnable：**
```python
# core/runnable.py
analyze_runnable.invoke(input_data)
  └─ _analyze_project(**input_data)
       └─ graph.invoke(initial_state)
```
- Runnable接口
- 封装了analyze_project()

---

## 设计意图

runnable.py的目标用途：

### 1. Python API

```python
from evaluator.core import analyze_runnable

result = analyze_runnable.invoke({
    "path": "/path/to/project",
    "display_name": "My Project"
})
```

### 2. Web API（FastAPI）

```python
from fastapi import FastAPI
from evaluator.core import analyze_runnable

app = FastAPI()

@app.post("/analyze")
async def analyze(request: AnalyzeRequest):
    return analyze_runnable.invoke(request.dict())
```

### 3. 管道组合

```python
from evaluator.core import analyze_runnable, compare_runnable

# 先分析，再对比
pipeline = analyze_runnable.pipe(compare_runnable)
result = pipeline.invoke({...})
```

### 4. LangChain集成

```python
from langchain_core.runnables import RunnableParallel

# 并行分析多个项目
parallel = RunnableParallel(
    project_a=analyze_runnable,
    project_b=analyze_runnable,
)
```

---

## 待决策问题

### 问题1：是否需要统一到runnable？

**当前情况：**
- CLI不使用runnable
- analyze_project()和compare_projects()是函数式接口
- runnable提供了Runnable接口但未使用

**需要回答：**
- [ ] 是否需要让CLI使用runnable？
- [ ] 还是保留当前架构？

---

### 问题2：runnable的定位是什么？

**定位A：统一入口**
- 所有调用都通过runnable
- analyze_project()和compare_projects()改为内部函数
- 优点：接口统一
- 缺点：需要重构CLI

**定位B：可选的高级接口**
- CLI继续用graph.invoke()
- runnable用于需要Runnable接口的场景
- 优点：不影响现有代码
- 缺点：存在两套接口

**定位C：未来扩展**
- 当前保留但不使用
- 未来有Web API需求时再启用
- 优点：无需当前投入
- 缺点：代码闲置

---

### 问题3：如果统一，需要多大改动？

**CLI改用runnable：**

**需要修改：**
- `cli/app.py`：_handle_analyze()和_handle_compare()
- 改动量：~20行

**影响：**
- ⚠️ 需要适配initial_state结构
- ⚠️ 需要处理返回值格式
- ⚠️ 可能影响错误处理

---

## 决策方案

### 方案A：统一入口

**实现：**
- CLI改用analyze_runnable和compare_runnable
- analyze_project()和compare_projects()改为内部函数

**优点：**
- ✅ 接口统一
- ✅ 所有调用都有Runnable接口

**缺点：**
- ⚠️ 需要重构CLI（~20行）
- ⚠️ 需要适配接口

**推荐度：⚠️ 可选**

---

### 方案B：双接口并存

**实现：**
- CLI继续用graph.invoke()
- runnable用于Python API、Web API等场景
- 两者并存，各有用途

**优点：**
- ✅ 不影响现有代码
- ✅ 灵活性高
- ✅ 为不同场景提供合适接口

**缺点：**
- ⚠️ 存在两套接口
- ⚠️ 需要文档说明

**推荐度：✅ 推荐**

---

### 方案C：未来扩展

**实现：**
- 当前保留runnable.py但不使用
- 添加文档说明用途
- 未来有需求时再启用

**优点：**
- ✅ 无需当前投入
- ✅ 不影响现有代码
- ✅ 为未来留有余地

**缺点：**
- ⚠️ 代码闲置
- ⚠️ 可能被遗忘

**推荐度：✅ 推荐**

---

### 方案D：删除

**实现：**
- 删除runnable.py
- 删除相关导出

**优点：**
- ✅ 减少代码量

**缺点：**
- ❌ 失去未来扩展能力
- ❌ 失去Runnable接口
- ❌ 影响Web API等未来需求

**推荐度：❌ 不推荐**

---

## 决策矩阵

| 方案 | CLI改动 | 架构统一性 | 维护成本 | 未来扩展性 | 推荐度 |
|------|---------|----------|---------|-----------|--------|
| **A: 统一入口** | ⚠️ 中等 | ✅ 好 | ✅ 低 | ✅ 好 | ⚠️ 可选 |
| **B: 双接口** | ✅ 无需 | ⚠️ 中等 | ⚠️ 中等 | ✅ 好 | ✅ 推荐 |
| **C: 未来扩展** | ✅ 无需 | ⚠️ 中等 | ✅ 低 | ⚠️ 中等 | ✅ 推荐 |
| **D: 删除** | ✅ 无需 | ❌ 差 | ✅ 低 | ❌ 差 | ❌ 不推荐 |

---

## 建议

**推荐：方案B或C**

**理由：**
1. ✅ runnable.py代码质量好，设计合理
2. ✅ 提供了有价值的Runnable接口
3. ✅ 不影响现有CLI功能
4. ✅ 为未来扩展留有余地

**不推荐：**
- ❌ 方案A：需要重构CLI，收益不大
- ❌ 方案D：失去未来扩展能力

---

## 实施步骤

### 如果选择方案B或C：

1. **添加文档说明**
   - 在runnable.py添加详细注释
   - 在AGENTS.md说明用途

2. **添加使用示例**
   - 创建examples/runnable_usage.py
   - 展示Python API用法

3. **保留代码**
   - 不做修改
   - 保持当前状态

### 如果选择方案A：

1. **修改CLI**
   - cli/app.py改用runnable

2. **调整接口**
   - 适配initial_state结构
   - 处理返回值格式

3. **测试验证**
   - 运行测试
   - 验证功能

---

## 相关文件

**核心文件：**
- `src/evaluator/core/runnable.py` - runnable定义
- `src/evaluator/core/__init__.py` - 导出
- `src/evaluator/core/analyze.py` - analyze_project()
- `src/evaluator/core/compare.py` - compare_projects()

**相关文件：**
- `src/evaluator/cli/app.py` - CLI实现
- `AGENTS.md` - 需要更新说明

---

## 下一步

**在新session中：**
1. 决定采用哪个方案
2. 实施选定方案
3. 更新文档
4. Git提交

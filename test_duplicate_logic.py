"""验证当前逻辑是否能正确处理重复workflow详情块"""
import re

def extract_workflows_new_method(content: str):
    """使用新的提取逻辑"""
    # 直接提取所有 #### workflow.yml 详情块
    wf_pattern = r'(####\s+(?:\d+\.?\d*\s+)?([\w\.-]+\.yml).*?)(?=####\s+|##\s+|$)'
    wf_matches = re.findall(wf_pattern, content, re.DOTALL)

    # 按 workflow 名称去重
    seen_workflows = {}
    for wf_full, wf_name in wf_matches:
        if wf_name and ('.yml' in wf_name or '.yaml' in wf_name):
            if wf_name not in seen_workflows:
                seen_workflows[wf_name] = wf_full.strip()

    return seen_workflows

# 读取部分llm_response.md内容来测试
sample_content = """## 阶段详情

### 工作流详情

#### 1.1 generated-linux-s390x-binary-manywheel-nightly.yml

**目的**: 为 Linux s390x 架构生成多个 Python 版本的 manywheel 二进制包

**触发条件**:
```yaml
on:
  push:
  workflow_dispatch:
```

**包含的Job**（共22个）:
| 序号 | Job名称 | 运行环境 | 目的 |
|-----|---------|---------|------|

#### 2.1 构建任务组（8个并行构建Job）

**目的**: 为 s390x 架构构建不同 Python 版本的 PyTorch manywheel 包

#### 3.1 generated-linux-s390x-binary-manywheel-nightly.yml

**目的**: 这是同一个workflow的另一份详情（来自另一个batch）
"""

workflows = extract_workflows_new_method(sample_content)

print("提取到的workflows:")
for name, content in workflows.items():
    print(f"  {name}")
    print(f"    内容预览: {content[:100]}...")
    print()

print(f"总共提取到 {len(workflows)} 个workflow")
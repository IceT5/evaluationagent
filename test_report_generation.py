#!/usr/bin/env python3
"""测试报告生成逻辑"""
import json
import re
import sys
sys.path.insert(0, r'F:\code\evaluationagent\src')

from evaluator.agents.cicd.stage_organization_agent import StageOrganizationAgent

def main():
    data_dir = r'F:\code\evaluationagent\dist\eval-agent\data\projects\cccl\v1_20260324_200130'
    
    print("=" * 60)
    print("测试报告生成逻辑")
    print("=" * 60)
    
    # 加载数据
    with open(f'{data_dir}/llm_response.md', 'r', encoding='utf-8') as f:
        llm_response = f.read()
    
    with open(f'{data_dir}/architecture.json', 'r', encoding='utf-8') as f:
        architecture_json = json.load(f)
    
    with open(f'{data_dir}/ci_data.json', 'r', encoding='utf-8') as f:
        ci_data = json.load(f)
    
    print(f"\n1. 数据加载完成:")
    print(f"   - llm_response.md: {len(llm_response)} 字符")
    print(f"   - architecture.json: {len(architecture_json.get('layers', []))} 层")
    print(f"   - ci_data.json: {len(ci_data.get('workflows', {}))} 个工作流")
    
    # 创建 Agent
    agent = StageOrganizationAgent()
    
    # 测试 _extract_all_workflow_details
    print(f"\n2. 测试 _extract_all_workflow_details():")
    workflow_details = agent._extract_all_workflow_details(llm_response)
    print(f"   - 提取到 {len(workflow_details)} 个工作流详细描述")
    
    # 统计 Job 表格和步骤详情
    job_table_count = 0
    step_detail_count = 0
    for wf_name, content in workflow_details.items():
        if '| 序号 |' in content:
            job_table_count += 1
        step_detail_count += len(re.findall(r'步骤\d+:', content))
    
    print(f"   - 包含 Job 表格: {job_table_count} 个")
    print(f"   - 包含步骤详情: {step_detail_count} 个")
    
    # 测试 _get_full_workflow_name
    print(f"\n3. 测试 _get_full_workflow_name():")
    test_labels = ['ci-workflow-pull-request', 'build-rapids', 'two-stage-group-linux', 
                   'release-create-new', 'backport-prs', 'workflow-dispatch-two-stage-windows']
    for label in test_labels:
        full_name = agent._get_full_workflow_name(label, ci_data)
        print(f"   - '{label}' -> '{full_name}'")
    
    # 测试 _reorganize_by_architecture
    print(f"\n4. 测试 _reorganize_by_architecture():")
    reorganized = agent._reorganize_by_architecture(llm_response, architecture_json, ci_data)
    print(f"   - 重组后长度: {len(reorganized)} 字符")
    
    # 统计重组后的内容
    reorganized_job_tables = len(re.findall(r'\| 序号 \|', reorganized))
    reorganized_step_details = len(re.findall(r'步骤\d+:', reorganized))
    reorganized_workflows = len(re.findall(r'####\s+\d+\.\d+\s+[\w-]+\.yml', reorganized))
    
    print(f"   - 工作流详细描述: {reorganized_workflows} 个")
    print(f"   - Job 表格: {reorganized_job_tables} 个")
    print(f"   - 步骤详情: {reorganized_step_details} 个")
    
    # 保存重组后的报告
    output_path = f'{data_dir}/CI_ARCHITECTURE_test.md'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(reorganized)
    print(f"\n5. 重组后的报告已保存到: {output_path}")
    
    # 对比原始报告
    print(f"\n6. 对比分析:")
    with open(f'{data_dir}/CI_ARCHITECTURE.md', 'r', encoding='utf-8') as f:
        original_report = f.read()
    
    original_job_tables = len(re.findall(r'\| 序号 \|', original_report))
    original_step_details = len(re.findall(r'步骤\d+:', original_report))
    original_workflows = len(re.findall(r'####\s+\d+\.\d+\s+[\w-]+\.yml', original_report))
    
    print(f"   原始报告:")
    print(f"   - 工作流详细描述: {original_workflows} 个")
    print(f"   - Job 表格: {original_job_tables} 个")
    print(f"   - 步骤详情: {original_step_details} 个")
    
    print(f"\n   重组后报告:")
    print(f"   - 工作流详细描述: {reorganized_workflows} 个")
    print(f"   - Job 表格: {reorganized_job_tables} 个")
    print(f"   - 步骤详情: {reorganized_step_details} 个")
    
    print(f"\n   改进:")
    print(f"   - 工作流详细描述: +{reorganized_workflows - original_workflows} 个")
    print(f"   - Job 表格: +{reorganized_job_tables - original_job_tables} 个")
    print(f"   - 步骤详情: +{reorganized_step_details - original_step_details} 个")

if __name__ == '__main__':
    main()
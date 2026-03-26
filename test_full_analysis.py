#!/usr/bin/env python3
"""完整测试流程 - 模拟完整的 CI/CD 分析"""
import json
import re
import sys
import os
from pathlib import Path

sys.path.insert(0, r'F:\code\evaluationagent\src')

from dotenv import load_dotenv
load_dotenv(r'F:\code\evaluationagent\.env')

from evaluator.llm import LLMClient
from evaluator.agents.cicd.data_extraction_agent import DataExtractionAgent
from evaluator.agents.cicd.analysis_planning_agent import AnalysisPlanningAgent
from evaluator.agents.cicd.llm_invocation_agent import LLMInvocationAgent
from evaluator.agents.cicd.result_merging_agent import ResultMergingAgent
from evaluator.agents.cicd.quality_check_agent import QualityCheckAgent
from evaluator.agents.cicd.architecture_validation_agent import ArchitectureValidationAgent
from evaluator.agents.cicd.stage_organization_agent import StageOrganizationAgent
from evaluator.agents.cicd.report_generation_agent import ReportGenerationAgent

def main():
    project_path = r'F:\code\cccl'
    output_dir = Path(r'F:\code\evaluationagent\dist\eval-agent\data\projects\cccl\v1_20260324_200130_test')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("完整测试流程")
    print("=" * 60)
    
    # 初始化 LLM
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    model = os.getenv("DEFAULT_MODEL", "glm-4")
    
    llm = LLMClient(api_key=api_key, base_url=base_url, model=model)
    
    # Step 1: 数据提取
    print("\n[Step 1] 数据提取...")
    extraction_agent = DataExtractionAgent()
    ci_data_path = str(output_dir / "ci_data.json")
    state = {
        "project_path": project_path,
        "storage_dir": str(output_dir),
    }
    state = extraction_agent.run(state)
    ci_data = state.get("ci_data", {})
    print(f"  提取到 {len(ci_data.get('workflows', {}))} 个工作流")
    
    # Step 2: 分析规划
    print("\n[Step 2] 分析规划...")
    planning_agent = AnalysisPlanningAgent(llm=llm)
    state["ci_data_path"] = ci_data_path
    state = planning_agent.run(state)
    print(f"  生成了 {len(state.get('prompt_files', []))} 个 prompt 文件")
    
    # Step 3: LLM 调用
    print("\n[Step 3] LLM 调用...")
    invocation_agent = LLMInvocationAgent(llm=llm)
    state = invocation_agent.run(state)
    llm_responses = state.get("llm_responses", [])
    print(f"  收到 {len(llm_responses)} 个 LLM 响应")
    
    # Step 4: 结果合并
    print("\n[Step 4] 结果合并...")
    merging_agent = ResultMergingAgent()
    state = merging_agent.run(state)
    merged_response = state.get("merged_response", "")
    print(f"  合并后长度: {len(merged_response)} 字符")
    
    # 保存合并后的响应
    with open(output_dir / "llm_response.md", "w", encoding="utf-8") as f:
        f.write(merged_response)
    
    # Step 5: 质量检查
    print("\n[Step 5] 质量检查...")
    quality_agent = QualityCheckAgent(llm=llm)
    state = quality_agent.run(state)
    architecture_json = state.get("architecture_json", {})
    print(f"  architecture.json 层数: {len(architecture_json.get('layers', []))}")
    
    # Step 6: 架构验证
    print("\n[Step 6] 架构验证...")
    arch_validation_agent = ArchitectureValidationAgent()
    state = arch_validation_agent.run(state)
    
    # Step 7: 阶段组织
    print("\n[Step 7] 阶段组织...")
    stage_org_agent = StageOrganizationAgent(llm=llm)
    state = stage_org_agent.run(state)
    organized_response = state.get("merged_response", "")
    print(f"  组织后长度: {len(organized_response)} 字符")
    
    # Step 8: 报告生成
    print("\n[Step 8] 报告生成...")
    report_agent = ReportGenerationAgent()
    state["merged_response"] = organized_response
    state = report_agent.run(state)
    
    # 统计最终报告
    report_path = output_dir / "CI_ARCHITECTURE.md"
    if report_path.exists():
        with open(report_path, "r", encoding="utf-8") as f:
            report_content = f.read()
        
        # 统计
        wf_count = len(re.findall(r'####\s+\d+\.\d+\s+[\w-]+\.yml', report_content))
        job_table_count = len(re.findall(r'\|\s*序号\s*\|\s*Job名称\s*\|', report_content))
        step_count = len(re.findall(r'步骤\d+:', report_content))
        json_count = len(re.findall(r'<!--\s*ARCHITECTURE_JSON', report_content, re.IGNORECASE))
        batch_count = len(re.findall(r'#\s*CI/CD\s+架构分析.*?批次', report_content, re.IGNORECASE))
        
        print(f"\n最终报告统计:")
        print(f"  工作流详细描述: {wf_count} 个")
        print(f"  Job 表格: {job_table_count} 个")
        print(f"  步骤详情: {step_count} 个")
        print(f"  ARCHITECTURE_JSON 标记: {json_count} 个")
        print(f"  批次标记: {batch_count} 个")
        print(f"  文件长度: {len(report_content)} 字符")
        
        # 检查 architecture.json
        arch_path = output_dir / "architecture.json"
        if arch_path.exists():
            with open(arch_path, "r", encoding="utf-8") as f:
                arch_data = json.load(f)
            
            print(f"\narchitecture.json 统计:")
            for i, layer in enumerate(arch_data.get("layers", []), 1):
                layer_name = layer.get("name", "")
                nodes = layer.get("nodes", [])
                yml_nodes = [n for n in nodes if n.get("label", "").endswith(".yml")]
                print(f"  {i}. {layer_name}: {len(yml_nodes)} 个工作流")
    
    print("\n" + "=" * 60)
    print("测试完成!")
    print(f"输出目录: {output_dir}")
    print("=" * 60)

if __name__ == '__main__':
    main()
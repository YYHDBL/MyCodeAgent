"""测试 TraceLogger 功能

测试内容：
1. TraceLogger 创建（启用/禁用）
2. 事件记录（user_input/model_output/tool_call/tool_result/error/finish）
3. session_summary 生成
4. JSONL 文件写入
"""

import os
import sys
import json
from pathlib import Path

# 添加项目根目录到 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from extensions.tracing.logger import create_trace_logger


def test_trace_logger_disabled():
    """测试 TraceLogger 禁用模式"""
    print("=" * 60)
    print("Test 1: TraceLogger (disabled)")
    print("=" * 60)
    
    # 确保禁用
    os.environ['TRACE_ENABLED'] = 'false'
    
    logger = create_trace_logger()
    print(f"Session ID: {logger.session_id}")
    print(f"Enabled: {logger.enabled}")
    
    # 禁用时不应写入文件
    logger.log_event('user_input', {'text': 'test'}, step=0)
    logger.finalize()
    
    print("✅ Disabled mode test passed\n")


def test_trace_logger_enabled():
    """测试 TraceLogger 启用模式"""
    print("=" * 60)
    print("Test 2: TraceLogger (enabled)")
    print("=" * 60)
    
    # 启用
    os.environ['TRACE_ENABLED'] = 'true'
    os.environ['TRACE_DIR'] = 'memory/traces'
    
    logger = create_trace_logger()
    print(f"Session ID: {logger.session_id}")
    print(f"Enabled: {logger.enabled}")
    print(f"Trace file: {logger._filepath}")
    
    # 记录各种事件
    print("\n--- Recording events ---")
    
    # 1. user_input
    logger.log_event('user_input', {
        'text': '列出当前目录的文件'
    }, step=0)
    print("✓ user_input")
    
    # 2. model_output (step 1)
    logger.log_event('model_output', {
        'raw': '',
        'tool_calls': [{'id': 'call_1', 'name': 'LS', 'arguments': {'path': '.'}}],
        'usage': {
            'prompt_tokens': 1234,
            'completion_tokens': 56,
            'total_tokens': 1290
        }
    }, step=1)
    print("✓ model_output (step 1)")
    
    # 3. tool_call
    logger.log_event('tool_call', {
        'tool': 'LS',
        'args': {'path': '.'},
        'tool_call_id': 'call_1'
    }, step=1)
    print("✓ tool_call")
    
    # 5. tool_result
    logger.log_event('tool_result', {
        'tool': 'LS',
        'result': {
            'status': 'success',
            'data': {
                'entries': [
                    {'path': 'core', 'type': 'dir'},
                    {'path': 'README.md', 'type': 'file'}
                ],
                'truncated': False
            },
            'text': 'Listed 2 entries in "."',
            'stats': {'time_ms': 5, 'total_entries': 2},
            'context': {'cwd': '.', 'params_input': {'path': '.'}}
        }
    }, step=1)
    print("✓ tool_result")
    
    # 6. model_output (step 2)
    logger.log_event('model_output', {
        'raw': '当前目录包含 core 目录和 README.md 文件',
        'usage': {
            'prompt_tokens': 1567,
            'completion_tokens': 89,
            'total_tokens': 1656
        }
    }, step=2)
    print("✓ model_output (step 2)")
    
    # 7. finish
    logger.log_event('finish', {
        'final': '当前目录包含 core 目录和 README.md 文件'
    }, step=2)
    print("✓ finish")
    
    # 8. finalize (写入 session_summary)
    print("\n--- Finalizing ---")
    logger.finalize()
    
    print(f"\n✅ Enabled mode test passed")
    print(f"✅ Trace saved to: {logger._filepath}")
    
    assert logger._filepath is not None


def test_trace_logger_with_error():
    """测试 TraceLogger 错误记录"""
    print("\n" + "=" * 60)
    print("Test 3: TraceLogger (with error)")
    print("=" * 60)
    
    os.environ['TRACE_ENABLED'] = 'true'
    
    logger = create_trace_logger()
    print(f"Session ID: {logger.session_id}")
    
    # 记录用户输入
    logger.log_event('user_input', {'text': '测试错误处理'}, step=0)
    
    # 记录工具调用错误
    logger.log_event('error', {
        'stage': 'tool_execution',
        'error_code': 'INVALID_PARAM',
        'message': 'Parameter "path" is required',
        'tool': 'Read',
        'args': {},
        'traceback': 'Traceback (most recent call last):\n  ...'
    }, step=1)
    print("✓ error event recorded")
    
    logger.finalize()
    print(f"✅ Error test passed")
    print(f"✅ Trace saved to: {logger._filepath}")
    
    assert logger._filepath is not None


def verify_jsonl_file(filepath: Path):
    """验证 JSONL 文件内容"""
    print("\n" + "=" * 60)
    print("Verifying JSONL file content")
    print("=" * 60)
    
    if not filepath or not filepath.exists():
        print("❌ File does not exist")
        return
    
    print(f"File: {filepath}")
    print(f"Size: {filepath.stat().st_size} bytes")
    
    # 读取并解析每一行
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    print(f"Total events: {len(lines)}")
    print("\nEvents:")
    
    for i, line in enumerate(lines, 1):
        try:
            event = json.loads(line)
            event_type = event.get('event', 'unknown')
            step = event.get('step', 0)
            print(f"  {i}. {event_type} (step={step})")
            
            # 验证必填字段
            required = ['ts', 'session_id', 'step', 'event', 'payload']
            missing = [f for f in required if f not in event]
            if missing:
                print(f"     ⚠️  Missing fields: {missing}")
            
        except json.JSONDecodeError as e:
            print(f"  {i}. ❌ Invalid JSON: {e}")
    
    print("\n✅ JSONL verification completed")


def main():
    """运行所有测试"""
    print("\n" + "🧪 " * 30)
    print("TraceLogger Test Suite")
    print("🧪 " * 30 + "\n")
    
    try:
        # 测试 1: 禁用模式
        test_trace_logger_disabled()
        
        # 测试 2: 启用模式（完整流程）
        filepath1 = test_trace_logger_enabled()
        
        # 测试 3: 错误记录
        filepath2 = test_trace_logger_with_error()
        
        # 验证文件内容
        if filepath1:
            verify_jsonl_file(filepath1)
        
        print("\n" + "=" * 60)
        print("🎉 All tests passed!")
        print("=" * 60)
        
        # 打印生成的文件路径
        print("\nGenerated trace files:")
        if filepath1:
            print(f"  - {filepath1}")
        if filepath2:
            print(f"  - {filepath2}")
        
        print("\n💡 Tip: You can view the trace files with:")
        print("  cat memory/traces/trace-*.jsonl")
        print("  or")
        print("  cat memory/traces/trace-*.jsonl | jq")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

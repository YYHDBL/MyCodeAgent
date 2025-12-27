#!/usr/bin/env python3
"""一键运行所有协议合规性测试

傻瓜式自动化测试脚本，直接运行即可。

使用方式：
    python tests/run_all_tests.py
    python tests/run_all_tests.py -v          # 详细输出
    python tests/run_all_tests.py --quick     # 快速模式（跳过慢测试）
"""

import sys
import os
import unittest
import argparse
import time
from pathlib import Path

# 确保项目根目录在 Python 路径中
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def run_tests(verbosity: int = 2, quick_mode: bool = False) -> bool:
    """
    运行所有测试
    
    Args:
        verbosity: 输出详细程度 (0=静默, 1=简洁, 2=详细)
        quick_mode: 是否快速模式（跳过慢测试）
    
    Returns:
        bool: 是否全部通过
    """
    print("=" * 60)
    print("🔍 通用工具响应协议合规性测试")
    print("=" * 60)
    print()
    
    start_time = time.time()
    
    # 发现并加载测试
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # 加载测试模块
    test_modules = [
        "tests.test_protocol_compliance",
    ]
    
    for module_name in test_modules:
        try:
            tests = loader.loadTestsFromName(module_name)
            suite.addTests(tests)
            print(f"✅ 加载测试模块: {module_name}")
        except Exception as e:
            print(f"❌ 加载失败 {module_name}: {e}")
    
    print()
    print("-" * 60)
    print()
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)
    
    # 统计结果
    elapsed = time.time() - start_time
    
    print()
    print("=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)
    print(f"运行测试: {result.testsRun}")
    print(f"成功: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"失败: {len(result.failures)}")
    print(f"错误: {len(result.errors)}")
    print(f"跳过: {len(result.skipped)}")
    print(f"耗时: {elapsed:.2f}s")
    print()
    
    if result.wasSuccessful():
        print("🎉 所有测试通过！协议合规性验证成功。")
        return True
    else:
        print("❌ 测试未通过，请检查上述错误。")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="运行通用工具响应协议合规性测试",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python tests/run_all_tests.py           # 运行所有测试
  python tests/run_all_tests.py -v        # 详细输出
  python tests/run_all_tests.py -q        # 静默模式
  python tests/run_all_tests.py --quick   # 快速模式
        """
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")
    parser.add_argument("-q", "--quiet", action="store_true", help="静默模式")
    parser.add_argument("--quick", action="store_true", help="快速模式（跳过慢测试）")
    
    args = parser.parse_args()
    
    # 确定详细程度
    if args.quiet:
        verbosity = 0
    elif args.verbose:
        verbosity = 2
    else:
        verbosity = 1
    
    # 运行测试
    success = run_tests(verbosity=verbosity, quick_mode=args.quick)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

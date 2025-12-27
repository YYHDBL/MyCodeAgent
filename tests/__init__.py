"""通用工具响应协议合规性测试框架

验证所有工具返回的响应是否严格遵循《通用工具响应协议》。

运行方式：
    # 运行所有测试
    python -m pytest tests/ -v

    # 仅运行协议合规性测试
    python -m pytest tests/test_protocol_compliance.py -v

    # 快速验证单个响应
    python -m tests.utils.protocol_validator '{"status":"success",...}'
"""

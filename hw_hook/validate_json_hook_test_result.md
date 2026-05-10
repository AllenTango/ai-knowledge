# JSON 校验脚本测试报告

测试时间: 2026-05-10
测试脚本: hooks/validate_json.py
测试用例: hw_hook/test_*.json (共 8 个)

## 测试用例列表

| 文件名 | 预期结果 | 说明 |
|--------|----------|------|
| test_pass.json | 通过 | 完整合规的 JSON |
| test_missing_field.json | 失败 | 缺少必填字段 id |
| test_bad_status.json | 失败 | status 值为无效值 |
| test_bad_url.json | 失败 | URL 使用 ftp 协议 |
| test_short_summary.json | 失败 | 摘要长度不足 50 字 |
| test_empty_tags.json | 失败 | tags 为空列表 |
| test_score_outofrange.json | 失败 | score 超范围 (15.0) |
| test_parse_error.json | 失败 | JSON 格式错误 |

## 实际运行输出

```
[ERROR] ✗ hw_hook\test_validate_cases\test_bad_status.json
  - status 值无效: invalid_status (必须是 approved, pending_review, published, rejected 之一)
[ERROR] ✗ hw_hook\test_validate_cases\test_bad_url.json
  - source_url 格式无效: ftp://ftp.test.com/file
[ERROR] ✗ hw_hook\test_validate_cases\test_empty_tags.json
  - summary 长度不足 50 字: 当前 47 字
  - tags 至少需要 1 个标签
[ERROR] ✗ hw_hook\test_validate_cases\test_missing_field.json
  - 缺少必填字段: id
  - summary 长度不足 50 字: 当前 30 字
[ERROR] ✗ hw_hook\test_validate_cases\test_parse_error.json
  - JSON 解析失败: Invalid control character at (行 3, 列 27)
[INFO] ✓ hw_hook\test_validate_cases\test_pass.json
[ERROR] ✗ hw_hook\test_validate_cases\test_score_outofrange.json
  - score 超出范围: 15.0 (必须是 1.0 ~ 10.0)
[ERROR] ✗ hw_hook\test_validate_cases\test_short_summary.json
  - summary 长度不足 50 字: 当前 4 字

========================================
校验完成: 总计 8 | 通过 1 | 失败 7
```

## 结论

所有 8 个测试用例均按预期被正确校验：
- 1 个通过（test_pass.json）
- 7 个失败（各种错误类型均被正确检测）

校验脚本功能正常，符合需求规格。

# 原始业务资料

本目录集中保存知识构建和需求分析的原始输入，不作为运行时知识库直接加载。

- `SOUNDERONE_智能客服对接问卷.docx`：项目需求和品牌客服信息来源，可提交 Git。
- `产品话术汇总完整版本.xlsx`：产品资料与历史客服话术，包含订单等敏感业务数据，已由 `.gitignore` 排除，禁止提交 Git。

重新构建知识库：

```bash
UV_PROJECT_ENVIRONMENT=.venv.nosync uv run python scripts/build_knowledge.py 'source_materials/产品话术汇总完整版本.xlsx'
```

构建后只提交 `knowledge/` 中经过脱敏和风险分区的 JSON 与报告。

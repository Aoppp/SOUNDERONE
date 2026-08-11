# Hand-off（更新于 2026-08-11）

## 当前状态

项目已重构为抖音单平台 Agent MVP，不应直接连接生产店铺。核心流程使用 LangGraph，知识库使用 Qdrant Dense + BM25 混合 RAG 和 RRF 融合。默认 `LLM_PROVIDER=mock`、`EMBEDDING_PROVIDER=hash`，可离线测试；生产回答层已支持 `deepseek-v4-flash`。

运行知识已拆分为 `product_knowledge.json`（64条）和 `customer_faq.json`（223条），其中合计210条 active 写入 Qdrant。高危先转人工；范围外问题从20条 SOUNDERONE 文案中稳定选择；相关但缺产品信息时追问；有效问题经受约束改写、知识类型路由和混合检索，未可靠命中则转人工。工作区 Git 对象位于 `.git.nosync`，避免再次被 iCloud 自动卸载。

原始业务资料已统一移动到 `source_materials/`；知识重建命令和测试路径均已更新。旧损坏备份、重复环境和缓存的可恢复副本位于 macOS 废纸篓 `SounderOne-cleanup-20260811/`。

最后验证结果为46项自动化测试通过；`deepseek-v4-flash` 已完成真实 API 和运行中完整 Graph 调用。回复已禁止内部资料转述及 Markdown 标记，并由输出规则兜底清理。选品推荐支持多轮续问和目标同义词扩展；“美白推荐 → 那有没有什么抗衰的呢”已实测连续回答，去黑头推荐因无知识转人工。本地 `.env` 已切换为 `LLM_PROVIDER=deepseek`，密钥不在 Git 中。

## iCloud 恢复记录（已处理）

原工作区曾被 iCloud 卸载为 `dataless`，已通过非 iCloud 临时目录重建并推送。原损坏内容保存在 `*.nosync` 备份目录，正常开发无需使用。验证命令：

```bash
git fsck --full
UV_CACHE_DIR=/tmp/sounderone-uv-cache UV_PROJECT_ENVIRONMENT=.venv.nosync uv run pytest -q
git status --short --branch
```

远程地址：`git@github.com:Aoppp/SOUNDERONE.git`，分支：`main`。

## 恢复后业务推进顺序

1. 查看 `knowledge/build_report.json` 的 46 个冲突，优先确认麦角硫因 0.5%/2%、孕期可用性和旧/新版产品禁忌差异。
2. 建立 50–100 条真实问题的评测集，覆盖正常 FAQ、未知问题、不良反应、退款投诉、功效禁词和夜间场景。
3. 向业务方确认客服系统、工作时间和转人工队列；拿到抖音脱敏 webhook/回复/转人工样例与应用权限。
4. 配置 GitHub CI、Secret 和分支保护。

## 运行方式

```bash
cp .env.example .env
UV_CACHE_DIR=/tmp/sounderone-uv-cache UV_PROJECT_ENVIRONMENT=.venv.nosync uv venv --python /Users/ao/anaconda3/bin/python
UV_CACHE_DIR=/tmp/sounderone-uv-cache UV_PROJECT_ENVIRONMENT=.venv.nosync uv sync --extra dev
UV_CACHE_DIR=/tmp/sounderone-uv-cache UV_PROJECT_ENVIRONMENT=.venv.nosync uv run pytest
UV_CACHE_DIR=/tmp/sounderone-uv-cache UV_PROJECT_ENVIRONMENT=.venv.nosync uv run uvicorn app.main:app --reload
```

详见 `README.md`。接口文档在服务启动后的 `/docs`。

## 尚缺资料/权限

- Excel 中 39 条 review-required 内容的业务审核结果，尤其是浓度、孕期禁忌和监管声明。
- 正式 SKU 唯一编码、在售/停售状态、版本生效日期和知识负责人。
- 抖音应用的 `app_key` / `app_secret`、客服消息权限包、官方回调和回复样例。
- 人工工作时间、节假日规则、技能组、SLA、升级路径。
- 数据控制方/处理方责任、留存周期、删除流程、日志脱敏与安全审计要求。

## 重要限制

- `knowledge/sample.json` 仅保留为测试夹具；运行时默认使用 `product_knowledge.json` 和 `customer_faq.json`，`sounderone_knowledge.json` 是完整审计基准。
- 原始 Excel 位于 `source_materials/`，含订单数据，不会推送 GitHub；更新知识时在本地重新构建，只提交脱敏后的 JSON 与报告。
- 不要给 Agent 退款、补发或改订单权限。订单能力应先只读并经过脱敏和审计。
- 不良反应必须直接转人工，不提供诊断；涉及强情绪、监管、法律和媒体同样转人工。
- `DouyinAdapter` 目前只是归一化联调契约，上线前必须做官方验签、解密、幂等、重放保护、限流和沙箱认证。
- 默认 hash embedding 是离线开发基线，抖音灰度前必须切换并评测真实语义 embedding。
- 当前正式知识库没有可靠的发货时效条目；“多久发货”会按预期转人工。业务确认话术后应补充对应 FAQ，而不是降低检索门槛。
- 当前机器未发现 Docker CLI，容器镜像尚未实际构建；在 CI 或装有 Docker 的环境补跑 `docker compose build`。

## 下一阶段完成定义

- 抖音真实消息能通过官方验签进入系统、可靠回复或转人工，失败可重试且不重复发送。
- 正式知识库可追溯到版本和负责人，评测集通过业务验收。
- 会话、审计和工单持久化；人工端能看到完整上下文与引用。
- 监控至少覆盖错误率、延迟、转人工率、无答案率、禁词命中和平台发送失败。

# Development Log

## 2026-08-08

### 需求与发现

- 读取 `SOUNDERONE_智能客服对接问卷.docx`。
- 覆盖渠道：淘宝、抖音、京东、小红书、微信小店、快手、拼多多、蘑菇街、得物；抖音约占 70%–80%。
- 6 月咨询 6000+，7 月 3400+；售前和售中各约 20%，售后约 60%。
- 红线：复杂售后、强烈情绪、AI 未知问题、不良反应转人工；AI 不允许退款、补发或修改订单。
- 品牌客服语气为亲切、柔和，称呼用户“宝宝”。只可描述产品资料明确支持的功效。
- 夜间回复曾出现不可控错误，因此非工作时间必须缩权。
- 现有客服系统、订单 API、CRM、工单、隐私要求尚不清楚；库存系统为旺店通企业版。
- 目录起初只有问卷，不是 Git 仓库，也没有 GitHub remote。

### 架构决策

- 选择 Python 3.11+ / FastAPI / Pydantic 作为首期分层单体，先降低多平台业务规则分叉风险。
- 平台差异放入 Adapter，核心只处理统一消息模型。
- 本地使用 JSON 词法检索和内存会话，确保无外部账号也可端到端开发；生产迁移 PostgreSQL/pgvector/Redis。
- LLM 默认 Mock，可配置 OpenAI Responses API。风险判断与合规后处理独立于 LLM。
- 任何低置信度问题均转人工，正式知识库到位前禁止生产自动回复。

### 已完成

- FastAPI 应用、健康检查、统一 webhook、知识库热重载和会话查询接口。
- 九个平台标识及 GenericAdapter 开发契约。
- 测试知识库、可替换检索层、引用输出。
- 红线转人工、敏感信息检测、非工作时间缩权、禁用功效词拦截。
- webhook 消息幂等、审计文本敏感信息脱敏、管理接口独立鉴权。
- OpenAI 与 Mock 双模型实现。
- 单元测试、API 集成测试、Docker 与配置样例。
- README、架构文档、平台接入清单和交接文档。

### 验证结果

- Python 3.11.9 环境完成依赖锁定和安装。
- `pytest`：15 个测试全部通过（知识检索、风险策略、鉴权、API、幂等、脱敏、输入校验）。
- `compileall`：应用与测试代码编译通过。
- 唯一警告来自 FastAPI/Starlette TestClient 对 httpx 兼容层的弃用提示，不影响运行；后续依赖升级时处理。
- 当前机器未安装 Docker CLI，因此 Dockerfile/Compose 已静态检查但未执行镜像构建。
- 公开网络检索未找到足够可靠的 SounderOne 官方品牌页面，因此品牌事实以问卷为准，未把非官方搜索内容写进知识库。

### 待输入

- 正式 SKU、话术、FAQ、培训资料及详情页素材未在当前目录中。
- 真实平台授权、客服系统 API、旺店通只读接口和人工队列配置。

## 2026-08-10

### Git 同步状态

- 已配置 `origin = git@github.com:Aoppp/SOUNDERONE.git`。
- 本地根提交：`2e2a5d6 feat: bootstrap multi-platform customer service agent`。
- 首次 push 失败：macOS/iCloud 自动把工作区和部分 `.git/objects` 卸载为 `compressed,dataless`，Git 报 `mmap failed: Operation timed out`，远程拒绝不完整 pack。
- 再次执行 `git ls-remote` 未返回 `main` 或 HEAD，确认 GitHub 远程仍为空，没有留下损坏分支。
- `brctl download`、Finder reveal 与文件提供器检查未能在无人值守环境完成实体下载。
- 原日志占位文件保留为 `development_log.md.icloud-placeholder`；本文件为重建的可读副本。

### 恢复步骤

1. 在 Finder 中右键项目目录，选择“立即下载”，等待云朵图标消失。
2. 运行 `ls -lO app/main.py .git/objects/*/* | head`，确认不再出现 `dataless`。
3. 运行 `git add .`，注意不要提交 `*.icloud-placeholder` 备份。
4. 运行 `git commit --amend --no-edit`（或新建恢复提交）。
5. 运行 `git fsck --full`、`uv run pytest -q`，再执行 `git push -u origin main`。

### 已解决

- 在非 iCloud 的 `/tmp` 重建内容等价的干净仓库，保留原始问卷与全部项目文件。
- 重新生成 `uv.lock`，再次运行测试：15 passed；`compileall` 通过。
- 干净根提交 `f6f51ca` 已成功推送至 `origin/main`。
- 工作区使用 `.git.nosync` 保存 Git 对象，虚拟环境固定为 `.venv.nosync`，避免 iCloud 再次自动卸载；原损坏 Git 对象和占位源码保留在 `*.nosync` 备份目录，不会入库。

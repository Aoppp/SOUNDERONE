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

### 产品与客服知识库构建

- 深度解析 `产品话术汇总完整版本.xlsx`：11 个工作表、28 张嵌入图片。
- `CXD`、`无所谓`、`Sheet14` 为订单/金额/负责人数据，整体排除；两个空表排除。
- `三蛋丸` 作为当前产品权威表；`三蛋丸产品介绍` 作为旧版，仅用于差异检测。
- 从产品字段、通用话术、运营话术、微信群 QA、京东问答生成 291 条原始候选；合并 4 条完全重复内容并保留替代来源后得到 287 条知识。
- 安全分区：210 active、39 review-required、38 handoff-only；非 active 内容不参与自动回答。
- 检出 46 个冲突：27 个产品版本差异、13 个 FAQ 答案差异、6 个权威浓度冲突。
- 修复 Excel 合并单元格继承；识别“护发产品”复合表头，将木/水/火/土映射为具体洗护品，并将 D/E 列按搭配方案分块；产品“区别”行单独归类，不再误生成用法和禁忌。
- 构建报告中的敏感预览也会脱敏，防止退货电话/地址通过冲突报告进入 Git。
- 明确识别麦角硫因 0.5%/2% 冲突并禁止 2% 内容自动检索；孕期、医美、不良反应、复杂售后强制转人工或审核。
- 生成文件不含手机号、订单号、退货地址或收件人信息；原始 Excel 因包含交易数据加入 `.gitignore`。
- 检索升级为 IDF 加权的中文单字/双字 + 英文数字词元策略，加入浓度/英文缩写硬匹配和使用/搭配意图过滤。
- 最终测试：26 passed（含 Excel 重建、PII 排除、冲突隔离、护发搭配、产品对比检索和 Agent 端到端）；`compileall` 通过。

### 抖音单平台 LangGraph + 混合 RAG 重构

- 开发范围从九平台收缩为 `douyin` 和 `simulator`，删除其他平台枚举、GenericAdapter、Adapter 基类和旧平台接入文档。
- 删除线性 `CustomerServiceAgent` 和旧 `LocalKnowledgeBase`，引入 LangGraph `StateGraph`。
- 新图包含 `safety_guard`、`understand_query`、`hybrid_retrieve`、`relevance_gate`、`generate_answer`、`output_guard`、`finalize_response` 和 `handoff` 节点。
- 引入 Qdrant；每条 active 知识同时索引 Dense Vector 和 BM25 Sparse Vector，两路 Top 50 使用 RRF 和 IDF 覆盖率融合。
- 默认 hash embedding 保证无密钥、无网络的可复现测试；配置 `EMBEDDING_PROVIDER=openai` 后使用真实语义向量。
- 每次 Agent 回复增加 `graph_trace` 和 `retrieval_channels`，可核对节点路径与 Dense/BM25 召回情况。
- 新增 `scripts/index_knowledge.py`，可将审核后 JSON 重建为 Qdrant 双索引。
- 重构后验证：28 passed；持久 Qdrant 索引命令成功写入 210 条 active 知识；`compileall` 和 `git diff --check` 通过。

### Agent Lab 浏览器测试窗口

- 新增 `/tester` 可视化对话页，由 FastAPI 直接提供 HTML/CSS/JavaScript，不增加独立前端工程和构建链。
- 支持连续多轮消息、新建会话、Webhook Secret、快捷场景和服务健康状态。
- 回复可视化 `decision`、转人工原因、风险标签、Excel 来源、RRF 分数、Dense/BM25 通道和 LangGraph 节点轨迹。
- 用户文本统一通过 DOM `textContent` 渲染，不把测试输入作为 HTML 执行。
- 测试配置强制使用内存 Qdrant，避免与正在运行的本地持久索引争抢文件锁。
- 验证：29 passed；JavaScript 语法检查通过；页面、健康接口和浏览器模拟问答烟雾测试通过。

### 纯问候错误召回修复

- 问题：“你好”被直接送入混合 RAG，检索器硬选了麦角硫因/EUK-134 对比条目，导致无关产品回答。
- 修复：在 `understand_query` 后新增条件分支和 `smalltalk_response` 节点；纯问候不再进入 Qdrant 或 LLM。
- 边界：“你好，多久发货？”等包含业务问题的消息仍进入 Dense + BM25 RAG。
- 验证：31 passed；纯问候引用为空，Graph 轨迹正确；带业务问题的问候仍命中正确知识。

### 低信息与意图错配召回修复

- 问题：“他好”等无业务含义文本与产品话术共享“他/好”两个中文单字，旧检索门槛将两个单字碰撞误判为有效重合；已有产品会话上下文还可能放大误召回。
- 查询入口新增领域与上下文门控：无业务语义直接进入 `clarify_response`；“怎么用/效果怎么样”等产品问题没有产品名或有效上文时先追问；物流、订单和售后等可独立成意图的问题仍可检索。
- 检索层改为必须共享至少一个多字词，不能用多个高噪声单字凑相关性；英文缩写和数字实体继续执行硬匹配。
- 新增物流、发票、促销的意图/类别/标题标签一致性过滤。正式知识库缺少发货资料时，“多久发货”现在转人工，不再回答“多久有效果”。
- `safe_fallback` 澄清与真正的 `handoff` 分离，抖音适配响应中的 `handoff` 仅在决策确实为 `handoff` 时为 true。
- 回归覆盖纯问候、无厘头文本、标点、域外问题、缺产品用法、无上下文指代、带历史产品上下文的无厘头消息、正确发货知识及正式库缺失发货知识。
- 验证：35 passed；JavaScript 语法、Python `compileall` 和 `git diff --check` 均通过；运行中正式知识库烟雾测试确认“他好”安全澄清且无引用，“多久发货”因无可靠答案转人工。

## 2026-08-11

### SOUNDERONE 范围路由、双知识库与 DeepSeek Flash

- 将客服能力范围明确为“SOUNDERONE 品牌及其相关产品”，所有新增话术均不包含“王叔”或“王叔和”。
- LangGraph 调整为：`safety_guard -> intent_router -> rewrite_query -> route_knowledge -> hybrid_retrieve -> relevance_gate -> generate_answer -> output_guard -> finalize_response`；任一高危、无可靠命中、生成资料不足、模型故障或输出违规分支均可进入 `handoff`。
- 高危逻辑仍是消息进入后的第一个判断，不良反应、孕期、医美、复杂售后、法律/舆情等不会先经过普通意图或 RAG。
- 范围外问题进入 `out_of_scope_response`；创建20条已审核的 SOUNDERONE 范围说明，使用会话ID和消息ID哈希稳定选择，既有文案变化又保持 webhook 重试一致。
- 将范围外问题和信息不足分开：“天气怎么样/他好”等回复能力范围；“怎么用/这个适合吗”等缺少产品上下文的问题进入 `clarify_response` 追问产品名。
- 新增受约束问题改写：只把 LangGraph 会话中已确认的上一产品补入查询，不调用 LLM，不允许创造产品名、浓度或用户情况。
- 将完整审计源无损拆分为 `product_knowledge.json`（64条，47 active）与 `customer_faq.json`（223条，163 active）；运行时加载两文件，完整 `sounderone_knowledge.json` 保留为审计基准。
- `route_knowledge` 对物流、发票、促销只检索 FAQ；产品用法、搭配、对比和信息问题同时检索产品知识与 FAQ。引用新增 `knowledge_type`。
- `relevance_gate` 新增可靠候选裁剪：低于最低分或与 Top1 分差超过 `KNOWLEDGE_SCORE_WINDOW` 的次级结果不会发送给生成模型，也不会出现在引用中。
- 接入官方 OpenAI 兼容接口的 `DeepSeekLanguageModel`，默认生产模型配置为 `deepseek-v4-flash`；模型只依据召回片段组织话术，返回 `INSUFFICIENT_KNOWLEDGE`、空内容或 API 故障时统一转人工。
- 保留 Mock 和 OpenAI 适配器；自动化测试不需要模型密钥。DeepSeek 适配器先使用模拟响应完成请求结构隔离测试，随后使用本地 `.env` 中的密钥完成真实 `deepseek-v4-flash` 调用；密钥文件被 Git 忽略，密钥值不写入日志或提交。
- 第一次真实调用因上下文只包含规范标题和正文、缺少“5%传明酸”别名标签而安全返回 `INSUFFICIENT_KNOWLEDGE`。修复为向模型提供知识类型、分类、标签和正文，并明确标签只用于产品身份确认；复测与运行中完整 Graph 请求均正确回答且引用唯一可靠产品文档。
- 客服口吻改为官方直接回答：生成提示明确禁止“根据产品介绍”“根据现有资料”“知识库里提到的”“目前资料里”等内部来源表达；Mock 同步移除固定前缀，`output_guard` 增加确定性清理作为第二层保障。
- 验证：43 passed；Python `compileall`、JavaScript 语法和 `git diff --check` 通过。正式 DeepSeek 烟雾测试以直接客服口吻回答5%传明酸用法，没有内部资料转述措辞。

### 无指定产品的选品推荐

- 将“有什么美白产品推荐”等信息完整的选品问题从“缺少产品名”澄清分支中独立出来，新增 `recommendation` 意图并同时查询产品知识与 FAQ。
- 推荐检索增加目标词组约束，当前覆盖美白/提亮/淡斑/去黄、毛孔、控油、祛痘、抗皱、保湿、黑头、眼袋、敏感和去屑；候选必须包含对应目标词，不能只凭“产品/推荐”召回无关条目。
- 真实 DeepSeek 测试“有什么美白产品推荐”使用两条产品功效 FAQ 和一条传明酸特证限制，直接推荐夜猫子精华和10%传明酸精华；“有去黑头产品推荐吗”无可靠知识，按预期转人工且引用为空。
- 验证：45 passed；完整 Graph、引用、未命中转人工、Python 编译、JavaScript 语法及差异格式检查通过。

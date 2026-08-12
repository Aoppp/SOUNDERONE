# Development Log

## 2026-08-08

### 需求与发现

- 读取 `source_materials/SOUNDERONE_智能客服对接问卷.docx`。
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

- 深度解析 `source_materials/产品话术汇总完整版本.xlsx`：11 个工作表、28 张嵌入图片。
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

- 将客服能力范围明确为“SOUNDERONE 品牌及其相关产品”。
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
- 修复多轮续问：“那有没有什么抗衰的呢”会继承上一轮 `recommendation`，并将抗衰扩展为抗皱、淡纹、细纹、紧致、抗老和初老检索词。推荐优先使用正式产品介绍；FAQ 必须包含用户本轮原始目标词，非洗护问题排除护发产品。
- 输出口吻兜底扩大到任何包含“资料里/资料中/知识库”的转述句，并清理 Markdown `**`，避免抖音纯文本显示内部表达或星号。
- 真实同会话 DeepSeek 复测“美白有没有产品推荐 → 那有没有什么抗衰的呢”成功，第二轮推荐玻色因面霜、双A醇眼霜、EUK-134精华和30%玻色因精华。
- 验证：46 passed；完整 Graph、引用、未命中转人工、Python 编译、JavaScript 语法及差异格式检查通过。

### 阶段总结（2026-08-11）

今天完成了 SOUNDERONE 抖音客服 Agent 从“基础混合 RAG”到“可控业务路由 + 双知识库 + 真实模型回答”的阶段性升级。

#### 已完成

- 明确客服范围为 SOUNDERONE 品牌及相关产品；高危问题继续在流程最前面转人工。
- 用 LangGraph 建立问候、范围外、信息不足、知识问答、生成失败和人工转接等独立分支。
- 创建20条范围外话术，并以会话ID和消息ID稳定选择，保证回复多样且 webhook 重试一致。
- 将知识拆分为产品知识64条和FAQ 223条；两类共210条 active 文档进入 Qdrant Dense + BM25 + RRF 混合检索。
- 增加受约束问题改写、知识类型路由、产品/浓度/意图一致性过滤、多字词重合门槛和可靠候选分数窗口。
- 接入并真实验证 DeepSeek V4 Flash；本地运行已使用 DeepSeek，密钥仅保存在被 Git 忽略的 `.env`。
- 生成上下文加入知识类型、分类、产品别名标签和正文；模型资料不足、返回空内容或 API 故障时转人工。
- 客服以品牌官方身份直接回答；禁止内部资料转述，输出层清理“资料里/知识库”等表达及 Markdown 标记。
- 支持无指定产品的选品推荐，以及“美白推荐 → 那有没有什么抗衰的呢”这类多轮推荐意图继承和同义目标扩展。
- 推荐有可靠知识才回答；例如美白、抗衰已通过真实 DeepSeek 验证，去黑头推荐因没有可靠知识转人工。

#### 当前最终流程

```text
接收消息
  -> safety_guard
  -> intent_router
       | 问候 -> smalltalk_response
       | 范围外 -> out_of_scope_response
       | 信息不足 -> clarify_response
       | 有效问题 -> rewrite_query
  -> route_knowledge
  -> hybrid_retrieve (Dense + BM25 + RRF)
  -> relevance_gate
       | 未可靠命中 -> handoff
  -> generate_answer (DeepSeek V4 Flash)
       | 资料不足/模型故障 -> handoff
  -> output_guard
       | 违规内容 -> handoff
  -> finalize_response
```

#### 验证与同步

- 自动化测试：46 passed。
- 正式双库加载：287条文档，其中210条 active。
- 真实 DeepSeek 已验证产品用法、美白推荐和多轮抗衰推荐。
- Python `compileall`、JavaScript 语法和 `git diff --check` 均通过。
- 今日主要 Git 提交：`b135a32`、`59f0cc9`、`24db834`、`f85180d`、`2318b40`。

#### 下一阶段重点

- 使用真实抖音客服问题建立推荐与问答评测集，持续校准目标词、阈值和转人工率。
- 审核39条 `review_required` 知识和46个知识冲突，尤其是浓度、美白特证、孕期及产品版本差异。
- 接入抖音官方验签、解密、消息发送、失败重试和真实人工队列。
- 将 LangGraph Checkpointer、幂等记录、审计日志和会话记录迁移到持久化存储。
- 正式上线前轮换当前通过聊天传递过的 DeepSeek API Key，并通过 Secret 管理服务注入。

### 项目目录整理（2026-08-11）

- 新建 `source_materials/`，集中存放原始对接问卷和产品话术 Excel；Excel 继续被 Git 忽略，问卷以 Git rename 方式保留历史。
- 同步更新知识构建命令、正式知识测试、知识审计文档和历史日志中的原始资料路径。
- Docker Compose 从旧的单一 `KNOWLEDGE_PATH` 改为 `PRODUCT_KNOWLEDGE_PATH` 与 `FAQ_KNOWLEDGE_PATH`，并补齐 DeepSeek 与候选分数窗口环境变量，与当前双知识库运行方式一致。
- 清理旧 iCloud 损坏仓库备份、重复 `.venv`、pytest 缓存、Python `__pycache__` 和 `.DS_Store`；均移动到 `/Users/ao/.Trash/SounderOne-cleanup-20260811/`，需要时可恢复。
- 保留 `.git.nosync`（当前有效 Git 数据）、`.venv.nosync`（实际开发环境）、`data/qdrant`（本地运行索引）和 `.env`（本地密钥配置）。
- 从新路径重新构建知识：287条文档、210 active、39 review-required、38 handoff-only、46个冲突，生成结果保持确定性。
- 验证：46 passed；JavaScript 语法、Python `compileall` 和 `git diff --check` 通过。

### Excel 数值显示精度修复（2026-08-11）

- 复现“b5洗发水，b5含量百分之多少呢”错误回答 `2E-3`。确认该值是 Excel OOXML 内部保存的小数，单元格样式为内置百分比 `0.00%`，业务上的正确显示值是 `0.20%`。
- 扩展自研 OOXML 导入器：读取 `styles.xml` 的单元格样式和自定义数字格式，对百分比按 Excel 显示精度及四舍五入规则转换；无缩放样式的科学计数法会转为普通十进制文本。
- 全工作簿审计确认：当前只有 `三蛋丸微信群QA记录!B85` 受数字格式影响；修复后生成知识中不再存在科学计数法内容。
- 重建完整知识库和 FAQ 库；B5 该条知识内容由 `2E-3` 更新为 `0.20%`，其他文档、安全状态和46个冲突保持不变。
- 新增数值格式、源单元格、混合检索和 Agent API 四层回归测试；验证为50 passed，`compileall` 和 `git diff --check` 通过。

### FAQ 直答与用户主动转人工（2026-08-11）

- LangGraph 新增 `direct_faq_answer` 节点。混合检索结果通过原有最低置信度和分数窗口后，如果排名第一的可靠知识是 active FAQ，直接返回该条标准答案，不再调用 DeepSeek。
- FAQ 直答只保留排名第一的引用，仍经过内部资料表达和输出安全清理；不受非工作时段的生成模型缩权影响。低置信度相似文本仍按“未命中”转人工，不会被误当成 FAQ。
- `SafetyPolicy` 新增用户主动转人工识别，覆盖“转人工”“人工服务”“人工客服”“人工”“不要/别用机器人”“真人客服”和“转接客服”。命中后从 `safety_guard` 直达 `handoff`，记录 `user_requested_handoff` 标签。
- 实际运行服务验证：B5 含量问题直接回复“宝宝，0.20%”，轨迹不含 `generate_answer`；“不要机器人，我要人工服务”正确转人工且无知识引用。
- 回归覆盖 FAQ 直答、模型返回资料不足、模型非工作时段、产品知识生成失败以及5类人工请求说法；验证为53 passed，`compileall` 和 `git diff --check` 通过。
- 用户主动要求人工时使用专用确认话术“好的，这就为您转接人工～”；不良反应、售后、低置信度等系统判定的转人工场景仍保留原有原因说明。

## 2026-08-12

### 现有 FAQ 被范围路由拦截的修复

- 复现“为什么没装满”“容量”和“为什么没装满/容量”：三种问法都能在 FAQ 中以 `0.99–1.00` 分命中 `三蛋丸微信群QA记录!80`，但旧 `intent_router` 因关键词列表缺少“装满/容量”，在 RAG 前就进入 `out_of_scope_response`，因此测试页显示“本次未使用知识文档”。
- 在意图路由前新增 active FAQ 高置信度预识别，门槛为 `0.90`。命中后不受手工业务关键词列表限制，只路由至 FAQ 库，再经原有相关性门控进入 `direct_faq_answer`。
- 未直接把“容量”硬编码到业务词表，因此今后新增的非典型 FAQ 标题也能利用同一机制进入 RAG。纯问候仍优先走问候分支，用户主动转人工仍在更前的 `safety_guard` 处理。
- 回归测试覆盖三种容量问法，并保留范围外、无厘头、缺产品名和多轮上下文边界；验证为56 passed。

### 通用多轮上下文修复

- 复现“美白推荐 → 还有其他的吗 → 这些都可以美白吗”：原因不是第三句缺少美白关键词，而是 LangGraph 仅保存上一产品，没有独立保存会话主题、业务意图、已回答知识和产品集合；第二轮的普通 FAQ 意图还会覆盖原推荐主题。
- 将会话主题建模为 `topic_query` / `topic_intent` / `topic_document_ids` / `topic_products`，不再依赖上一节点的瞬时意图。
- 通用识别追加式续问（“还有别的吗/再推荐”）、集合指代（“这些/它们/前面的”）和单产品指代（“这个/这款”）。追加问题使用原主题重写，并排除已回答文档以及同一产品的所有别名；集合确认把历史引用以 `conversation_context` 通道重新交给生成节点。
- 修复不绑定美白词表：回归同时覆盖“抗衰推荐 → 还有别的吗 → 它们都适合油皮吗”和原有“5%传明酸 → 这个怎么用”。
- 真实 DeepSeek 三轮验证成功：第二轮不再重复已推荐的夜猫子精华，第三轮继承历史引用并对各产品提亮/美白定位作区分回答。验证为58 passed，`compileall` 和 `git diff --check` 通过。

### 负面情绪与智能回答分流

- 修复“我现在很不满意”被当成范围外问题：原因是 `strong_emotion` 只包含“骗子/垃圾/气死/太差”等少量完整短语。新增通用模式检测，覆盖“不+强调副词+满意”、失望、生气、糟糕/离谱/过分及“什么态度/没人管/给个说法”等投诉语气。该判断继续位于 `safety_guard`，早于意图和RAG。
- 缩小 `direct_faq_answer` 边界：含量、容量、香型、发货规则等单一标准事实仍直答；推荐、选择、对比、搭配、适合性和多轮综合问题统一交给 DeepSeek 结合多条可靠知识生成。
- 重排知识路由优先级：开放式综合意图优先于“高置信度FAQ”，避免“有什么美白产品推荐”因Top1是FAQ而机械复制单条话术。
- DeepSeek 系统提示词加入任务型约束：推荐需回应需求、选择有依据的候选并说明侧重点；对比按同一维度对齐；搭配明确能否同用和顺序；信息会实质影响选择时允许一个简短追问。同时明确“提亮/去黄/净透”不等同于“美白特证”。
- 真实服务验证：强负面情绪从 `safety_guard` 直接转人工；美白推荐调用 DeepSeek 综合 FAQ 与产品介绍；B5含量仍使用FAQ标准答案。回归覆盖正向误报边界、推荐、对比、搭配和模型失败转人工。

### 全面测试用例文档

- 在根目录新增 `TEST_CASES.md`，作为当前拖音 Agent 的手工验收、业务回归和发布准入基线。
- 文档包含161条编号用例，覆盖15条P0发布阻断场景，以及主动转人工、强负面情绪、高危规则、范围路由、FAQ直答、产品RAG、LLM推荐/对比/搭配、多轮上下文、安全降级、输出合规、引用轨迹、API鉴权/幂等、知识构建和非功能稳定性。
- 为LLM场景定义“事实+行为约束”验收方式，不锁死逐字文案；附含本地执行命令、测试记录模板和灰度发布标准。

### 自动化验收执行与测试报告

- 将 `TEST_CASES.md` 的高风险、主动转人工、负面情绪、范围路由、FAQ、推荐/综合回答、多轮上下文、输出语言、幂等与脱敏场景落地为 `tests/test_acceptance_cases.py`，新增52项可重复执行的业务验收测试。
- 全量自动化最终结果为 `114 passed, 1 failed`（115项）；业务验收集为 `51 passed, 1 failed`（52项）。唯一失败是 `FAQ-009 / AM质地为什么这么稀`。
- 根因定位：正确 FAQ `AM质地稀` 是混合检索第一名、源行62、分数0.8588，但低于前置 FAQ 预识别阈值0.90；同时未识别明确产品，导致请求在正式RAG前被范围路由拦截。该缺陷本轮仅记录，没有修改业务逻辑。
- 真实 DeepSeek 冒烟覆盖强负面情绪、B5数值、美白推荐、传明酸对比、无知识推荐转人工、A醇搭配和失败FAQ；6项通过、1项失败，与确定性测试结论一致。
- 性能小样本：FAQ直答20次 P50/P95 为22.1/22.8ms；DeepSeek综合回答3次 P50/P95 为2263.4/3167.1ms。
- 知识确定性、百分比、PII、订单表排除、冲突隔离重点检查6项通过；`compileall` 与 `git diff --check` 通过。
- 根目录新增 `TEST_REPORT_2026-08-12.md`。当前测试门禁未通过，不建议进入抖音灰度；还需补做真实抖音端到端、100会话、20轮长会话、并发压力和至少50条真实客服问题人工复核。
- 测试时确认本地Qdrant存储不适合服务进程与测试进程同时打开；固定使用 `.venv.nosync` 且在测试前停止本地服务。生产环境应使用Qdrant Server。
- 应用户要求补充逐条对话实录：新增可复跑脚本 `scripts/run_conversation_transcript.py`，使用真实 DeepSeek 执行98组场景、113条消息，并把每轮用户输入、客服完整原文、decision、转人工原因、风险标签、LangGraph轨迹和知识引用写入 `TEST_CONVERSATION_REPORT_2026-08-12.md`，原始结构化结果写入 `test_results/conversation_results_2026-08-12.json`。
- 对话批量结果为83组决策通过、8组决策失败、7组需人工语义复核。除已知 `FAQ-009` 外，还发现混合问候被判范围外、VCIP未命中走澄清而非人工、综合回答偶发不足，以及无上下文“这几款”产生虚假产品上下文等问题；已如实补入总测试报告，未在测试任务中修改业务逻辑。

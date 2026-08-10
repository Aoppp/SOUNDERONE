# Hand-off（2026-08-10 周一衔接）

## 当前状态

项目已具备可运行、可测试的多平台客服 Agent MVP 骨架，但不应直接连接生产店铺。默认 `LLM_PROVIDER=mock`，知识库 `knowledge/sample.json` 明确为虚假测试数据。真实平台 Adapter、数据库持久化和正式知识仍待输入。

自动化测试最后一次执行结果为 15 passed；本地根提交是 `2e2a5d6`。GitHub 远程目前仍为空，原因不是 SSH 权限，而是 iCloud 把工作区和 Git 对象自动卸载为 `dataless`，push 无法读取完整对象。详见 `development_log.md`。

## 周一先做：恢复本地文件并推送

1. Finder 右键 `/Users/ao/Desktop/SounderOne客服开发`，选择“立即下载”。
2. 确认 `ls -lO app/main.py .git/objects/*/* | head` 不再显示 `dataless`。
3. 删除或忽略 `development_log.md.icloud-placeholder` 与 `hand_off.md.icloud-placeholder`；它们是不可读占位备份。
4. 执行：

```bash
git add .
git commit --amend --no-edit
git fsck --full
UV_CACHE_DIR=/tmp/sounderone-uv-cache uv run pytest -q
git push -u origin main
```

远程地址：`git@github.com:Aoppp/SOUNDERONE.git`。

## 恢复后业务推进顺序

1. 把正式知识资料放入单独目录，先做来源、版本、生效时间、负责人和敏感内容盘点，不要直接覆盖测试数据。
2. 向业务方确认客服系统、工作时间、转人工队列和平台权限；优先拿到抖音脱敏 webhook/回复/转人工样例。
3. 建立 50–100 条真实问题的评测集，覆盖正常 FAQ、未知问题、不良反应、退款投诉、功效禁词和夜间场景。
4. 配置 GitHub CI、Secret 和分支保护。

## 运行方式

```bash
cp .env.example .env
UV_CACHE_DIR=/tmp/sounderone-uv-cache uv venv --python /Users/ao/anaconda3/bin/python
UV_CACHE_DIR=/tmp/sounderone-uv-cache uv sync --extra dev
UV_CACHE_DIR=/tmp/sounderone-uv-cache uv run pytest
UV_CACHE_DIR=/tmp/sounderone-uv-cache uv run uvicorn app.main:app --reload
```

详见 `README.md`。接口文档在服务启动后的 `/docs`。

## 尚缺资料/权限

- 正式产品 SKU、成分/浓度/禁忌、搭配顺序、价格活动、话术、FAQ、培训材料和素材 URL。
- 九个平台应用凭证、权限范围、官方回调样例、客服系统对接方式。
- 旺店通企业版 API 文档和只读测试凭证。
- 人工工作时间、节假日规则、技能组、SLA、升级路径。
- 数据控制方/处理方责任、留存周期、删除流程、日志脱敏与安全审计要求。

## 重要限制

- 不要把 `knowledge/sample.json` 当成品牌事实；每条都标记为测试数据。
- 不要给 Agent 退款、补发或改订单权限。订单能力应先只读并经过脱敏和审计。
- 不良反应必须直接转人工，不提供诊断；涉及强情绪、监管、法律和媒体同样转人工。
- GenericAdapter 不是任何平台的真实协议实现，上线前必须做官方验签、幂等、重放保护、限流和沙箱认证。
- 当前机器未发现 Docker CLI，容器镜像尚未实际构建；在 CI 或装有 Docker 的环境补跑 `docker compose build`。

## 下一阶段完成定义

- 抖音真实消息能通过官方验签进入系统、可靠回复或转人工，失败可重试且不重复发送。
- 正式知识库可追溯到版本和负责人，评测集通过业务验收。
- 会话、审计和工单持久化；人工端能看到完整上下文与引用。
- 监控至少覆盖错误率、延迟、转人工率、无答案率、禁词命中和平台发送失败。


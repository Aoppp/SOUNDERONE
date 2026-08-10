# 抖音单平台接入边界

当前只保留 `douyin` 和本地 `simulator` 两个消息入口。`DouyinAdapter` 目前接受归一化开发载荷，用于让 LangGraph 和混合 RAG 在没有平台凭证时也能完整测试：

```json
{
  "message_id": "douyin-message-id",
  "conversation_id": "douyin-conversation-id",
  "user_id": "douyin-user-id",
  "text": "5%传明酸怎么用？",
  "metadata": {}
}
```

正式联调前必须从抖店开放平台确认应用类型和客服消息权限包，再补齐：

1. 官方回调载荷解析和 AES 解密。
2. HMAC-SHA256 签名校验、时间窗和重放防护。
3. `app_key` / `app_secret` / access token 生命周期。
4. 客服消息发送、限流、超时和可重试错误分类。
5. 测试店铺端到端认证。

在拿到官方回调样例前，不在代码中猜测平台字段或签名算法。

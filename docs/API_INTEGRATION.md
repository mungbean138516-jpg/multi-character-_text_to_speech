# 外部 API、密钥与计费设计

## 为什么分成两个模型

自动角色识别不是 TTS 自带能力。

- 千问负责：人物、别名、指代、特质、当前情绪和台词归属。
- TTS 负责：按已经确定的文本、voice、语速与音高生成音频。

将两层拆开后，任何一家 TTS 都能被替换，而角色纠错和项目数据仍然保留。

## 千问

本项目使用百炼 OpenAI 兼容 Chat Completions：

```text
POST {DASHSCOPE_LLM_BASE_URL}/chat/completions
Authorization: Bearer <DASHSCOPE_API_KEY>
Content-Type: application/json
```

请求要求 `response_format: {"type": "json_object"}`，提示中明确要求 JSON。返回仍会经过本地解析和枚举校验；失败则退回规则结果。

配置：

```bash
export DASHSCOPE_LLM_BASE_URL="https://YOUR_WORKSPACE_ID.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
export DASHSCOPE_LLM_MODEL="qwen3.7-flash"
```

需要更高角色识别质量时可改成 `qwen3.7-plus`，代码不变。

官方资料：

- [OpenAI Chat 兼容](https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope)
- [千问结构化输出](https://help.aliyun.com/zh/model-studio/qwen-structured-output)

## 百炼非实时 TTS

当前 provider 请求：

```text
POST https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer
Authorization: Bearer <DASHSCOPE_API_KEY>
Content-Type: application/json
```

示意请求：

```json
{
  "model": "cosyvoice-v3-flash",
  "input": {
    "text": "火车来啦！",
    "voice": "longjielidou_v3",
    "format": "wav",
    "sample_rate": 24000,
    "rate": 1.08,
    "pitch": 1.3,
    "language_hints": ["zh"],
    "enable_aigc_tag": true
  }
}
```

注意：

- model 与 voice 必须兼容；
- 系统音色、复刻音色和设计音色不能跨模型乱用；
- 非流式响应给出的音频 URL 会过期，必须立即下载；
- 真实费用以供应商控制台为准，不在前端硬编码；
- 每个未缓存片段目前是一条请求；内容哈希缓存会跳过未变化片段；
- 相邻同角色短句合并仍是下一阶段优化。

官方资料：

- [非实时 TTS HTTP API](https://help.aliyun.com/zh/model-studio/cosyvoice-tts-http-api)
- [语音合成模型对比](https://help.aliyun.com/zh/model-studio/tts-model/)
- [CosyVoice 音色列表](https://help.aliyun.com/en/model-studio/cosyvoice-voice-list)

## 声音设计与复刻

MVP 不需要声音设计。后续可用 `cosyvoice-v3.5-plus` / `flash` 将“60 岁、低沉、克制而威严的男声”生成专属 voice。流程必须是：

1. 生成 2–3 个试听候选；
2. 用户明确确认；
3. 保存 voice ID 与 target model；
4. 全书固定使用；
5. 模型升级前重新试听回归。

声音复刻还需要被复刻者明确授权、可撤回记录和防滥用审核。不能把“上传一段公众人物音频就能模仿”做成默认功能。

## 平台统一 Key

适合普通消费者：

- 用户购买应用内积分；
- 服务端用团队 Key 调供应商；
- 用量账本记录 `user_id / job_id / model / 字符数 / 状态 / 成本`；
- 生成前预授权额度，成功后结算，失败释放；
- 单独业务空间、模型白名单、IP 白名单和每日预算；
- Key 轮换不影响客户端。

## BYOK

适合开发者或内测：

- 浏览器只把 Key 通过 TLS 发送到安全后端；
- 后端加密保存，或仅在当前会话内存中使用；
- 绝不写日志、异常消息或前端存储；
- 提供删除与连通性测试；
- 不让一个用户看到另一个用户的 provider 错误详情。

对于这次课堂 MVP，不建议做 Key 输入框。团队在演示机服务端配置一个受限 Key 更快、更安全。

## 成本与限流

不要把 LLM Token 和 TTS 字符混成一个指标：

- 角色分析通常按输入 / 输出 Token；
- TTS 通常按有效字符或供应商定义的语音用量；
- 一个章节还会产生多个网络请求。

正式账本至少记录：

```text
analysis_input_tokens
analysis_output_tokens
tts_characters
tts_request_count
cache_hit_count
provider_model
provider_request_id
```

Alpha 版的 `/api/render/plan` 已返回：

```text
segments
cached_segments
estimated_requests
billable_characters
estimated_billable_characters
estimated_cost_cny
```

人民币估算只有在服务端配置
`DASHSCOPE_TTS_PRICE_PER_10K_CNY` 后才显示；这个值应从当前供应商控制台确认，不能在代码里长期写死。真实账单仍是最终依据。

渲染时每段最多尝试 `APP_TTS_MAX_ATTEMPTS` 次。若仍失败，任务返回 `partial`，成功段已进入缓存；用户重新提交时只会请求没有缓存的片段。正式版仍需加入队列、指数退避、幂等业务 job ID、缓存淘汰和预算硬上限。多个 Key 可能仍共享账号级限流，不能用“多建 Key”代替队列。

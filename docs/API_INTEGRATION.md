# 外部 API、密钥与计费设计

## 为什么分成两个模型

自动角色识别不是 TTS 自带能力。

- 千问负责：人物特质、当前情绪和复杂台词归属建议。
- TTS 负责：按已经确定的文本、voice、语速与音高生成音频。

将两层拆开后，任何一家 TTS 都能被替换，而角色纠错和项目数据仍然保留。

## 消费层不暴露这些概念

本文件面向开发者。普通用户页面默认只显示“自动识别角色”“试听”“换声音”“纠错”和“开始生成”。模型、provider、Token、计费请求和输出格式必须留在服务端或高级设置；内部诊断音不进入用户界面。

## Mac 免费本地语音

在 macOS 上，`MacOSLocalTTSProvider` 会枚举已经安装的中文系统声音，
优先选择普通话标准人声并避开系统效果音。每句先由系统 `say` 生成，
再由 `afconvert` 转成统一的 24kHz、16-bit、单声道 WAV，因此可以直接
进入现有缓存、逐句播放和章节拼接链路。

儿童和老年角色只使用温和的节奏差异；系统没有合适的对应声线时，
宁可复用自然中文人声，也不通过夸张升降调制造失真。这个 provider
不需要 API Key，但只适用于安装了中文系统声音的 Mac。

## 免费 Neural 中文声线包

`NeuralVoicePackProvider` 是课堂体验用的可选适配器。安装：

```bash
python3 -m pip install edge-tts miniaudio
```

`edge-tts` 从 Microsoft Edge 使用的在线语音服务取得 MP3，`miniaudio`
在本机把它解码、重采样为统一的 24kHz、16-bit、单声道 WAV。之后仍
进入同一内容缓存、逐句重做、后台任务和章节拼接链路。

免费版只自动使用五类经过筛选的中文 Neural 角色声线，并由应用内部
`voice_id` 确定性映射：

- `Xiaoxiao`：女旁白；
- `Xiaoyi`：成年女性使用原生参数；小女孩复用其更活泼的普通话底声并采用独立童声参数；
- `Yunyang`：专业叙事取向的成年男性；
- `Yunxia`：小男孩，配合轻微童声参数。

更多年龄、方言和定制音色保留在高级 provider 中；未连接付费服务时
在普通用户界面标灰，不会自动分配。

Neural provider 的旁白和成年角色使用原生音高；小男孩保持
`+2Hz / +4%`，小女孩使用 `+8Hz / +6%` 的受控童声参数。老年角色回退到
对应性别的自然成年声，不再用降调模拟年龄。这个
provider 不需要 API Key，但需要联网，上游也没有为本项目提供 SLA；
因此它只适合原型和课堂体验。正式商业版本应换成官方 Azure Speech、
百炼 CosyVoice 等有明确服务条款、计费和稳定性承诺的接口。

参考：

- [edge-tts 项目](https://github.com/rany2/edge-tts)
- [Microsoft 中文语音与角色支持](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support)

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
    "rate": 1.04,
    "pitch": 1.09,
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

## 发音词典与单句生成

`AnalysisResult.pronunciations` 保存项目级“原词 → 朗读写法”。`audio.py` 在调用 provider 前生成临时 `spoken_text`：

- 按原词长度从长到短匹配；
- 一次替换，不让替换结果继续触发另一条规则；
- `segment.text` 与页面原文不变；
- 缓存键使用 `spoken_text`，所以只让受影响的句子失效。

`POST /api/render/segment` 接收完整项目和 `segment_id`，只抽出该句进入标准渲染管线。它仍执行付费确认、字符限制、重试、WAV 校验和内容缓存；下一次生成全书时会复用这句结果。

## 后台章节任务与首批播放

消费界面使用异步任务接口，不需要让一个 HTTP 请求一直等到整章拼接完成：

```text
POST /api/render/jobs
GET  /api/render/jobs/{job_id}
POST /api/render/jobs/{job_id}/pause
POST /api/render/jobs/{job_id}/resume
```

创建任务仍需提交当前章 `analysis`、provider、输出格式与付费确认。服务端返回 `202` 和 `job_id`，随后每完成一句就在任务状态的 `playable_segments` 中增加一个 WAV URL。浏览器从第一句开始连续播放，同时轮询剩余进度。

暂停只在当前供应商请求结束后的句子边界生效，避免留下半个 WAV。继续任务会按完全相同的内容哈希缓存从头快速校验，已成功句子不会再次调用供应商；`partial` 任务也用同一方式只补缺失内容。

任务公开快照只保存状态、计数和输出 URL，不复制分析原文；快照位于输出根目录的私有 `_jobs` 子目录。浏览器把每章最近的 `job_id` 保存在 IndexedDB 草稿中，所以页面刷新后可以继续查询。当前版本不承诺 Python 服务整体重启后的自动续跑。

## 书籍项目与跨章角色

`POST /api/import/epub` 直接接收 `application/epub+zip` 二进制，并返回版本化的 `BookProject`；EPUB 不会被转成 base64 塞进 JSON。浏览器随后只把当前章节送到 `/api/analyze`，避免一次把几十万字交给大模型。

`/api/analyze` 的可选 `character_registry` 包含本书已确认的角色。响应会返回更新后的同名字段：

- 明确姓名或别名匹配时沿用稳定 ID 和 voice；
- `locked=true` 的人工资料优先；
- 未匹配人物在容量内加入主要角色；
- 超过 10 位后使用“其他角色”，仍保留全部台词。

这套数据属于产品层，不绑定百炼。未来接入第二家 TTS 时，角色身份、别名和人工纠错仍然有效。

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

渲染时每段最多尝试 `APP_TTS_MAX_ATTEMPTS` 次。若仍失败，任务返回 `partial`，成功段已进入缓存；用户继续任务时只会请求没有缓存的片段。Alpha 已有受限并发队列，正式版仍需加入指数退避、可跨进程恢复的幂等业务 job ID、缓存淘汰和预算硬上限。多个 Key 可能仍共享账号级限流，不能用“多建 Key”代替队列。

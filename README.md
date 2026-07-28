# 声场 VoxCast

> 把中文小说自动拆成旁白与角色台词，生成角色卡、匹配不同声线，并在人工确认后合成多角色听书。

[![CI](https://github.com/mungbean138516-jpg/multi-character-_text_to_speech/actions/workflows/ci.yml/badge.svg)](https://github.com/mungbean138516-jpg/multi-character-_text_to_speech/actions/workflows/ci.yml)

当前版本是可实际试用的 `0.2 Alpha`。它不训练 TTS 模型，而是把真正困难且有产品价值的中间层做出来：

```mermaid
flowchart LR
    A["小说文本"] --> B["旁白 / 对话分段"]
    B --> C["角色与说话人识别"]
    C --> D["角色特质与声线匹配"]
    D --> E["人工纠错台"]
    E --> F["逐段 TTS"]
    F --> G["缓存、拼接与 WAV / MP3"]
```

## 现在已经能做什么

- 粘贴或拖入 TXT，自动识别 UTF-8、UTF-16、GB18030 编码。
- 用堆栈解析 `“”`、`「」`、`『』`、英文双引号及嵌套引号。
- 离线识别 `张三说：“……”`、`“……”张三问道`、`林夏笑了笑：“……”` 等常见句式。
- 将旁白和人物分开，推断有证据支持的年龄段、性别呈现、声音特质与当前情绪。
- 低置信度结果明确标黄或标红，不把猜测伪装成事实。
- 自动从同一 CosyVoice 模型的兼容音色库中选角，避免跨模型混用 voice ID。
- 网页中修改角色名、别名、年龄、性别呈现、声线、台词文字、情绪和说话人。
- 可把重复角色人工合并；被改过的角色与台词显示“人工锁定”。
- 项目自动保存在当前浏览器，可刷新恢复，也可随时删除本机保存副本。
- 无 API Key 时，使用浏览器 Web Speech API 做真实多人试听。
- 无 API Key 时，使用离线诊断音跑通服务端“逐段生成 → 插入停顿 → 拼接 → 下载 WAV”。
- 配置百炼后，调用真实 CosyVoice HTTP API 并立即下载供应商的临时音频。
- 生成前显示未缓存字符、请求数与可选人民币估算；重复片段使用内容哈希缓存。
- 某个片段失败时保留成功缓存，按钮只重试失败片段。
- 可导出 WAV；服务器安装 ffmpeg 后也可输出 MP3。
- 可选用千问增强别名、指代和隐含说话人的识别；失败时自动退回本地规则结果。
- 零 Python 第三方运行依赖，现场机器只需要 Python 3.10+。

## 30 秒启动

```bash
git clone https://github.com/mungbean138516-jpg/multi-character-_text_to_speech.git
cd multi-character-_text_to_speech
python3 -m audiobook_app
```

浏览器打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)，然后：

1. 点击“载入原创演示文本”。
2. 或把自己的合法 TXT 拖入输入框。
3. 点击“开始选角”。
4. 检查角色卡、合并别名或修改台词。
5. 点击“浏览器多人试听”。
6. 查看预算后生成离线检测音或百炼真实语音。

WAV 输出只需要 Python。MP3 需要系统已安装 `ffmpeg`；仓库里的 Dockerfile 已包含它。

也可以直接分析文件：

```bash
python3 -m audiobook_app analyze examples/demo_chapter.txt
```

## 连接阿里云百炼

密钥只能放在服务端环境变量中，不能写进 `app.js`、Git、浏览器 `localStorage` 或日志。

```bash
export DASHSCOPE_API_KEY="your-api-key"
export DASHSCOPE_WORKSPACE_ID="your-workspace-id"
export DASHSCOPE_LLM_BASE_URL="https://YOUR_WORKSPACE_ID.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
export DASHSCOPE_LLM_MODEL="qwen3.7-flash"
export DASHSCOPE_TTS_MODEL="cosyvoice-v3-flash"
# 可选：把下方占位符换成供应商控制台显示的当前数字单价
# export DASHSCOPE_TTS_PRICE_PER_10K_CNY="<每万字符人民币单价>"

python3 -m audiobook_app
```

也可参考 `.env.example`。本项目刻意不自动读取 `.env`，避免误把文件暴露或让现场环境行为不透明；使用 Docker、IDE 或进程管理器时，让它负责注入环境变量即可。

百炼当前的非实时语音合成接口是：

```text
POST https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer
Authorization: Bearer <DASHSCOPE_API_KEY>
```

官方将 HTTP 模式定位为有声阅读和音频内容制作场景。返回的完整音频 URL 只有有限有效期，所以适配器会立即下载并保存 WAV。参考：

- [百炼非实时 TTS HTTP API](https://help.aliyun.com/zh/model-studio/cosyvoice-tts-http-api)
- [百炼语音合成模型选型](https://help.aliyun.com/zh/model-studio/tts-model/)
- [CosyVoice 音色列表](https://help.aliyun.com/en/model-studio/cosyvoice-voice-list)
- [千问 OpenAI 兼容接口](https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope)

默认 TTS 模型与 voice ID 都在环境变量和 `audiobook_app/voices.py` 中集中管理。供应商模型更新或下线时，不需要改业务流程。

## 用户到底要不要自己买 Token？

不一定。产品有两种正常模式：

| 模式 | 用户体验 | 费用归属 | 适合阶段 |
|---|---|---|---|
| 平台统一 Key | 用户直接上传文本、购买应用内积分 | 团队向供应商付费 | 正式消费产品，体验最好 |
| BYOK | 用户在安全设置中绑定自己的供应商 Key | 用户直接向供应商付费 | 开发者工具、内测 |

当前 Alpha 用团队自己的服务端 Key 最省事，普通用户不需要理解 Token。正式上线后建议采用“平台积分为默认，BYOK 为高级选项”；无论哪一种，永久 Key 都不能到达浏览器。

## 目录

```text
audiobook_app/
  analyzer.py       离线文本分段与说话人基线
  textio.py         UTF-8 / UTF-16 / GB18030 TXT 解码
  qwen.py           千问 JSON 增强与安全降级
  voices.py         语义特征到供应商音色的确定性映射
  audio.py          缓存、失败重试、WAV 拼接与 MP3 转码
  server.py         零依赖网页与 JSON API
  providers/
    base.py         TTS 统一接口
    demo.py         离线诊断音适配器
    dashscope.py    百炼非实时 TTS 适配器
web/
  index.html        单页工作台
  styles.css        响应式界面
  app.js            角色纠错、浏览器试听、生成控制
tests/              全离线单元测试
examples/           原创演示文本
docs/               PRD、架构、路线、演示与 Qoder 记录
```

## API

| 方法 | 路径 | 作用 |
|---|---|---|
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/config` | 可用分析器、TTS、声线和限制；不返回密钥 |
| `POST` | `/api/analyze` | 文本 → 角色卡与台词轨道 |
| `POST` | `/api/render/plan` | 生成前统计缓存、请求、计费字符与可选费用 |
| `POST` | `/api/render` | 使用离线或百炼 provider 生成 WAV / MP3 |

完整数据合同见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 测试

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q audiobook_app
```

当前 27 个测试不访问公网、不消耗 API 额度，覆盖：

- 前置、后置和动作式说话人；
- 嵌套、同型嵌套、未闭合和英文引号；
- UTF-8 BOM、UTF-16、GB18030 与二进制拒绝；
- 老人、儿童角色类型；
- 无对话文本的旁白降级；
- 人物特质不从相邻角色错误借用；
- 声线年龄与性别匹配；
- WAV 参数检查、静音插入、MP3 输出与完整任务；
- 内容哈希缓存命中、部分失败和只重试失败片段；
- HTTP 分析 → 计划 → 渲染 → 下载闭环与缓存目录隔离；
- 调用前的字符限额。

## 稳定演示

任务书要求的 2 分钟以上现场 Demo 已写成逐步脚本：

- [演示脚本](docs/DEMO_SCRIPT.md)
- [1.5 天冲刺与七人分工](docs/DEVELOPMENT_ROADMAP.md)
- [Qoder Prompt 与留痕模板](docs/QODER_LOG.md)

PPT 按当前安排继续暂缓，等进入路演制作阶段再从真实 Demo 截图生成。

## 当前边界

这一版仍然不把“整本书全自动”当成已经完成：

- 嵌套引号和明确说话人已有本地基线；复杂别名、跨章指代和自由间接引语仍需要千问与人工确认。
- 浏览器试听依赖操作系统安装的中文声音，音质和声线数量因设备而异。
- 服务端诊断音是可区分的音调，不冒充真实 TTS。
- 当前已有 WAV / 可选 MP3、片段缓存和失败重试；EPUB、后台队列和多章项目仍在后续阶段。
- 浏览器草稿只保存在当前设备的 `localStorage`，不是账号云同步；共享设备用完请点击“删除保存副本”。
- 不提供小说网站抓取。只处理用户自有、已授权或公版文本。
- 不开放声音克隆；未来加入时必须核验被克隆者授权，并禁止仿冒公众人物。

## 文档导航

- [产品需求 PRD](docs/PRD.md)
- [系统架构](docs/ARCHITECTURE.md)
- [开发路线与团队分工](docs/DEVELOPMENT_ROADMAP.md)
- [真实 API 接入与计费设计](docs/API_INTEGRATION.md)
- [现场演示脚本](docs/DEMO_SCRIPT.md)
- [Qoder 使用记录](docs/QODER_LOG.md)
- [贡献指南](CONTRIBUTING.md)

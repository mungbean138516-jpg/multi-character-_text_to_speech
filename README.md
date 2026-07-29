# 声场 VoxCast

> 上传一本中文小说，系统自动认出每个角色，用不同声音读给你听。

[![CI](https://github.com/mungbean138516-jpg/multi-character-_text_to_speech/actions/workflows/ci.yml/badge.svg)](https://github.com/mungbean138516-jpg/multi-character-_text_to_speech/actions/workflows/ci.yml)

当前版本是可实际试用的 `0.6 Natural Voice Alpha`。它不训练 TTS 模型，而是把大模型、角色一致性、多家语音服务、音频拼接和播放器整合成普通人会用的产品：

```mermaid
flowchart LR
    A["上传或粘贴小说"] --> B["自动识别人物"]
    B --> C["自动分配声音"]
    C --> D["试听与一键纠错"]
    D --> E["生成多人有声书"]
```

## 现在已经能做什么

- 默认使用“自动识别”，普通用户无需选择模型、供应商、Token、SSML 或音频轨道。
- 粘贴或拖入 TXT，自动识别 UTF-8、UTF-16、GB18030 编码。
- 导入合法 EPUB，读取书名、作者与书脊顺序，自动拆成可逐章分析的书籍项目。
- EPUB 解包限制文件数、总大小、单文件大小与异常压缩比，并拒绝越界路径和加密 / DRM 内容。
- 章节选择、上一章 / 下一章和已分析标记都在输入区直接可见；切章前自动保存当前修改。
- 全书角色注册表跨章保留稳定 ID、别名、声线和人工锁定；旁白之外最多保留 10 位主要角色，超出者安全归入“其他角色”。
- 可下载或重新打开 `.voxcast.json` 项目备份，保留章节、角色、台词纠错和全书发音记忆。
- 用堆栈解析 `“”`、`「」`、`『』`、英文双引号及嵌套引号。
- 离线识别 `张三说：“……”`、`“……”张三问道`、`林夏笑了笑：“……”` 等常见句式。
- 将旁白和人物分开，推断有证据支持的年龄段、性别呈现、声音特质与当前情绪。
- 低置信度结果明确标黄或标红，不把猜测伪装成事实。
- 自动从同一 CosyVoice 模型的 24 个精选兼容音色中选角，避免跨模型混用 voice ID。
- 角色卡只突出“系统判断、默认声音、试听和更换”；别名、证据等专业信息收进高级设置。
- 网页中修改角色名、别名、年龄、性别呈现、声线、台词文字、情绪和说话人。
- 可把重复角色人工合并；被改过的角色与台词显示“人工锁定”。
- 项目自动保存在当前浏览器的 IndexedDB，可容纳多章项目、刷新恢复，也可随时删除本机保存副本；旧浏览器回退到 localStorage。
- 无 API Key 时，使用浏览器 Web Speech API 做多人试听；优先选择标准中文人声、避开效果音声线，并把角色变调限制在自然范围内。
- Mac 会自动发现已经安装的中文系统声音，免费生成真实朗读 WAV；它同样支持逐句缓存、边生成边播放和完整章节导出。
- 每句话都提供“角色错了”“这个字读错了”“重做这句”三个低门槛纠错入口。
- 全书发音词典会记住人名、多音字和专有名词的朗读写法，原文显示保持不变。
- `/api/render/segment` 只生成被修改的一句；生成全书时会直接复用这一句的缓存。
- 旧版诊断音只保留给自动测试，已经从普通用户界面和默认 API 路径移除，不再把测试音当成可用听书结果。
- 配置百炼后，调用真实 CosyVoice HTTP API 并立即下载供应商的临时音频。
- 生成前显示未缓存字符、请求数与可选人民币估算；重复片段使用内容哈希缓存。
- 某个片段失败时保留成功缓存，按钮只重试失败片段。
- 当前章节进入后台任务后会逐句生成；第一句完成即可播放，不必等待整章拼接完成。
- 显示章节生成进度，支持暂停、继续和失败补齐；暂停只会在当前句完成后生效。
- 任务 ID 保存在浏览器本机草稿中，刷新页面后会自动接回进度和已完成片段。
- 可导出 WAV；服务器安装 ffmpeg 后也可输出 MP3。
- 可选用千问增强人物特质和复杂台词归属建议；失败时自动退回本地规则结果。
- 零 Python 第三方运行依赖，现场机器只需要 Python 3.10+。

## 30 秒启动

```bash
git clone https://github.com/mungbean138516-jpg/multi-character-_text_to_speech.git
cd multi-character-_text_to_speech
python3 -m audiobook_app
```

浏览器打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)，然后：

1. 点击“载入原创演示文本”。
2. 或把自己的合法 TXT / EPUB 拖入输入框。
3. EPUB 导入后选择一章，点击“自动识别角色”。
4. 试听角色声音；有需要时直接更换。
5. 切到下一章继续识别，已经确认的角色和声音会自动沿用。
6. 点击“从头试听”，或从任意一句开始听。
7. 发现串台或错音时，用句子下方的纠错按钮修正。
8. 在 Mac 上点击“免费生成（Mac）”，或在高品质语音已连接时点击“开始生成”；第一批句子完成后即可播放。

WAV / MP3 格式等选项放在“导出与开发检查”中，不干扰普通用户主流程。MP3 需要系统安装 `ffmpeg`；仓库里的 Dockerfile 已包含它。

如果 Mac 没有显示“免费生成（Mac）”，请前往“系统设置 → 辅助功能 → 朗读内容”，下载至少一个中文系统声音后重启本项目。Apple 的官方步骤见[更改 Mac 用于朗读文本的声音](https://support.apple.com/guide/mac-help/mchlp2290/mac)。

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
  epub.py           安全 EPUB 解包、书脊解析与章节拆分
  books.py          书籍项目与章节数据合同
  registry.py       跨章节角色一致性与主要角色上限
  textio.py         UTF-8 / UTF-16 / GB18030 TXT 解码
  qwen.py           千问 JSON 增强与安全降级
  voices.py         语义特征到供应商音色的确定性映射
  audio.py          缓存、失败重试、WAV 拼接与 MP3 转码
  jobs.py           后台章节任务、进度、暂停与继续
  server.py         零依赖网页与 JSON API
  providers/
    base.py         TTS 统一接口
    macos.py        Mac 已安装中文系统声音的免费真实朗读适配器
    demo.py         仅供自动测试使用的内部音频管线适配器
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
| `POST` | `/api/import/epub` | EPUB 二进制 → 带章节的声场书籍项目 |
| `POST` | `/api/analyze` | 文本 → 角色卡与台词轨道 |
| `POST` | `/api/render/plan` | 生成前统计缓存、请求、计费字符与可选费用 |
| `POST` | `/api/render/segment` | 只重新生成指定的一句并写入内容缓存 |
| `POST` | `/api/render/jobs` | 创建后台章节生成任务 |
| `GET` | `/api/render/jobs/{job_id}` | 获取进度与已可播放片段 |
| `POST` | `/api/render/jobs/{job_id}/pause` | 在当前句完成后暂停 |
| `POST` | `/api/render/jobs/{job_id}/resume` | 继续暂停或部分失败的任务 |
| `POST` | `/api/render` | 使用 Mac 本地中文语音或百炼生成 WAV / MP3 |

完整数据合同见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 测试

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q audiobook_app
```

当前 55 个测试不访问公网、不消耗 API 额度，覆盖：

- 前置、后置和动作式说话人；
- 嵌套、同型嵌套、未闭合和英文引号；
- UTF-8 BOM、UTF-16、GB18030 与二进制拒绝；
- 老人、儿童角色类型；
- 无对话文本的旁白降级；
- 人物特质不从相邻角色错误借用；
- 声线年龄与性别匹配；
- WAV 参数检查、静音插入、MP3 输出与完整任务；
- 内容哈希缓存命中、部分失败和只重试失败片段；
- 全书发音替换、最长词优先、不级联替换和原文保留；
- 自动分析模式与单句重新生成 API；
- HTTP 分析 → 计划 → 渲染 → 下载闭环与缓存目录隔离；
- 后台任务首批可播放片段、进度、暂停、缓存续跑与私有状态隔离；
- HTML ID / JavaScript 绑定和消费级主操作契约；
- EPUB 元数据、书脊顺序、超长章节拆分、非法路径与损坏文件拒绝；
- 书籍项目往返、跨章别名匹配、人工锁定继承和主要角色溢出降级；
- 24 个精选音色的数量、唯一性与模型版本约束；
- 浏览器声线的自然变调范围、效果音规避与 Mac 本地中文语音转换；
- 调用前的字符限额。

## 稳定演示

任务书要求的 2 分钟以上现场 Demo 已写成逐步脚本：

- [演示脚本](docs/DEMO_SCRIPT.md)
- [1.5 天冲刺与七人分工](docs/DEVELOPMENT_ROADMAP.md)
- [Qoder Prompt 与留痕模板](docs/QODER_LOG.md)

PPT 按当前安排继续暂缓，等进入路演制作阶段再从真实 Demo 截图生成。

## 当前边界

这一版仍然不把“整本书全自动”当成已经完成：

- 嵌套引号和明确说话人已有本地基线；复杂自由对白仍可能需要千问建议或用户纠错。
- 浏览器试听依赖操作系统安装的中文声音，音质和声线数量因设备而异；系统没有合适的男声或女声时会优先保证自然度，而不是用极端变调硬凑年龄。
- Mac 免费生成依赖系统自带的 `say`、`afconvert` 和至少一个已下载的中文声音；其他操作系统仍可使用浏览器试听或连接 CosyVoice。
- 当前已有 EPUB、多章项目、跨章角色记忆、全书发音记忆、单句重做、后台章节任务、首批播放、暂停 / 继续、WAV / 可选 MP3、片段缓存和失败补齐。
- 跨章角色一致性只依据明确姓名和用户保存的别名；不再增加额外的人物关系推断功能。
- 刷新浏览器可以接回任务；如果整个 Python 服务进程重启，已生成片段仍可播放，但任务需要重新提交。
- 浏览器草稿只保存在当前设备的 IndexedDB，不是账号云同步；共享设备用完请点击“删除保存副本”。
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

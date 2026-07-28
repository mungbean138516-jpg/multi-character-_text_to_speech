# Contributing

## 开发前

1. 从 `main` 创建短生命周期分支。
2. 先写清一个可验证目标，不在同一 PR 混入无关重构。
3. 不提交 `.env`、API Key、用户小说、供应商生成的临时 URL 或个人数据。

## 本地检查

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q audiobook_app
python3 -m audiobook_app analyze examples/demo_chapter.txt
```

涉及网页时，再从零启动：

```bash
python3 -m audiobook_app
```

检查以下路径：

- 空文本错误；
- 演示文本分析；
- 修改角色声线；
- 修改一条台词说话人；
- 浏览器试听开始与停止；
- 离线 WAV 生成与下载；
- 未配置百炼时真实按钮禁用。

## 代码边界

- 文本识别逻辑进入 `analyzer.py` 或后续 `text/` 模块。
- 模型调用进入 `qwen.py`，不能散落在 UI。
- 供应商 TTS 进入 `providers/`。
- 供应商 voice ID 只进入 `voices.py`。
- 音频格式和拼接进入 `audio.py`。
- 前端不能知道永久 API Key。

## 新增规则

任何新的中文句式必须同时提交：

1. 最小原文；
2. 预期 speaker；
3. 失败前的回归测试；
4. 对误判风险的说明。

不要为一个具体人物姓名写硬编码。

## 新增 TTS Provider

实现 `TTSProvider.synthesize()`，并保证：

- 输出标准 WAV；
- 错误不泄露密钥和完整用户文本；
- URL 立即下载；
- 可通过环境变量禁用；
- CI 有纯离线替身；
- README 标明官方 API 与模型 / voice 兼容规则。


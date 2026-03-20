# Nanobanana2 OpenClaw Skill 🔮

> 使用 OpenClaw + Telegram 对话执行 AI 生图 / 图像编辑的技能包  
> 默认面向兼容 Gemini 图像生成接口的工作流

## 功能概览

- **文生图**：根据提示词直接生成图片
- **图生图**：基于 1 张或多张参考图生成
- **连续编辑**：基于当前会话上一张结果继续修改
- **多 API 切换**：主 API / 备用 API 自动重试与切换
- **熔断机制**：连续失败后自动冷却
- **会话隔离**：不同 `session-id` 独立保存历史
- **Dry Run**：只构造请求，不实际调用 API

---

## 目录结构

```text
nanobanana/
├── README.md
├── SKILL.md
├── .gitignore
├── scripts/
│   ├── generate_image.py
│   └── .user_api.example
└── history/
```

> 注意：真实配置文件 `scripts/.user_api` 不应提交到 GitHub。

---

## 配置方式

先复制示例配置：

```bash
cp scripts/.user_api.example scripts/.user_api
```

再编辑 `scripts/.user_api`：

```bash
# API[main] (必填)
API_KEY=YOUR-API-KEY
API_BASE=https://your-api-endpoint.example/v1/chat/completions
MODEL=gemini-3.1-flash-image-preview

# API[switch1] (可选)
API_KEY2=YOUR-API-KEY
API_BASE2=https://your-backup-api-endpoint.example/v1/chat/completions
MODEL2=gemini-3.1-flash-image-preview

# API[switch2] (可选)
API_KEY3=YOUR-API-KEY
API_BASE3=https://your-third-api-endpoint.example/v1/chat/completions
MODEL3=gemini-3.1-flash-image-preview

# 运行参数（可选）
OUTPUT_DIR=~/.openclaw/downloads/nanobanana
HISTORY_DIR=~/.openclaw/shared-skills/nanobanana/history
API_TIMEOUT=120
API_RETRY=2
CIRCUIT_BREAKER_THRESHOLD=3
MAX_INLINE_IMAGE_BYTES=15728640
MAX_INPUT_IMAGES=14
```

---

## 快速开始

### 1) 文生图

```bash
python3 scripts/generate_image.py \
  -p "一只可爱的橘猫，暖色调，电影感摄影" \
  --session-id demo-session
```

### 2) 图生图

```bash
python3 scripts/generate_image.py \
  -p "保持主体结构，改成电影感摄影风格" \
  -i /path/to/reference.png \
  --session-id demo-session
```

### 3) 多图参考

```bash
python3 scripts/generate_image.py \
  -p "将图1角色服装改成图2样式，保持图1人物脸部特征" \
  -i /path/to/file1.png \
  -i /path/to/file2.png \
  --session-id demo-session
```

### 4) 基于上一张继续编辑

```bash
python3 scripts/generate_image.py \
  -p "保留构图，换成赛博朋克夜景" \
  --auto-ref \
  --session-id demo-session
```

### 5) 查看当前会话历史

```bash
python3 scripts/generate_image.py \
  -p "占位提示词" \
  --session-id demo-session \
  --show-history
```

### 6) Dry Run（不调用 API）

```bash
python3 scripts/generate_image.py \
  -p "测试提示词" \
  --session-id demo-session \
  --dry-run
```

---

## 参数说明

| 参数 | 简写 | 说明 |
|---|---|---|
| `--prompt` | `-p` | 文本提示，必填 |
| `--image` | `-i` | 参考图片，可重复多次 |
| `--output` | `-o` | 指定保存路径 |
| `--resolution` | `-r` | 分辨率：`1K` / `2K` / `4K` |
| `--aspect` | `-a` | 宽高比，如 `1:1` / `16:9` / `9:16` |
| `--auto-ref` | - | 自动引用当前会话上一张图 |
| `--session-id` | - | 会话 ID，强烈建议始终传入 |
| `--show-history` | - | 查看当前会话历史 |
| `--reset` | - | 重置当前会话历史 |
| `--json` | - | JSON 输出 |
| `--no-fail-fast` | - | 失败时不立即退出 |
| `--dry-run` | - | 仅构造 payload，不请求 API |
| `--model` | `-m` | 覆盖模型名 |

---

## 宽高比建议

| 比例 | 适用场景 |
|---|---|
| `1:1` | 头像、Logo、通用社媒图 |
| `9:16` | 手机壁纸、短视频封面 |
| `16:9` | 电脑壁纸、视频封面 |
| `21:9` | 超宽屏、电影感横幅 |
| `3:2` | 摄影作品 |
| `4:3` | 传统画幅 |

---

## OpenClaw 使用建议

在 OpenClaw 中建议遵循以下流程：

1. 识别用户是文生图还是图生图
2. 优化提示词
3. 把优化后的提示词发给用户确认
4. 用户确认后再执行正式生成
5. 生成成功后把图片发回用户

### 图片编辑规则

- 用户上传图片并要求修改时，必须传 `-i`
- 多图融合/参考时，传多个 `-i`
- 室内空间摄影改写时，提示词应强调：
  - 保持原图透视效果
  - 保留空间布局与结构
  - 指定镜头感（广角 / 一点透视 / 两点透视）

---

## 输出示例

### 正常生成

```text
✅ 生成成功!

📝 描述: 一只可爱的橘猫，暖色调，电影感摄影...

🖼️ 图片数量: 1

💾 已保存: /home/yy/.openclaw/downloads/nanobanana/nanobanana_1.png
📋 类型: new
📋 会话ID: demo-session
📡 使用API: main
```

### Dry Run

```text
✅ Dry run 成功，未调用 API
{
  "messages": [...],
  "max_tokens": 4096,
  "generation_config": {
    "response_modalities": ["image", "text"]
  }
}
```

---

## 安全说明

- 不要把真实 `scripts/.user_api` 提交到 GitHub
- 仓库中只应保留 `scripts/.user_api.example`
- 不要提交 `__pycache__/`、历史缓存、输出图片

---

License: MIT

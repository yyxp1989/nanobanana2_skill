# Nanobanana2 Openclaw SKILL 🔮

> 使用 Telegram 与Openclaw Agent对话执行AI生图的skill，使用gemini-3.1-flash-image-preview (Nanobanana2)模型

## 特性

### 核心功能
- **文生图** - 文本描述生成图片
- **图生图** - 参考图片风格生成新图
- **图片编辑** - 修改图片局部元素
- **多轮对话** - 连续编辑同一主题

### v2.0 新特性
- **多API支持** - 主API + 备用API 自动切换
- **自动重试** - 失败后指数退避重试
- **熔断机制** - 连续失败自动冷却
- **会话管理** - 支持多会话隔离

## 快速开始

### 1. 配置 API

编辑 `scripts/.user_api`：

```bash
# API[main] (必须)
API_KEY=your-api-key
API_BASE=https://poloai.top/v1/chat/completions
MODEL=gemini-3.1-flash-image-preview

# API[switch1] (可选)
# API_KEY2=
# API_BASE2=
# MODEL2=

# API[switch2] (可选)
# API_KEY3=
# API_BASE3=
```

### 2. 生成图片

```bash
# 文生图
python3 scripts/generate_image.py -p "一只可爱的橘猫"

# 图生图
python3 scripts/generate_image.py -p "类似的风格画一个女孩" -i 参考图.png

# 编辑图片
python3 scripts/generate_image.py -p "把背景改成海边" -i 原图.png

# 继续编辑 (自动引用上一张)
python3 scripts/generate_image.py -p "换个风格" --auto-ref
```

## 参数说明

| 参数 | 简写 | 说明 |
|------|------|------|
| `--prompt` | `-p` | 文本提示 (必须) |
| `--image` | `-i` | 参考图片 |
| `--output` | `-o` | 保存路径 |
| `--resolution` | `-r` | 分辨率 (1K/2K/4K) |
| `--aspect` | `-a` | 宽高比 (1:1/16:9/9:16...) |
| `--auto-ref` | - | 引用上一张图 |
| `--reset` | - | 重置对话历史 |
| `--json` | - | JSON输出 |

## 宽高比

| 比例 | 用途 |
|------|------|
| 1:1 | 社交媒体头像 |
| 9:16 | 手机壁纸 |
| 16:9 | 电脑壁纸 |
| 21:9 | 电影宽银幕 |

## 配置选项

```bash
# 超时时间 (秒)
API_TIMEOUT=120

# 重试次数
API_RETRY=2

# 熔断阈值 (连续失败N次后冷却)
CIRCUIT_BREAKER_THRESHOLD=3
```

## 输出

```
✅ 生成成功!
📝 描述: 一只可爱的橘猫...
🖼️ 图片数量: 1
💾 已保存: /path/to/nanobanana_1.png
📡 使用API: main
```

## 目录结构

```
nanobanana/
├── SKILL.md                 # 技能说明
├── scripts/
│   ├── generate_image.py   # 核心脚本
│   └── .user_api           # API配置
└── history/                 # 对话历史
```

## 提示词技巧

好的提示词应包含：
- **主体** - 谁/什么（尽量具体）
- **构图** - 特写/全景/角度
- **风格** - 3D动画/水彩/电影感
- **情绪** - 温馨/神秘/酷炫

---

License: MIT

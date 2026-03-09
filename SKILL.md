---
name: nanobanana
description: |
  使用 Google Gemini 模型进行 AI 图像生成与编辑。支持文生图、图生图、多轮对话修改。
  触发条件：(1) 用户要求生成图片、AI绘图 (2) 图片编辑、修改、风格转换 (3) 提到 nanobanana 或图像生成 (4) 使用 gemini 模型生成图像
allowed-tools: Read, Write, Glob, Grep, Task, Bash(cat:*), Bash(ls:*), Bash(tree:*), Bash(python3:*)
---

# Nanobanana 图片生成技能

通过 nanobanana 工具使用 Google Gemini API 生成或编辑图片。

## 快速开始

### 1. 文生图
```
画一只可爱的橘猫
```

### 2. 图生图
```
[发送图片] 类似的风格画一个女孩
```

### 3. 图片编辑
```
[发送图片] 把背景改成海边
```

---

## Skill 执行流程

### Step 1: 获取当前会话 ID

```bash
CLAUDE_SESSION_ID=$(python3 -c "
import json, subprocess
result = subprocess.run(['sessions_list', '--activeMinutes', '60', '--messageLimit', '1'], capture_output=True, text=True)
data = json.loads(result.stdout)
print(data['sessions'][0]['sessionId'] if data.get('sessions') else '')
")
```

### Step 2: 语义判断 --auto-ref

通过用户 prompt 判断是否继续编辑：

```bash
# 继续编辑的关键词
EDIT_KEYWORDS="调整 修改 换 改成 加 去掉 改成 改一下 换一个 改成什么 继续"

if echo "$USER_PROMPT" | grep -qE "$EDIT_KEYWORDS"; then
    AUTO_REF="--auto-ref"
else
    AUTO_REF=""
fi
```

| 关键词示例 | 场景 | 行为 |
|-----------|------|------|
| 画一只、生成、创建一个... | 全新生成 | 不加 `--auto-ref` |
| 调整一下、换个风格、把...改成... | 继续编辑 | `--auto-ref` |

### Step 3: 用户是否提供图片

如果用户发送了图片附件，优先使用用户图片：

```bash
if [ -n "$USER_IMAGE_PATH" ]; then
    # 用户提供了图片
    python3 $SCRIPT_DIR/generate_image.py -p "$USER_PROMPT" -i "$USER_IMAGE_PATH" --session-id "$SESSION_ID"
else
    # 使用语义判断的结果
    python3 $SCRIPT_DIR/generate_image.py -p "$USER_PROMPT" $AUTO_REF --session-id "$SESSION_ID"
fi
```

### Step 4: 返回结果

- 成功：返回图片，提示可用 "调整/修改/换..." 继续
- 失败：返回错误信息

---

## 会话管理

### 原理
- 通过 `--session-id` 区分不同会话
- 会话ID不匹配时自动重置历史

### 历史文件结构
```json
{
  "session_id": "086fd970-ec67-41c3-9b01-e20be1c2e47d",
  "last_image": "/path/to/image.png",
  "last_active": 1706745600,
  "last_type": "new",
  "history": [...]
}
```

---

## 运行示例

### 1. 文生图
```bash
python3 scripts/generate_image.py -p "一只小猫" --session-id "086fd970-ec67-41c3-9b01-e20be1c2e47d"
```

### 2. 继续编辑（语义判断触发）
```bash
# 用户说"换个风格" → 自动加 --auto-ref
python3 scripts/generate_image.py -p "换个风格" --auto-ref --session-id "086fd970-ec67-41c3-9b01-e20be1c2e47d"
```

### 3. 用户提供图片
```bash
python3 scripts/generate_image.py -p "类似的风格画一个女孩" -i /path/to/image.png --session-id "086fd970-ec67-41c3-9b01-e20be1c2e47d"
```

---

## 可用选项

| 参数 | 简写 | 说明 |
|------|------|------|
| `--prompt` | `-p` | 文本提示 |
| `--image` | `-i` | 参考图片（可多次使用） |
| `--output` | `-o` | 保存路径 |
| `--resolution` | `-r` | 分辨率 (1K, 2K, 4K) |
| `--aspect` | `-a` | 宽高比 (1:1, 16:9, 9:16, 21:9 等) |
| `--model` | `-m` | 模型名称 |
| `--session-id` | - | 会话ID（区分不同会话） |
| `--auto-ref` | - | 自动引用上一张图片 |
| `--reset` | - | 重置对话历史 |
| `--json` | - | 输出JSON格式 |

---

## 宽高比参考

| 比例 | 用途 |
|------|------|
| 1:1 | 社交媒体头像 |
| 9:16 | 手机壁纸、故事 |
| 16:9 | 电脑壁纸 |
| 21:9 | 电影宽银幕 |

---

## 提示词指南

好的提示词应包含：
- **主体**：谁/什么？（尽量具体）
- **构图**：特写、全景、低角度？
- **风格**：3D动画、水彩画、电影风格？
- **编辑指令**：把XX改成YY

### 最佳实践
1. Prompt 要具体（风格、情绪、颜色、构图）
2. Logo/图形用 1:1，壁纸用 16:9 或 21:9
3. 先生成 1K 测试，再升级 2K/4K

---

## 错误处理

- 快速失败模式（默认）：API 返回错误或未提取到图片时立即退出
- 使用 `--no-fail-fast` 关闭快速失败

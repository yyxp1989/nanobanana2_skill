#!/usr/bin/env python3
"""
Nanobanana - Gemini图像生成核心脚本
支持文生图、图生图、多轮修改、自动会话管理
v2.0: 备用API切换 + 自动重试 + 熔断机制
"""

import os
import sys
import json
import base64
import argparse
import time
import requests
from typing import List, Optional, Dict, Any
from collections import defaultdict

# ========== 加载用户配置 ==========
def load_user_config():
    config = {}
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_paths = [
        os.path.join(script_dir, ".user_api"),
        os.path.expanduser("~/.config/nanobanana/.user_api"),
    ]
    
    for config_path in config_paths:
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        config[key.strip()] = value.strip()
            break
    return config

user_config = load_user_config()

# 解析多个API配置
def parse_api_list():
    """解析API列表，支持 API_KEY/BASE/MODEL + API_KEY2/BASE2/MODEL2 格式"""
    apis = []
    
    # API 1 (必须)
    api1 = {
        "key": user_config.get("API_KEY", ""),
        "base": user_config.get("API_BASE", ""),
        "model": user_config.get("MODEL", "gemini-3.1-flash-image-preview")
    }
    if api1["key"] and api1["key"] != "sk-your-api-key-here" and api1["base"]:
        apis.append(api1)
    
    # API 2 (可选)
    if user_config.get("API_KEY2"):
        api2 = {
            "key": user_config.get("API_KEY2", ""),
            "base": user_config.get("API_BASE2", ""),
            "model": user_config.get("MODEL2", user_config.get("MODEL", "gemini-3.1-flash-image-preview"))
        }
        if api2["base"]:
            apis.append(api2)
    
    # API 3 (可选)
    if user_config.get("API_KEY3"):
        api3 = {
            "key": user_config.get("API_KEY3", ""),
            "base": user_config.get("API_BASE3", ""),
            "model": user_config.get("MODEL3", user_config.get("MODEL", "gemini-3.1-flash-image-preview"))
        }
        if api3["base"]:
            apis.append(api3)
    
    return apis

API_LIST = parse_api_list()

if not API_LIST:
    print("⚠️ 请先配置 API_KEY 和 API_BASE！")
    print("方法: 编辑 scripts/.user_api 文件")
    sys.exit(1)

# 兼容旧版本：第一个API作为默认
API_KEY = API_LIST[0]["key"]
API_BASE = API_LIST[0]["base"]
MODEL = API_LIST[0]["model"]

OUTPUT_DIR = user_config.get("OUTPUT_DIR", "/home/yy/.openclaw/downloads/nanobanana")
HISTORY_DIR = user_config.get("HISTORY_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "history"))

# 重试与熔断配置
API_TIMEOUT = int(user_config.get("API_TIMEOUT", "120"))
API_RETRY = int(user_config.get("API_RETRY", "2"))
CIRCUIT_BREAKER_THRESHOLD = int(user_config.get("CIRCUIT_BREAKER_THRESHOLD", "3"))

DEFAULT_API_LIST = API_LIST
DEFAULT_MODEL = MODEL
DEFAULT_OUTPUT_DIR = OUTPUT_DIR
DEFAULT_HISTORY_DIR = HISTORY_DIR


class CircuitBreaker:
    """熔断器：记录每个API的连续失败次数"""
    def __init__(self, threshold: int = 3):
        self.threshold = threshold
        self.fail_counts: Dict[str, int] = defaultdict(int)
        self.last_fail_time: Dict[str, float] = {}
        self.cooldown = 60  # 冷却60秒后重试
    
    def record_failure(self, api_url: str):
        self.fail_counts[api_url] += 1
        self.last_fail_time[api_url] = time.time()
    
    def record_success(self, api_url: str):
        self.fail_counts[api_url] = 0
    
    def is_available(self, api_url: str) -> bool:
        # 超过阈值，检查是否在冷却期
        if self.fail_counts[api_url] >= self.threshold:
            if time.time() - self.last_fail_time.get(api_url, 0) > self.cooldown:
                print(f"🔄 API {api_url} 冷却结束，恢复使用")
                self.fail_counts[api_url] = 0
                return True
            return False
        return True
    
    def get_status(self) -> Dict[str, Any]:
        return {api: count for api, count in self.fail_counts.items() if count > 0}


class Nanobanana:
    def __init__(self, api_list: List[Dict] = None, model: str = DEFAULT_MODEL,
                 history_file: str = None, history_dir: str = DEFAULT_HISTORY_DIR,
                 session_id: str = None, timeout: int = API_TIMEOUT, 
                 retry: int = API_RETRY):
        self.api_list = api_list or DEFAULT_API_LIST
        self.model = model
        self.conversation_history: List[Dict] = []
        self.output_dir = DEFAULT_OUTPUT_DIR
        self.last_image_path: Optional[str] = None
        self.session_id = session_id
        self.timeout = timeout
        self.retry = retry
        self.current_api_index = 0
        
        # 熔断器
        self.circuit_breaker = CircuitBreaker(threshold=CIRCUIT_BREAKER_THRESHOLD)
        
        if history_file:
            self.history_file = history_file
        else:
            os.makedirs(history_dir, exist_ok=True)
            self.history_file = os.path.join(history_dir, "conversation.json")
        
        self._load_history()
    
    def _get_current_api(self) -> tuple:
        """获取当前可用的API (api_dict, index)"""
        # 先尝试当前索引的API
        for i in range(len(self.api_list)):
            idx = (self.current_api_index + i) % len(self.api_list)
            api = self.api_list[idx]
            if self.circuit_breaker.is_available(api["base"]):
                return api, idx
        # 所有API都熔断，强制使用第一个
        print("⚠️ 所有API均处于熔断状态，强制尝试第一个")
        return self.api_list[0], 0
        
    def _load_history(self):
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    saved_session = data.get("session_id", "")
                    
                    # 会话不匹配 → 重置
                    if saved_session != self.session_id:
                        print(f"📋 新会话: {self.session_id} (原: {saved_session})")
                        self.conversation_history = []
                        self.last_image_path = None
                        return
                    
                    self.conversation_history = data.get("history", [])
                    self.last_image_path = data.get("last_image", None)
            except (json.JSONDecodeError, IOError):
                self.conversation_history = []
                self.last_image_path = None
    
    def _save_history(self):
        try:
            os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump({
                    "session_id": self.session_id,
                    "history": self.conversation_history,
                    "last_image": self.last_image_path,
                    "last_active": time.time(),
                    "last_type": self.last_type if hasattr(self, 'last_type') else "new"
                }, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"⚠️ 警告：保存历史失败: {e}", file=sys.stderr)
        
    def reset_conversation(self):
        self.conversation_history = []
        self.last_image_path = None
        if os.path.exists(self.history_file):
            os.remove(self.history_file)
        
    def _get_output_path(self, index: int = 1) -> str:
        os.makedirs(self.output_dir, exist_ok=True)
        return os.path.join(self.output_dir, f"nanobanana_{index}.png")
        
    def _build_messages(self, prompt: str, images: Optional[List[str]] = None) -> List[Dict]:
        content = [{"type": "text", "text": prompt}]
        
        if images:
            for img in images:
                if img.startswith("http"):
                    content.append({"type": "image_url", "image_url": {"url": img}})
                elif img.startswith("data:"):
                    content.append({"type": "image_url", "image_url": {"url": img}})
                else:
                    if os.path.exists(img):
                        with open(img, "rb") as f:
                            img_data = base64.b64encode(f.read()).decode()
                            mime = self._guess_mime(img)
                            content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img_data}"}})
                    else:
                        print(f"⚠️ 警告：图片不存在: {img}", file=sys.stderr)
        
        user_message = {"role": "user", "content": content}
        return self.conversation_history + [user_message]
    
    def _guess_mime(self, path: str) -> str:
        ext = os.path.splitext(path)[1].lower()
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", 
                    ".gif": "image/gif", ".webp": "image/webp"}
        return mime_map.get(ext, "image/jpeg")
    
    def _call_api(self, payload: Dict, headers: Dict) -> Optional[requests.Response]:
        """带备用API切换和重试的API调用"""
        last_error = None
        
        for attempt in range(self.retry + 1):
            api, api_idx = self._get_current_api()
            api_url = api["base"]
            api_key = api["key"]
            
            # 更新headers中的API key
            headers["Authorization"] = f"Bearer {api_key}"
            
            if attempt > 0:
                # 指数退避: 1s, 2s, 4s...
                wait_time = 2 ** (attempt - 1)
                print(f"⏳ 等待 {wait_time}s 后重试 (尝试 {attempt + 1}/{self.retry + 1})...")
                time.sleep(wait_time)
            
            # 标签映射
            labels = ["main", "switch1", "switch2"]
            api_label = labels[api_idx] if api_idx < len(labels) else f"switch{api_idx}"
            
            print(f"📡 使用 API[{api_label}]: {api_url}")
            
            try:
                response = requests.post(api_url, headers=headers, json=payload, timeout=self.timeout)
                
                if response.status_code == 200:
                    self.circuit_breaker.record_success(api_url)
                    self.current_api_index = api_idx
                    return response
                else:
                    error_msg = f"API错误 {response.status_code}"
                    print(f"❌ {error_msg}: {response.text[:100]}")
                    self.circuit_breaker.record_failure(api_url)
                    last_error = error_msg
                    
            except requests.exceptions.Timeout:
                error_msg = "请求超时"
                print(f"❌ {error_msg}: {api_url}")
                self.circuit_breaker.record_failure(api_url)
                last_error = error_msg
                
            except requests.exceptions.RequestException as e:
                error_msg = f"请求异常: {str(e)}"
                print(f"❌ {error_msg}: {api_url}")
                self.circuit_breaker.record_failure(api_url)
                last_error = str(e)
        
        return None
    
    def generate(self, prompt: str, images: Optional[List[str]] = None, 
                 save_path: Optional[str] = None, resolution: str = None,
                 aspect_ratio: str = None, fail_fast: bool = True,
                 auto_ref: bool = False) -> Dict[str, Any]:
        self.last_type = "edit" if (images or auto_ref) else "new"
        
        # 自动引用上一张图片
        if auto_ref and self.last_image_path and not images:
            if os.path.exists(self.last_image_path):
                images = [self.last_image_path]
                print(f"🔗 自动引用上一张图片: {self.last_image_path}")
            else:
                print(f"⚠️ 上一张图片不存在: {self.last_image_path}", file=sys.stderr)
        
        messages = self._build_messages(prompt, images)
        
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 4096
        }
        
        generation_config = {"response_modalities": ["image", "text"]}
        
        if resolution:
            resolution = resolution.upper()
            if resolution in ("1K", "2K", "4K"):
                generation_config["image_size"] = resolution
        
        if aspect_ratio:
            valid_ratios = ("1:1", "1:4", "1:8", "2:3", "3:2", "3:4", "4:1", "4:3", "4:5", 
                           "5:4", "8:1", "9:16", "16:9", "21:9", "auto")
            if aspect_ratio in valid_ratios:
                generation_config["aspect_ratio"] = aspect_ratio
        
        payload["generation_config"] = generation_config
        
        # 使用当前API的model
        current_api = self.api_list[self.current_api_index]
        payload["model"] = current_api.get("model", self.model)
        
        headers = {
            "Content-Type": "application/json"
        }
        
        # 使用新的API调用方法（带备用切换）
        response = self._call_api(payload, headers)
        
        if response is None:
            error_msg = f"❌ 所有API尝试失败 (已重试 {self.retry} 次)"
            if fail_fast:
                print(error_msg, file=sys.stderr)
                # 显示熔断状态
                breaker_status = self.circuit_breaker.get_status()
                if breaker_status:
                    print(f"🔧 熔断状态: {breaker_status}", file=sys.stderr)
                sys.exit(1)
            return {"success": False, "error": error_msg}
        
        result = response.json()
        
        if "choices" not in result or len(result["choices"]) == 0:
            error_msg = f"❌ API 无响应内容: {str(result)[:200]}"
            if fail_fast:
                print(error_msg, file=sys.stderr)
                sys.exit(1)
            return {"success": False, "error": error_msg}
        
        choice = result["choices"][0]
        message = choice.get("message", {})
        content = message.get("content", "")
        
        # 更新对话历史
        self.conversation_history.append({"role": "user", "content": prompt})
        self.conversation_history.append({"role": "assistant", "content": self._extract_text(content)})
        
        images_result = self._extract_images(content)
        
        # 错误处理：未提取到图片
        if not images_result:
            error_msg = "❌ 未提取到图片，API 可能未正确生成图像"
            if fail_fast:
                print(error_msg, file=sys.stderr)
                print(f"📝 API 返回内容: {content[:500]}...", file=sys.stderr)
                sys.exit(1)
            return {"success": False, "error": error_msg, "content": content}
        
        # 保存图片
        saved_paths = []
        for i, img_data in enumerate(images_result):
            if img_data.startswith("data:"):
                import re
                match = re.search(r'data:image/(\w+);base64,(.+)', img_data)
                if match:
                    img_bytes = base64.b64decode(match.group(2))
                    path = save_path if save_path else self._get_output_path(i + 1)
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, "wb") as f:
                        f.write(img_bytes)
                    saved_paths.append(path)
        
        if saved_paths:
            self.last_image_path = saved_paths[0]
        
        self._save_history()
        
        return {
            "success": True,
            "text": self._extract_text(content),
            "images": images_result,
            "saved": saved_paths,
            "last_image": self.last_image_path,
            "last_type": self.last_type,
            "session_id": self.session_id,
            "api_used": self.api_list[self.current_api_index]["base"],
            "raw": result
        }
    
    def _extract_images(self, content: str) -> List[str]:
        images = []
        import re
        for match in re.finditer(r'data:image/(\w+);base64,([A-Za-z0-9+/=]+)', content):
            images.append(f"data:image/{match.group(1)};base64,{match.group(2)}")
        for match in re.finditer(r'https?://[^\s<>"]+\.(?:jpg|jpeg|png|gif|webp)', content):
            images.append(match.group(0))
        return images
    
    def _extract_text(self, content: str) -> str:
        import re
        text = re.sub(r'data:image/\w+;base64,[A-Za-z0-9+/=]+', '[图片]', content)
        text = re.sub(r'https?://[^\s<>"]+\.(?:jpg|jpeg|png|gif|webp)', '[图片]', text)
        return text.strip()


def main():
    parser = argparse.ArgumentParser(description="Nanobanana - Gemini图像生成 (v2.0)")
    parser.add_argument("-p", "--prompt", required=True, help="文本提示")
    parser.add_argument("-i", "--image", action="append", help="参考图片路径或URL")
    parser.add_argument("-o", "--output", help="保存图片路径")
    parser.add_argument("-r", "--resolution", choices=["1K", "2K", "4K"], help="分辨率")
    parser.add_argument("-a", "--aspect", dest="aspect_ratio", help="宽高比")
    parser.add_argument("--reset", action="store_true", help="重置对话历史")
    parser.add_argument("--json", action="store_true", help="输出JSON格式")
    parser.add_argument("--no-fail-fast", action="store_true", help="关闭快速失败模式")
    parser.add_argument("--auto-ref", action="store_true", help="自动引用上一张生成的图片")
    parser.add_argument("--history-file", help="指定历史文件路径")
    parser.add_argument("--history-dir", default=DEFAULT_HISTORY_DIR, help="历史文件目录")
    parser.add_argument("--session-id", help="会话ID（用于区分不同会话）")
    parser.add_argument("--show-history", action="store_true", help="显示当前对话历史")
    parser.add_argument("-m", "--model", default=None, help="模型名称")
    
    args = parser.parse_args()
    
    if args.model is None:
        args.model = DEFAULT_MODEL
    nanobanana = Nanobanana(
        api_list=DEFAULT_API_LIST,
        model=args.model,
        history_file=args.history_file,
        history_dir=args.history_dir,
        session_id=args.session_id
    )
    
    if args.show_history:
        print("📜 对话历史:")
        print(json.dumps(nanobanana.conversation_history, ensure_ascii=False, indent=2))
        print(f"\n🖼️ 最后图片: {nanobanana.last_image_path}")
        print(f"📋 会话ID: {nanobanana.session_id}")
        print(f"🔧 熔断状态: {nanobanana.circuit_breaker.get_status()}")
        sys.exit(0)
    
    if args.reset:
        nanobanana.reset_conversation()
        print("✅ 对话历史已重置")
        sys.exit(0)
    
    fail_fast = not args.no_fail_fast
    
    result = nanobanana.generate(
        prompt=args.prompt,
        images=args.image,
        save_path=args.output,
        resolution=args.resolution,
        aspect_ratio=args.aspect_ratio,
        fail_fast=fail_fast,
        auto_ref=args.auto_ref
    )
    
    if not result["success"]:
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"❌ 生成失败: {result.get('error')}")
        sys.exit(1)
    
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("✅ 生成成功!")
        if result.get("text"):
            print(f"\n📝 描述: {result['text']}")
        if result.get("images"):
            print(f"\n🖼️ 图片数量: {len(result['images'])}")
        if result.get("saved"):
            print(f"\n💾 已保存: {', '.join(result['saved'])}")
        if result.get("last_image"):
            print(f"\n🔗 最后图片: {result['last_image']}")
            print(f"📋 类型: {result.get('last_type', 'new')}")
            print(f"📋 会话ID: {result.get('session_id', 'N/A')}")
            labels = ["main", "switch1", "switch2"]
            api_label = labels[self.current_api_index] if self.current_api_index < len(labels) else f"switch{self.current_api_index}"
            print(f"📡 使用API: {api_label}")


if __name__ == "__main__":
    main()

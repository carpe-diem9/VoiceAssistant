# VoiceAssistant - AI 智能语音助理

基于大语言模型的多端智能语音助理系统，支持 Android 应用、Chrome 浏览器扩展，提供文本/语音对话、语音唤醒、TTS 语音合成、无障碍辅助等功能。

## 系统架构

- **后端**：Python FastAPI，提供 REST API + SSE 流式响应 + WebSocket 实时通信
- **移动端**：Flutter Android 应用
- **网页端**：Chrome 浏览器扩展（Vue 3 + TypeScript）
- **数据库**：SQLite（用户信息、会话存储）

## 功能特性

### 核心功能
- 语音对话：录音 → ASR 识别 → LLM 回复 → TTS 语音播放
- 语音唤醒：自定义唤醒词，免触控开始对话
- TTS 控制：可选语音/文本回答模式，支持音色、语速、音调、音量调节
- 会话管理：多会话切换、历史记录、左滑删除
- 深度研究：支持深度推理模式，复杂问题深度分析

### 移动端特性
- 悬浮球：全局快捷入口，随时唤醒语音助手
- 无障碍服务：屏幕朗读辅助，文本内容语音播报
- Material Design：流畅的 Android 原生体验

### 浏览器扩展特性
- 网页悬浮球：任意网页快速唤起语音助手
- 侧边栏聊天：网页内嵌聊天界面
- 网页朗读：朗读网页内容

## 项目结构

```
VoiceAssistant/
├── backend/                    # 后端服务
│   ├── main.py                 # FastAPI 主入口
│   ├── config.py               # 配置管理
│   ├── .env                    # 环境变量（需自行创建）
│   ├── database.py             # 数据库操作
│   ├── auth.py                 # JWT 认证
│   ├── models.py               # 数据模型
│   ├── requirements.txt        # Python 依赖
│   ├── routers/                # 路由模块
│   │   ├── auth_router.py      # 认证接口
│   │   ├── chat_router.py      # 对话接口（文本/语音/WebSocket）
│   │   ├── session_router.py   # 会话管理接口
│   │   ├── settings_router.py  # 设置接口
│   │   └── accessibility_router.py  # 无障碍服务接口
│   ├── services/               # 服务模块
│   │   ├── asr_service.py      # 语音识别
│   │   ├── tts_service.py      # 语音合成
│   │   ├── llm_service.py      # 大语言模型
│   │   ├── deep_research.py    # 深度研究服务
│   │   ├── audio_processor.py  # 音频处理
│   │   └── vad_service.py      # 语音活动检测
│   └── benchmark/              # 性能基准测试
├── mobile/                     # Flutter 移动端
│   ├── lib/
│   │   ├── main.dart           # 应用入口
│   │   ├── config/             # 应用配置
│   │   ├── models/             # 数据模型
│   │   ├── providers/          # 状态管理（Provider）
│   │   ├── screens/            # UI 页面
│   │   ├── services/           # 服务层（API、音频、唤醒词）
│   │   └── widgets/            # 自定义组件
│   ├── android/                # Android 原生配置
│   └── pubspec.yaml            # Flutter 依赖
├── extension/                  # Chrome 浏览器扩展
│   ├── manifest.json           # 扩展清单
│   ├── package.json            # Node.js 依赖
│   ├── vite.config.ts          # Vite 构建配置
│   ├── src/
│   │   ├── background/         # 后台 Service Worker
│   │   ├── content/            # 内容脚本（悬浮球）
│   │   ├── popup/              # 弹出窗口
│   │   ├── sidepanel/          # 侧边栏
│   │   ├── options/            # 设置页面
│   │   └── shared/             # 共享模块（API、状态管理）
│   └── dist/                   # 构建产物
└── start.bat                   # Windows 一键启动脚本
```

## 部署指南

### 环境要求

| 组件 | 版本要求 |
|------|---------|
| Python | 3.10+ |
| Flutter SDK | 3.0.0+ |
| Android SDK | API 21+ |
| Node.js | 16+（浏览器扩展） |

### 第一步：配置后端

```bash
# 进入后端目录
cd backend

# 创建 Python 虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

创建 `backend/.env` 文件，填入配置：

```env
# ===== ASR 语音识别配置 =====
ASR_MODEL=qwen3-asr-flash
ASR_API_KEY=你的DashScope API Key
ASR_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

# ===== TTS 语音合成配置 =====
TTS_MODEL=qwen3-tts-instruct-flash
TTS_API_KEY=你的DashScope API Key
TTS_BASE_URL=https://dashscope.aliyuncs.com/api/v1
TTS_REALTIME_MODEL=qwen3-tts-flash-realtime
TTS_REALTIME_URL=wss://dashscope.aliyuncs.com/api-ws/v1/realtime

# ===== LLM 大语言模型配置 =====
LLM_MODEL=qwen3.5-plus
LLM_API_KEY=你的DashScope API Key
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

# ===== JWT 认证配置 =====
JWT_SECRET_KEY=请替换为一个随机字符串
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=10080

# ===== 服务端配置 =====
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
```

> **注意**：ASR、TTS、LLM 的 API Key 可以使用同一个 DashScope Key。

### 第二步：启动后端

**方式一：使用启动脚本（Windows）**

双击项目根目录下的 `start.bat`，会自动创建虚拟环境、安装依赖并启动服务。
```bash
cd 本项目目录 && start.bat
```

**方式二：手动启动**

```bash
cd backend
# 激活虚拟环境后
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

启动成功后访问：
- API 服务：http://localhost:8000
- 交互式文档：http://localhost:8000/docs

### 第三步：构建 Flutter 移动端

```bash
cd mobile

# 获取依赖
flutter pub get

# 构建 Debug APK
flutter build apk --debug
```

构建产物位于：`mobile/build/app/outputs/flutter-apk/app-debug.apk`

### 第四步：安装到 Android 设备

**USB 连接真机调试：**

```bash
# 1. 确认设备已连接（需开启 USB 调试）
adb devices

# 2. 设置端口转发（让手机 localhost:8000 转发到电脑后端）
adb reverse tcp:8000 tcp:8000

# 3. 安装 APK
adb install -r mobile/build/app/outputs/flutter-apk/app-debug.apk
```

> **重要**：每次重新连接设备后都需要执行 `adb reverse` 命令。

**使用模拟器：**

如果使用 Android 模拟器，需修改 `mobile/lib/config/app_config.dart` 中的 `baseUrl`：

```dart
// 模拟器使用 10.0.2.2 访问宿主机
static const String baseUrl = 'http://10.0.2.2:8000';
static const String wsUrl = 'ws://10.0.2.2:8000';
```


### 第五步：构建 Chrome 浏览器扩展（可选）

```bash
cd extension

# 安装依赖
npm install

# 构建
npm run build
```

**加载到 Chrome：**
1. 打开 Chrome 浏览器，访问 `chrome://extensions/`
2. 开启右上角的"开发者模式"
3. 点击"加载已解压的扩展程序"
4. 选择 `extension/dist` 目录

## 技术栈

**后端**
- FastAPI + Uvicorn（异步 Web 框架）
- SQLite + aiosqlite（异步数据库）
- JWT（用户认证）
- DashScope SDK（AI 服务调用）

**移动端**
- Flutter 3.0+（跨平台 UI 框架）
- Provider（状态管理）
- record（音频录制）
- just_audio（音频播放）
- shared_preferences（本地存储）

**浏览器扩展**
- Vue 3 + TypeScript
- Vite（构建工具）
- Pinia（状态管理）
- Chrome Extension API

## 许可证

MIT License

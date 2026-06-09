# AI 语音助理 Chrome 扩展

## 安装与构建

```bash
cd extension
npm install
npm run build          # 构建到 extension/dist
# 或开发模式
npm run dev
```

Chrome 加载方式：打开 `chrome://extensions/` → 开启开发者模式 → 加载已解压的扩展 → 选择 `extension/dist` 目录（开发模式下选择 `extension` 目录即可）。

## 图标

在 `public/icons/` 下放置 `icon16.png` / `icon48.png` / `icon128.png`。如暂无，可先放占位图。

## 使用流程

1. 打开扩展弹窗，登录或注册账号（后端需先启动）
2. 点击右下角悬浮球（需在「设置」页开启）在任意网页朗读：
   - 整页原文朗读 / 整页 LLM 总结朗读
   - 点击元素朗读 - 原文 / 点击元素朗读 - 总结
3. 设置页可配置：后端地址、音色/语速/音调/音量、LLM 模型、唤醒词、悬浮球开关与默认模式

## 权限说明

- `<all_urls>`：允许在任意网页注入悬浮球
- `storage`：保存 token 和设置
- `sidePanel`：提供更大的对话面板
- `tabs` / `activeTab`：获取当前激活标签用于侧边栏定位

## 架构要点

- `popup` / `sidepanel`：Vue 3 + Element Plus，承载登录、对话、会话管理
- `content script`：纯 TS（Shadow DOM）注入悬浮球与点击拾取交互
- `service worker`：代理 content 的朗读请求，携带 JWT 调后端 `/api/accessibility/read-text`

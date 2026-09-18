# VoiceChat

一个语音对话产品原型：像 ChatGPT 那样，既能打字聊天，也能像语音模式一样实时说话、实时听 AI 回复，还能"口述转文字"——说一段话，AI 整理成通顺的书面文字再发出去，类似 Typeless。默认对接 **Qwen-Omni-Realtime**（阿里云 DashScope/百炼），也可以切换回 OpenAI Realtime API——两者的 WebSocket 事件协议基本一致。

**当前只有网页版**（`web-demo/`）。这个项目最早同时维护一个原生 iOS App（SwiftUI）和网页 demo，两边跑同一套协议、功能对齐；2026-08-28 决定暂时把 iOS 端全部移除，只保留网页版——原因是这个开发环境没有 Swift 工具链/Xcode，iOS 端的所有改动全靠"源码走查 + 端侧真机反馈"来回沟通，尤其是自定义 WebSocket 传输层（为了绕开 `URLSessionWebSocketTask` 在这条链路上的已知问题而手写的 swift-nio-transport-services 实现）在真机上排查出好几处根本性的连接 bug，投入产出比很差；相比之下网页版从一开始就能在这个环境里用 Playwright 端到端跑通、验证快得多。**以后如果要重新做原生 iOS，`VoiceChat/` 目录被删除前的完整源码和这次调试过程留下的详细文档（`docs/realtime-websocket-transport-design.md`）都还在 git 历史里**，不是凭空重来。

网页 demo 的完整说明（怎么跑起来、架构、功能设计、实测记录）见 [`web-demo/README.md`](web-demo/README.md)。

**LiveKit + Pipecat 对比方案**（模块化 STT→LLM→TTS，WebRTC 传输）见 [`web-demo/pipecat-livekit/README.md`](web-demo/pipecat-livekit/README.md) 与 [`docs/pipecat-livekit-comparison.md`](docs/pipecat-livekit-comparison.md)。

**Mac Mini 本地 Agent + LiveKit Cloud 出站**（SenseVoice / llama.cpp / Qwen3-TTS / LanceDB，模型可环境变量配置）见 [`web-demo/pipecat-local-agent/README.md`](web-demo/pipecat-local-agent/README.md) 与 [`docs/pipecat-local-agent-architecture.md`](docs/pipecat-local-agent-architecture.md)。

## 相关文档

- [`docs/app-design.md`](docs/app-design.md) — 完整功能设计（三种交互模式、口述转文字、回复长度策略等）
- [`docs/qwen-realtime-voice-setup.md`](docs/qwen-realtime-voice-setup.md) — Qwen Realtime API 踩过的坑（域名选择、模型/音色选型）
- [`docs/agentnexus-memory-integration-proposal.md`](docs/agentnexus-memory-integration-proposal.md) — 给智枢（AgentNexus）团队的记忆体系集成建议
- [`docs/roadmap-todo.md`](docs/roadmap-todo.md) — 开发讨论纪要/已完成事项记录（其中部分历史条目涉及已移除的 iOS 端，作为决策背景保留，不代表当前代码状态）
- [`docs/testing-deployment.md`](docs/testing-deployment.md) — 部署/测试相关笔记（同样有历史 iOS 内容）
- [`docs/realtime-websocket-transport-design.md`](docs/realtime-websocket-transport-design.md) — 已移除的 iOS 端 WebSocket 传输层调试全过程，供以后重新做原生 iOS 时参考

## 制造专家会话式工作流采集（另一条产品线）

本仓库同时存放了一条独立的产品线：**制造专家会话式 DAG 工作流采集**——用会话式交互（自然语言 + 语音）从制造业专家那里采集真实工作流程，自动整理成结构化的工作流图（DAG），供后续数据集管理、Dashboard 评估与实验使用。这条产品线跟上面的 VoiceChat 语音对话原型是两个不同的产品，只是共用同一个仓库存放设计资料，两者**不共享代码、不共享数据边界**（专家采集产品线是封闭域采集，不接入公网搜索；VoiceChat 用于日常语音助手场景）。

完整设计资料见 [`docs/expert-workflow-collection/`](docs/expert-workflow-collection/)：

- [`docs/expert-workflow-collection/PRD.md`](docs/expert-workflow-collection/PRD.md) — 产品需求设计文档，覆盖桌面端三栏会话式采集设计 + 移动浏览器端新增需求（会话主页、历史抽屉、右滑查看可缩放 DAG 只读页、语音口述转文字输入）
- [`docs/expert-workflow-collection/design/`](docs/expert-workflow-collection/design/) — 原始设计文档与高保真 HTML 原型（会话式采集 v2.1、平台级说明书、数据集设计规范）
- [`docs/expert-workflow-collection/schema/`](docs/expert-workflow-collection/schema/) — Graph-based Workflow Dataset Schema v2 的 JSON Schema 定义与样例数据
- [`docs/expert-workflow-collection/legacy-prototype/`](docs/expert-workflow-collection/legacy-prototype/) — 更早的 Streamlit 研究原型（Collaborative Workflow Distillation 实验平台），保留作为研究方法论参考

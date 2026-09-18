# 测试与部署指南

这个仓库的产品只做浏览器（`web-demo/`），不做原生 App，也不需要任何本地工具链之外的东西——随时能跑，用来验证 Realtime API 协议本身。这份文档只讲"怎么跑起来测试"，架构设计看根目录 `README.md` 和 `web-demo/README.md`。

## 网页 Demo（`web-demo/`）

任何装了 Python 的机器都能跑。

```bash
cd web-demo
pip install -r requirements.txt
python3 server.py
```

浏览器打开 `http://127.0.0.1:8765/`，允许麦克风权限，点"开始对话"。Key 从仓库根目录的 `.env` 读取（`QWEN_API_KEY=...`），照着 `.env.example` 建一份，不要提交到 git。

细节和已经跑过的连通性测试记录见 `web-demo/README.md`。

## 尚未覆盖的部分

这个开发环境是无 GUI 的 Linux 容器，没有真实麦克风/扬声器可用，所以下面这些必须靠你在自己设备上用真实浏览器实测，目前完全没验证过：

- 真实语音的识别准确率
- 回复内容质量、语气
- 打断体验（协议层已确认 Qwen 支持 `interrupt_response`，但阈值/灵敏度这些参数没调过）
- 后台运行的稳定性
- 弱网/断线重连behavior（目前没做自动重连）
- 口述转文字全程（真实说话 → 识别 → AI 整理 → 回填/直接发送），尤其是"直接发"路径的连接复用——目前只用假麦克风 + 注入模拟转写文本测过链路本身能跑通，没有真实语音

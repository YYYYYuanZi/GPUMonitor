# GPU Monitor (Agentless SSH 版)

> **服务器集群监控面板 / 课题组显卡状态看板 / 轻量级 GPU 监控系统**
> **A lightweight, agentless GPU cluster monitoring dashboard for Labs & Servers.**

## 📝 更新日志

* **2026-06-13**：新增 Docker 部署支持，发布镜像 `yyyyyyyz/gpumonitor`，免配环境一键运行。
* **2026-05-23**：新增“批量添加服务器”功能：在设置弹窗中可按行粘贴 `hostname,port,username,password`，一次性导入多台节点。

## 📸 截图预览
<img width="2940" height="1662" alt="image" src="https://github.com/user-attachments/assets/df3c6a3a-544e-40aa-ad4d-e7bf325acb3a" />
<img width="2940" height="1662" alt="image" src="https://github.com/user-attachments/assets/bf889d8b-4a09-403d-9935-002f659ab54e" />

## 📖 项目简介 (Introduction)

这是一个基于 Python + Flask 开发的**轻量级 GPU 集群监控面板**，专为**深度学习课题组、实验室或小型服务器集群**设计。

与传统的监控工具（如 Prometheus + Grafana）不同，本项目采用**无 Agent (Agentless)** 模式：你**无需**在被监控的 GPU 服务器上安装任何客户端或 Python 包。只需在主控机上启动服务，即可通过 SSH 协议分布式采集所有节点的 GPU 数据。

## 💡 致敬与改编说明 (Credits & Modifications)

本项目基于 **[fgaim/gpuview](https://github.com/fgaim/gpuview)** 进行深度二次开发。感谢原作者提供了优秀的 UI 概念。

**核心重构与优化点 (Key Features):**

1. **架构进化 (Agentless)**: 从原版的“每台机器必装 Agent”升级为 **SSH 直连模式**。被监控端只需有 NVIDIA 驱动并开启 SSH 即可。
2. **后端高并发优化**:
* 引入 **SSH 连接池** 与 Keep-Alive 机制，避免频繁建立连接的开销。
* 采用 **后台独立线程轮询 (ThreadPoolExecutor)**，限制最大并发数（默认 5），防止触发防火墙拦截或 SSH 拥堵，同时实现 API 毫秒级无感响应。
* 合并 `nvidia-smi` 显卡与进程指令，单次会话拉取全部数据。


3. **前端体验重制**: 全新深色模式 (Dark Mode)，优化数据刷新布局，彻底解决原版页面闪烁问题。
4. **动态节点管理**: 支持在前端/API **动态添加、删除服务器、拖拽重排**，配置自动持久化。


---

## ✨ 功能特点

* **零侵入 (Agentless)**：被监控节点“即插即用”，不占用目标机多余常驻资源。
* **用户级进程识别**：通过 `nvidia-smi` 与 `ps` 命令联动，直观显示**哪个 Linux 用户 (`username`)** 正在运行什么进程、消耗了多少显存，方便课题组协调算力资源。
* **高安全性**：管理接口及配置返回时，自动**对 SSH 密码进行脱敏处理**，保障资产安全。
* **全维数据**：实时监控温度、显存、利用率、功耗（当前/限制）、进程详情，支持每 3 秒平滑刷新。

---

## 🛠️ 安装与使用

### 1. Docker 部署 (推荐)

如果您习惯使用 Docker，可以直接拉取镜像并一键运行，免去环境配置的烦恼：

```bash
# 从 Docker Hub 拉取最新镜像
docker pull yyyyyyyz/gpumonitor:latest

# 运行容器，将本地 8888 端口映射至容器的 8888 端口
docker run -d \
  --name gpumonitor \
  --restart always \
  -p 8888:8888 \
  -e TZ=Asia/Shanghai \
  yyyyyyyz/gpumonitor:latest

# 使用 Docker Compose
services:
  gpumonitor:
    container_name: gpumonitor
    image: yyyyyyyz/gpumonitor:latest   # 或指定架构 :amd64/:arm64
    restart: always
    ports:
      - "8888:8888"
    environment:
      - TZ=Asia/Shanghai
```

> *启动后，在浏览器访问：[http://localhost:8888*](https://www.google.com/search?q=http://localhost:8888)

### 2. 本地源码部署

如果您需要进行二次开发或直接在宿主机运行：

```bash
git clone https://github.com/3355190239/GPU-Monitor.git
cd GPU-Monitor

# 推荐使用虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 安装依赖
pip install flask paramiko

# 启动服务
python app.py

```

*启动后，在浏览器访问：[http://localhost:8888*](https://www.google.com/search?q=http://localhost:8888)

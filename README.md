
# GPU Monitor (Agentless SSH 版)


[![Python](https://img.shields.io/badge/Python-3.9%2B-green)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-2.x-blue)](https://flask.palletsprojects.com/)
[![Docker](https://img.shields.io/badge/Docker-yyyyyyyz%2Fgpumonitor-blue)](https://hub.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

---

## 📝 更新日志

- **2026-09-19**：新增 **快捷筛选按钮** —— 左侧用户 / 空闲显卡快捷栏，右侧服务器快捷栏，支持一键过滤、悬停联动高亮、拖拽排序。
- **2026-06-13**：新增 Docker 部署支持，发布镜像 `yyyyyyyz/gpumonitor`，免配环境一键运行。
- **2026-05-23**：新增「批量添加服务器」功能：在设置弹窗中可按行粘贴 `hostname,port,username,password`，一次性导入多台节点。

---

## 📸 截图预览

<img width="2940" height="1662" alt="dashboard" src="https://github.com/user-attachments/assets/df3c6a3a-544e-40aa-ad4d-e7bf325acb3a" />
<img width="2940" height="1662" alt="settings" src="https://github.com/user-attachments/assets/bf889d8b-4a09-403d-9935-002f659ab54e" />

---

## 📖 项目简介 (Introduction)

这是一个基于 **Python + Flask** 开发的**轻量级 GPU 集群监控面板**，专为**深度学习课题组、实验室或小型服务器集群**设计。

与传统的监控方案（如 Prometheus + Grafana + Node Exporter）不同，本项目采用 **无 Agent (Agentless)** 架构：**无需**在被监控的 GPU 服务器上安装任何客户端、Python 包或常驻进程。只需在主控机上启动服务，即可通过 **SSH 协议**分布式采集所有节点的 GPU 数据。

> 一句话总结：**一台主控机 + 若干台带 NVIDIA 显卡且开启 SSH 的节点 = 完整集群监控。**

---

## 💡 致敬与改编说明 (Credits & Modifications)

本项目基于 **[fgaim/gpuview](https://github.com/fgaim/gpuview)** 进行深度二次开发。感谢原作者提供了优秀的 UI 概念与基础实现。

**核心重构与优化点 (Key Features):**

1. **架构进化 (Agentless)**：从原版的「每台机器必装 Agent」升级为 **SSH 直连模式**。被监控端只需有 NVIDIA 驱动并开启 SSH 即可，真正即插即用。
2. **后端高并发优化**：
   - 引入 **SSH 连接池** 与 **Keep-Alive 机制**，避免频繁建立连接的开销。
   - 采用 **后台独立线程轮询 (ThreadPoolExecutor)**，限制最大并发数（默认 5），防止触发防火墙拦截或 SSH 拥堵。
   - 数据缓存于内存，实现 API **毫秒级无感响应**。
   - 合并 `nvidia-smi` 显卡与进程指令，单次会话拉取全部数据。
3. **前端体验重制**：全新 **深色模式 (Dark Mode)**，优化数据刷新布局，彻底解决原版页面闪烁问题。
4. **动态节点管理**：支持在前端 / API **动态添加、删除服务器、拖拽重排**，配置自动持久化至 `servers.json`。

---

## ✨ 功能特点

| 特性 | 说明 |
| --- | --- |
| 🖥️ **零侵入 (Agentless)** | 被监控节点「即插即用」，不占用目标机多余常驻资源 |
| 👤 **用户级进程识别** | 通过 `nvidia-smi` 与 `ps` 命令联动，直观显示**哪个 Linux 用户 (`username`)** 正在运行什么进程、消耗多少显存，方便课题组协调算力 |
| 🔐 **高安全性** | 管理接口及配置返回时，自动**对 SSH 密码进行脱敏处理**，保障资产安全 |
| 📊 **全维数据** | 实时监控温度、显存、利用率、功耗（当前/限制）、进程详情 |
| ⏱️ **平滑刷新** | 支持每 3 秒无闪烁刷新 |
| 📦 **批量导入** | 设置弹窗中可按行粘贴 `hostname,port,username,password`，一次性导入多台节点 |
| 🐳 **Docker 部署** | 官方镜像 `yyyyyyyz/gpumonitor`，免配环境一键运行 |
| 🔀 **拖拽重排** | 前端直接拖拽调整节点顺序，自动持久化 |
| 🧩 **动态节点** | 支持前端 / API 动态添加、删除服务器 |

---

## 🛠️ 安装与使用

### 方式一：Docker 一键部署（推荐）

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
```

启动后，浏览器访问：**http://localhost:8888**

---

### 方式二：Docker Compose 部署

在任意装有 Docker 的机器上，新建 `docker-compose.yml`：

```yaml
services:
  gpumonitor:
    container_name: gpumonitor
    image: yyyyyyyz/gpumonitor:latest   # 或指定架构 :amd64 / :arm64
    restart: always
    ports:
      - "8888:8888"
    environment:
      - TZ=Asia/Shanghai
```

启动：

```bash
docker compose up -d          # 首次自动拉取镜像并启动
docker compose logs -f        # 查看日志
docker compose down           # 停止
```

启动后，浏览器访问：**http://localhost:8888**

---

### 方式三：自行从源码构建 Docker 镜像（自己编译）

适合：想改代码、自定义镜像、离线部署、构建 `amd64 / arm64` 多平台镜像的场景。

> GPU Monitor 是 Python + Flask 项目，本身不需要编译；这里的“自己编译”指自行构建 Docker 镜像。

#### 1. 本机架构构建

```bash
cd GPU-Monitor

# 构建本地镜像
docker build -t gpumonitor:local .
```

运行自己构建的镜像：

```bash
docker run -d \
  --name gpumonitor \
  --restart always \
  -p 8888:8888 \
  -e TZ=Asia/Shanghai \
  gpumonitor:local
```

访问：`http://localhost:8888`

如果需要把 `servers.json` 持久化到宿主机，避免容器重建后节点配置丢失：

> 注意：下面挂载路径中的 `/app/servers.json` 需要按你 Dockerfile 里的 `WORKDIR` 调整。常见为 `/app/servers.json`。

```bash
# 先确保宿主机存在 servers.json
touch servers.json

docker run -d \
  --name gpumonitor \
  --restart always \
  -p 8888:8888 \
  -e TZ=Asia/Shanghai \
  -v "$(pwd)/servers.json:/app/servers.json" \
  gpumonitor:local
```

Windows PowerShell：

```powershell
docker run -d `
  --name gpumonitor `
  --restart always `
  -p 8888:8888 `
  -e TZ=Asia/Shanghai `
  -v "${PWD}/servers.json:/app/servers.json" `
  gpumonitor:local
```

#### 2. 多平台构建并推送（amd64 / arm64）

适合发布到 Docker Hub，或给不同架构机器使用。

```bash
# 创建 buildx 构建器
docker buildx create --use --name gpumonitor-builder
docker buildx inspect --bootstrap

# 登录 Docker Hub
docker login

# 构建并推送多平台镜像
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t <你的DockerHub用户名>/gpumonitor:latest \
  --push .
```

如果只想本地加载单平台镜像：

```bash
docker buildx build --platform linux/amd64 -t gpumonitor:amd64 --load .
docker buildx build --platform linux/arm64 -t gpumonitor:arm64 --load .
```

> `--load` 一次只能加载一个平台；多平台镜像建议用 `--push` 推到镜像仓库。

#### 3. Docker Compose 自己构建运行

如果你不想先手动 `docker build`，可以直接用 Compose 构建并启动：

```yaml
services:
  gpumonitor:
    build: .
    image: gpumonitor:local
    container_name: gpumonitor
    restart: always
    ports:
      - "8888:8888"
    environment:
      - TZ=Asia/Shanghai
    volumes:
      - ./servers.json:/app/servers.json
```

```bash
docker compose up -d --build
docker compose logs -f
docker compose down
```


---

### 方式四：本地源码部署（开发 / 二次开发）

如果您需要进行二次开发或直接在宿主机运行：

```bash
git clone https://github.com/3355190239/GPU-Monitor.git
cd GPU-Monitor

# 推荐使用虚拟环境
python -m venv venv
source venv/bin/activate      # Linux / Mac
# venv\Scripts\activate       # Windows

# 安装依赖
pip install flask paramiko

# 启动服务
python app.py
```

启动后，浏览器访问：**http://localhost:8888**

---

### 批量添加服务器

1. 启动服务，浏览器打开 `http://<主控机IP>:8888`
2. 点击右上角 **「设置」**
3. 添加节点：填写 `hostname`、`port`、`username`、`password`
4. 保存后返回主页，即可看到各节点 GPU 实时状态

**批量导入格式**（每行一条）：

```
node1.lab.com,22,root,password123
192.168.1.101,22,ubuntu,mypass
192.168.1.102,2222,dl-user,secret
```

---

## 📁 项目结构

```text
GPUMonitor/
├── app.py               # Flask 主程序：路由 / SSH 采集 / 连接池 / 线程池
├── servers.json         # 服务器节点配置（自动生成，含明文密码，注意保护）
├── requirements.txt     # Python 依赖（flask、paramiko）
├── Dockerfile           # Docker 镜像构建文件
├── templates/           # 前端页面模板
│   └── index.html       # 深色主题监控面板
├── .gitattributes
└── README.md
```

> ⚠️ `servers.json` 中保存的是节点的明文 SSH 凭据，**切勿提交至公开仓库**。建议将 `servers.json` 加入 `.gitignore`。

---

## ⚙️ 环境要求

| 项目 | 要求 |
| --- | --- |
| 主控机 Python | 3.9+（推荐 3.10/3.11） |
| 主控机依赖 | `flask`、`paramiko` |
| 被监控节点 | NVIDIA 驱动 + `nvidia-smi` 可用 + SSH 服务开启 |
| 网络 | 主控机能以 SSH 访问各节点（22 端口或自定义端口） |
| Docker（可选） | 任意支持 Docker 的平台 |

---

## 🚀 快速开始

1. 启动服务，浏览器打开 `http://<主控机IP>:8888`
2. 点击右上角 **「设置」**
3. 添加节点：填写 `hostname`、`port`、`username`、`password`
4. 保存后返回主页，即可看到各节点 GPU 实时状态

**批量导入示例：**

```
192.168.1.101,22,root,password123
192.168.1.102,22,ubuntu,mypass
192.168.1.103,2222,dl-user,secret
```

---

## 🔌 API 接口

以下为常用接口（具体以实际实现为准）：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/` | 监控面板首页 |
| `GET` | `/api/servers` | 获取所有节点及实时 GPU 数据（密码已脱敏） |
| `POST` | `/api/servers` | 新增节点 |
| `DELETE` | `/api/servers/<id>` | 删除节点 |
| `POST` | `/api/servers/reorder` | 调整节点顺序 |
| `POST` | `/api/servers/batch` | 批量导入节点 |

**示例：获取所有节点状态**

```bash
curl http://localhost:8888/api/servers
```

```json
{
  "ok": true,
  "servers": [
    {
      "id": "node1",
      "hostname": "192.168.1.101",
      "gpus": [
        {
          "index": 0,
          "name": "NVIDIA RTX 4090",
          "utilization": 87,
          "memory_used": 18432,
          "memory_total": 24576,
          "temperature": 68,
          "power_draw": 320,
          "power_limit": 450,
          "processes": [
            {"pid": 12345, "user": "alice", "memory": 12000, "command": "python train.py"}
          ]
        }
      ]
    }
  ]
}
```

---

## 🔔 使用建议


- **并发限制**：默认最大并发 5，如节点数量大（>20），可适当调大，但需注意防火墙阈值。
- **刷新频率**：默认 3 秒，如需降低对节点的压力，可调整前端轮询间隔。
- **安全加固**：面板默认监听 `0.0.0.0:8888`，如需公网访问，请务必置于反向代理（Nginx）+ 鉴权之下，或仅在内网使用。

---


## ⚠️ 安全提示

- 本项目通过 SSH 采集数据，**所有节点凭据保存在主控机上**，请确保主控机本身安全。
- 面板**默认无登录鉴权**，请勿直接暴露在公网。
- 生产环境建议：
  1. 使用 SSH Key 替代密码
  2. 通过 Nginx 反向代理 + Basic Auth / OAuth 保护面板
  3. 限制面板仅内网访问
- `servers.json` 保存节点 SSH 凭据，请勿提交到公开仓库；建议加入 `.gitignore`，生产环境优先使用 SSH Key。

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request。如果这个项目对你有帮助，请给个 ⭐ Star！

---

## 📄 License

本项目采用 **MIT License** 开源协议，完整条款见 [LICENSE](LICENSE)。

**第三方依赖**：本项目依赖 `Flask`、`paramiko` 等开源库，均遵循其各自的开源许可证。

---

## 🙏 致谢

- 原版项目：[fgaim/gpuview](https://github.com/fgaim/gpuview)

> 本项目仅供技术学习与研究使用，请遵守所在机构的网络与安全规范。

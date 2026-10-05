<img width="2940" height="1594" alt="image" src="https://github.com/user-attachments/assets/02973b76-c645-46ef-9efb-3e3c1fcae2c8" /># GPU Monitor (Agentless SSH 版)

[![Python](https://img.shields.io/badge/Python-3.9%2B-green)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-2.x-blue)](https://flask.palletsprojects.com/)
[![Docker](https://img.shields.io/badge/Docker-yyyyyyyz%2Fgpumonitor-blue)](https://hub.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

---

## 📝 更新日志

* **2026-10-05**：

  * 重构前端 UI，新增**亮色 / 暗黑模式切换**。
  * 新增 **GPU 任务查询与使用记录**，支持查看用户、服务器、GPU、进程、PID、开始时间、结束时间及 GPU 使用时长。
  * 支持 **Running / Finish** 状态、历史记录、搜索和分页。
  * 优化进程信息显示，支持完整用户名、进程命令及启动时间。

* **2026-09-19**：

  * 新增**快捷筛选按钮**，支持用户、空闲 GPU、服务器快捷筛选，以及一键过滤、悬停联动高亮和拖拽排序。

* **2026-06-13**：

  * 新增 Docker 部署支持，发布镜像 `yyyyyyyz/gpumonitor`。

* **2026-05-23**：

  * 新增**批量添加服务器**功能，支持按行粘贴 `hostname,port,username,password` 导入多台节点。

---

## 📸 截图预览

<img width="2940" height="1594" alt="image" src="https://github.com/user-attachments/assets/b978f353-1367-4adc-8cf3-d69b34eca768" />

<img width="2940" height="1594" alt="image" src="https://github.com/user-attachments/assets/64bd2052-c37a-41ad-bf32-5eae75bdb32b" />

<img width="2940" height="1594" alt="image" src="https://github.com/user-attachments/assets/44fb29bc-59ac-4dec-a282-540d681b91be" />

<img width="2940" height="1594" alt="image" src="https://github.com/user-attachments/assets/7d9c4be3-0c79-4d58-b16c-5fcbe682cbec" />

---

## 📖 项目简介 (Introduction)

这是一个基于 **Python + Flask** 开发的**轻量级 GPU 集群监控面板**，专为**深度学习课题组、实验室或小型服务器集群**设计。

与传统的 Prometheus + Grafana + Node Exporter 方案不同，本项目采用 **Agentless（无 Agent）** 架构：无需在被监控服务器上安装客户端、Python 包或常驻进程，只需在主控机上启动服务，即可通过 **SSH** 采集各节点的 GPU 数据和进程信息。

> 一句话总结：**一台主控机 + 若干台带 NVIDIA 显卡且开启 SSH 的节点 = 完整集群监控。**

---


## ✨ 功能特点

| 特性                      | 说明                                  |
| ----------------------- | ----------------------------------- |
| 🖥️ **零侵入 (Agentless)** | 被监控节点无需安装 Agent，通过 SSH 直接采集数据       |
| 👤 **用户级进程识别**          | 显示 GPU 使用用户、进程、PID 及显存占用            |
| 🔔 **GPU 任务记录**         | 记录用户、服务器、GPU、进程、开始 / 结束时间及 GPU 使用时长 |
| 🔎 **任务查询**             | 支持历史任务搜索、分页以及 Running / Finish 状态查看 |
| 📊 **全维数据**             | 实时监控温度、显存、利用率、功耗及进程详情               |
| 🌙 **主题切换**             | 支持亮色 / 暗黑模式                         |
| ⏱️ **平滑刷新**             | 支持定时刷新 GPU 数据，减少页面闪烁                |
| ⚡ **快捷筛选**              | 支持用户、空闲 GPU、服务器快捷筛选                 |
| 🔀 **拖拽重排**             | 支持调整服务器及快捷筛选项顺序                     |
| 🧩 **动态节点**             | 支持添加、删除及批量导入服务器                     |
| 🐳 **Docker 部署**        | 提供 `yyyyyyyz/gpumonitor` 镜像         |

---

## 🛠️ 安装与使用

### 方式一：Docker 一键部署（推荐）

```bash
docker pull yyyyyyyz/gpumonitor:latest

docker run -d \
  --name gpumonitor \
  --restart always \
  -p 8888:8888 \
  -e TZ=Asia/Shanghai \
  yyyyyyyz/gpumonitor:latest
```

启动后访问：

**http://localhost:8888**

---

### 方式二：Docker Compose 部署

创建 `docker-compose.yml`：

```yaml
services:
  gpumonitor:
    container_name: gpumonitor
    image: yyyyyyyz/gpumonitor:latest
    restart: always
    ports:
      - "8888:8888"
    environment:
      - TZ=Asia/Shanghai
```

启动：

```bash
docker compose up -d
docker compose logs -f
docker compose down
```

---

### 方式三：自行构建 Docker 镜像

```bash
git clone https://github.com/YYYYYuanZi/GPUMonitor.git
cd GPUMonitor

docker build -t gpumonitor:local .
```

运行：

```bash
docker run -d \
  --name gpumonitor \
  --restart always \
  -p 8888:8888 \
  -e TZ=Asia/Shanghai \
  -v "$(pwd)/servers.json:/app/servers.json" \
  gpumonitor:local
```

---

### 方式四：本地源码部署

```bash
git clone https://github.com/YYYYYuanZi/GPUMonitor.git
cd GPUMonitor

python -m venv venv
source venv/bin/activate       # Linux / macOS
# venv\Scripts\activate        # Windows

pip install -r requirements.txt

python app.py
```

访问：

**http://localhost:8888**

---

### 批量添加服务器

1. 打开 **Server Config / 设置**。
2. 填写 `hostname`、`port`、`username`、`password`。
3. 保存后即可开始监控。

批量导入时，每行一台服务器：

```text
node1.lab.com,22,root,password123
192.168.1.101,22,ubuntu,mypass
192.168.1.102,2222,dl-user,secret
```

---

## 📁 项目结构

```text
GPUMonitor/
├── app.py               # Flask 主程序：路由 / SSH 采集 / 连接池 / 线程池
├── servers.json         # 服务器节点配置
├── requirements.txt     # Python 依赖
├── Dockerfile           # Docker 镜像构建文件
├── templates/
│   └── index.html       # Web 前端页面
├── .gitattributes
└── README.md
```

> ⚠️ `servers.json` 中保存服务器 SSH 凭据，请勿提交至公开仓库，建议加入 `.gitignore`。

---

## ⚙️ 环境要求

| 项目         | 要求                             |
| ---------- | ------------------------------ |
| 主控机 Python | 3.9+（推荐 3.10 / 3.11）           |
| 主控机依赖      | `flask`、`paramiko`             |
| 被监控节点      | NVIDIA 驱动 + `nvidia-smi` + SSH |
| 网络         | 主控机可通过 SSH 访问各节点               |
| Docker     | 可选                             |

---

## 🔌 API 接口

| 方法       | 路径                     | 说明              |
| -------- | ---------------------- | --------------- |
| `GET`    | `/`                    | 监控面板首页          |
| `GET`    | `/api/servers`         | 获取服务器及实时 GPU 数据 |
| `POST`   | `/api/servers`         | 新增服务器           |
| `DELETE` | `/api/servers/<id>`    | 删除服务器           |
| `POST`   | `/api/servers/reorder` | 调整服务器顺序         |
| `POST`   | `/api/servers/batch`   | 批量导入服务器         |

---

## 🔔 使用建议

* **并发限制**：默认最大并发 5，节点较多时可根据实际环境调整。
* **刷新频率**：默认每 3 秒刷新一次，可根据节点数量适当调整。
* **安全访问**：面板默认监听 `0.0.0.0:8888`，不建议直接暴露到公网。

---

## ⚠️ 安全提示

* `servers.json` 保存服务器 SSH 凭据，请妥善保护。
* 面板默认**无登录鉴权**，建议仅在内网使用。
* 生产环境建议使用 **SSH Key** 替代密码。
* 如需公网访问，建议使用 **Nginx + Basic Auth / OAuth** 进行保护。

---

## 💡 致敬与改编说明 (Credits & Modifications)

本项目基于 **[fgaim/gpuview](https://github.com/fgaim/gpuview)** 进行深度二次开发，感谢原作者提供的 UI 概念与基础实现。


---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request。如果这个项目对你有帮助，请给个 ⭐ Star！

---

## 📄 License

本项目采用 **MIT License** 开源协议，完整条款见 [LICENSE](LICENSE)。

第三方依赖包括 Flask、Paramiko 等开源库，并遵循其各自的开源许可证。

---

## 🙏 致谢

* [fgaim/gpuview](https://github.com/fgaim/gpuview)

> 本项目仅供技术学习与研究使用，请遵守所在机构的网络与安全规范。

import json
import os
import time
import threading
import paramiko
from flask import Flask, render_template, request, jsonify
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)

# ================= 配置与全局变量 =================
# 配置文件路径
CONFIG_FILE = 'servers.json'

# 全局服务器列表
SERVERS = []
SERVERS_LOCK = threading.Lock()  # 读写 SERVERS 列表时使用的锁

# SSH 连接池
SSH_CLIENTS = {}
SSH_LOCK = threading.Lock()

# 全局数据缓存
GLOBAL_GPU_STATS = []
CACHE_LOCK = threading.Lock()


# ================= 持久化存储逻辑 =================
def load_config():
    """从 JSON 加载配置"""
    global SERVERS
    if not os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump([], f)
            SERVERS = []
        except Exception as e:
            print(f"Error creating config file: {e}")
    else:
        try:
            with open(CONFIG_FILE, 'r') as f:
                SERVERS = json.load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            SERVERS = []


def save_config():
    """保存配置到 JSON"""
    with SERVERS_LOCK:
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(SERVERS, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")


load_config()

# ================= 命令定义 =================
SEPARATOR = "|||SECTION_SPLIT|||"
NVIDIA_SMI_GPU_FIELDS = (
    'uuid', 'index', 'name', 'temperature.gpu', 'utilization.gpu',
    'memory.used', 'memory.total', 'power.draw', 'power.limit'
)
CMD_GPU = f'nvidia-smi --query-gpu={",".join(NVIDIA_SMI_GPU_FIELDS)} --format=csv,noheader,nounits'
NVIDIA_SMI_PROC_FIELDS = ('gpu_uuid', 'pid', 'process_name', 'used_gpu_memory')
CMD_PROC = f'nvidia-smi --query-compute-apps={",".join(NVIDIA_SMI_PROC_FIELDS)} --format=csv,noheader,nounits'
COMBINED_CMD = f"{CMD_GPU} ; echo '{SEPARATOR}' ; {CMD_PROC}"


# ================= 核心逻辑 =================

def get_ssh_client(host_details):
    """获取或创建带有 Keep-Alive 的 SSH 连接 (带重试机制)"""
    hostname = host_details['hostname']

    with SSH_LOCK:
        # 1. 尝试复用现有连接
        client = SSH_CLIENTS.get(hostname)
        if client and client.get_transport() and client.get_transport().is_active():
            return client

        # 如果连接无效，先清理
        if hostname in SSH_CLIENTS:
            try:
                SSH_CLIENTS[hostname].close()
            except:
                pass
            SSH_CLIENTS.pop(hostname, None)

    # 2. 建立新连接（在锁外部进行，避免阻塞其他线程，但写入时需要锁）
    # 重试机制：防止偶尔的网络抖动或 Banner 读取失败
    retries = 3
    last_error = None

    for attempt in range(retries):
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            client.connect(
                hostname,
                port=int(host_details.get('port', 22)),
                username=host_details['username'],
                password=host_details['password'],
                timeout=10,  # TCP socket 连接超时
                banner_timeout=60,  # 增加 Banner 等待时间到 60s
                auth_timeout=30,  # 认证超时
                look_for_keys=False,  # 禁用私钥搜索
                allow_agent=False  # 禁用 Agent
            )
            client.get_transport().set_keepalive(30)

            with SSH_LOCK:
                SSH_CLIENTS[hostname] = client
            return client

        except Exception as e:
            last_error = e
            try:
                client.close()
            except:
                pass
            # 失败后等待一小段时间再重试
            time.sleep(1 + attempt)

            # 如果重试多次后依然失败
    raise last_error


def fetch_single_server_data(host_details):
    """采集单台服务器数据"""
    hostname = host_details['hostname']
    try:
        client = get_ssh_client(host_details)

        stdin, stdout, stderr = client.exec_command(COMBINED_CMD, timeout=15)
        output = stdout.read().decode('utf-8').strip()

        if not output:
            return {"hostname": hostname, "error": "Empty response"}

        parts = output.split(SEPARATOR)
        gpu_lines = parts[0].strip().splitlines() if len(parts) > 0 else []
        proc_lines = parts[1].strip().splitlines() if len(parts) > 1 else []

        gpus = []
        for line in gpu_lines:
            if not line.strip(): continue
            vals = [v.strip() for v in line.split(',')]
            if len(vals) < len(NVIDIA_SMI_GPU_FIELDS): continue
            gpus.append(dict(zip(NVIDIA_SMI_GPU_FIELDS, vals)))

        if not gpus:
            return {"hostname": hostname, "error": "No GPUs found"}

        processes_by_uuid = {}
        all_pids = set()

        for line in proc_lines:
            if not line.strip(): continue
            vals = [v.strip() for v in line.split(',')]
            p_info = dict(zip(NVIDIA_SMI_PROC_FIELDS, vals))
            uuid = p_info['gpu_uuid']
            if uuid not in processes_by_uuid: processes_by_uuid[uuid] = []
            processes_by_uuid[uuid].append(p_info)
            all_pids.add(p_info['pid'])

        pid_to_user = {}
        if all_pids:
            pids_str = ",".join(all_pids)
            try:
                cmd_ps = f"ps -o pid=,user= -p {pids_str}"
                stdin, stdout, stderr = client.exec_command(cmd_ps, timeout=10)
                ps_out = stdout.read().decode('utf-8').strip()
                for line in ps_out.splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        pid_to_user[parts[0]] = parts[1]
            except Exception:
                pass

        final_gpu_list = []
        for gpu in gpus:
            try:
                mem_used = int(float(gpu['memory.used']))
                mem_total = int(float(gpu['memory.total']))
                temp = int(float(gpu['temperature.gpu']))
                util = int(float(gpu['utilization.gpu']))
                power_draw = int(float(gpu['power.draw']))
                power_limit = int(float(gpu['power.limit']))
            except ValueError:
                mem_used = mem_total = temp = util = power_draw = power_limit = 0

            procs = processes_by_uuid.get(gpu['uuid'], [])
            proc_strs = []
            for p in procs:
                pid = p['pid']
                user = pid_to_user.get(pid, 'unknown')
                try:
                    mem = int(float(p['used_gpu_memory']))
                except ValueError:
                    mem = 0
                name = p['process_name'].replace(' ', '')
                proc_strs.append(f"{user}({name},{mem}M)")

            final_gpu_list.append({
                "index": str(int(gpu['index'])),
                "name": gpu['name'],
                "temperature.gpu": temp,
                "utilization.gpu": util,
                "memory.used": mem_used,
                "memory.total": mem_total,
                "memory": round((mem_used / mem_total) * 100) if mem_total > 0 else 0,
                "power.draw": power_draw,
                "enforced.power.limit": power_limit,
                "user_processes": " ".join(proc_strs),
                "users": len(proc_strs)
            })

        return {"hostname": hostname, "gpus": final_gpu_list}

    except Exception as e:
        # 连接失败时，从缓存中移除，下次重试
        with SSH_LOCK:
            SSH_CLIENTS.pop(hostname, None)
        return {"hostname": hostname, "error": str(e), "gpus": []}


def background_monitor_loop():
    """后台线程：轮询采集所有服务器"""
    global GLOBAL_GPU_STATS
    print("Starting background monitor thread...")
    while True:
        start_time = time.time()

        with SERVERS_LOCK:
            current_servers = list(SERVERS)

        if not current_servers:
            with CACHE_LOCK:
                GLOBAL_GPU_STATS = []
            time.sleep(2)
            continue

        results = []
        # === 关键修改：限制最大并发数为 5 ===
        # 避免同时发起过多 SSH 连接导致被防火墙拦截或 Banner 读取失败
        max_threads = min(5, len(current_servers))

        # 如果服务器数量 > 0，才执行
        if max_threads > 0:
            with ThreadPoolExecutor(max_workers=max_threads) as executor:
                futures = executor.map(fetch_single_server_data, current_servers)
                results = list(futures)
        else:
            results = []

        with CACHE_LOCK:
            GLOBAL_GPU_STATS = results

        elapsed = time.time() - start_time
        sleep_time = max(1.0, 3.0 - elapsed)  # 稍微增加最小等待时间
        time.sleep(sleep_time)


# ================= Flask 路由 =================

@app.route('/')
def dashboard():
    return render_template('index.html')


@app.route('/api/gpustat/all')
def api_gpu_data():
    with CACHE_LOCK:
        return jsonify(GLOBAL_GPU_STATS)


# --- 管理接口 ---

@app.route('/api/admin/servers', methods=['GET'])
def get_servers():
    with SERVERS_LOCK:
        safe_list = []
        for s in SERVERS:
            safe_s = s.copy()
            if 'password' in safe_s:
                safe_s.pop('password')
            safe_list.append(safe_s)
        return jsonify(safe_list)


@app.route('/api/admin/servers', methods=['POST'])
def add_server():
    data = request.json
    required = ['hostname', 'port', 'username', 'password']
    if not all(k in data for k in required):
        return jsonify({"error": "Missing fields"}), 400

    with SERVERS_LOCK:
        for s in SERVERS:
            if s['hostname'] == data['hostname']:
                return jsonify({"error": "Hostname already exists"}), 400
        SERVERS.append(data)

    save_config()
    return jsonify({"success": True})


@app.route('/api/admin/servers', methods=['DELETE'])
def delete_server():
    data = request.json
    hostname = data.get('hostname')

    with SERVERS_LOCK:
        global SERVERS
        SERVERS = [s for s in SERVERS if s['hostname'] != hostname]

    with SSH_LOCK:
        if hostname in SSH_CLIENTS:
            try:
                SSH_CLIENTS[hostname].close()
            except:
                pass
            SSH_CLIENTS.pop(hostname, None)

    save_config()
    return jsonify({"success": True})


@app.route('/api/admin/servers/reorder', methods=['POST'])
def reorder_servers():
    new_order_hostnames = request.json
    if not isinstance(new_order_hostnames, list):
        return jsonify({"error": "Invalid data format"}), 400

    with SERVERS_LOCK:
        global SERVERS
        server_map = {s['hostname']: s for s in SERVERS}
        new_servers_list = []
        seen_hosts = set()

        for hostname in new_order_hostnames:
            if hostname in server_map:
                new_servers_list.append(server_map[hostname])
                seen_hosts.add(hostname)

        for s in SERVERS:
            if s['hostname'] not in seen_hosts:
                new_servers_list.append(s)

        SERVERS = new_servers_list

    save_config()
    return jsonify({"success": True})


if __name__ == '__main__':
    monitor_thread = threading.Thread(target=background_monitor_loop, daemon=True)
    monitor_thread.start()
    print(f"Server started on port 8888. Configuration loaded from {CONFIG_FILE}")
    app.run(debug=False, host='0.0.0.0', port=8888)

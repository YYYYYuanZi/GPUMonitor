import json
import os
import re
import time
import threading
import paramiko
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)

# ================= 配置与全局变量 =================
CONFIG_FILE = 'servers.json'
NOTIFICATIONS_FILE = 'notifications.json'
VISITS_FILE = 'visits.json'

SERVERS = []
SERVERS_LOCK = threading.Lock()

SSH_CLIENTS = {}
SSH_LOCK = threading.Lock()

GLOBAL_GPU_STATS = []
CACHE_LOCK = threading.Lock()

# ===== 通知相关 =====
NOTIFICATIONS = []
NOTIFICATIONS_LOCK = threading.Lock()
ACTIVE_PIDS = {}
NOTIFICATIONS_MAX = 1000

# ===== 访问统计相关 =====
VISITS = []
VISITS_LOCK = threading.Lock()
VISITS_MAX = 5000


# ================= 持久化存储逻辑 =================
def load_config():
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
    with SERVERS_LOCK:
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(SERVERS, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")


def load_notifications():
    global NOTIFICATIONS, ACTIVE_PIDS
    if not os.path.exists(NOTIFICATIONS_FILE):
        NOTIFICATIONS = []
    else:
        try:
            with open(NOTIFICATIONS_FILE, 'r', encoding='utf-8') as f:
                NOTIFICATIONS = json.load(f)
                if not isinstance(NOTIFICATIONS, list):
                    NOTIFICATIONS = []
        except Exception as e:
            print(f"Error loading notifications: {e}")
            NOTIFICATIONS = []

    ACTIVE_PIDS = {}
    for i, n in enumerate(NOTIFICATIONS):
        if n.get('end_time') is None:
            ACTIVE_PIDS[(n.get('hostname', ''), str(n.get('pid', '')))] = i


def save_notifications():
    # 注意：调用者必须在 NOTIFICATIONS_LOCK 之外调用本函数。
    # 避免 update_notifications 持锁后再次获取同一把 threading.Lock() 导致死锁。
    with NOTIFICATIONS_LOCK:
        try:
            with open(NOTIFICATIONS_FILE, 'w', encoding='utf-8') as f:
                json.dump(NOTIFICATIONS, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving notifications: {e}")


def load_visits():
    global VISITS
    if not os.path.exists(VISITS_FILE):
        VISITS = []
    else:
        try:
            with open(VISITS_FILE, 'r', encoding='utf-8') as f:
                VISITS = json.load(f)
                if not isinstance(VISITS, list):
                    VISITS = []
        except Exception as e:
            print(f"Error loading visits: {e}")
            VISITS = []


def save_visits_locked():
    # 调用者必须已持有 VISITS_LOCK
    try:
        with open(VISITS_FILE, 'w', encoding='utf-8') as f:
            json.dump(VISITS[-VISITS_MAX:], f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving visits: {e}")


load_config()
load_notifications()
load_visits()


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

# 关键修复：给 user / lstart 指定足够列宽，避免 ps 把长用户名截断成 "chengle+"。
# 同时输出 uid= 用于兜底反查完整用户名。
PS_FIELDS = "pid=,user:64=,uid=,lstart:32=,args="


# ================= 工具函数 =================
def simplify_gpu_model(name):
    if not name:
        return ''
    name = name.replace('NVIDIA ', '').replace('GeForce ', '')
    return name.strip()


def format_duration(seconds):
    if seconds < 0:
        seconds = 0
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}h {m:02d}m {s:02d}s"
    if m > 0:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def parse_lstart(lstart_str):
    if not lstart_str:
        return None
    try:
        s = ' '.join(lstart_str.split())
        tm = time.strptime(s, '%a %b %d %H:%M:%S %Y')
        return time.strftime('%Y-%m-%d %H:%M:%S', tm)
    except Exception:
        return None


def looks_truncated(username):
    """ps 截断用户名时通常以 '+' 结尾（如 chengle+ / wangxin+）。"""
    if not username:
        return False
    return username.endswith('+') or username.endswith('+ ')


# ================= 访问统计工具 =================
def _get_client_ip():
    xff = request.headers.get('X-Forwarded-For', '')
    if xff:
        return xff.split(',')[0].strip()
    xri = request.headers.get('X-Real-IP', '')
    if xri:
        return xri.strip()
    return request.remote_addr or 'unknown'


def _parse_ua(ua):
    """从 User-Agent 粗略解析设备 / 操作系统 / 浏览器。"""
    ua = ua or ''
    low = ua.lower()

    # 设备类型
    if re.search(r'bot|crawler|spider|slurp|bingpreview|curl|wget|python-requests|httpclient', low):
        device = 'Bot'
    elif re.search(r'ipad|tablet|kindle|playbook|silk', low):
        device = 'Tablet'
    elif re.search(r'mobile|iphone|ipod|android.*mobile|windows phone|blackberry', low):
        device = 'Mobile'
    elif re.search(r'windows|macintosh|linux|x11|cros', low):
        device = 'Desktop'
    else:
        device = 'Unknown'

    # 操作系统
    os_name = 'Unknown'
    if 'windows nt 10' in low:
        os_name = 'Windows 10/11'
    elif 'windows nt 6.3' in low:
        os_name = 'Windows 8.1'
    elif 'windows nt 6.1' in low:
        os_name = 'Windows 7'
    elif 'windows' in low:
        os_name = 'Windows'
    elif 'android' in low:
        os_name = 'Android'
    elif 'iphone' in low or 'ipad' in low or 'ipod' in low:
        os_name = 'iOS'
    elif 'mac os x' in low or 'macintosh' in low:
        os_name = 'macOS'
    elif 'cros' in low:
        os_name = 'ChromeOS'
    elif 'linux' in low:
        os_name = 'Linux'

    # 浏览器
    browser = 'Unknown'
    if 'edg/' in low or 'edgios' in low or 'edga' in low:
        browser = 'Edge'
    elif 'opr/' in low or 'opera' in low:
        browser = 'Opera'
    elif 'chrome/' in low or 'crios' in low:
        browser = 'Chrome'
    elif 'firefox/' in low or 'fxios' in low:
        browser = 'Firefox'
    elif 'safari/' in low:
        browser = 'Safari'
    elif 'msie' in low or 'trident' in low:
        browser = 'IE'

    return device, os_name, browser


# ================= SSH / GPU 数据 =================
def get_ssh_client(host_details):
    hostname = host_details['hostname']

    with SSH_LOCK:
        client = SSH_CLIENTS.get(hostname)
        if client and client.get_transport() and client.get_transport().is_active():
            return client

        if hostname in SSH_CLIENTS:
            try:
                SSH_CLIENTS[hostname].close()
            except Exception:
                pass
            SSH_CLIENTS.pop(hostname, None)

    retries = 1
    last_error = None

    for attempt in range(retries):
        client = None
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                hostname,
                port=int(host_details.get('port', 22)),
                username=host_details['username'],
                password=host_details['password'],
                timeout=5,
                banner_timeout=3,
                auth_timeout=3,
                look_for_keys=False,
                allow_agent=False
            )
            client.get_transport().set_keepalive(30)

            with SSH_LOCK:
                SSH_CLIENTS[hostname] = client
            return client

        except Exception as e:
            last_error = e
            try:
                if client:
                    client.close()
            except Exception:
                pass
            time.sleep(1 + attempt)

    raise last_error


def fetch_single_server_data(host_details):
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
            if not line.strip():
                continue
            vals = [v.strip() for v in line.split(',')]
            if len(vals) < len(NVIDIA_SMI_GPU_FIELDS):
                continue
            gpus.append(dict(zip(NVIDIA_SMI_GPU_FIELDS, vals)))

        if not gpus:
            return {"hostname": hostname, "error": "No GPUs found"}

        processes_by_uuid = {}
        all_pids = set()

        for line in proc_lines:
            if not line.strip():
                continue
            vals = [v.strip() for v in line.split(',')]
            p_info = dict(zip(NVIDIA_SMI_PROC_FIELDS, vals))
            uuid = p_info['gpu_uuid']
            if uuid not in processes_by_uuid:
                processes_by_uuid[uuid] = []
            processes_by_uuid[uuid].append(p_info)
            all_pids.add(p_info['pid'])

        # ---- 兜底：建立 uid -> username 映射（用于 ps 截断时反查） ----
        uid_to_user = {}
        try:
            stdin, stdout, stderr = client.exec_command("getent passwd", timeout=10)
            passwd_out = stdout.read().decode('utf-8', errors='ignore')
            for line in passwd_out.splitlines():
                cols = line.split(':')
                if len(cols) >= 3:
                    uid_to_user[cols[2]] = cols[0]
        except Exception as e:
            print(f"[{hostname}] getent passwd failed: {e}")

        pid_to_info = {}
        if all_pids:
            pids_str = ",".join(all_pids)
            try:
                cmd_ps = f"ps -o {PS_FIELDS} -p {pids_str}"
                stdin, stdout, stderr = client.exec_command(cmd_ps, timeout=10)
                ps_out = stdout.read().decode('utf-8', errors='ignore')

                for line in ps_out.splitlines():
                    line = line.strip()
                    if not line:
                        continue

                    parts_ps = line.split(None, 9)

                    if len(parts_ps) >= 9:
                        pid = parts_ps[0]
                        user_raw = parts_ps[1]
                        uid = parts_ps[2]
                        lstart_str = ' '.join(parts_ps[3:8])
                        args = parts_ps[8] if len(parts_ps) > 8 else ''
                    elif len(parts_ps) >= 8:
                        pid = parts_ps[0]
                        user_raw = parts_ps[1]
                        uid = ''
                        lstart_str = ' '.join(parts_ps[2:7])
                        args = parts_ps[7] if len(parts_ps) > 7 else ''
                    elif len(parts_ps) >= 7:
                        pid = parts_ps[0]
                        user_raw = parts_ps[1]
                        uid = ''
                        lstart_str = ' '.join(parts_ps[2:7])
                        args = ''
                    else:
                        continue

                    user = user_raw
                    if looks_truncated(user_raw) and uid and uid in uid_to_user:
                        user = uid_to_user[uid]
                    elif (not user or user == 'unknown') and uid and uid in uid_to_user:
                        user = uid_to_user[uid]

                    pid_to_info[pid] = {
                        'user': user,
                        'command': args[:512],
                        'start_time': parse_lstart(lstart_str),
                    }
            except Exception as e:
                print(f"[{hostname}] ps failed: {e}")

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
            proc_details = []
            for p in procs:
                pid = p['pid']
                info = pid_to_info.get(pid, {})
                user = info.get('user', 'unknown')
                cmd = info.get('command', p['process_name'])
                start_time = info.get('start_time')

                try:
                    mem = int(float(p['used_gpu_memory']))
                except ValueError:
                    mem = 0
                name = p['process_name'].replace(' ', '')
                proc_strs.append(f"{user}({name},{mem}M)")
                proc_details.append({
                    'pid': int(pid),
                    'user': user,
                    'command': cmd,
                    'memory': mem,
                    'process_name': p['process_name'],
                    'start_time': start_time,
                })

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
                "users": len(proc_strs),
                "_processes": proc_details,
            })

        return {"hostname": hostname, "gpus": final_gpu_list}

    except Exception as e:
        with SSH_LOCK:
            SSH_CLIENTS.pop(hostname, None)
        return {"hostname": hostname, "error": str(e), "gpus": []}


# ================= 通知核心逻辑 =================
def update_notifications(results):
    """
    对比当前轮抓到的进程集合与 ACTIVE_PIDS：
      - 新 PID → 新建通知记录
      - 已有 PID → 更新 gpus / user / command / gpu_model
      - 消失的 PID → 标记 end_time

    重要：save_notifications() 必须在 NOTIFICATIONS_LOCK 释放后调用，
    否则会因为 threading.Lock 不可重入而发生死锁。
    """
    global NOTIFICATIONS, ACTIVE_PIDS

    now_str = time.strftime('%Y-%m-%d %H:%M:%S')
    seen_keys = set()

    with NOTIFICATIONS_LOCK:
        for node in results:
            if not node or node.get('error'):
                continue

            hostname = node.get('hostname', '')

            for gpu in node.get('gpus', []):
                gpu_index = '#' + str(gpu.get('index', ''))
                gpu_model = simplify_gpu_model(gpu.get('name', ''))

                for proc in gpu.get('_processes', []):
                    pid = str(proc.get('pid', ''))
                    if not pid:
                        continue

                    key = (hostname, pid)
                    seen_keys.add(key)

                    if key in ACTIVE_PIDS:
                        idx = ACTIVE_PIDS[key]
                        if not (0 <= idx < len(NOTIFICATIONS)):
                            continue

                        notif = NOTIFICATIONS[idx]

                        if gpu_index not in notif['gpus']:
                            notif['gpus'].append(gpu_index)
                        if proc.get('user'):
                            notif['user'] = proc['user']
                        if proc.get('command'):
                            notif['command'] = proc['command']
                        if gpu_model:
                            notif['gpu_model'] = gpu_model
                    else:
                        start_time = proc.get('start_time') or now_str
                        new_notif = {
                            'hostname': hostname,
                            'pid': int(pid),
                            'user': proc.get('user', 'unknown'),
                            'command': proc.get('command', ''),
                            'gpus': [gpu_index],
                            'gpu_model': gpu_model,
                            'start_time': start_time,
                            'end_time': None,
                        }
                        NOTIFICATIONS.append(new_notif)
                        ACTIVE_PIDS[key] = len(NOTIFICATIONS) - 1

        disappeared = [
            k for k in list(ACTIVE_PIDS.keys())
            if k not in seen_keys
        ]

        for key in disappeared:
            idx = ACTIVE_PIDS.pop(key)
            if 0 <= idx < len(NOTIFICATIONS):
                NOTIFICATIONS[idx]['end_time'] = now_str

        if len(NOTIFICATIONS) > NOTIFICATIONS_MAX:
            running = [
                n for n in NOTIFICATIONS
                if n.get('end_time') is None
            ]
            finished = [
                n for n in NOTIFICATIONS
                if n.get('end_time') is not None
            ]
            finished.sort(
                key=lambda x: x.get('end_time', ''),
                reverse=True
            )

            keep_count = max(0, NOTIFICATIONS_MAX - len(running))
            keep = running + finished[:keep_count]
            NOTIFICATIONS[:] = keep

            ACTIVE_PIDS.clear()
            for i, n in enumerate(NOTIFICATIONS):
                if n.get('end_time') is None:
                    ACTIVE_PIDS[
                        (n.get('hostname', ''), str(n.get('pid', '')))
                    ] = i

    # 锁已经释放，再执行文件写入。
    save_notifications()


def background_monitor_loop():
    global GLOBAL_GPU_STATS

    while True:
        start_time = time.time()

        with SERVERS_LOCK:
            current_servers = list(SERVERS)

        if not current_servers:
            with CACHE_LOCK:
                GLOBAL_GPU_STATS = []
            time.sleep(1)
            continue

        max_threads = min(10, len(current_servers))
        if max_threads > 0:
            with ThreadPoolExecutor(max_workers=max_threads) as executor:
                results = list(
                    executor.map(fetch_single_server_data, current_servers)
                )
        else:
            results = []

        with CACHE_LOCK:
            GLOBAL_GPU_STATS = results

        try:
            update_notifications(results)
        except Exception as e:
            print(f"update_notifications failed: {e}")

        elapsed = time.time() - start_time
        sleep_time = max(0.5, 1.0 - elapsed)
        time.sleep(sleep_time)


# ================= Flask 路由 =================
@app.route('/')
def dashboard():
    return render_template('index.html')


@app.route('/stats.html')
def stats_page():
    # 如果 stats.html 放在 templates 下，用 render_template；
    # 如果和 app.py 同目录，可直接 send_from_directory。
    return render_template('stats.html')


@app.route('/api/gpustat/all')
def api_gpu_data():
    with CACHE_LOCK:
        safe = []
        for node in GLOBAL_GPU_STATS:
            node_copy = dict(node)
            if 'gpus' in node_copy:
                gpus_copy = []
                for g in node_copy['gpus']:
                    g2 = {
                        k: v for k, v in g.items()
                        if k != '_processes'
                    }
                    gpus_copy.append(g2)
                node_copy['gpus'] = gpus_copy
            safe.append(node_copy)
        return jsonify(safe)


# ================= 访问统计接口 =================
@app.route('/api/track', methods=['POST'])
def api_track():
    try:
        payload = request.get_json(silent=True) or {}
    except Exception:
        payload = {}

    ip = _get_client_ip()
    ua = request.headers.get('User-Agent', '')
    device, os_name, browser = _parse_ua(ua)

    record = {
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'ip': ip,
        'device': device,
        'os': os_name,
        'browser': browser,
        'ua': ua[:300],
        'path': str(payload.get('path', '/'))[:200],
        'referrer': str(payload.get('referrer', ''))[:300],
        'screen': str(payload.get('screen', ''))[:40],
        'language': str(payload.get('language', ''))[:40],
        'tz': str(payload.get('tz', ''))[:60],
    }

    global VISITS
    with VISITS_LOCK:
        VISITS.append(record)
        if len(VISITS) > VISITS_MAX:
            VISITS = VISITS[-VISITS_MAX:]
        save_visits_locked()

    return jsonify({'success': True})


@app.route('/api/stats')
def api_stats():
    with VISITS_LOCK:
        visits = list(VISITS)

    total = len(visits)
    unique_ips = len({v.get('ip') for v in visits if v.get('ip')})
    unique_devices = len({
        f"{v.get('device')}|{v.get('os')}|{v.get('browser')}" for v in visits
    })

    today_str = datetime.now().strftime('%Y-%m-%d')
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    today = sum(1 for v in visits if str(v.get('time', '')).startswith(today_str))
    yesterday = sum(1 for v in visits if str(v.get('time', '')).startswith(yesterday_str))

    # 最近一次访问时间
    last_time = visits[-1].get('time', '') if visits else ''

    # 趋势（14 天，前端会自己按 24h/7d/14d/30d 重新分桶）
    trend_map = {}
    for i in range(13, -1, -1):
        d = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        trend_map[d] = 0
    for v in visits:
        d = str(v.get('time', ''))[:10]
        if d in trend_map:
            trend_map[d] += 1
    trend = [{'date': d, 'count': c} for d, c in trend_map.items()]

    devices = {}
    for v in visits:
        k = v.get('device', 'Unknown')
        devices[k] = devices.get(k, 0) + 1

    hours = {str(i).zfill(2): 0 for i in range(24)}
    for v in visits:
        t = str(v.get('time', ''))
        if len(t) >= 13:
            h = t[11:13]
            if h in hours:
                hours[h] += 1

    ua_map = {}
    for v in visits:
        key = f"{v.get('browser', 'Unknown')} / {v.get('os', 'Unknown')}"
        ua_map[key] = ua_map.get(key, 0) + 1
    ua_sorted = dict(sorted(ua_map.items(), key=lambda x: x[1], reverse=True)[:8])

    recent = list(reversed(visits))

    return jsonify({
        'total': total,
        'uniqueIPs': unique_ips,
        'uniqueDevices': unique_devices,
        'today': today,
        'yesterday': yesterday,       # ← 新增
        'lastTime': last_time,        # ← 新增
        'trend': trend,
        'devices': devices,
        'hours': hours,
        'ua': ua_sorted,
        'visits': recent,             # 前端会用这个现算 24h / 7d / 14d / 30d 趋势
    })


# ================= 通知接口 =================
def _notification_ordered_locked():
    """Return notifications in the same order used by the UI.

    Caller must hold NOTIFICATIONS_LOCK.
    """
    running_list = [n for n in NOTIFICATIONS if n.get('end_time') is None]
    finished_list = [n for n in NOTIFICATIONS if n.get('end_time') is not None]

    running_list.sort(key=lambda x: x.get('start_time', ''), reverse=True)
    finished_list.sort(key=lambda x: x.get('start_time', ''), reverse=True)
    return running_list + finished_list


def _notification_to_api_item(n):
    duration = None
    if n.get('end_time') and n.get('start_time'):
        try:
            t1 = time.mktime(time.strptime(n['start_time'], '%Y-%m-%d %H:%M:%S'))
            t2 = time.mktime(time.strptime(n['end_time'], '%Y-%m-%d %H:%M:%S'))
            duration = format_duration(int(t2 - t1))
        except Exception:
            duration = None

    return {
        'status': 'Running' if n.get('end_time') is None else 'Finish',
        'user': n.get('user', ''),
        'server': n.get('hostname', ''),
        'gpus': n.get('gpus', []),
        'gpuModel': n.get('gpu_model', ''),
        'pid': n.get('pid'),
        'command': n.get('command', ''),
        'startTime': n.get('start_time', ''),
        'endTime': n.get('end_time'),
        'duration': duration,
    }


def _paginate_notification_items(ordered, page, page_size):
    total = len(ordered)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(max(1, page), total_pages)
    start = (page - 1) * page_size
    page_items = ordered[start:start + page_size]
    return page_items, total, page, total_pages


@app.route('/api/notifications')
def api_notifications():
    try:
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('pageSize', 10))
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid page/pageSize'}), 400

    page = max(1, page)
    page_size = max(1, min(100, page_size))

    with NOTIFICATIONS_LOCK:
        ordered = _notification_ordered_locked()
        page_items, total, page, total_pages = _paginate_notification_items(
            ordered, page, page_size
        )
        items = [_notification_to_api_item(n) for n in page_items]

    return jsonify({
        'items': items,
        'total': total,
        'page': page,
        'pageSize': page_size,
        'totalPages': total_pages,
        'query': '',
    })


@app.route('/api/notifications/search')
def api_notifications_search():
    """Search the complete notification history, then paginate the matches.

    Query terms are ANDed: `root 5090` means both terms must occur in the
    searchable fields of the same notification.
    """
    try:
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('pageSize', 10))
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid page/pageSize'}), 400

    query = str(request.args.get('q', '') or '').strip()
    page = max(1, page)
    page_size = max(1, min(100, page_size))

    terms = [term.casefold() for term in query.split() if term.strip()]

    with NOTIFICATIONS_LOCK:
        ordered = _notification_ordered_locked()

        if terms:
            matched = []
            for n in ordered:
                status = 'running' if n.get('end_time') is None else 'finish'
                searchable = ' '.join([
                    status,
                    'running' if status == 'running' else '',
                    'finished' if status == 'finish' else '',
                    str(n.get('user', '')),
                    str(n.get('hostname', '')),
                    str(n.get('gpu_model', '')),
                    ' '.join(str(x) for x in (n.get('gpus') or [])),
                    str(n.get('pid', '')),
                    str(n.get('command', '')),
                    str(n.get('start_time', '')),
                    str(n.get('end_time', '') or ''),
                ]).casefold()

                if all(term in searchable for term in terms):
                    matched.append(n)
            ordered = matched

        page_items, total, page, total_pages = _paginate_notification_items(
            ordered, page, page_size
        )
        items = [_notification_to_api_item(n) for n in page_items]

    return jsonify({
        'items': items,
        'total': total,
        'page': page,
        'pageSize': page_size,
        'totalPages': total_pages,
        'query': query,
    })


# ================= 管理接口 =================
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


@app.route('/api/admin/servers/bulk', methods=['POST'])
def add_servers_bulk():
    data = request.json
    if not isinstance(data, dict) or 'servers' not in data or not isinstance(data['servers'], list):
        return jsonify({"error": "Invalid payload"}), 400

    added = 0
    skipped = []
    invalid_count = 0

    with SERVERS_LOCK:
        existing_hosts = {s['hostname'] for s in SERVERS}

        for server in data['servers']:
            if not isinstance(server, dict):
                invalid_count += 1
                continue

            if not all(
                k in server
                for k in ['hostname', 'port', 'username', 'password']
            ):
                invalid_count += 1
                continue

            hostname = server['hostname']

            if hostname in existing_hosts:
                skipped.append(hostname)
                continue

            existing_hosts.add(hostname)
            SERVERS.append({
                'hostname': hostname,
                'port': server['port'],
                'username': server['username'],
                'password': server['password']
            })
            added += 1

    save_config()
    return jsonify({
        "success": True,
        "added": added,
        "skipped": skipped,
        "invalid": invalid_count
    })


@app.route('/api/admin/servers', methods=['DELETE'])
def delete_server():
    global SERVERS

    data = request.json
    hostname = data.get('hostname')

    with SERVERS_LOCK:
        SERVERS = [
            s for s in SERVERS
            if s['hostname'] != hostname
        ]

    with SSH_LOCK:
        if hostname in SSH_CLIENTS:
            try:
                SSH_CLIENTS[hostname].close()
            except Exception:
                pass
            SSH_CLIENTS.pop(hostname, None)

    save_config()
    return jsonify({"success": True})


@app.route('/api/admin/servers/reorder', methods=['POST'])
def reorder_servers():
    global SERVERS

    new_order_hostnames = request.json
    if not isinstance(new_order_hostnames, list):
        return jsonify({"error": "Invalid data format"}), 400

    with SERVERS_LOCK:
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
    monitor_thread = threading.Thread(
        target=background_monitor_loop,
        daemon=True
    )
    monitor_thread.start()

    print(
        f"Server started on port 8888. "
        f"Configuration loaded from {CONFIG_FILE}"
    )

    app.run(
        debug=True,
        host='0.0.0.0',
        port=8888
    )
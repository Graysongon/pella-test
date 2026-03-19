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

# 使用新的环境变量名 PELLA_ACCOUNT，如果未设置则尝试读取旧的 KERIT_ACCOUNT
_account_str = os.environ.get("PELLA_ACCOUNT") or os.environ.get("KERIT_ACCOUNT", "")
_account = _account_str.split(",")
PELLA_EMAIL    = _account[0].strip() if len(_account) > 0 else ""
GMAIL_PASSWORD = _account[1].strip() if len(_account) > 1 else ""

LOCAL_PROXY    = "http://127.0.0.1:8080"
MASKED_EMAIL   = "******@" + PELLA_EMAIL.split("@")[-1] if "@" in PELLA_EMAIL else ""

# 更新为 Pella 新域名
LOGIN_URL      = "https://www.pella.app/"
DASHBOARD_URL  = "https://www.pella.app/dashboard"

_tg_raw = os.environ.get("TG_BOT", "")
if _tg_raw and "," in _tg_raw:
    _tg = _tg_raw.split(",")
    TG_CHAT_ID = _tg[0].strip()
    TG_TOKEN   = _tg[1].strip()
else:
    TG_CHAT_ID = ""
    TG_TOKEN   = ""

# ============================================================
# 工具函数：TG 推送与时间
# ============================================================

def now_str():
    import datetime
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def send_tg(result, server_info=None, remaining=None):
    lines = [
        f"🎮 Pella 服务器续期通知",
        f"🕐 运行时间: {now_str()}",
        f"📊 任务结果: {result}"
    ]
    if server_info: lines.append(f"🖥 信息: {server_info}")
    if remaining: lines.append(f"⏱️ 状态: {remaining}")
    
    msg = "\n".join(lines)
    if not TG_TOKEN or not TG_CHAT_ID:
        print("⚠️ TG未配置，跳过推送")
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": TG_CHAT_ID, "text": msg}).encode()
    try:
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"📨 TG推送成功")
    except Exception as e:
        print(f"⚠️ TG推送失败：{e}")

# ============================================================
# Gmail OTP 读取逻辑
# ============================================================

def fetch_otp_from_gmail(wait_seconds=60) -> str:
    print(f"📬 连接Gmail，等待{wait_seconds}s...")
    deadline = time.time() + wait_seconds
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    try:
        mail.login(PELLA_EMAIL, GMAIL_PASSWORD)
    except Exception as e:
        raise Exception(f"Gmail登录失败: {e}")

    # 寻找垃圾箱文件夹
    spam_folder = None
    _, folder_list = mail.list()
    for f in folder_list:
        decoded = f.decode("utf-8", errors="ignore")
        if any(k in decoded.lower() for k in ["spam", "junk", "垃圾"]):
            match = re.search(r'"([^"]+)"\s*$', decoded) or re.search(r'(\S+)\s*$', decoded)
            if match:
                spam_folder = match.group(1).strip('"')
                break

    folders = ["INBOX"]
    if spam_folder: folders.append(spam_folder)

    seen_uids = {f: set() for f in folders}
    # 记录初始状态
    for f in folders:
        try:
            mail.select(f)
            _, data = mail.uid("search", None, "ALL")
            seen_uids[f] = set(data[0].split())
        except: pass

    while time.time() < deadline:
        time.sleep(5)
        for f in folders:
            try:
                mail.select(f)
                # 匹配发件人包含 pella 的邮件
                _, data = mail.uid("search", None, 'FROM "pella"')
                current_uids = set(data[0].split())
                new_uids = current_uids - seen_uids[f]

                for uid in new_uids:
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

                    otp = re.search(r'\b(\d{4,6})\b', body)
                    if otp:
                        code = otp.group(1)
                        print(f"✅ 找到 OTP: {code}")
                        mail.logout()
                        return code
            except: continue
    mail.logout()
    raise TimeoutError("❌ 未收到验证码邮件")

# ============================================================
# Cloudflare Turnstile 破解工具
# ============================================================

def xdotool_click(x, y):
    try:
        subprocess.run(["xdotool", "mousemove", str(int(x)), str(int(y))], timeout=2)
        time.sleep(0.1)
        subprocess.run(["xdotool", "click", "1"], timeout=2)
        return True
    except: return False

def solve_turnstile(sb):
    print("🛡️ 正在处理 Turnstile 验证...")
    # 展开隐藏的验证框
    sb.execute_script("""
        (function() {
            var iframes = document.querySelectorAll('iframe[src*="challenges.cloudflare.com"]');
            iframes.forEach(i => { i.style.width = '300px'; i.style.height = '65px'; i.style.opacity = '1'; });
        })();
    """)
    time.sleep(1)
    
    # 寻找坐标并点击
    coords = sb.execute_script("""
        (function(){
            var i = document.querySelector('iframe[src*="challenges.cloudflare.com"]');
            if(!i) return null;
            var r = i.getBoundingClientRect();
            return { x: r.x + 30, y: r.y + r.height/2 };
        })()
    """)
    
    if coords:
        # 获取窗口偏移
        off = sb.execute_script("return {x: window.screenX, y: window.screenY, h: window.outerHeight - window.innerHeight};")
        xdotool_click(coords['x'] + off['x'], coords['y'] + off['y'] + off['h'])
        
    # 等待 Token 生成
    for _ in range(20):
        if sb.execute_script("return document.querySelector('input[name=\"cf-turnstile-response\"]')?.value.length > 20"):
            print("✅ Turnstile 已通过")
            return True
        time.sleep(1)
    return False

# ============================================================
# 🚨 核心逻辑：物理点击续期按钮
# ============================================================

def do_renew(sb):
    print("🔄 进入仪表盘，准备续期...")
    time.sleep(8)
    sb.save_screenshot("dashboard_initial.png")

    # 识别 Add Hours 按钮 (根据截图)
    ad_selectors = [
        "//a[contains(., 'Add') and contains(., 'Hours')]",
        "//button[contains(., 'Add') and contains(., 'Hours')]",
        "a[href*='cuty']",
        "a[href*='shrink']"
    ]

    found_targets = []
    for sel in ad_selectors:
        try:
            elements = sb.find_elements(sel)
            for el in elements:
                if el.is_displayed():
                    href = el.get_attribute("href")
                    text = el.text.strip()
                    found_targets.append({'el': el, 'url': href, 'text': text})
        except: continue

    if not found_targets:
        print("❌ 未发现任何 Add Hours 按钮")
        send_tg("❌ 未发现续期按钮，请检查面板")
        return

    print(f"📊 发现 {len(found_targets)} 个续期目标")
    
    for target in found_targets:
        print(f"🔗 正在尝试触发: {target['text']}")
        try:
            # 1. 尝试静默请求
            if target['url']:
                sb.execute_script(f"fetch('{target['url']}', {{mode: 'no-cors'}});")
            
            # 2. 物理模拟点击
            sb.execute_script("arguments[0].scrollIntoView({block: 'center'});", target['el'])
            time.sleep(1)
            target['el'].click()
            
            # 3. 处理可能弹出的新标签页
            time.sleep(3)
            if len(sb.driver.window_handles) > 1:
                sb.driver.switch_to.window(sb.driver.window_handles[-1])
                sb.driver.close()
                sb.driver.switch_to.window(sb.driver.window_handles[0])
            print(f"✅ 已触发点击: {target['text']}")
        except Exception as e:
            print(f"⚠️ 点击失败: {e}")

    # 最终刷新确认
    time.sleep(5)
    sb.execute_script("window.location.reload();")
    time.sleep(5)
    sb.save_screenshot("dashboard_final.png")
    
    try:
        status_text = sb.get_text("//div[contains(., 'Hours') and contains(., 'Minutes')]")
        print(f"⏰ 续期后状态: {status_text}")
        send_tg("✅ 续期指令已下达", "Pella_Server", status_text)
    except:
        send_tg("✅ 续期指令已下达，请稍后手动确认")

# ============================================================
# 主执行流程
# ============================================================

def run_script():
    print(f"🚀 启动 Pella 自动化脚本 - 目标: {MASKED_EMAIL}")
    with SB(uc=True, test=True, proxy=LOCAL_PROXY) as sb:
        # 1. 登录
        sb.uc_open_with_reconnect(LOGIN_URL, reconnect_time=4)
        time.sleep(3)

        if sb.execute_script("return document.querySelector('input[name=\"cf-turnstile-response\"]') !== null"):
            solve_turnstile(sb)

        print("🔑 填写账号...")
        sb.wait_for_element_visible('#email-input', timeout=20)
        sb.type('#email-input', PELLA_EMAIL)
        
        # 点击继续按钮
        for btn_sel in ["//button[contains(., 'Continue')]", "button[type='submit']"]:
            try:
                if sb.is_element_visible(btn_sel):
                    sb.click(btn_sel)
                    break
            except: pass

        # 2. 处理 OTP
        print("📨 等待 OTP 框...")
        sb.wait_for_element_visible('.otp-input', timeout=30)
        code = fetch_otp_from_gmail()
        
        for i, char in enumerate(code):
            sb.execute_script(f"document.querySelectorAll('.otp-input')[{i}].value='{char}';")
            sb.execute_script(f"document.querySelectorAll('.otp-input')[{i}].dispatchEvent(new Event('input', {{bubbles:true}}));")
        
        time.sleep(1)
        for verify_sel in ["//button[contains(., 'Verify')]", "button[type='submit']"]:
            try:
                if sb.is_element_visible(verify_sel):
                    sb.click(verify_sel)
                    break
            except: pass

        # 3. 等待进入面板
        for _ in range(60):
            if "dashboard" in sb.get_current_url() or "session" in sb.get_current_url():
                print("✅ 登录成功")
                break
            time.sleep(1)
        else:
            print("❌ 登录超时")
            sb.save_screenshot("login_timeout.png")
            return

        # 4. 执行续期
        do_renew(sb)

if __name__ == "__main__":
    run_script()

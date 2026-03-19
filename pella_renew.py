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

_account = os.environ.get("PELLA_ACCOUNT", "").split(",")
PELLA_EMAIL    = _account[0].strip() if len(_account) > 0 else ""
GMAIL_PASSWORD = _account[1].strip() if len(_account) > 1 else ""

LOCAL_PROXY    = "http://127.0.0.1:8080"
MASKED_EMAIL   = "******@" + PELLA_EMAIL.split("@")[-1] if "@" in PELLA_EMAIL else PELLA_EMAIL

# Pella URL配置
LOGIN_URL      = "https://www.pella.app/"
PANEL_URL      = "https://www.pella.app/dashboard" # 登录成功后的主面板

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
        lines.append(f"⏱️ 备注: {remaining}")
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
            if not match: match = re.search(r'(\S+)\s*$', decoded)
            if match:
                spam_folder = match.group(1).strip('"')
                break

    folders_to_check = ["INBOX"]
    if spam_folder: folders_to_check.append(spam_folder)

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

                    otp = re.search(r'\b(\d{4,6})\b', body)
                    if otp:
                        code = otp.group(1)
                        print(f"✅ Gmail OTP: {code}")
                        mail.logout()
                        return code
            except Exception:
                continue
    mail.logout()
    raise TimeoutError("❌ Gmail超时")

# ============================================================
# Turnstile 工具函数 
# ============================================================

EXPAND_POPUP_JS = """
(function() {
    var turnstileInput = document.querySelector('input[name="cf-turnstile-response"]');
    if (!turnstileInput) return;
    var el = turnstileInput;
    for (var i = 0; i < 20; i++) {
        el = el.parentElement;
        if (!el) break;
        var style = window.getComputedStyle(el);
        if (style.overflow === 'hidden' || style.overflowX === 'hidden' || style.overflowY === 'hidden') {
            el.style.overflow = 'visible';
        }
        el.style.minWidth = 'max-content';
    }
    var iframes = document.querySelectorAll('iframe');
    iframes.forEach(function(iframe) {
        if (iframe.src && iframe.src.includes('challenges.cloudflare.com')) {
            iframe.style.width = '300px';
            iframe.style.height = '65px';
            iframe.style.minWidth = '300px';
            iframe.style.visibility = 'visible';
            iframe.style.opacity = '1';
        }
    });
})();
"""

def xdotool_click(x, y):
    try:
        subprocess.run(["xdotool", "search", "--onlyvisible", "--class", "chrome"], capture_output=True, text=True, timeout=3)
        subprocess.run(["xdotool", "mousemove", str(int(x)), str(int(y))], timeout=2, check=True)
        time.sleep(0.15)
        subprocess.run(["xdotool", "click", "1"], timeout=2, check=True)
        return True
    except Exception:
        return False

def get_turnstile_coords(sb):
    try:
        return sb.execute_script("""
            (function(){
                var iframes = document.querySelectorAll('iframe');
                for (var i = 0; i < iframes.length; i++) {
                    var src = iframes[i].src || '';
                    if (src.includes('cloudflare') || src.includes('turnstile')) {
                        var rect = iframes[i].getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) return { click_x: Math.round(rect.x + 30), click_y: Math.round(rect.y + rect.height / 2) };
                    }
                }
                return null;
            })()
        """)
    except Exception:
        return None

def get_window_offset(sb):
    try:
        info = sb.execute_script("(function(){ return { screenX: window.screenX || 0, screenY: window.screenY || 0, outer: window.outerHeight, inner: window.innerHeight }; })()")
        toolbar = info['outer'] - info['inner']
        if not (30 <= toolbar <= 200): toolbar = 87
        return info['screenX'], info['screenY'], toolbar
    except Exception:
        return 0, 0, 87

def check_token(sb) -> bool:
    try:
        return sb.execute_script("(function(){ var i = document.querySelector('input[name=\"cf-turnstile-response\"]'); return i && i.value.length > 20; })()")
    except Exception:
        return False

def turnstile_exists(sb) -> bool:
    try:
        return sb.execute_script("(function(){ return document.querySelector('input[name=\"cf-turnstile-response\"]') !== null; })()")
    except Exception:
        return False

def solve_turnstile(sb) -> bool:
    for _ in range(3):
        sb.execute_script(EXPAND_POPUP_JS)
        time.sleep(0.5)
    if check_token(sb): return True
    coords = get_turnstile_coords(sb)
    if not coords: return False
    win_x, win_y, toolbar = get_window_offset(sb)
    xdotool_click(coords['click_x'] + win_x, coords['click_y'] + win_y + toolbar)
    for _ in range(30):
        time.sleep(0.5)
        if check_token(sb): return True
    return False

# ============================================================
# 🚨 核心重写：Pella 物理续期流程 
# ============================================================

def do_renew(sb):
    print("🔄 尝试执行物理点击续期逻辑...")
    # 等待仪表盘完全加载
    time.sleep(6) 
    sb.save_screenshot("pella_dashboard_loaded.png")

    # 1. 寻找所有的 Renew 按钮并点击
    renew_selectors = [
        "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'renew')]",
        "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'renew')]",
        ".renew-btn", 
        "button[title*='Renew']"
    ]

    clicked_renew = False
    for sel in renew_selectors:
        try:
            elements = sb.find_elements(sel)
            for el in elements:
                if el.is_displayed():
                    # 滚动到按钮位置并强制点击
                    sb.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                    time.sleep(1)
                    sb.execute_script("arguments[0].click();", el)
                    clicked_renew = True
                    print(f"✅ 成功点击页面上的 'Renew' 按钮")
                    break
        except Exception:
            pass
        if clicked_renew:
            break

    if not clicked_renew:
        print("❌ 未能在页面上找到或点击续期按钮")
        sb.save_screenshot("pella_no_renew_found.png")
        send_tg("❌ 找不到续期按钮，可能是已经达到了续期上限或页面结构不同。")
        return

    # 等待可能出现的弹窗或验证
    time.sleep(3)
    sb.save_screenshot("pella_after_click.png")

    # 2. 如果弹出验证码，处理它
    if turnstile_exists(sb):
        print("🛡️ 检测到续期验证码，尝试破解...")
        solve_turnstile(sb)
        time.sleep(3)

    # 3. 寻找可能弹出的“确认 (Confirm)”或“是的 (Yes)”按钮
    confirm_selectors = [
        "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'confirm')]",
        "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'yes')]",
        ".modal-content button.btn-primary"
    ]
    
    for sel in confirm_selectors:
        try:
            if sb.is_element_visible(sel):
                sb.click(sel)
                print("✅ 点击了弹窗中的 '确认' 按钮")
                time.sleep(2)
                break
        except Exception:
            pass

    # 4. 等待续期请求发送并保存最终状态
    print("⏳ 等待服务器响应...")
    time.sleep(5)
    sb.save_screenshot("pella_renew_final.png")
    
    page_text = sb.get_page_source().lower()
    if "success" in page_text or "renewed" in page_text or "successfully" in page_text:
        print("🎉 检测到成功提示！")
        send_tg("✅ 续期操作执行完毕，且检测到成功提示！")
    else:
        print("⚠️ 续期已点击，但页面未显示明确的 success 字样")
        send_tg("⚠️ 续期按钮已点击，请人工登录面板确认时长是否增加。")


# ============================================================
# 主流程
# ============================================================

def run_script():
    print("🔧 启动浏览器...")
    with SB(uc=True, test=True, proxy=LOCAL_PROXY) as sb:
        print("🚀 浏览器就绪！")

        print("🔑 打开登录页面...")
        sb.uc_open_with_reconnect(LOGIN_URL, reconnect_time=4)
        time.sleep(3)

        if turnstile_exists(sb):
            if not solve_turnstile(sb):
                send_tg("❌ 登录页Turnstile验证失败")
                return

        print("📭 等待邮箱框...")
        try:
            sb.wait_for_element_visible('#email-input', timeout=20)
        except Exception:
            sb.save_screenshot("pella_no_email.png")
            return

        sb.type('#email-input', PELLA_EMAIL)
        
        for sel in ["//button[contains(., 'Continue with Email')]", "button[type='submit']"]:
            try:
                if sb.is_element_visible(sel):
                    sb.click(sel)
                    break
            except Exception:
                continue

        try:
            sb.wait_for_element_visible('.otp-input', timeout=30)
            code = fetch_otp_from_gmail(wait_seconds=60)
            
            for i, char in enumerate(code):
                sb.execute_script(f"""
                    var inp = document.querySelectorAll('.otp-input')[{i}];
                    if(inp){{ inp.value='{char}'; inp.dispatchEvent(new Event('input', {{bubbles:true}})); }}
                """)
                time.sleep(0.1)
                
            time.sleep(0.5)
            for sel in ["//button[contains(., 'Verify Code')]", "button[type='submit']"]:
                try:
                    if sb.is_element_visible(sel):
                        sb.click(sel)
                        break
                except Exception:
                    continue
        except Exception as e:
            print(f"登录步骤异常: {e}")
            return

        print("⏳ 等待登录跳转...")
        for _ in range(80):
            try:
                url = sb.get_current_url()
                if "/session" in url or "panel" in url or "dashboard" in url:
                    print("✅ 登录成功！")
                    break
            except Exception:
                pass
            time.sleep(0.5)
        else:
            print("❌ 登录等待超时")
            return

        do_renew(sb)

if __name__ == "__main__":
    run_script()

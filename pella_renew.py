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
_account_str = os.environ.get("PELLA_ACCOUNT") or os.environ.get("KERIT_ACCOUNT", "")
_account = _account_str.split(",")
PELLA_EMAIL    = _account[0].strip() if len(_account) > 0 else ""
GMAIL_PASSWORD = _account[1].strip() if len(_account) > 1 else ""

LOCAL_PROXY    = "http://127.0.0.1:8080"
LOGIN_URL      = "https://www.pella.app/"

_tg_raw = os.environ.get("TG_BOT", "")
TG_CHAT_ID, TG_TOKEN = (_tg_raw.split(",")[0].strip(), _tg_raw.split(",")[1].strip()) if "," in _tg_raw else ("", "")

def send_tg(msg, remaining=None):
    if not TG_TOKEN: return
    text = f"🎮 Pella 服务器续期通知\n📊 结果: {msg}"
    if remaining: text += f"\n⏱️ 状态: {remaining}"
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": TG_CHAT_ID, "text": text}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method="POST"), timeout=15)
    except: pass

# ============================================================
# 核心逻辑：Gmail 验证码提取
# ============================================================
def fetch_otp():
    print("📬 正在检查 Gmail 验证码...")
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(PELLA_EMAIL, GMAIL_PASSWORD)
    except Exception as e:
        print(f"❌ Gmail 登录失败: {e}")
        return None

    for _ in range(12):
        time.sleep(5)
        for folder in ["INBOX", "[Gmail]/Spam", "垃圾邮件"]:
            try:
                mail.select(folder)
                _, data = mail.uid("search", None, 'FROM "pella"')
                uids = data[0].split()
                if uids:
                    _, msg_data = mail.uid("fetch", uids[-1], "(RFC822)")
                    msg = email.message_from_bytes(msg_data[0][1])
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                body = part.get_payload(decode=True).decode(errors='ignore')
                                break
                    else:
                        body = msg.get_payload(decode=True).decode(errors='ignore')
                    
                    otp = re.search(r'\b(\d{4,6})\b', body)
                    if otp: 
                        print(f"✅ 提取到验证码: {otp.group(1)}")
                        mail.logout()
                        return otp.group(1)
            except: continue
    mail.logout()
    return None

# ============================================================
# 核心逻辑：物理模拟续期 (针对广告链接)
# ============================================================
def do_renew(sb):
    print("🔄 开始寻找续期按钮...")
    time.sleep(8) # 等待面板加载
    sb.save_screenshot("dashboard_check.png")

    # 识别 Add Hours 按钮 (根据截图：包含 cuty 或 shrink)
    targets = []
    ad_selectors = ["//a[contains(@href, 'cuty')]", "//a[contains(@href, 'shrink')]", "//a[contains(., 'Add')]"]
    
    for sel in ad_selectors:
        try:
            elements = sb.find_elements(sel)
            for el in elements:
                href = el.get_attribute("href")
                if href and href not in [t['url'] for t in targets]:
                    targets.append({'el': el, 'url': href})
        except: continue

    if not targets:
        print("❌ 未发现任何续期按钮")
        send_tg("未发现续期按钮，请检查面板截图")
        return

    main_window = sb.driver.current_window_handle
    success_count = 0

    for target in targets:
        print(f"🔗 尝试触发广告链接: {target['url']}")
        try:
            # 1. 尝试静默 fetch 触发
            sb.execute_script(f"fetch('{target['url']}', {{mode: 'no-cors'}});")
            
            # 2. 模拟真实点击并在新标签页停留
            sb.execute_script(f"window.open('{target['url']}', '_blank');")
            time.sleep(2)
            
            windows = sb.driver.window_handles
            if len(windows) > 1:
                sb.driver.switch_to.window(windows[-1])
                print("⏳ 模拟广告观看中 (30s)...")
                time.sleep(30) # 关键：停留足够长时间
                sb.driver.close()
                sb.driver.switch_to.window(main_window)
            
            success_count += 1
            time.sleep(2)
        except Exception as e:
            print(f"⚠️ 触发失败: {e}")

    # 刷新确认
    sb.execute_script("window.location.reload();")
    time.sleep(8)
    sb.save_screenshot("final_result.png")
    
    try:
        remaining = sb.get_text("//div[contains(., 'Hours') and contains(., 'Minutes')]")
        send_tg(f"已触发 {success_count} 个续期链接", remaining)
    except:
        send_tg(f"已触发 {success_count} 个续期链接，请检查截图")

# ============================================================
# 主执行程序
# ============================================================
def run_script():
    with SB(uc=True, test=True, proxy=LOCAL_PROXY) as sb:
        print("🌐 正在连接 Pella...")
        sb.uc_open_with_reconnect(LOGIN_URL, reconnect_time=5)
        time.sleep(5)

        # 1. 处理入口和邮箱输入
        print("🔑 准备登录...")
        # 兼容性：如果页面有 Login 按钮则先点 Login
        for btn in ["a:contains('Login')", "button:contains('Login')"]:
            if sb.is_element_visible(btn):
                sb.click(btn)
                time.sleep(2)

        # 寻找邮箱框 (多重选择器)
        email_input = None
        for selector in ["#email-input", "input[type='email']", "input[placeholder*='Email']"]:
            if sb.is_element_visible(selector):
                email_input = selector
                break
        
        if not email_input:
            sb.save_screenshot("error_no_email.png")
            print("❌ 找不到邮箱输入框")
            return

        sb.type(email_input, PELLA_EMAIL)
        sb.click('button[type="submit"]')

        # 2. 处理 OTP
        code = fetch_otp()
        if not code:
            print("❌ 验证码获取超时")
            return
        
        print("⌨️ 填写验证码...")
        for i, char in enumerate(code):
            sb.execute_script(f"document.querySelectorAll('.otp-input')[{i}].value='{char}';")
            sb.execute_script(f"document.querySelectorAll('.otp-input')[{i}].dispatchEvent(new Event('input', {{bubbles:true}}));")
        
        time.sleep(2)
        sb.click("//button[contains(., 'Verify')]")

        # 3. 执行续期
        print("⌛ 等待进入面板...")
        time.sleep(10)
        do_renew(sb)

if __name__ == "__main__":
    run_script()

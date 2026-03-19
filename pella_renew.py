import os
import time
import imaplib
import email
import re
import urllib.request
import urllib.parse
from seleniumbase import SB

# ============================================================
# 1. 基础配置（从 GitHub Secrets 读取）
# ============================================================
_account_str = os.environ.get("PELLA_ACCOUNT") or os.environ.get("KERIT_ACCOUNT", "")
if "," not in _account_str:
    raise ValueError("PELLA_ACCOUNT 格式应为: 邮箱,密码")

PELLA_EMAIL, GMAIL_PASSWORD = [x.strip() for x in _account_str.split(",")]
LOCAL_PROXY = "http://127.0.0.1:8080"
# 你的特定服务器详情页
TARGET_SERVER_URL = "https://www.pella.app/server/bca8a69447964c2db3b2a187252420b5"

_tg_raw = os.environ.get("TG_BOT", "")
TG_CHAT_ID, TG_TOKEN = (_tg_raw.split(",")[0].strip(), _tg_raw.split(",")[1].strip()) if "," in _tg_raw else ("", "")

def send_tg(msg):
    if not TG_TOKEN: return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": TG_CHAT_ID, "text": f"🎮 Pella 续期: {msg}"}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method="POST"), timeout=15)
    except: pass

# ============================================================
# 2. 邮件 OTP 提取
# ============================================================
def fetch_otp():
    print("📬 正在检查 Gmail 验证码...")
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(PELLA_EMAIL, GMAIL_PASSWORD)
        for _ in range(12): # 尝试 60 秒
            time.sleep(5)
            for folder in ["INBOX", "[Gmail]/Spam"]:
                try:
                    mail.select(folder)
                    _, data = mail.uid("search", None, '(OR FROM "pella" FROM "kerit")')
                    uids = data[0].split()
                    if uids:
                        _, msg_data = mail.uid("fetch", uids[-1], "(RFC822)")
                        msg = email.message_from_bytes(msg_data[0][1])
                        body = msg.get_payload(decode=True).decode(errors='ignore') if not msg.is_multipart() else ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                if part.get_content_type() == "text/plain":
                                    body = part.get_payload(decode=True).decode(errors='ignore')
                        otp = re.search(r'\b(\d{4,6})\b', body)
                        if otp: 
                            return otp.group(1)
                except: continue
        mail.logout()
    except Exception as e: print(f"❌ 邮件错误: {e}")
    return None

# ============================================================
# 3. 核心加时逻辑
# ============================================================
def do_renew(sb):
    print(f"🚀 跳转至特定服务器: {TARGET_SERVER_URL}")
    sb.activate_cdp() # 启用高级反检测
    sb.open(TARGET_SERVER_URL)
    time.sleep(10)
    sb.save_screenshot("server_page.png")

    # 寻找加时链接 (cuty, shrink 或 包含 Add 字样)
    targets = sb.find_elements("//a[contains(@href, 'cuty') or contains(@href, 'shrink') or contains(., 'Add')]")
    if not targets:
        print("⚠️ 未发现加时按钮，可能时长已满或页面未加载")
        return

    main_handle = sb.driver.current_window_handle
    for target in targets:
        try:
            href = target.get_attribute("href")
            print(f"🔗 触发加时链接: {href}")
            sb.execute_script(f"window.open('{href}', '_blank');")
            time.sleep(2)
            # 模拟观看广告
            sb.switch_to_window(sb.driver.window_handles[-1])
            print("⏳ 模拟广告停留 (45秒)...")
            time.sleep(45)
            sb.driver.close()
            sb.switch_to_window(main_handle)
        except: continue

    sb.refresh()
    time.sleep(5)
    sb.save_screenshot("final_result.png")
    send_tg("续期流程执行完毕，请检查面板截图。")

# ============================================================
# 4. 主运行入口
# ============================================================
def run():
    with SB(uc=True, test=True, proxy=LOCAL_PROXY, locale_code="en") as sb:
        print("🌐 访问 Pella 官网...")
        sb.uc_open_with_reconnect("https://www.pella.app/", reconnect_time=10)
        time.sleep(5)

        # 解决“找不到邮箱框”：点击 Login 按钮跳转
        login_btns = ["a:contains('Login')", "button:contains('Login')", "a[href*='login']"]
        for btn in login_btns:
            if sb.is_element_visible(btn):
                sb.click(btn)
                time.sleep(5)
                break

        # 输入邮箱
        email_field = None
        for sel in ["#email-input", "input[type='email']", "input[name='email']"]:
            if sb.is_element_visible(sel):
                email_field = sel
                break
        
        if not email_field:
            sb.save_screenshot("error_no_email.png")
            print("❌ 无法定位邮箱框，请检查截图")
            return

        sb.type(email_field, PELLA_EMAIL)
        sb.click("//button[@type='submit']|//button[contains(., 'Continue')]")
        
        # 处理 OTP
        code = fetch_otp()
        if not code:
            print("❌ 未收到验证码")
            return

        print(f"⌨️ 填入验证码: {code}")
        for i, char in enumerate(code):
            sb.execute_script(f"document.querySelectorAll('.otp-input')[{i}].value='{char}';")
            sb.execute_script(f"document.querySelectorAll('.otp-input')[{i}].dispatchEvent(new Event('input', {{bubbles:true}}));")
        
        time.sleep(2)
        sb.click("//button[contains(., 'Verify')]")
        
        # 登录成功后进入加时流程
        time.sleep(10)
        do_renew(sb)

if __name__ == "__main__":
    run()

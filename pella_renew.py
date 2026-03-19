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
# 配置：优先读取 PELLA_ACCOUNT
# ============================================================
_account_str = os.environ.get("PELLA_ACCOUNT") or os.environ.get("KERIT_ACCOUNT", "")
_account = _account_str.split(",")
PELLA_EMAIL    = _account[0].strip() if len(_account) > 0 else ""
GMAIL_PASSWORD = _account[1].strip() if len(_account) > 1 else ""

LOCAL_PROXY    = "http://127.0.0.1:8080"
LOGIN_URL      = "https://www.pella.app/"

_tg_raw = os.environ.get("TG_BOT", "")
TG_CHAT_ID, TG_TOKEN = (_tg_raw.split(",")[0].strip(), _tg_raw.split(",")[1].strip()) if "," in _tg_raw else ("", "")

def send_tg(msg):
    if not TG_TOKEN: return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": TG_CHAT_ID, "text": f"🎮 Pella 状态: {msg}"}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method="POST"), timeout=15)
    except: pass

def fetch_otp():
    print("📬 正在检查 Gmail 验证码...")
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(PELLA_EMAIL, GMAIL_PASSWORD)
    for _ in range(12):
        time.sleep(5)
        for folder in ["INBOX", "[Gmail]/Spam", "垃圾邮件"]:
            try:
                mail.select(folder)
                _, data = mail.uid("search", None, '(OR FROM "pella" FROM "kerit")')
                uids = data[0].split()
                if uids:
                    _, msg_data = mail.uid("fetch", uids[-1], "(RFC822)")
                    body = email.message_from_bytes(msg_data[0][1]).get_payload(decode=True).decode(errors='ignore')
                    otp = re.search(r'\b(\d{4,6})\b', body)
                    if otp: return otp.group(1)
            except: continue
    return None

def do_renew(sb):
    print("🔄 检测续期按钮...")
    time.sleep(8)
    sb.save_screenshot("dashboard_check.png")
    
    # 匹配截图中的 cuty 和 shrink 链接
    targets = sb.find_elements("//a[contains(@href, 'cuty') or contains(@href, 'shrink')]")
    if not targets:
        send_tg("❌ 未发现续期链接，请检查面板截图")
        return

    main_window = sb.driver.current_window_handle
    for target in targets:
        href = target.get_attribute("href")
        print(f"🔗 正在处理广告: {href}")
        # 在新标签页打开，模拟真人观看 40 秒
        sb.execute_script(f"window.open('{href}', '_blank');")
        time.sleep(2)
        
        windows = sb.driver.window_handles
        sb.driver.switch_to.window(windows[-1])
        time.sleep(40) # 关键：广告商检测停留时间
        sb.driver.close()
        sb.driver.switch_to.window(main_window)
        time.sleep(2)

    sb.execute_script("window.location.reload();")
    time.sleep(5)
    sb.save_screenshot("final_result.png")
    send_tg("✅ 续期指令已发送，请检查时长")

def run():
    with SB(uc=True, test=True, proxy=LOCAL_PROXY) as sb:
        print("🌐 连接 Pella...")
        sb.uc_open_with_reconnect(LOGIN_URL, reconnect_time=5)
        time.sleep(5)

        # 解决找不到邮箱框的问题：处理登录跳转
        if sb.is_element_visible("a:contains('Login')"):
            sb.click("a:contains('Login')")
            time.sleep(3)

        # 多重选择器寻找邮箱框
        email_selector = None
        for sel in ["#email-input", "input[type='email']", "input[name='email']"]:
            if sb.is_element_visible(sel):
                email_selector = sel
                break
        
        if not email_selector:
            sb.save_screenshot("error_no_email.png")
            print("❌ 无法定位邮箱框")
            return

        sb.type(email_selector, PELLA_EMAIL)
        sb.click('button[type="submit"]')
        
        code = fetch_otp()
        if not code: return
        
        for i, char in enumerate(code):
            sb.execute_script(f"document.querySelectorAll('.otp-input')[{i}].value='{char}';")
            sb.execute_script(f"document.querySelectorAll('.otp-input')[{i}].dispatchEvent(new Event('input', {{bubbles:true}}));")
        
        time.sleep(2)
        sb.click("//button[contains(., 'Verify')]")
        time.sleep(10)
        do_renew(sb)

if __name__ == "__main__":
    run()

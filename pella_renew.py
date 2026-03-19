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
# 配置
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
    data = urllib.parse.urlencode({"chat_id": TG_CHAT_ID, "text": msg}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method="POST"), timeout=15)
    except: pass

def fetch_otp():
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(PELLA_EMAIL, GMAIL_PASSWORD)
    for _ in range(12): # 等待60秒
        time.sleep(5)
        for folder in ["INBOX", "[Gmail]/Spam"]:
            try:
                mail.select(folder)
                _, data = mail.uid("search", None, 'FROM "pella"')
                uids = data[0].split()
                if uids:
                    _, msg_data = mail.uid("fetch", uids[-1], "(RFC822)")
                    body = email.message_from_bytes(msg_data[0][1]).get_payload(decode=True).decode()
                    otp = re.search(r'\b(\d{4,6})\b', body)
                    if otp: return otp.group(1)
            except: continue
    return None

def do_renew(sb):
    print("🔄 开始深度模拟续期...")
    time.sleep(8)
    sb.save_screenshot("before_click.png")

    # 精准匹配截图中的按钮
    targets = sb.find_elements("//a[contains(@href, 'cuty') or contains(@href, 'shrink')]")
    
    if not targets:
        send_tg("❌ 未发现 Add Hours 按钮")
        return

    main_window = sb.driver.current_window_handle
    
    for target in targets:
        href = target.get_attribute("href")
        text = target.text.strip()
        print(f"🔗 正在处理: {text}")

        # 模拟真人：在新标签页打开，并保持开启一段时间
        sb.execute_script(f"window.open('{href}', '_blank');")
        time.sleep(2)
        
        # 切换到广告页模拟“观看”
        windows = sb.driver.window_handles
        sb.driver.switch_to.window(windows[-1])
        print(f"⏳ 正在后台加载广告页，等待 20 秒...")
        time.sleep(20) # 关键：必须给广告页足够的加载时间
        
        sb.driver.close()
        sb.driver.switch_to.window(main_window)
        time.sleep(2)

    # 刷新确认
    sb.execute_script("window.location.reload();")
    time.sleep(5)
    sb.save_screenshot("after_click.png")
    send_tg(f"✅ 已尝试模拟点击 {len(targets)} 个广告链接，请检查截图确认时长。")

def run():
    with SB(uc=True, test=True, proxy=LOCAL_PROXY) as sb:
        sb.uc_open_with_reconnect(LOGIN_URL, reconnect_time=4)
        sb.wait_for_element_visible('#email-input')
        sb.type('#email-input', PELLA_EMAIL)
        sb.click('button[type="submit"]')
        
        code = fetch_otp()
        if not code: return
        
        for i, char in enumerate(code):
            sb.execute_script(f"document.querySelectorAll('.otp-input')[{i}].value='{char}';")
            sb.execute_script(f"document.querySelectorAll('.otp-input')[{i}].dispatchEvent(new Event('input', {{bubbles:true}}));")
        
        time.sleep(2)
        sb.click("//button[contains(., 'Verify')]")
        
        # 等待进入 Dashboard
        time.sleep(10)
        do_renew(sb)

if __name__ == "__main__":
    run()

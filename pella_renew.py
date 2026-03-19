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
    text = f"🎮 Pella 续期通知\n📊 结果: {msg}"
    if remaining: text += f"\n⏱️ 状态: {remaining}"
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": TG_CHAT_ID, "text": text}).encode()
    try: urllib.request.urlopen(urllib.request.Request(url, data=data, method="POST"), timeout=15)
    except: pass

def fetch_otp():
    print("📬 正在检查 Gmail 验证码...")
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(PELLA_EMAIL, GMAIL_PASSWORD)
        for _ in range(15):
            time.sleep(5)
            for folder in ["INBOX", "[Gmail]/Spam", "垃圾邮件"]:
                try:
                    mail.select(folder)
                    _, data = mail.uid("search", None, '(OR FROM "pella" FROM "kerit")')
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
                            mail.logout()
                            return otp.group(1)
                except: continue
        mail.logout()
    except Exception as e:
        print(f"❌ Gmail 错误: {e}")
    return None

def do_renew(sb):
    print("🔄 开始执行加时逻辑...")
    time.sleep(10)
    sb.save_screenshot("dashboard_check.png")
    
    # 针对截图中的 Add 24/32 Hours 按钮进行匹配
    targets = sb.find_elements("//a[contains(@href, 'cuty') or contains(@href, 'shrink') or contains(., 'Add')]")
    
    if not targets:
        print("❌ 未发现续期按钮")
        return

    main_window = sb.driver.current_window_handle
    for target in targets:
        try:
            href = target.get_attribute("href")
            print(f"🔗 触发链接: {href}")
            sb.execute_script(f"window.open('{href}', '_blank');")
            time.sleep(2)
            windows = sb.driver.window_handles
            if len(windows) > 1:
                sb.driver.switch_to.window(windows[-1])
                time.sleep(35) # 模拟广告停留
                sb.driver.close()
                sb.driver.switch_to.window(main_window)
        except: continue

    sb.execute_script("window.location.reload();")
    time.sleep(5)
    try:
        rem = sb.get_text("//div[contains(., 'Hours')]")
        send_tg("已尝试触发所有续期链接", rem)
    except:
        send_tg("续期操作完成，请检查面板")

def run_script():
    with SB(uc=True, test=True, proxy=LOCAL_PROXY) as sb:
        print("🌐 正在连接 Pella...")
        sb.uc_open_with_reconnect(LOGIN_URL, reconnect_time=10)
        time.sleep(5)

        # 解决“找不到邮箱框”：先尝试寻找并点击登录入口
        for login_sel in ["a:contains('Login')", "button:contains('Login')", "a[href*='login']"]:
            if sb.is_element_visible(login_sel):
                sb.click(login_sel)
                time.sleep(5)
                break

        # 定位邮箱框（多选择器适配）
        email_input = None
        for sel in ["#email-input", "input[type='email']", "input[name='email']"]:
            if sb.is_element_visible(sel):
                email_input = sel
                break
        
        if not email_input:
            sb.save_screenshot("error_no_email.png")
            print("❌ 邮箱框加载失败")
            return

        print("🔑 填写账号...")
        sb.type(email_input, PELLA_EMAIL)
        sb.click("//button[@type='submit']|//button[contains(., 'Continue')]")
        
        print("📨 获取验证码...")
        code = fetch_otp()
        if not code:
            print("❌ 验证码获取超时")
            return

        print(f"⌨️ 填入验证码: {code}")
        for i, char in enumerate(code):
            sb.execute_script(f"document.querySelectorAll('.otp-input')[{i}].value='{char}';")
            sb.execute_script(f"document.querySelectorAll('.otp-input')[{i}].dispatchEvent(new Event('input', {{bubbles:true}}));")
        
        time.sleep(2)
        sb.click("//button[contains(., 'Verify')]|//button[contains(., 'Submit')]")
        time.sleep(10)
        
        do_renew(sb)

if __name__ == "__main__":
    run_script()

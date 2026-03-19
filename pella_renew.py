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
# 邮件 OTP 提取逻辑
# ============================================================
def fetch_otp():
    print("📬 正在检查 Gmail 验证码...")
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(PELLA_EMAIL, GMAIL_PASSWORD)
    except Exception as e:
        print(f"❌ Gmail 登录失败: {e}")
        return None

    for _ in range(15): # 等待约 75 秒
        time.sleep(5)
        for folder in ["INBOX", "[Gmail]/Spam", "垃圾邮件"]:
            try:
                mail.select(folder)
                # 兼容旧发件人 kerit 和新发件人 pella
                _, data = mail.uid("search", None, '(OR FROM "pella" FROM "kerit")')
                uids = data[0].split()
                if uids:
                    _, msg_data = mail.uid("fetch", uids[-1], "(RFC822)")
                    msg = email.message_from_bytes(msg_data[0][1])
                    
                    # 提取正文内容
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                body = part.get_payload(decode=True).decode(errors='ignore')
                                break
                    else:
                        body = msg.get_payload(decode=True).decode(errors='ignore')
                    
                    # 匹配 4-6 位数字验证码
                    otp = re.search(r'\b(\d{4,6})\b', body)
                    if otp: 
                        print(f"✅ 提取到验证码: {otp.group(1)}")
                        mail.logout()
                        return otp.group(1)
            except: continue
    mail.logout()
    return None

# ============================================================
# 核心续期逻辑 (针对广告链接)
# ============================================================
def do_renew(sb):
    print("🔄 开始执行深度续期逻辑...")
    time.sleep(10) # 留出充足时间让面板渲染
    sb.save_screenshot("dashboard_check.png")

    # 识别 Add Hours 按钮 (根据上传的图片布局)
    # 优先匹配包含 cuty, shrink 字样的链接，或包含 Add 24/32 Hours 的文字
    targets = []
    ad_selectors = [
        "//a[contains(@href, 'cuty')]", 
        "//a[contains(@href, 'shrink')]", 
        "//button[contains(., 'Add')]",
        "//a[contains(., 'Add')]"
    ]
    
    for sel in ad_selectors:
        try:
            elements = sb.find_elements(sel)
            for el in elements:
                if el.is_displayed():
                    href = el.get_attribute("href")
                    text = el.text.strip()
                    if href and href not in [t['url'] for t in targets]:
                        targets.append({'el': el, 'url': href, 'text': text})
        except: continue

    if not targets:
        print("❌ 未发现任何续期按钮")
        send_tg("未发现续期按钮，请检查 dashboard_check.png 截图")
        return

    print(f"📊 发现 {len(targets)} 个目标链接")
    main_window = sb.driver.current_window_handle
    success_count = 0

    for target in targets:
        print(f"🔗 正在点击: {target['text']} -> {target['url']}")
        try:
            # 在新标签页打开广告，模拟观看时长
            sb.execute_script(f"window.open('{target['url']}', '_blank');")
            time.sleep(2)
            
            windows = sb.driver.window_handles
            if len(windows) > 1:
                sb.driver.switch_to.window(windows[-1])
                print("⏳ 模拟广告停留加载中 (35s)...")
                time.sleep(35) # 关键停留时长，确保后端计入
                sb.driver.close()
                sb.driver.switch_to.window(main_window)
            
            success_count += 1
            time.sleep(3)
        except Exception as e:
            print(f"⚠️ 触发失败: {e}")

    # 强制刷新页面确认时长
    sb.execute_script("window.location.reload();")
    time.sleep(8)
    sb.save_screenshot("final_result.png")
    
    try:
        # 尝试抓取“剩余多长时间”的文本通知 TG
        remaining = sb.get_text("//div[contains(., 'Hours') and contains(., 'Minutes')]")
        send_tg(f"已模拟点击 {success_count} 个续期链接", remaining)
    except:
        send_tg(f"已完成 {success_count} 次模拟点击，请通过截图确认结果")

# ============================================================
# 主登录程序
# ============================================================
def run_script():
    with SB(uc=True, test=True, proxy=LOCAL_PROXY) as sb:
        print("🌐 正在连接 Pella...")
        sb.uc_open_with_reconnect(LOGIN_URL, reconnect_time=5)
        time.sleep(5)

        # 1. 处理登录入口
        print("🔑 准备登录...")
        # 如果首页有 Login/Sign In 按钮，先点击进入登录框页面
        for btn in ["a:contains('Login')", "button:contains('Login')", "a:contains('Sign In')"]:
            if sb.is_element_visible(btn):
                sb.click(btn)
                time.sleep(3)

        # 2. 填写邮箱 (多重选择器适配，解决找不到邮箱框的问题)
        email_selector = None
        selectors = ["#email-input", "input[type='email']", "input[name='email']", "input[placeholder*='Email']"]
        for s in selectors:
            if sb.is_element_visible(s):
                email_selector = s
                break
        
        if not email_selector:
            sb.save_screenshot("error_no_email.png")
            print("❌ 找不到邮箱输入框，请查看 error_no_email.png")
            return

        sb.type(email_selector, PELLA_EMAIL)
        # 点击继续/提交
        submit_btn = "//button[contains(., 'Continue')]|//button[@type='submit']"
        sb.click(submit_btn)

        # 3. 处理 OTP
        code = fetch_otp()
        if not code:
            print("❌ 验证码获取超时")
            return
        
        print("⌨️ 填入验证码...")
        for i, char in enumerate(code):
            try:
                # 物理模拟填充 OTP 框
                sb.execute_script(f"document.querySelectorAll('.otp-input')[{i}].value='{char}';")
                sb.execute_script(f"document.querySelectorAll('.otp-input')[{i}].dispatchEvent(new Event('input', {{bubbles:true}}));")
            except: pass
        
        time.sleep(2)
        verify_btn = "//button[contains(., 'Verify')]|//button[contains(., 'Submit')]"
        sb.click(verify_btn)

        # 4. 进入面板并续期
        print("⌛ 登录提交完成，等待面板加载...")
        time.sleep(12)
        do_renew(sb)

if __name__ == "__main__":
    run_script()

import os
import time
import imaplib
import email
import re
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

# ============================================================
# 核心登录逻辑增强
# ============================================================

def run_script():
    # 使用 uc=True 开启反检测模式，设定较长的重连时间
    with SB(uc=True, test=True, proxy=LOCAL_PROXY, locale_code="en") as sb:
        print("🌐 正在连接 Pella 官网...")
        sb.uc_open_with_reconnect(LOGIN_URL, reconnect_time=10)
        time.sleep(8)
        
        # 步骤 1: 检查是否卡在 Cloudflare 验证页
        if sb.is_element_visible('iframe[src*="challenges.cloudflare.com"]'):
            print("🛡️ 检测到 Cloudflare 验证，尝试自动绕过...")
            sb.uc_gui_click_captcha() # 尝试 SeleniumBase 内置的验证码点击
            time.sleep(5)

        # 步骤 2: 寻找并进入登录页面
        # 有些 IP 访问首页是营销页，需要点击 Login 按钮
        login_found = False
        for login_btn in ["a:contains('Login')", "button:contains('Login')", "a[href*='login']"]:
            if sb.is_element_visible(login_btn):
                print(f"🖱️ 点击登录入口: {login_btn}")
                sb.click(login_btn)
                time.sleep(5)
                login_found = True
                break
        
        # 步骤 3: 定位邮箱输入框
        print("🔑 尝试多重定位邮箱框...")
        # 扩充选择器，防止 ID 变化
        selectors = [
            '#email-input', 
            'input[type="email"]', 
            'input[name="email"]', 
            'input[placeholder*="Email"]'
        ]
        
        target_field = None
        for sel in selectors:
            if sb.is_element_visible(sel):
                target_field = sel
                break
        
        if not target_field:
            sb.save_screenshot("error_no_email_field.png")
            print("❌ 无法定位邮箱框。请在 GitHub Artifacts 查看 error_no_email_field.png 确认页面状态。")
            # 如果是由于 IP 被封，通常截图会显示 "Access Denied"
            return

        print(f"✅ 找到输入框: {target_field}，正在输入账号...")
        sb.type(target_field, PELLA_EMAIL)
        
        # 点击继续
        submit_btn = "//button[@type='submit']|//button[contains(., 'Continue')]"
        sb.click(submit_btn)
        
        # 后续 OTP 处理逻辑保持不变...
        # [此处省略原有的 fetch_otp 和 do_renew 逻辑，请保持你原脚本中的该部分]
        print("📨 已提交，等待 OTP...")
        # ... (接你之前的代码)

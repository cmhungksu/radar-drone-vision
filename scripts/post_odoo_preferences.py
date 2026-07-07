#!/usr/bin/env python3
"""
Post-installation Odoo preferences for radar-drone-vision.
Handles all Odoo 18 SOP steps via XML-RPC:
  Step 2: Language & timezone
  Step 3: Admin credentials
  Step 4: Company info & system parameters
  Step 5: Login redirect to dashboard
  Step 6: Logout redirect URL
  Step 7.5: Homepage URL
"""
import sys
import time
import xmlrpc.client

ODOO_URL = 'http://localhost:46069'
DB = 'radar_drone_vision'
ADMIN_EMAIL = 'chun.min.hung@gmail.com'
ADMIN_PW = 'bio5234'


def wait_for_odoo(url, retries=30, delay=5):
    """Wait until Odoo XML-RPC is reachable."""
    common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
    for i in range(retries):
        try:
            ver = common.version()
            if ver:
                print(f"Odoo is ready (version {ver.get('server_version', '?')})")
                return common
        except Exception:
            pass
        print(f"  Waiting for Odoo... ({i+1}/{retries})")
        time.sleep(delay)
    print("ERROR: Odoo did not become reachable.")
    sys.exit(1)


def main():
    common = wait_for_odoo(ODOO_URL)
    models_proxy = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/object')

    # Try authenticating with the target credentials first, then fallback to defaults
    uid = None
    pw_used = ADMIN_PW
    for login, pw in [
        (ADMIN_EMAIL, ADMIN_PW),
        ('admin', 'admin'),
        ('admin', ADMIN_PW),
    ]:
        try:
            uid = common.authenticate(DB, login, pw, {})
            if uid:
                pw_used = pw
                print(f"Authenticated as '{login}' (uid={uid})")
                break
        except Exception:
            continue

    if not uid:
        print("ERROR: Cannot authenticate with any known credentials.")
        sys.exit(1)

    def ex(model, method, *args, **kwargs):
        kw = kwargs if kwargs else {}
        return models_proxy.execute_kw(DB, uid, pw_used, model, method, *args, **kw)

    # ── Step 2: Language & Timezone ──────────────────────────────
    print("\n[Step 2] Setting all users lang=zh_TW, tz=Asia/Taipei...")
    # Ensure zh_TW is installed
    try:
        lang_ids = ex('res.lang', 'search', [[('code', '=', 'zh_TW')]])
        if not lang_ids:
            # Try to load zh_TW
            try:
                wiz_id = ex('base.language.install', 'create', [{'overwrite': True}])
                # Set the lang field via write since create may not accept it
                ex('base.language.install', 'write', [[wiz_id], {'lang_ids': [[0, 0, {'code': 'zh_TW'}]]}])
            except Exception as e:
                print(f"  Warning: Could not install zh_TW: {e}")
    except Exception as e:
        print(f"  Warning: Language check failed: {e}")

    all_users = ex('res.users', 'search', [[('active', '=', True)]])
    if all_users:
        ex('res.users', 'write', [all_users, {'lang': 'zh_TW', 'tz': 'Asia/Taipei'}])
        print(f"  Updated {len(all_users)} users")

    # ── Step 3: Admin credentials ────────────────────────────────
    print("\n[Step 3] Setting admin credentials...")
    admin_ids = ex('res.users', 'search', [[('login', 'in', ['admin', ADMIN_EMAIL])]])
    if admin_ids:
        ex('res.users', 'write', [admin_ids, {
            'login': ADMIN_EMAIL,
            'email': ADMIN_EMAIL,
            'password': ADMIN_PW,
            'name': '系統管理者',
        }])
        # Re-authenticate with new credentials
        pw_used = ADMIN_PW
        uid = common.authenticate(DB, ADMIN_EMAIL, ADMIN_PW, {})
        if uid:
            print(f"  Re-authenticated as {ADMIN_EMAIL} (uid={uid})")
        else:
            print("  Warning: Re-authentication failed, continuing with old session")

    # ── Step 4: Company info & system parameters ─────────────────
    print("\n[Step 4] Setting company info and system parameters...")
    try:
        ex('res.company', 'write', [[1], {
            'name': '酷冷科技 CoolCold Tech',
            'street': '71005 台南市永康區南台街 1 號',
            'city': '台南市',
            'phone': '06-203-6993',
            'email': 'chun.min.hung@gmail.com',
            'website': 'https://www.coolcold.com.tw',
        }])
        print("  Company info updated")
    except Exception as e:
        print(f"  Warning: Company update failed: {e}")

    ex('ir.config_parameter', 'set_param', ['web.base.url', 'https://radar.ksu.coolcold.com.tw'])
    ex('ir.config_parameter', 'set_param', ['web.base.url.freeze', 'True'])
    ex('ir.config_parameter', 'set_param', ['report.url', 'http://localhost:8069'])
    print("  System parameters set")

    # Enable proxy mode
    try:
        ex('ir.config_parameter', 'set_param', ['web.proxy_mode', 'True'])
    except Exception:
        pass

    # ── Step 5: Login redirect to dashboard ──────────────────────
    print("\n[Step 5] Setting home action to dashboard...")
    dashboard_actions = ex('ir.model.data', 'search_read',
        [[('module', '=', 'radar_drone_vision'), ('name', '=', 'action_dashboard')]],
        {'fields': ['res_id']})

    if dashboard_actions:
        dashboard_id = dashboard_actions[0]['res_id']
        print(f"  Dashboard action_id = {dashboard_id}")

        # Set for all existing users
        all_users = ex('res.users', 'search', [[('active', '=', True)]])
        if all_users:
            ex('res.users', 'write', [all_users, {'action_id': dashboard_id}])
            print(f"  Set action_id for {len(all_users)} existing users")

        # Set ir.default for new users
        field_ids = ex('ir.model.fields', 'search',
            [[('model', '=', 'res.users'), ('name', '=', 'action_id')]])
        if field_ids:
            existing = ex('ir.default', 'search', [[('field_id', '=', field_ids[0])]])
            if existing:
                ex('ir.default', 'write', [existing, {'json_value': str(dashboard_id)}])
                print("  Updated ir.default for new users")
            else:
                ex('ir.default', 'create', [{'field_id': field_ids[0], 'json_value': str(dashboard_id)}])
                print("  Created ir.default for new users")
    else:
        print("  WARNING: action_dashboard not found! Module may not be installed yet.")

    # ── Step 6: Logout redirect URL ──────────────────────────────
    print("\n[Step 6] Setting logout redirect...")
    ex('ir.config_parameter', 'set_param', ['auth_signup.logout_redirect_url', '/'])
    print("  Logout will redirect to /")

    # ── Step 7.5: Homepage URL ───────────────────────────────────
    print("\n[Step 7.5] Setting homepage URL...")
    try:
        website_ids = ex('website', 'search', [[]])
        if website_ids:
            ex('website', 'write', [website_ids[:1], {
                'homepage_url': '/radar-home',
                'name': '雷達無人機視覺辨識平台',
            }])
            print("  Homepage URL set to /radar-home")
        else:
            print("  Warning: No website record found")
    except Exception as e:
        print(f"  Warning: Website update failed: {e}")

    # ── Summary ──────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("All post-production preferences applied!")
    print(f"  URL:       https://radar.ksu.coolcold.com.tw")
    print(f"  Login:     {ADMIN_EMAIL} / {ADMIN_PW}")
    print(f"  Dashboard: action_dashboard")
    print(f"  Logout:    redirect to /")
    print(f"  Homepage:  /radar-home")
    print("=" * 60)


if __name__ == '__main__':
    main()

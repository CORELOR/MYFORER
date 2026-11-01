import json
import os
import random
import re
import threading
import time
import telebot
from telebot import types
from telebot.apihelper import ApiTelegramException
from flask import Flask, request, jsonify
from flask_cors import CORS

# توکن ربات
TOKEN = '8995866424:AAF6FQMgihqbVAxOVliwd4sfFHBQv55_V_c'
bot = telebot.TeleBot(TOKEN)

# راه‌اندازی وب‌سرور Flask برای همگام‌سازی لابی رولت روسی
app = Flask(__name__)
CORS(app)

# لابی رولت روسی (ذخیره آنلاین بازیکنان برای حل مشکل ۱ از ۴)
roulette_lobby = []

@app.route('/api/status', methods=['GET'])
def api_status():
    return jsonify({"players": roulette_lobby})

@app.route('/api/join', methods=['GET'])
def api_join():
    global roulette_lobby
    user_id = request.args.get('user_id')
    name = request.args.get('name', 'کاربر')
    photo = request.args.get('photo', '')
    
    if not user_id:
        return jsonify({"error": "user_id required"}), 400
    
    existing = next((p for p in roulette_lobby if str(p['id']) == str(user_id)), None)
    if not existing:
        if len(roulette_lobby) < 4:
            roulette_lobby.append({"id": user_id, "name": name, "photo": photo})
    else:
        existing['name'] = name
        existing['photo'] = photo
        
    return jsonify({"players": roulette_lobby})

@app.route('/api/reset', methods=['GET'])
def api_reset():
    global roulette_lobby
    roulette_lobby = []
    return jsonify({"status": "reset", "players": roulette_lobby})


OWNER_ID = 1136559020
DEFAULT_REQUIRED_CHANNEL = "@xiarv"
CHANGELOG_CHANNEL = "@xiarv"  # کانال انتشار تغییرات ربات

# اطلاعات واریز وجه
CARD_NUMBER = "6219861998799224"
CARD_NAME = "علیرضا درخش"

# لینک مینی‌اپ رولت روسی (Netlify) با کدهای جدید پویا و پاپ‌آپ انتظار
ROULETTE_MINI_APP_URL = "https://lighthearted-smakager-bae123.netlify.app"

# زمان انتظار بین هر بار چرخش/پرتاب برای هر کاربر (به ثانیه)
USER_GAME_COOLDOWN = 10

user_configs = {}
user_states = {}
owner_temp_data = {}

# ذخیره زمان آخرین بازی هر کاربر {user_id: timestamp}
user_last_game_time = {}

# ساختار مدیریت لابی‌های بازی‌های گروهی {chat_id: dict}
active_group_games = {}

# فایل‌ها
DASHBOARD_FILE = "dashboard_id.txt"
USERS_FILE = "users.json"
RULES_FILE = "member_rules.txt"
ORDERS_FILE = "active_orders.json"
REFERRALS_FILE = "referrals.json"
REWARDS_FILE = "reward_requests.json"
SUBSCRIPTION_FILE = "subscription_config.json"
SUBSCRIPTION_PACKAGES_FILE = "subscription_packages.json"
BOT_SETTINGS_FILE = "bot_settings.json"
GROUPS_FILE = "groups.json"
PACKAGES_FILE = "member_packages.json"
TICKETS_FILE = "tickets.json"
USER_CONFIGS_FILE = "user_configs.json"
EXCHANGES_FILE = "exchanges.json"
CHANGELOG_FILE = "changelog.json"
CHANGELOG_MSG_FILE = "changelog_msg.txt"

file_lock = threading.RLock()
state_lock = threading.RLock()


def atomic_write_json(path, data):
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    temp_path = f"{path}.tmp"
    with file_lock:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, path)


def load_json_file(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        print(f"خطا در خواندن {path}: {exc}")
        return default


def escape_markdown(value):
    text_value = str(value if value is not None else "")
    for char in ("\\", "_", "*", "`", "["):
        text_value = text_value.replace(char, "\\" + char)
    return text_value


def load_bot_settings():
    default_settings = {
        "games_enabled": True, 
        "buttons_control": {
            "game_button": True,
            "member_button": True,
            "sub_button": True,
            "referral_button": True,
            "support_button": True
        }
    }
    if os.path.exists(BOT_SETTINGS_FILE):
        try:
            with open(BOT_SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "games_enabled" not in data:
                    data["games_enabled"] = True
                if not isinstance(data.get("buttons_control"), dict):
                    data["buttons_control"] = dict(default_settings["buttons_control"])
                else:
                    for key, value in default_settings["buttons_control"].items():
                        data["buttons_control"].setdefault(key, value)
                return data
        except Exception as e:
            print(f"خطا در خواندن تنظیمات ربات: {e}")
    return default_settings


def save_bot_settings(settings):
    try:
        atomic_write_json(BOT_SETTINGS_FILE, settings)
    except Exception as e:
        print(f"خطا در ذخیره save_bot_settings: {e}")


bot_settings = load_bot_settings()


def load_changelog():
    return load_json_file(CHANGELOG_FILE, [])


def save_changelog(changelog_list):
    try:
        atomic_write_json(CHANGELOG_FILE, changelog_list)
    except Exception as e:
        print(f"خطا در ذخیره changelog: {e}")


def load_changelog_msg_id():
    if os.path.exists(CHANGELOG_MSG_FILE):
        try:
            with open(CHANGELOG_MSG_FILE, "r") as f:
                content = f.read().strip()
                if content.isdigit():
                    return int(content)
        except Exception:
            pass
        return None


def save_changelog_msg_id(msg_id):
    with file_lock:
        try:
            with open(CHANGELOG_MSG_FILE, "w", encoding="utf-8") as f:
                f.write(str(msg_id))
        except Exception as e:
            print(f"خطا در ذخیره آیدی پیام کانال تغییرات: {e}")


def update_changelog_channel():
    changelog_list = load_changelog()
    if not changelog_list:
        text = "🚀 **آخرین به‌روزرسانی‌ها و تغییرات ربات:**\n\nهنوز قابلیتی ثبت نشده است."
    else:
        text = "🚀 **لیست به‌روزرسانی‌ها و قابلیت‌های جدید ربات:**\n\n"
        for idx, item in enumerate(changelog_list, 1):
            text += f"{idx}. {item}\n"
        text += f"\n📅 آخرین به‌روزرسانی: {time.strftime('%Y/%m/%d - %H:%M')}"

    msg_id = load_changelog_msg_id()
    if msg_id:
        try:
            bot.edit_message_text(text, chat_id=CHANGELOG_CHANNEL, message_id=msg_id, parse_mode="Markdown")
            return True
        except Exception:
            pass
    
    try:
        sent = bot.send_message(CHANGELOG_CHANNEL, text, parse_mode="Markdown")
        save_changelog_msg_id(sent.message_id)
        return True
    except Exception as e:
        print(f"خطا در ارسال پیام کانال تغییرات: {e}")
        return False


def load_tickets():
    return load_json_file(TICKETS_FILE, [])


def save_tickets(tickets_list):
    try:
        atomic_write_json(TICKETS_FILE, tickets_list)
    except Exception as e:
        print(f"خطا در ذخیره save_tickets: {e}")


tickets_data = load_tickets()
if not isinstance(tickets_data, list):
    tickets_data = []


def load_exchanges():
    return load_json_file(EXCHANGES_FILE, [])


def save_exchanges(exchanges_list):
    try:
        atomic_write_json(EXCHANGES_FILE, exchanges_list)
    except Exception as e:
        print(f"خطا در ذخیره save_exchanges: {e}")


exchanges_data = load_exchanges()
if not isinstance(exchanges_data, list):
    exchanges_data = []


def load_member_packages():
    default_pkgs = [
        {"id": 1, "count": 100, "price_num": 50000, "price": "۵۰,۰۰۰ تومان"},
        {"id": 2, "count": 500, "price_num": 200000, "price": "۲۰۰,۰۰۰ تومان"},
        {"id": 3, "count": 1000, "price_num": 350000, "price": "۳۵۰,۰۰۰ تومان"}
    ]
    pkgs = load_json_file(PACKAGES_FILE, default_pkgs)
    for p in pkgs:
        if "price_num" not in p:
            p["price_num"] = 50000
    return pkgs


def save_member_packages(pkgs):
    try:
        atomic_write_json(PACKAGES_FILE, pkgs)
    except Exception as e:
        print(f"خطا در ذخیره save_member_packages: {e}")


member_packages = load_member_packages()
if not isinstance(member_packages, list):
    member_packages = []


def load_subscription_packages():
    default_sub_pkgs = [
        {"id": 1, "days": 30, "price_num": 100000, "title": "اشتراک ۱ ماهه", "price": "۱۰۰,۰۰۰ تومان"},
        {"id": 2, "days": 90, "price_num": 250000, "title": "اشتراک ۳ ماهه", "price": "۲۵۰,۰۰۰ تومان"}
    ]
    pkgs = load_json_file(SUBSCRIPTION_PACKAGES_FILE, default_sub_pkgs)
    for p in pkgs:
        if "price_num" not in p:
            p["price_num"] = 100000
    return pkgs


def save_subscription_packages(pkgs):
    try:
        atomic_write_json(SUBSCRIPTION_PACKAGES_FILE, pkgs)
    except Exception as e:
        print(f"خطا در ذخیره save_subscription_packages: {e}")


subscription_packages = load_subscription_packages()
if not isinstance(subscription_packages, list):
    subscription_packages = []


def load_groups():
    raw = load_json_file(GROUPS_FILE, {})
    if isinstance(raw, dict):
        return {int(k): v for k, v in raw.items() if str(k).lstrip("-").isdigit()}
    return {}


def save_groups(groups_data):
    try:
        atomic_write_json(GROUPS_FILE, {str(k): v for k, v in groups_data.items()})
    except Exception as e:
        print(f"خطا در ذخیره save_groups: {e}")


registered_groups = load_groups()


def load_subscription_config():
    return load_json_file(SUBSCRIPTION_FILE, {
        "rules": "📌 **شرایط و تعرفه خرید اشتراک ویژه:**\n\nبرای فعال‌سازی قابلیت فوروارد خودکار، افزایش سرعت ارسال و دسترسی به کلیه ابزارهای ربات، لطفاً یکی از پلن‌های اشتراک را تهیه کنید.",
        "subscribers": {},
    })


def save_subscription_config(sub_data):
    try:
        atomic_write_json(SUBSCRIPTION_FILE, sub_data)
    except Exception as e:
        print(f"خطا در ذخیره save_subscription_config: {e}")


sub_config = load_subscription_config()
if not isinstance(sub_config, dict):
    sub_config = {"rules": "", "subscribers": {}}
sub_config.setdefault("rules", "")
if not isinstance(sub_config.get("subscribers"), dict):
    sub_config["subscribers"] = {}


def has_active_subscription(user_id):
    with state_lock:
        value = sub_config.get("subscribers", {}).get(str(user_id), False)
    if isinstance(value, dict):
        try:
            expires_at = float(value.get("expires_at", 0))
        except (TypeError, ValueError):
            return False
        return expires_at > time.time()
    return value is True


def grant_subscription(user_id, days):
    days = int(days)
    if days <= 0:
        raise ValueError("مدت اشتراک باید بیشتر از صفر باشد")
    key = str(user_id)
    with state_lock:
        current = sub_config.get("subscribers", {}).get(key, False)
        now = time.time()
        if current is True:
            expires_at = now + days * 86400
        elif isinstance(current, dict):
            try:
                expires_at = max(now, float(current.get("expires_at", 0))) + days * 86400
            except (TypeError, ValueError):
                expires_at = now + days * 86400
        else:
            expires_at = now + days * 86400
        sub_config["subscribers"][key] = {"expires_at": expires_at, "days_last_granted": days}
        save_subscription_config(sub_config)
    return expires_at


def load_reward_requests():
    return load_json_file(REWARDS_FILE, [])


def save_reward_requests(rewards_list):
    try:
        atomic_write_json(REWARDS_FILE, rewards_list)
    except Exception as e:
        print(f"خطا در ذخیره save_reward_requests: {e}")


reward_requests = load_reward_requests()
if not isinstance(reward_requests, list):
    reward_requests = []


def load_referrals():
    return load_json_file(REFERRALS_FILE, {"invites": {}, "referred_users": {}, "required_count": 10})


def save_referrals(ref_data):
    try:
        atomic_write_json(REFERRALS_FILE, ref_data)
    except Exception as e:
        print(f"خطا در ذخیره save_referrals: {e}")


referral_data = load_referrals()
if not isinstance(referral_data, dict):
    referral_data = {"invites": {}, "referred_users": {}, "required_count": 10}
referral_data.setdefault("invites", {})
referral_data.setdefault("referred_users", {})


def load_active_orders():
    return load_json_file(ORDERS_FILE, [])


def save_active_orders(orders_list):
    try:
        atomic_write_json(ORDERS_FILE, orders_list)
    except Exception as e:
        print(f"خطا در ذخیره save_active_orders: {e}")


active_orders = load_active_orders()
if not isinstance(active_orders, list):
    active_orders = []


def load_member_rules():
    if os.path.exists(RULES_FILE):
        try:
            with open(RULES_FILE, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            print(f"خطا در خواندن قوانین ممبرگیری: {e}")
    return "📌 **تعرفه و قوانین ممبرگیری:**\n\nبرای ثبت سفارش ممبر واقعی و فعال جهت افزایش عضویت کانال، یکی از بسته‌های زیر را انتخاب و سفارش دهید."


def save_member_rules(rules_text):
    with file_lock:
        try:
            with open(RULES_FILE, "w", encoding="utf-8") as f:
                f.write(rules_text)
        except Exception as e:
            print(f"خطا در ذخیره قوانین ممبرگیری: {e}")


def load_registered_users():
    raw = load_json_file(USERS_FILE, {})
    result = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            if str(k).lstrip("-").isdigit():
                uid = int(k)
                if isinstance(v, dict):
                    v.setdefault("wallet_balance", 0)
                    result[uid] = v
                else:
                    result[uid] = {"name": str(v), "username": "", "wallet_balance": 0}
    return result


def save_registered_users():
    try:
        atomic_write_json(USERS_FILE, {str(k): v for k, v in registered_users.items()})
    except Exception as e:
        print(f"خطا در ذخیره save_registered_users: {e}")


registered_users = load_registered_users()
if not isinstance(registered_users, dict):
    registered_users = {}


def load_dashboard_msg_id():
    if os.path.exists(DASHBOARD_FILE):
        try:
            with open(DASHBOARD_FILE, "r") as f:
                content = f.read().strip()
                if content.isdigit():
                    return int(content)
        except Exception as e:
            print(f"خطا در خواندن آیدی داشبورد: {e}")
    return None


def save_dashboard_msg_id(msg_id):
    with file_lock:
        try:
            with open(DASHBOARD_FILE, "w", encoding="utf-8") as f:
                f.write(str(msg_id))
        except Exception as e:
            print(f"خطا در ذخیره آیدی داشبورد: {e}")


owner_dashboard_msg_id = load_dashboard_msg_id()

DEFAULT_USER_CONFIG = {
    "destination": None, "mode": "forward", "message": None,
    "from_chat_id": None, "start_message_id": None, "count": 1,
    "interval_minutes": 5, "last_sent": 0, "error_count": 0,
    "is_running": False, "total_sent": 0,
}


def load_user_configs():
    raw = load_json_file(USER_CONFIGS_FILE, {})
    result = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            try:
                uid = int(key)
            except (TypeError, ValueError):
                continue
            cfg = dict(DEFAULT_USER_CONFIG)
            if isinstance(value, dict):
                cfg.update(value)
            cfg["is_running"] = False
            result[uid] = cfg
    return result


def save_user_configs():
    with state_lock:
        try:
            atomic_write_json(USER_CONFIGS_FILE, {str(k): v for k, v in user_configs.items()})
        except Exception as exc:
            print(f"خطا در ذخیره تنظیمات فوروارد کاربران: {exc}")


user_configs = load_user_configs()


def get_user_config(user_id):
    with state_lock:
        if user_id not in user_configs:
            user_configs[user_id] = dict(DEFAULT_USER_CONFIG)
        else:
            for key, value in DEFAULT_USER_CONFIG.items():
                user_configs[user_id].setdefault(key, value)
        return user_configs[user_id]


def get_active_channels_list():
    channels = [DEFAULT_REQUIRED_CHANNEL]
    for order in active_orders:
        if not isinstance(order, dict) or not order.get("is_active", True) or not order.get("link"):
            continue
        try:
            if int(order.get("current_count", 0)) < max(1, int(order.get("target_count", 100))):
                channels.append(order["link"])
        except (TypeError, ValueError):
            continue
    return channels


def _is_member_status(member):
    status = getattr(member, "status", None)
    if status in ("member", "administrator", "creator"):
        return True
    if status == "restricted":
        return bool(getattr(member, "is_member", False))
    return False


def check_membership(user_id):
    if user_id == OWNER_ID:
        return True
    for channel in get_active_channels_list():
        try:
            member = bot.get_chat_member(channel, user_id)
            if not _is_member_status(member):
                return False
        except Exception as exc:
            print(f"خطا در بررسی عضویت کانال {channel}: {exc}")
            return False
    return True


def increment_order_counters_for_user(user_id):
    updated = False
    for order in active_orders:
        if not isinstance(order, dict) or not order.get("is_active", True) or not order.get("link"):
            continue
        try:
            target = max(1, int(order.get("target_count", 100)))
            current = max(0, int(order.get("current_count", 0)))
        except (TypeError, ValueError):
            continue
        if current >= target:
            order["is_active"] = False
            continue
        counted = {int(uid) for uid in order.get("counted_users", []) if str(uid).lstrip("-").isdigit()}
        if user_id in counted:
            continue
        try:
            member = bot.get_chat_member(order["link"], user_id)
            if not _is_member_status(member):
                continue
        except Exception:
            continue
        counted.add(user_id)
        order["counted_users"] = sorted(counted)
        order["current_count"] = current + 1
        updated = True
        if order["current_count"] >= target:
            order["is_active"] = False
            try:
                bot.send_message(OWNER_ID, f"🎉 سفارش کانال {order['link']} به سقف تعیین‌شده ({target} ممبر) رسید.")
            except Exception:
                pass
            try:
                bot.send_message(order.get("user_id"), f"🎉 سفارش ممبرگیری شما تکمیل شد!\n\nکانال: {order['link']}")
            except Exception:
                pass
    if updated:
        save_active_orders(active_orders)


def get_join_keyboard(user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    channels = get_active_channels_list()

    for idx, channel in enumerate(channels, 1):
        try:
            member = bot.get_chat_member(channel, user_id)
            is_member = _is_member_status(member)
        except Exception:
            is_member = False

        if not is_member:
            clean_channel = channel.replace("@", "").replace("https://t.me/", "")
            btn_channel = types.InlineKeyboardButton(f"📢 کانال {idx}", url=f"https://t.me/{clean_channel}")
            markup.add(btn_channel)

    btn_check = types.InlineKeyboardButton("✅ بررسی عضویت", callback_data="check_join")
    markup.add(btn_check)
    return markup


def get_owner_dashboard_keyboard():
    markup = types.InlineKeyboardMarkup()
    btn_refresh = types.InlineKeyboardButton("🔄 بروزرسانی داشبورد", callback_data="refresh_dashboard")
    markup.add(btn_refresh)
    return markup


def get_manage_orders_view():
    orders_text = (
        "⚙️ **مدیریت کامل سفارشات ممبرگیری:**\n\n"
        "در این بخش لیست تمام سفارشات فعال کانال‌ها، میزان پیشرفت ممبرگیری و گزینه‌های مدیریت دستی قرار گرفته است.\n\n"
    )
    markup = types.InlineKeyboardMarkup(row_width=2)
    if not active_orders:
        orders_text += "🔴 هیچ سفارشی در حال حاضر ثبت نشده است.\n"
    else:
        for idx, order in enumerate(active_orders, 1):
            if not isinstance(order, dict):
                continue
            curr = order.get("current_count", 0)
            target = order.get("target_count", 100)
            link = escape_markdown(order.get("link", "نامشخص"))
            orders_text += f"🔹 **سفارش {idx}:** {link}\n📈 پیشرفت: [{curr}/{target}] ممبر\n\n"
            markup.add(types.InlineKeyboardButton(f"❌ لغو {idx}", callback_data=f"cancel_ord_{idx-1}"))
            
    markup.add(
        types.InlineKeyboardButton("➕ افزودن کانال دستی", callback_data="set_order_link"),
        types.InlineKeyboardButton("🗑 پاکسازی کامل همه", callback_data="clear_orders")
    )
    markup.add(types.InlineKeyboardButton("🔙 بازگشت به منوی قبلی", callback_data="menu_member"))
    return orders_text, markup


def get_users_list_text():
    users_text = "📊 **لیست جامع کاربران، آمار و اطلاعات حساب‌ها:**\n\n"
    
    if not registered_users:
        users_text += "هنوز کاربری ربات را استارت نزده است."
    else:
        for idx, (uid, info) in enumerate(registered_users.items(), 1):
            name = escape_markdown(info.get("name", "کاربر"))
            username = escape_markdown(info.get("username", ""))
            username_str = f"@{username}" if username else "بدون آیدی"
            wallet = info.get("wallet_balance", 0)
            
            has_sub = has_active_subscription(uid)
            sub_status = "اشتراک فعال 🟢" if has_sub else "بدون اشتراک 🔴"
            
            invites_count = referral_data.get("invites", {}).get(str(uid), 0)

            users_text += (
                f"👤 **{idx}. {name}**\n"
                f"   ├ 🏷 یوزرنیم: `{username_str}`\n"
                f"   ├ 🆔 آیدی عددی: `{uid}`\n"
                f"   ├ 💳 موجودی کیف‌پول: `{wallet:,} تومان`\n"
                f"   ├ 💎 وضعیت اشتراک: `{sub_status}`\n"
                f"   └ ⭐️ تعداد دعوت‌ها: `{invites_count} نفر`\n\n"
            )

    users_text += f"📈 **تعداد کل کاربران فعال ربات:** `{len(registered_users)}` نفر"
    return users_text


def update_owner_dashboard():
    global owner_dashboard_msg_id
    users_text = get_users_list_text()

    if owner_dashboard_msg_id:
        try:
            bot.edit_message_text(
                users_text,
                chat_id=OWNER_ID,
                message_id=owner_dashboard_msg_id,
                reply_markup=get_owner_dashboard_keyboard(),
                parse_mode="Markdown",
            )
            return
        except Exception:
            pass

    try:
        sent = bot.send_message(
            OWNER_ID,
            users_text,
            reply_markup=get_owner_dashboard_keyboard(),
            parse_mode="Markdown",
        )
        owner_dashboard_msg_id = sent.message_id
        save_dashboard_msg_id(owner_dashboard_msg_id)
    except Exception as ex:
        print(f"خطا در ارسال داشبورد جدید مالک: {ex}")


def get_admin_buttons_control_markup():
    markup = types.InlineKeyboardMarkup(row_width=2)
    ctrl = bot_settings.get("buttons_control", {})
    
    games_enabled_st = "🟢" if bot_settings.get("games_enabled", True) else "🔴"
    game_st = "🟢" if ctrl.get("game_button", True) else "🔴"
    member_st = "🟢" if ctrl.get("member_button", True) else "🔴"
    sub_st = "🟢" if ctrl.get("sub_button", True) else "🔴"
    ref_st = "🟢" if ctrl.get("referral_button", True) else "🔴"
    support_st = "🟢" if ctrl.get("support_button", True) else "🔴"
    
    markup.add(
        types.InlineKeyboardButton(f"🎮 بازی کلی {games_enabled_st}", callback_data="toggle_games_enabled"),
        types.InlineKeyboardButton(f"🎮 دکمه بازی {game_st}", callback_data="toggle_btn_game"),
        types.InlineKeyboardButton(f"👥 ممبرگیری {member_st}", callback_data="toggle_btn_member"),
        types.InlineKeyboardButton(f"💎 اشتراک {sub_st}", callback_data="toggle_btn_sub"),
        types.InlineKeyboardButton(f"⭐️ استارز {ref_st}", callback_data="toggle_btn_ref"),
        types.InlineKeyboardButton(f"📩 پشتیبانی {support_st}", callback_data="toggle_btn_support")
    )
    markup.add(types.InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_to_main"))
    return markup


def get_main_keyboard(user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    ctrl = bot_settings.get("buttons_control", {})
    
    if user_id == OWNER_ID:
        btn_member = types.InlineKeyboardButton("👥 ممبرگیری", callback_data="menu_member")
        btn_forward = types.InlineKeyboardButton("🔄 فوروارد خودکار", callback_data="menu_forward")
        btn_referral = types.InlineKeyboardButton("⭐️ استارز", callback_data="menu_referral")
        btn_sub = types.InlineKeyboardButton("💎 اشتراک", callback_data="menu_subscription")
        btn_games = types.InlineKeyboardButton("🎮 بازی", callback_data="menu_games")
        btn_exchange = types.InlineKeyboardButton("🔄 تبادل کانال", callback_data="menu_exchange")
        btn_wallet = types.InlineKeyboardButton("💰 کیف پول", callback_data="menu_wallet")
        btn_admin_sub = types.InlineKeyboardButton("➕ اعطای اشتراک", callback_data="admin_add_sub")
        btn_toggle_panel = types.InlineKeyboardButton("⚙️ دسترسی دکمه‌ها", callback_data="admin_buttons_panel")
        btn_stats = types.InlineKeyboardButton("📊 آمار ربات", callback_data="global_stats")
        
        markup.add(btn_member, btn_forward, btn_referral, btn_sub, btn_games, btn_exchange, btn_wallet, btn_admin_sub, btn_toggle_panel, btn_stats)
    else:
        row1 = []
        if ctrl.get("member_button", True):
            row1.append(types.InlineKeyboardButton("👥 ممبرگیری", callback_data="menu_member"))
        row1.append(types.InlineKeyboardButton("🔄 فوروارد خودکار", callback_data="menu_forward"))
        markup.add(*row1)

        row2 = []
        if ctrl.get("referral_button", True):
            row2.append(types.InlineKeyboardButton("⭐️ استارز", callback_data="menu_referral"))
        if ctrl.get("sub_button", True):
            row2.append(types.InlineKeyboardButton("💎 اشتراک", callback_data="menu_subscription"))
        if row2:
            markup.add(*row2)

        row3 = [
            types.InlineKeyboardButton("🔄 تبادل کانال", callback_data="menu_exchange"),
            types.InlineKeyboardButton("💰 کیف پول", callback_data="menu_wallet")
        ]
        markup.add(*row3)

        row4 = []
        if bot_settings.get("games_enabled", True) and ctrl.get("game_button", True):
            row4.append(types.InlineKeyboardButton("🎮 بازی", callback_data="menu_games"))
        if ctrl.get("support_button", True):
            row4.append(types.InlineKeyboardButton("📩 پشتیبانی", callback_data="menu_support"))
        if row4:
            markup.add(*row4)

    return markup


def get_forward_keyboard(user_id):
    cfg = get_user_config(user_id)
    markup = types.InlineKeyboardMarkup(row_width=2)

    run_text = "⏸ توقف" if cfg["is_running"] else "▶️ شروع"
    dest_text = "🎯 مقصد" if not cfg["destination"] else "🎯 مقصد (تنظیم)"
    mode_text = "🔄 فوروارد" if cfg["mode"] == "forward" else "📄 متن"

    if cfg["from_chat_id"] and cfg["start_message_id"]:
        source_text = f"🔗 مبدا ({cfg['count']})"
    else:
        source_text = "🔗 تنظیم مبدا"

    btn_run = types.InlineKeyboardButton(run_text, callback_data="toggle_run")
    btn_dest = types.InlineKeyboardButton(dest_text, callback_data="set_dest")
    btn_mode = types.InlineKeyboardButton(mode_text, callback_data="toggle_mode")
    btn_set_forward = types.InlineKeyboardButton(source_text, callback_data="set_forward")
    btn_set_text = types.InlineKeyboardButton("✍️ متن دلخواه", callback_data="set_text")
    btn_time = types.InlineKeyboardButton(f"⏱ زمان ({cfg['interval_minutes']}m)", callback_data="change_time")
    btn_status = types.InlineKeyboardButton("📊 وضعیت", callback_data="show_status")
    btn_clear = types.InlineKeyboardButton("🗑 پاکسازی", callback_data="clear_forward_config")
    btn_back = types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")

    markup.add(btn_run, btn_dest)
    markup.add(btn_mode, btn_set_forward)
    markup.add(btn_set_text, btn_time)
    markup.add(btn_status, btn_clear)
    markup.add(btn_back)
    return markup


def get_group_games_selection_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=3)
    markup.add(
        types.InlineKeyboardButton("🎰 اسلات", callback_data="select_game_slot"),
        types.InlineKeyboardButton("🎯 دارت", callback_data="select_game_dart"),
        types.InlineKeyboardButton("⚽ فوتبال", callback_data="select_game_football"),
        types.InlineKeyboardButton("🎳 بولینگ", callback_data="select_game_bowling"),
        types.InlineKeyboardButton("🏀 بسکتبال", callback_data="select_game_basketball")
    )
    return markup


def build_game_lobby_view(chat_id):
    with state_lock:
        game = active_group_games.get(chat_id)
        if not game:
            return "", None

        g_type = game.get("game_type", "slot")
        names_map = {
            "slot": "🎰 اسلات گروهی",
            "dart": "🎯 دارت گروهی",
            "football": "⚽ فوتبال گروهی",
            "bowling": "🎳 بولینگ گروهی",
            "basketball": "🏀 بسکتبال گروهی",
        }
        g_title = names_map.get(g_type, "بازی گروهی")

        players = game.get("players", [])
        count = len(players)

        text = f"🎮 **لابی مسابقه {g_title}**\n\n"
        text += "برای شرکت در مسابقه هیجان‌انگیز روی دکمه «🎮 ورود» بزنید.\nپس از تکمیل بازیکنان، سازنده مسابقه می‌تواند بازی را شروع کند.\n\n"
        text += f"👥 **لیست بازیکنان حاضر ({count} نفر):**\n" # ظرفیت /4 حذف شد

        if count == 0:
            text += "هنوز کسی ثبت‌نام نکرده است! اولین نفر باشید.\n"
        else:
            for idx, p in enumerate(players, 1):
                p_name = escape_markdown(p["name"])
                text += f"{idx}. {p_name}\n"

        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🎮 ورود", callback_data="group_game_join"), # ظرفیت /4 از روی دکمه حذف شد
            types.InlineKeyboardButton("🚀 شروع", callback_data="group_game_start")
        )
        markup.add(types.InlineKeyboardButton("❌ لغو مسابقه", callback_data="group_game_cancel"))
        return text, markup


# ================= سیستم تغییرات کانال (Changelog) =================
@bot.message_handler(commands=['add_update'])
def add_update_command(message):
    if message.from_user.id != OWNER_ID:
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "❌ لطفاً متن قابلیت جدید را بعد از دستور وارد کنید.\n\n📌 **مثال:**\n`/add_update اضافه شدن سیستم جدید`", parse_mode="Markdown")
        return
    
    feature_text = args[1].strip()
    with state_lock:
        changelog = load_changelog()
        changelog.append(feature_text)
        save_changelog(changelog)
    
    success = update_changelog_channel()
    if success:
        bot.reply_to(message, f"✅ قابلیت جدید اضافه شد و پیام کانال `{CHANGELOG_CHANNEL}` با موفقیت به‌روزرسانی شد!", parse_mode="Markdown")
    else:
        bot.reply_to(message, f"⚠️ قابلیت ثبت شد، اما در ویرایش پیام کانال خطایی رخ داد (اطمینان حاصل کنید ربات در کانال `{CHANGELOG_CHANNEL}` ادمین است).", parse_mode="Markdown")


@bot.message_handler(commands=['del_update'])
def del_update_command(message):
    if message.from_user.id != OWNER_ID:
        return
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        bot.reply_to(message, "❌ لطفاً شماره قابلیت را وارد کنید.\n\n📌 **مثال:**\n`/del_update 1`", parse_mode="Markdown")
        return
    
    idx = int(args[1]) - 1
    with state_lock:
        changelog = load_changelog()
        if 0 <= idx < len(changelog):
            removed = changelog.pop(idx)
            save_changelog(changelog)
        else:
            bot.reply_to(message, "❌ شماره وارد شده نامعتبر است.")
            return
    
    update_changelog_channel()
    bot.reply_to(message, f"✅ قابلیت شماره `{args[1]}` حذف شد و کانال به‌روزرسانی گردید.", parse_mode="Markdown")


@bot.message_handler(commands=['clear_updates'])
def clear_updates_command(message):
    if message.from_user.id != OWNER_ID:
        return
    with state_lock:
        save_changelog([])
    update_changelog_channel()
    bot.reply_to(message, "🗑 لیست تغییرات و به‌روزرسانی‌ها کامل پاکسازی شد.", parse_mode="Markdown")
# =========================================================================


@bot.message_handler(func=lambda message: message.chat.type != "private")
def handle_group_messages(message):
    chat_id = message.chat.id
    text = message.text or message.caption or ""

    with state_lock:
        if chat_id not in registered_groups:
            registered_groups[chat_id] = message.chat.title or "گروه"
            save_groups(registered_groups)

    bot_username = "@myforer_bot"

    if bot_username in text.lower():
        if not bot_settings.get("games_enabled", True):
            bot.reply_to(message, "🔴 بخش بازی‌ها در حال حاضر توسط مدیریت غیرفعال شده است.")
            return

        selection_text = "🎮 **به بخش بازی‌های گروهی خوش آمدید!**\n\nلطفاً یکی از بازی‌های زیر را انتخاب کنید تا لابی مسابقه در گروه ساخته شود:"
        try:
            bot.reply_to(
                message,
                selection_text,
                reply_markup=get_group_games_selection_keyboard(),
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"خطا در ارسال پنل انتخاب بازی در گروه: {e}")


@bot.message_handler(commands=["start", "settings"])
def send_welcome(message):
    if message.chat.type != "private":
        return

    user_id = message.from_user.id
    first_name = message.from_user.first_name or "بدون نام"
    username = message.from_user.username

    req_cnt = max(1, int(referral_data.get("required_count", 10) or 10))

    if not check_membership(user_id):
        join_text = (
            "❌ **دسترسی محدود شد!**\n\n"
            "جهت استفاده کامل از تمامی خدمات و امکانات ربات، ابتدا در کانال‌های زیر عضو شوید و سپس دکمه **«✅ بررسی عضویت»** را بزنید:"
        )
        bot.send_message(message.chat.id, join_text, reply_markup=get_join_keyboard(user_id), parse_mode="Markdown")
        return

    args = (message.text or "").split()
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referrer_id = int(args[1].replace("ref_", ""))
            with state_lock:
                if referrer_id != user_id and user_id not in registered_users:
                    str_uid, str_ref = str(user_id), str(referrer_id)
                    if str_uid not in referral_data["referred_users"]:
                        referral_data["referred_users"][str_uid] = referrer_id
                        referral_data["invites"][str_ref] = int(referral_data["invites"].get(str_ref, 0)) + 1
                        save_referrals(referral_data)
                        current_invites = referral_data["invites"][str_ref]
                        if current_invites > 0 and current_invites % req_cnt == 0:
                            bot.send_message(
                                referrer_id,
                                f"🎉 تبریک! شما با موفقیت `{req_cnt}` نفر را دعوت کردید و برنده **۱ استارز تلگرام** شدید! ⭐️\n\n🔗 لطفاً لینک پست اختصاصی خود جهت دریافت جایزه را ارسال کنید:",
                                parse_mode="Markdown",
                            )
                            user_states[referrer_id] = "waiting_for_reward_post_link"
        except Exception as e:
            print(f"خطا در پردازش زیرمجموعه: {e}")

    with state_lock:
        user_states[user_id] = None
        if user_id not in registered_users:
            registered_users[user_id] = {"name": first_name, "username": username, "wallet_balance": 0}
            save_registered_users()
            increment_order_counters_for_user(user_id)
            update_owner_dashboard()
        else:
            registered_users[user_id].setdefault("wallet_balance", 0)
            if user_id == OWNER_ID:
                update_owner_dashboard()

    menu_text = (
        "🤖 **پنل مدیریت ارشد مالکان ربات**\n\n"
        "به بخش مدیریت خوش آمدید. از طریق دکمه‌های زیر می‌توانید تمام بخش‌های ربات، آمار، کیف‌پول و دسترسی‌ها را کنترل نمایید."
        if user_id == OWNER_ID
        else 
        "🤖 **به منوی اصلی و خدمات هوشمند ربات خوش آمدید.**\n\n"
        "جهت شروع استفاده، یکی از بخش‌های مورد نظر را از دکمه‌های زیر انتخاب کنید:"
    )

    bot.send_message(message.chat.id, menu_text, reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")


@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    global member_packages, subscription_packages, owner_dashboard_msg_id
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id

    with state_lock:
        if call.data in {
            "back_to_main", "menu_member", "menu_subscription", "menu_forward", "menu_games",
            "menu_referral", "menu_support", "admin_manage_pkgs", "admin_manage_sub_pkgs",
            "manage_order", "global_stats", "admin_buttons_panel", "menu_wallet", "menu_exchange",
            "wallet_topup_guide", "register_exchange", "view_exchanges"
        }:
            user_states[user_id] = None

    try:
        # بررسی عضویت برای دکمه بازی در چت خصوصی
        if call.data == "menu_games":
            if not bot_settings.get("games_enabled", True) and user_id != OWNER_ID:
                bot.answer_callback_query(call.id, "🔴 بخش بازی‌ها غیرفعال است.", show_alert=True)
                return
            
            # اول چک کن کاربر عضو کانال‌ها هست یا نه
            if not check_membership(user_id):
                bot.answer_callback_query(call.id, "❌ ابتدا عضو کانال‌های ربات شوید!", show_alert=True)
                join_text = (
                    "❌ **دسترسی محدود شد!**\n\n"
                    "جهت ورود به بخش بازی‌ها، ابتدا در کانال‌های زیر عضو شوید و سپس دکمه **«✅ بررسی عضویت»** را بزنید:"
                )
                bot.edit_message_text(join_text, chat_id=chat_id, message_id=message_id, reply_markup=get_join_keyboard(user_id), parse_mode="Markdown")
                return

            bot.answer_callback_query(call.id)
            
            game_menu_text = (
                "🎮 **بخش سرگرمی و بازی‌های ربات:**\n\n"
                "از طریق گزینه‌های زیر می‌توانید در مسابقات گروهی شرکت کنید یا مستقیماً وارد مینی‌اپ رولت روسی شوید:"
            )
            markup = types.InlineKeyboardMarkup(row_width=1)
            # دکمه ورود به مینی اپ رولت روسی در چت خصوصی با web_app
            markup.add(
                types.InlineKeyboardButton("🇷🇺 رولت روسی (ورود به مینی‌اپ)", web_app=types.WebAppInfo(url=ROULETTE_MINI_APP_URL)),
                types.InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main")
            )
            bot.edit_message_text(game_menu_text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")
            return

        if call.data == "menu_wallet":
            bot.answer_callback_query(call.id)
            u_info = registered_users.get(user_id, {"wallet_balance": 0})
            balance = u_info.get("wallet_balance", 0)
            wallet_text = (
                f"💰 **مدیریت کیف پول دیجیتال شما:**\n\n"
                f"💳 **موجودی فعلی حساب:** `{balance:,} تومان`\n\n"
                f"💡 **مزایای کیف پول:**\n"
                f"با شارژ حساب، خرید بسته‌های ممبرگیری و فعال‌سازی اشتراک به‌صورت **آنی و اتوماتیک** بدون نیاز به تایید دستی فیش واریزی انجام می‌شود."
            )
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton("➕ افزایش موجودی (شارژ کیف پول)", callback_data="wallet_topup_guide"),
                types.InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main")
            )
            bot.edit_message_text(wallet_text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")
            return

        if call.data == "wallet_topup_guide":
            bot.answer_callback_query(call.id)
            with state_lock:
                user_states[user_id] = {"state": "waiting_for_wallet_receipt"}
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 انصراف", callback_data="menu_wallet"))
            guide_text = (
                f"➕ **راهنمای شارژ کیف پول:**\n\n"
                f"۱. مبلغ دلخواه خود را به شماره کارت زیر واریز کنید:\n"
                f"💳 شماره کارت: `{CARD_NUMBER}`\n"
                f"👤 به نام: {CARD_NAME}\n\n"
                f"۲. **تصویر فیش واریزی** خود را در پاسخ به همین پیام ارسال نمایید.\n"
                f"پس از بررسی، کیف پول شما بلافاصله شارژ خواهد شد."
            )
            bot.edit_message_text(guide_text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")
            return

        if call.data == "menu_exchange":
            bot.answer_callback_query(call.id)
            exch_text = (
                "🔄 **بازارچه تبادل هوشمند کانال‌های تلگرامی:**\n\n"
                "در این بخش می‌توانید کانال خود را برای تبادل اعضا و پست‌ها ثبت کنید یا از لیست کانال‌های فعال، کانال‌های هم‌رده را انتخاب کرده و درخواست تبادل مستقیم بفرستید."
            )
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton("➕ ثبت کانال من برای تبادل", callback_data="register_exchange"),
                types.InlineKeyboardButton("🌐 مشاهده لیست تبادل‌ها", callback_data="view_exchanges"),
                types.InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main")
            )
            bot.edit_message_text(exch_text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")
            return

        if call.data == "register_exchange":
            bot.answer_callback_query(call.id)
            with state_lock:
                user_states[user_id] = {"state": "waiting_for_exchange_channel_input"}
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 انصراف", callback_data="menu_exchange"))
            bot.edit_message_text(
                "➕ **ثبت کانال جدید در بازارچه تبادل:**\n\nلطفاً آیدی کانال و تعداد ممبرهای تقریبی آن را با کاما بفرستید.\n\n📌 **نمونه ارسال درست:**\n`@mychannel, 1500`",
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=markup,
                parse_mode="Markdown"
            )
            return

        if call.data == "view_exchanges":
            bot.answer_callback_query(call.id)
            markup = types.InlineKeyboardMarkup(row_width=1)
            active_exch = [e for e in exchanges_data if e.get("is_active", True)]
            
            if not active_exch:
                exch_list_text = "🌐 **لیست تبادل‌ها:**\n\nدر حال حاضر هیچ کانالی برای تبادل ثبت نشده است. با ثبت کانال خود، اولین پیشنهاد تبادل را ایجاد کنید!"
            else:
                exch_list_text = "🌐 **لیست کانال‌های متقاضی تبادل:**\n\nبرای درخواست تبادل روی دکمه کانال مورد نظر کلیک کنید:\n\n"
                for idx, exch in enumerate(active_exch, 1):
                    exch_list_text += f"🔹 {idx}. کانال: `{exch['channel']}` | 👥 اعضا: `{exch['members']} نفر`\n"
                    if exch["user_id"] != user_id:
                        markup.add(types.InlineKeyboardButton(f"🤝 درخواست تبادل با {exch['channel']}", callback_data=f"req_exch_{exch['id']}"))
            
            markup.add(types.InlineKeyboardButton("🔙 بازگشت به منوی تبادل", callback_data="menu_exchange"))
            bot.edit_message_text(exch_list_text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")
            return

        if call.data.startswith("req_exch_"):
            exch_id = int(call.data.split("_")[2])
            target_exch = next((e for e in exchanges_data if e.get("id") == exch_id), None)
            if not target_exch:
                bot.answer_callback_query(call.id, "❌ کانال مورد نظر یافت نشد!", show_alert=True)
                return
            
            target_uid = target_exch["user_id"]
            owner_info = registered_users.get(user_id, {})
            u_name = owner_info.get("name", "کاربر")
            
            bot.answer_callback_query(call.id, "✅ درخواست تبادل شما به مدیر کانال ارسال شد!")
            try:
                bot.send_message(
                    target_uid,
                    f"🤝 **درخواست تبادل جدید دریافت شد!**\n\nمدیر [{u_name}](tg://user?id={user_id}) متقاضی تبادل با کانال شما (`{target_exch['channel']}`) است.\nبرای هماهنگی می‌توانید مستقیماً به ایشان پیام دهید.",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
            return

        if call.data.startswith("wallet_buy_pkg_"):
            pkg_id = int(call.data.split("_")[3])
            selected_pkg = next((p for p in member_packages if p["id"] == pkg_id), None)
            if not selected_pkg:
                bot.answer_callback_query(call.id, "❌ بسته یافت نشد!", show_alert=True)
                return
            
            price_num = selected_pkg.get("price_num", 50000)
            u_info = registered_users.get(user_id, {"wallet_balance": 0})
            balance = u_info.get("wallet_balance", 0)
            
            if balance < price_num:
                bot.answer_callback_query(call.id, f"❌ موجودی کیف پول کافی نیست! (موجودی: {balance:,} تومان)", show_alert=True)
                return
            
            with state_lock:
                u_info["wallet_balance"] = balance - price_num
                save_registered_users()
                user_states[user_id] = {"state": "waiting_for_channel_link", "count": selected_pkg["count"]}
            
            bot.answer_callback_query(call.id, "✅ پرداخت آنی با موفقیت انجام شد!")
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 انصراف", callback_data="back_to_main"))
            bot.edit_message_text(
                f"🎉 **پرداخت آنلاین با موفقیت انجام شد!**\n\n"
                f"📦 بسته انتخاب‌شده: `{selected_pkg['count']}` ممبر\n"
                f"💰 مبلغ کسرشده: `{selected_pkg['price']}`\n\n"
                f"🔗 لطفاً آیدی یا لینک کانال عمومی خود را ارسال کنید (مثال: `@channel`):",
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=markup,
                parse_mode="Markdown"
            )
            return

        if call.data.startswith("wallet_buy_sub_"):
            pkg_id = int(call.data.split("_")[3])
            selected_pkg = next((p for p in subscription_packages if p["id"] == pkg_id), None)
            if not selected_pkg:
                bot.answer_callback_query(call.id, "❌ بسته یافت نشد!", show_alert=True)
                return
            
            price_num = selected_pkg.get("price_num", 100000)
            u_info = registered_users.get(user_id, {"wallet_balance": 0})
            balance = u_info.get("wallet_balance", 0)
            
            if balance < price_num:
                bot.answer_callback_query(call.id, f"❌ موجودی کیف پول کافی نیست! (موجودی: {balance:,} تومان)", show_alert=True)
                return
            
            with state_lock:
                u_info["wallet_balance"] = balance - price_num
                save_registered_users()
            
            grant_subscription(user_id, selected_pkg["days"])
            bot.answer_callback_query(call.id, "✅ اشتراک شما فعال شد!")
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main"))
            bot.edit_message_text(
                f"🎉 **پرداخت موفق!**\n\nاشتراک ویژه `{selected_pkg['title']}` (`{selected_pkg['days']} روزه`) با موفقیت از کیف پول شما خریداری و فعال گردید.",
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=markup,
                parse_mode="Markdown"
            )
            return

        if call.data.startswith("approve_wallet_"):
            if user_id != OWNER_ID:
                return
            target_user_id = int(call.data.split("_")[2])
            
            with state_lock:
                user_states[OWNER_ID] = {"state": "admin_waiting_for_wallet_amount", "target_id": target_user_id}
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 انصراف", callback_data="manage_order"))
            bot.answer_callback_query(call.id)
            bot.send_message(OWNER_ID, f"✍️ لطفاً مبلغ دقیق شارژ کیف پول برای کاربر `{target_user_id}` را به تومان (فقط عدد) ارسال کنید:", reply_markup=markup, parse_mode="Markdown")
            return

        if call.data.startswith("select_game_"):
            if not check_membership(user_id):
                bot.answer_callback_query(call.id, "❌ ابتدا عضو کانال‌های ربات شوید!", show_alert=True)
                return

            g_type = call.data.replace("select_game_", "")

            with state_lock:
                if chat_id in active_group_games:
                    bot.answer_callback_query(call.id, "⚠️ یک مسابقه در حال برگزاری است.", show_alert=True)
                    return

                active_group_games[chat_id] = {
                    "game_type": g_type,
                    "status": "lobby",
                    "creator_id": user_id,
                    "players": [],
                    "message_id": message_id,
                    "total_attempts": 0,
                    "bullet_count": 1
                }

            bot.answer_callback_query(call.id, "✅ لابی ایجاد شد!")
            text, markup = build_game_lobby_view(chat_id)
            try:
                bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")
            except Exception as e:
                print(f"خطا در تبدیل پیام به لابی: {e}")
            return

        if call.data == "group_game_cancel":
            with state_lock:
                game = active_group_games.get(chat_id)
                if not game:
                    bot.answer_callback_query(call.id, "❌ مسابقه‌ای یافت نشد.", show_alert=True)
                    return
                creator_id = game.get("creator_id")
                if user_id != creator_id and user_id != OWNER_ID:
                    bot.answer_callback_query(call.id, "⛔️ فقط سازنده مسابقه اجازه لغو دارد!", show_alert=True)
                    return
                active_group_games.pop(chat_id, None)

            bot.answer_callback_query(call.id, "✅ مسابقه لغو شد.")
            try:
                bot.edit_message_text("❌ **این مسابقه توسط سازنده لغو شد.**", chat_id=chat_id, message_id=message_id, parse_mode="Markdown")
            except Exception:
                pass
            return

        if call.data == "group_game_join":
            if not check_membership(user_id):
                bot.answer_callback_query(call.id, "❌ ابتدا عضو کانال‌های ربات شوید!", show_alert=True)
                return

            with state_lock:
                game = active_group_games.get(chat_id)
                if not game or game.get("status") != "lobby":
                    bot.answer_callback_query(call.id, "❌ لابی فعال نیست.", show_alert=True)
                    return

                players = game.get("players", [])
                if any(p["user_id"] == user_id for p in players):
                    bot.answer_callback_query(call.id, "⚠️ شما قبلاً ثبت‌نام کرده‌اید!", show_alert=True)
                    return

                # محدودیت ظرفیت ۴ نفر از اینجا حذف شد تا بازیکنان بدون محدودیت تعداد بتوانند شرکت کنند

                u_name = call.from_user.first_name or "کاربر"
                players.append({"user_id": user_id, "name": u_name})

            bot.answer_callback_query(call.id, "✅ وارد مسابقه شدید!")
            text, markup = build_game_lobby_view(chat_id)
            try:
                bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")
            except Exception:
                pass
            return

        if call.data == "group_game_start":
            if not check_membership(user_id):
                bot.answer_callback_query(call.id, "❌ ابتدا عضو کانال‌های ربات شوید!", show_alert=True)
                return

            with state_lock:
                game = active_group_games.get(chat_id)
                if not game or game.get("status") != "lobby":
                    bot.answer_callback_query(call.id, "❌ لابی یافت نشد.", show_alert=True)
                    return

                creator_id = game.get("creator_id")
                if user_id != creator_id and user_id != OWNER_ID:
                    bot.answer_callback_query(call.id, "⛔️ فقط سازنده مسابقه اجازه شروع دارد!", show_alert=True)
                    return

                players = game.get("players", [])
                if not players:
                    bot.answer_callback_query(call.id, "⚠️ هنوز کسی ثبت‌نام نکرده!", show_alert=True)
                    return

                game["status"] = "playing"
                game["message_id"] = message_id
                g_type = game.get("game_type", "slot")

            bot.answer_callback_query(call.id, "🚀 مسابقه شروع شد!")
            names_map = {
                "slot": ("🎰 چرخش", "🎰 مسابقه اسلات! (جفت شدن سه شکل = برد 🏆)"),
                "dart": ("🎯 پرتاب", "🎯 مسابقه دارت! (برخورد به مرکز هدف [Bullseye] = برد 🏆)"),
                "football": ("⚽ شوت", "⚽ مسابقه فوتبال! (گل زدن = برد 🏆)"),
                "bowling": ("🎳 پرتاب", "🎳 مسابقه بولینگ! (انداختن همه پین‌ها = برد 🏆)"),
                "basketball": ("🏀 پرتاب", "🏀 مسابقه بسکتبال! (گل زدن = برد 🏆)")
            }
            btn_title, start_msg_title = names_map.get(g_type, ("شروع", "بازی شروع شد!"))

            start_text = f"🎮 **{start_msg_title}**\n\nروی دکمه زیر کلیک کنید تا شانس خود را امتحان کنید."
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(btn_title, callback_data="roll_group_game"))

            try:
                bot.edit_message_text(
                    start_text,
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=markup,
                    parse_mode="Markdown"
                )
            except Exception as e:
                print(f"خطا در ویرایش پیام لابی به شروع بازی: {e}")
            return

        if call.data == "roll_group_game":
            if not check_membership(user_id):
                bot.answer_callback_query(call.id, "❌ ابتدا عضو کانال‌های ربات شوید!", show_alert=True)
                return

            with state_lock:
                game = active_group_games.get(chat_id)
                if not game or game.get("status") != "playing":
                    bot.answer_callback_query(call.id, "❌ مسابقه‌ای در جریان نیست.", show_alert=True)
                    return

                players = game.get("players", [])
                if not any(p["user_id"] == user_id for p in players) and user_id != OWNER_ID:
                    bot.answer_callback_query(call.id, "⛔️ شما جزو بازیکنان ثبت‌نام‌شده نیستید!", show_alert=True)
                    return

                game["total_attempts"] = game.get("total_attempts", 0) + 1
                total_att = game["total_attempts"]

            now = time.time()
            last_time = user_last_game_time.get(user_id, 0)
            elapsed = now - last_time

            if elapsed < USER_GAME_COOLDOWN:
                remaining = int(USER_GAME_COOLDOWN - elapsed) + 1
                bot.answer_callback_query(call.id, f"⏳ {remaining} ثانیه دیگر صبر کنید!", show_alert=True)
                return

            user_last_game_time[user_id] = now
            user_name = escape_markdown(call.from_user.first_name or "کاربر")
            g_type = game.get("game_type", "slot")
            
            emoji_map = {
                "slot": "🎰",
                "dart": "🎯",
                "football": "⚽",
                "bowling": "🎳",
                "basketball": "🏀"
            }
            chosen_emoji = emoji_map.get(g_type, "🎰")

            bot.answer_callback_query(call.id, "🎲 در حال شانس‌آزمایی...")
            
            try:
                dice_msg = bot.send_dice(chat_id, emoji=chosen_emoji)
            except Exception as e:
                print(f"خطا در ارسال دایس: {e}")
                return

            time.sleep(2.5)
            
            dice_value = 0
            try:
                if dice_msg and hasattr(dice_msg, 'dice') and dice_msg.dice:
                    dice_value = getattr(dice_msg.dice, 'value', 0)
            except Exception as e:
                print(f"خطا در خواندن مقدار دایس: {e}")
                dice_value = 0

            is_winner = False
            if g_type == "slot":
                is_winner = (dice_value == 64)
            elif g_type == "dart":
                is_winner = (dice_value == 6)
            elif g_type == "football":
                is_winner = (dice_value in (4, 5, 6))
            elif g_type == "bowling":
                is_winner = (dice_value == 6)
            elif g_type == "basketball":
                is_winner = (dice_value in (4, 5))

            if is_winner:
                with state_lock:
                    lobby_msg_id = game.get("message_id")
                    active_group_games.pop(chat_id, None)

                if lobby_msg_id:
                    try:
                        bot.delete_message(chat_id, lobby_msg_id)
                    except Exception as e:
                        print(f"خطا در حذف پیام لابی: {e}")

                win_messages = {
                    "slot": f"🎰 **جک‌پات بزرگ!** بازیکن **[{user_name}](tg://user?id={user_id})** سه شکل مشابه آورد و جایزه را درو کرد! 👑",
                    "dart": f"🎯 **تیر به هدف نشست!** بازیکن **[{user_name}](tg://user?id={user_id})** دارت را دقیقاً به مرکز هدف (Bullseye) زد و برنده شد! 👑",
                    "football": f"⚽ **گل طلایی!** بازیکن **[{user_name}](tg://user?id={user_id})** با یک شوت بی‌نقص دروازه را باز کرد و برنده مسابقه شد! 👑",
                    "bowling": f"🎳 **استرایک عالی!** بازیکن **[{user_name}](tg://user?id={user_id})** همه پین‌ها را ریخت و فاتح مسابقه شد! 👑",
                    "basketball": f"🏀 **باسکت تمیز!** بازیکن **[{user_name}](tg://user?id={user_id})** توپ را وارد سبد کرد و برنده شد! 👑"
                }

                win_detail = win_messages.get(g_type, f"🎉 **تبریک!** بازیکن **[{user_name}](tg://user?id={user_id})** برنده مسابقه شد! 👑")

                win_text = (
                    f"🏆 **پایان مسابقه و اعلام برنده!**\n\n"
                    f"{win_detail}\n\n"
                    f"📊 *این مسابقه پس از `{total_att}` بار تلاش به پایان رسید.*"
                )
                try:
                    bot.send_message(
                        chat_id,
                        win_text,
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass
            else:
                try:
                    bot.send_message(
                        chat_id, 
                        f"❌ تلاش **{user_name}** ناموفق بود!", 
                        reply_to_message_id=dice_msg.message_id, 
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass
            return

        if call.data == "admin_buttons_panel" or call.data.startswith("toggle_btn_") or call.data == "toggle_games_enabled":
            if user_id != OWNER_ID:
                bot.answer_callback_query(call.id, "⛔️ دسترسی غیرمجاز!", show_alert=True)
                return
            
            with state_lock:
                if call.data == "toggle_games_enabled":
                    bot_settings["games_enabled"] = not bot_settings.get("games_enabled", True)
                    save_bot_settings(bot_settings)
                    bot.answer_callback_query(call.id, "✅ تغییر کرد!")
                elif call.data.startswith("toggle_btn_"):
                    btn_type = call.data.replace("toggle_btn_", "")
                    ctrl = bot_settings.get("buttons_control", {})
                    key_map = {
                        "game": "game_button",
                        "member": "member_button",
                        "sub": "sub_button",
                        "ref": "referral_button",
                        "support": "support_button"
                    }
                    target_key = key_map.get(btn_type)
                    if target_key:
                        ctrl[target_key] = not ctrl.get(target_key, True)
                        bot_settings["buttons_control"] = ctrl
                        save_bot_settings(bot_settings)
                        bot.answer_callback_query(call.id, "✅ آپدیت شد!")
                    
            try:
                bot.edit_message_text(
                    "⚙️ **مدیریت دسترسی و نمایانی دکمه‌های اصلی:**\n\nاز این قسمت می‌توانید نمایش یا عدم نمایش دکمه‌های مختلف را برای کاربران کنترل کنید.",
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=get_admin_buttons_control_markup(),
                    parse_mode="Markdown"
                )
            except Exception:
                pass
            return

        if call.data == "menu_support":
            bot.answer_callback_query(call.id)
            with state_lock:
                user_states[user_id] = {"state": "waiting_for_user_ticket"}
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 انصراف و بازگشت", callback_data="back_to_main"))
            bot.edit_message_text(
                "📩 **ارسال تیکت به پشتیبانی:**\n\nپیام، سوال یا مشکل خود را به همراه توضیحات کامل ارسال کنید تا توسط تیم پشتیبانی بررسی و پاسخ داده شود.",
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=markup,
                parse_mode="Markdown"
            )
            return

        if call.data.startswith("reply_ticket_"):
            if user_id != OWNER_ID:
                return
            ticket_id = int(call.data.split("_")[2])
            with state_lock:
                user_states[OWNER_ID] = {"state": "admin_replying_ticket", "ticket_id": ticket_id}
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 انصراف و بازگشت", callback_data="back_to_main"))
            bot.send_message(OWNER_ID, f"✍️ لطفاً پاسخ خود را برای تیکت شماره #{ticket_id} وارد کنید:", reply_markup=markup, parse_mode="Markdown")
            bot.answer_callback_query(call.id)
            return

        if call.data == "admin_add_sub":
            if user_id != OWNER_ID:
                bot.answer_callback_query(call.id, "⛔️ دسترسی غیرمجاز!", show_alert=True)
                return
            with state_lock:
                user_states[user_id] = {"state": "admin_waiting_for_sub_userinput"}
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 انصراف و بازگشت", callback_data="back_to_main"))
            bot.edit_message_text(
                "➕ **اعطای اشتراک دستی مدیریت:**\n\nلطفاً آیدی عددی یا یوزرنیم کاربر مورد نظر را بفرستید:",
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=markup,
                parse_mode="Markdown"
            )
            bot.answer_callback_query(call.id)
            return

        if call.data == "check_join":
            if check_membership(user_id):
                bot.answer_callback_query(call.id, "✅ عضویت شما تایید شد!")
                first_name = call.from_user.first_name or "بدون نام"
                username = call.from_user.username
                with state_lock:
                    if user_id not in registered_users:
                        registered_users[user_id] = {"name": first_name, "username": username, "wallet_balance": 0}
                        save_registered_users()
                        update_owner_dashboard()
                    else:
                        registered_users[user_id].setdefault("wallet_balance", 0)
                increment_order_counters_for_user(user_id)
                
                menu_text = "🤖 **عضویت تایید شد. خوش آمدید!**\n\nاکنون می‌توانید از تمام امکانات منوی اصلی استفاده نمایید:"
                bot.edit_message_text(menu_text, chat_id=chat_id, message_id=message_id, reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")
            else:
                bot.answer_callback_query(call.id, "❌ هنوز در تمام کانال‌ها عضو نشده‌اید!", show_alert=True)
            return

        if call.data == "refresh_dashboard":
            if user_id != OWNER_ID:
                return
            owner_dashboard_msg_id = message_id
            save_dashboard_msg_id(owner_dashboard_msg_id)
            try:
                bot.edit_message_text(get_users_list_text(), chat_id=OWNER_ID, message_id=message_id, reply_markup=get_owner_dashboard_keyboard(), parse_mode="Markdown")
            except Exception:
                pass
            bot.answer_callback_query(call.id, "✅ اطلاعات به روز شد.")
            return

        if call.data == "global_stats":
            if user_id != OWNER_ID:
                return
            bot.answer_callback_query(call.id)
            
            total_users = len(registered_users)
            active_subs = sum(1 for uid in sub_config["subscribers"] if has_active_subscription(uid))
            total_groups = len(registered_groups)
            active_ord_count = len([o for o in active_orders if o.get("is_active", True)])
            pending_rewards = len(reward_requests)
            total_tickets = len(tickets_data)

            stats_text = (
                f"📊 **آمار جامع و کلی سیستم ربات:**\n\n"
                f"👥 کل کاربران ثبت‌شده: `{total_users}` نفر\n"
                f"💎 کاربران دارای اشتراک فعال: `{active_subs}` نفر\n"
                f"🌐 گروه‌های ثبت‌شده: `{total_groups}` گروه\n"
                f"📦 سفارشات ممبر فعال: `{active_ord_count}` کانال\n"
                f"⭐️ درخواست‌های استارز: `{pending_rewards}` مورد\n"
                f"📩 کل تیکت‌های پشتیبانی: `{total_tickets}` عدد"
            )

            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.add(
                types.InlineKeyboardButton("📢 پیام همگانی", callback_data="admin_broadcast"),
                types.InlineKeyboardButton("🔍 بررسی کاربر", callback_data="admin_lookup_user")
            )
            markup.add(types.InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main"))
            bot.edit_message_text(stats_text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")
            return

        if call.data == "admin_broadcast":
            if user_id != OWNER_ID:
                return
            with state_lock:
                user_states[user_id] = {"state": "admin_waiting_for_broadcast_msg"}
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 انصراف و بازگشت", callback_data="global_stats"))
            bot.edit_message_text("📢 **ارسال پیام همگانی به تمام کاربران:**\n\nپیام متنی یا رسانه‌ای خود را جهت ارسال عمومی بفرستید:", chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")
            bot.answer_callback_query(call.id)
            return

        if call.data == "admin_lookup_user":
            if user_id != OWNER_ID:
                return
            with state_lock:
                user_states[user_id] = {"state": "admin_waiting_for_lookup_id"}
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 انصراف و بازگشت", callback_data="global_stats"))
            bot.edit_message_text("🔍 **جستجو و بررسی مشخصات کاربر:**\n\nلطفاً آیدی عددی کاربر مورد نظر را بفرستید:", chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")
            bot.answer_callback_query(call.id)
            return

        if call.data == "menu_referral":
            bot.answer_callback_query(call.id)
            req_cnt = max(1, int(referral_data.get("required_count", 10) or 10))
            
            if user_id == OWNER_ID:
                reward_text = f"⭐️ **پنل مدیریت جایزه استارز (حد نصاب: {req_cnt} دعوت):**\n\n"
                markup = types.InlineKeyboardMarkup(row_width=2)
                if not reward_requests:
                    reward_text += "هیچ درخواستی در حال حاضر ثبت نشده است."
                else:
                    for idx, req in enumerate(reward_requests):
                        u_info = registered_users.get(req['user_id'], {})
                        u_name = u_info.get("name", "کاربر")
                        reward_text += f"{idx+1}. [{u_name}](tg://user?id={req['user_id']}) — `{req['link']}`\n"
                        req_id = req.get("request_id", idx)
                        markup.add(
                            types.InlineKeyboardButton(f"✅ تایید {idx+1}", callback_data=f"approve_stars_{req_id}"),
                            types.InlineKeyboardButton(f"❌ رد {idx+1}", callback_data=f"reject_stars_{req_id}")
                        )
                markup.add(
                    types.InlineKeyboardButton("✏️ تغییر تعداد لازم", callback_data="set_req_referral"),
                    types.InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_to_main")
                )
                bot.edit_message_text(reward_text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")
                return

            bot_info = bot.get_me()
            ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
            total_invites = referral_data["invites"].get(str(user_id), 0)
            current_cycle_invites = total_invites % req_cnt
            needed = max(0, req_cnt - current_cycle_invites)

            percent = int((current_cycle_invites / req_cnt) * 100) if req_cnt > 0 else 0
            bar_len = 10
            filled = int((percent / 100) * bar_len)
            bar_str = "⭐" * filled + "⚪️" * (bar_len - filled)

            ref_text = (
                f"🚀 **كسب استارز رایگان تلگرام!** ⭐️\n\n"
                f"با بنر و لینک زیر دوستان خود را دعوت کنید و با رسیدن به سقف تعیین‌شده، ۱ استارز رایگان دریافت کنید.\n\n"
                f"👥 دعوت‌شده‌های فعلی: `{current_cycle_invites}` از `{req_cnt}` نفر\n"
                f"🎯 تعداد مانده: `{needed}` نفر\n"
                f"[{bar_str}] — {percent}%\n\n"
                f"🔗 **لینک دعوت اختصاصی شما:**\n`{ref_link}`"
            )
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main"))
            bot.edit_message_text(ref_text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")
            return

        if call.data.startswith("approve_stars_"):
            if user_id != OWNER_ID:
                return
            request_key = int(call.data.split("_")[2])
            with state_lock:
                idx = next((i for i, item in enumerate(reward_requests) if isinstance(item, dict) and item.get("request_id") == request_key), -1)
                if idx < 0 and 0 <= request_key < len(reward_requests):
                    idx = request_key
                if 0 <= idx < len(reward_requests):
                    req = reward_requests.pop(idx)
                    save_reward_requests(reward_requests)
            bot.answer_callback_query(call.id, "✅ تایید شد.")
            try:
                bot.send_message(req["user_id"], f"🎉 **درخواست استارز شما تایید و واریز شد:**\n`{req['link']}`", parse_mode="Markdown")
            except Exception:
                pass
            try:
                bot.edit_message_text("⭐️ **پنل مدیریت جایزه استارز**", chat_id=chat_id, message_id=message_id, reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")
            except Exception:
                pass
            return

        if call.data.startswith("reject_stars_"):
            if user_id != OWNER_ID:
                return
            request_key = int(call.data.split("_")[2])
            with state_lock:
                idx = next((i for i, item in enumerate(reward_requests) if isinstance(item, dict) and item.get("request_id") == request_key), -1)
                if idx < 0 and 0 <= request_key < len(reward_requests):
                    idx = request_key
                if 0 <= idx < len(reward_requests):
                    req = reward_requests.pop(idx)
                    save_reward_requests(reward_requests)
            bot.answer_callback_query(call.id, "❌ رد شد.")
            try:
                bot.send_message(req["user_id"], f"❌ درخواست استارز شما برای `{req['link']}` رد شد.", parse_mode="Markdown")
            except Exception:
                pass
            try:
                bot.edit_message_text("⭐️ **پنل مدیریت جایزه استارز**", chat_id=chat_id, message_id=message_id, reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")
            except Exception:
                pass
            return

        if call.data == "menu_member":
            bot.answer_callback_query(call.id)
            if user_id == OWNER_ID:
                markup = types.InlineKeyboardMarkup(row_width=2)
                markup.add(
                    types.InlineKeyboardButton("✏️ ویرایش متن", callback_data="edit_rules"),
                    types.InlineKeyboardButton("🗑 پاکسازی متن", callback_data="clear_rules"),
                    types.InlineKeyboardButton("📦 مدیریت بسته‌ها", callback_data="admin_manage_pkgs"),
                    types.InlineKeyboardButton("⚙️ سفارشات فعال", callback_data="manage_order")
                )
                markup.add(types.InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_to_main"))
                bot.edit_message_text("👥 **مدیریت بخش ممبرگیری:**\n\nاز این بخش می‌توانید قوانین، بسته‌ها و سفارشات فعال را ویرایش و پیگیری کنید.", chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")
                return

            rules_text = load_member_rules()
            markup = types.InlineKeyboardMarkup(row_width=1)
            for pkg in member_packages:
                btn_text = f"🔹 بسته {pkg['count']} ممبر — {pkg['price']}"
                markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"buy_pkg_{pkg['id']}"))
            markup.add(types.InlineKeyboardButton("📊 وضعیت سفارشات من", callback_data="user_member_status"))
            markup.add(types.InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main"))
            
            display_text = rules_text if rules_text and rules_text.strip() else (
                "📦 **بسته‌های ویژه افزایش ممبر:**\n\nجهت ثبت سفارش، یکی از بسته‌های زیر را انتخاب نمایید:"
            )
            bot.edit_message_text(display_text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")
            return

        if call.data == "clear_rules":
            if user_id != OWNER_ID:
                return
            save_member_rules("")
            bot.answer_callback_query(call.id, "✅ پاک شد.")
            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.add(
                types.InlineKeyboardButton("✏️ ویرایش متن", callback_data="edit_rules"),
                types.InlineKeyboardButton("🗑 پاکسازی متن", callback_data="clear_rules"),
                types.InlineKeyboardButton("📦 مدیریت بسته‌ها", callback_data="admin_manage_pkgs"),
                types.InlineKeyboardButton("⚙️ سفارشات فعال", callback_data="manage_order")
            )
            markup.add(types.InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_to_main"))
            bot.edit_message_text("👥 **مدیریت بخش ممبرگیری:**", chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")
            return

        if call.data == "admin_manage_pkgs":
            if user_id != OWNER_ID:
                return
            pkgs_text = "📦 **لیست کامل بسته‌های ممبرگیری:**\n\n"
            markup = types.InlineKeyboardMarkup(row_width=2)
            for pkg in member_packages:
                pkgs_text += f"🔹 تعداد: `{pkg['count']}` ممبر — قیمت: `{pkg['price']}`\n"
                markup.add(
                    types.InlineKeyboardButton(f"✏️ ویرایش {pkg['count']}", callback_data=f"edit_pkg_{pkg['id']}"),
                    types.InlineKeyboardButton(f"❌ حذف {pkg['count']}", callback_data=f"del_pkg_{pkg['id']}")
                )
            
            markup.add(
                types.InlineKeyboardButton("➕ افزودن بسته جدید", callback_data="add_new_pkg"),
                types.InlineKeyboardButton("🔙 بازگشت به منوی ممبرگیری", callback_data="menu_member")
            )
            bot.edit_message_text(pkgs_text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")
            bot.answer_callback_query(call.id)
            return

        if call.data.startswith("edit_pkg_"):
            if user_id != OWNER_ID:
                return
            pkg_id = int(call.data.split("_")[2])
            with state_lock:
                user_states[user_id] = {"state": "waiting_for_edit_pkg_input", "pkg_id": pkg_id}
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 انصراف و بازگشت", callback_data="admin_manage_pkgs"))
            bot.edit_message_text("✏️ **ویرایش بسته ممبرگیری:**\n\nفرمت: `تعداد, مبلغ_عددی, متن_نمایشی`\nمثال:\n`500, 150000, ۱۵۰,۰۰۰ تومان`", chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")
            bot.answer_callback_query(call.id)
            return

        if call.data.startswith("del_pkg_"):
            if user_id != OWNER_ID:
                return
            pkg_id = int(call.data.split("_")[2])
            with state_lock:
                member_packages = [p for p in member_packages if p["id"] != pkg_id]
                save_member_packages(member_packages)
            bot.answer_callback_query(call.id, "✅ حذف شد.")
            
            pkgs_text = "📦 **لیست کامل بسته‌های ممبرگیری:**\n\n"
            markup = types.InlineKeyboardMarkup(row_width=2)
            for pkg in member_packages:
                pkgs_text += f"🔹 تعداد: `{pkg['count']}` ممبر — قیمت: `{pkg['price']}`\n"
                markup.add(
                    types.InlineKeyboardButton(f"✏️ ویرایش {pkg['count']}", callback_data=f"edit_pkg_{pkg['id']}"),
                    types.InlineKeyboardButton(f"❌ حذف {pkg['count']}", callback_data=f"del_pkg_{pkg['id']}")
                )
            markup.add(
                types.InlineKeyboardButton("➕ افزودن بسته جدید", callback_data="add_new_pkg"),
                types.InlineKeyboardButton("🔙 بازگشت به منوی ممبرگیری", callback_data="menu_member")
            )
            bot.edit_message_text(pkgs_text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")
            return

        if call.data == "add_new_pkg":
            if user_id != OWNER_ID:
                return
            with state_lock:
                user_states[user_id] = {"state": "waiting_for_new_pkg_input"}
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 انصراف و بازگشت", callback_data="admin_manage_pkgs"))
            bot.edit_message_text("➕ **افزودن بسته ممبرگیری جدید:**\n\nفرمت ارسال: `تعداد, مبلغ_عددی, متن_نمایشی`\nمثال:\n`2000, 500000, ۵۰۰,۰۰۰ تومان`", chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")
            bot.answer_callback_query(call.id)
            return

        if call.data.startswith("buy_pkg_"):
            pkg_id = int(call.data.split("_")[2])
            selected_pkg = next((p for p in member_packages if p["id"] == pkg_id), None)
            if not selected_pkg:
                bot.answer_callback_query(call.id, "❌ بسته یافت نشد!", show_alert=True)
                return

            with state_lock:
                user_states[user_id] = {"state": "waiting_for_payment_receipt", "pkg": selected_pkg}
            
            u_info = registered_users.get(user_id, {"wallet_balance": 0})
            balance = u_info.get("wallet_balance", 0)
            
            markup = types.InlineKeyboardMarkup(row_width=1)
            if balance >= selected_pkg.get("price_num", 0):
                markup.add(types.InlineKeyboardButton(f"⚡️ پرداخت آنی از کیف پول ({balance:,} تومان)", callback_data=f"wallet_buy_pkg_{pkg_id}"))
            markup.add(types.InlineKeyboardButton("🔙 انصراف و بازگشت", callback_data="menu_member"))
            
            pay_msg = (
                f"🎯 **مشخصات بسته انتخابی:**\n"
                f"📦 تعداد ممبر: `{selected_pkg['count']}` نفر\n"
                f"💰 مبلغ فاکتور: `{selected_pkg['price']}`\n\n"
                f"💳 **اطلاعات کارت جهت واریز:**\n`{CARD_NUMBER}`\nبه نام: {CARD_NAME}\n\n"
                f"📌 *می‌توانید پرداخت را مستقیماً از کیف‌پول انجام دهید یا عکس فیش واریزی را بفرستید:*"
            )
            bot.edit_message_text(pay_msg, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")
            bot.answer_callback_query(call.id)
            return

        if call.data.startswith("approve_pay_"):
            if user_id != OWNER_ID:
                return
            parts = call.data.split("_")
            target_user_id = int(parts[2])
            target_count = int(parts[3])

            with state_lock:
                user_states[target_user_id] = {"state": "waiting_for_channel_link", "count": target_count}
            bot.answer_callback_query(call.id, "✅ واریزی تایید شد.")
            
            try:
                bot.edit_message_caption(caption=call.message.caption + "\n\n✅ **پرداخت تایید شد.**", chat_id=chat_id, message_id=message_id, parse_mode="Markdown")
            except Exception:
                pass

            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 انصراف و بازگشت", callback_data="back_to_main"))
            bot.send_message(
                target_user_id,
                f"🎉 **پرداخت و فیش شما تایید شد!**\n\nتعداد: `{target_count}` ممبر\n\n🔗 لطفاً آیدی یا لینک عمومی کانال خود را ارسال کنید (مثال: `@channel`):",
                reply_markup=markup,
                parse_mode="Markdown"
            )
            return

        if call.data.startswith("reject_pay_"):
            if user_id != OWNER_ID:
                return
            try:
                target_user_id = int(call.data.split("_")[2])
            except Exception:
                target_user_id = 0

            with state_lock:
                user_states[OWNER_ID] = {"state": "admin_rejecting_pay", "target_id": target_user_id}
            
            try:
                bot.edit_message_caption(caption=call.message.caption + "\n\n❌ **فیش واریزی رد شد.**", chat_id=chat_id, message_id=message_id, parse_mode="Markdown")
            except Exception:
                pass

            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 انصراف و بازگشت", callback_data="manage_order"))
            bot.send_message(OWNER_ID, "✍️ لطفاً علت رد فیش را بفرستید:", reply_markup=markup)
            bot.answer_callback_query(call.id)
            return

        if call.data == "user_member_status":
            user_orders = [o for o in active_orders if o.get("user_id") == user_id]
            if not user_orders:
                bot.answer_callback_query(call.id, "ℹ️ شما در حال حاضر هیچ سفارش فعالی ندارید.", show_alert=True)
                return

            status_text = "📊 **گزارش لحظه‌ای سفارشات ممبرگیری شما:**\n\n"
            for idx, ord_item in enumerate(user_orders, 1):
                curr = ord_item.get("current_count", 0)
                target = ord_item.get("target_count", 100)
                percent = int((curr / target) * 100) if target > 0 else 0
                
                bar_len = 10
                filled = int((percent / 100) * bar_len)
                bar_str = "🟩" * filled + "⬜️" * (bar_len - filled)

                status_text += (
                    f"{idx}. کانال: `{ord_item['link']}`\n"
                    f"📈 میزان پیشرفت: [{curr}/{target}] ممبر — {percent}%\n"
                    f"[{bar_str}]\n\n"
                )

            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 بازگشت به منوی قبلی", callback_data="menu_member"))
            bot.edit_message_text(status_text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")
            bot.answer_callback_query(call.id)
            return

        if call.data == "manage_order":
            if user_id != OWNER_ID:
                return
            orders_text, markup = get_manage_orders_view()
            bot.edit_message_text(orders_text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")
            bot.answer_callback_query(call.id)
            return

        if call.data.startswith("cancel_ord_"):
            if user_id != OWNER_ID:
                return
            ord_idx = int(call.data.split("_")[2])
            with state_lock:
                if 0 <= ord_idx < len(active_orders):
                    removed = active_orders.pop(ord_idx)
                    save_active_orders(active_orders)
            bot.answer_callback_query(call.id, f"✅ سفارش {removed['link']} لغو شد.")
            try:
                bot.send_message(removed.get("user_id"), f"🔴 سفارش ممبرگیری کانال `{removed['link']}` متوقف شد.", parse_mode="Markdown")
            except Exception:
                pass
            orders_text, orders_markup = get_manage_orders_view()
            bot.edit_message_text(orders_text, chat_id=chat_id, message_id=message_id, reply_markup=orders_markup, parse_mode="Markdown")
            return

        if call.data == "set_order_link":
            if user_id != OWNER_ID:
                return
            with state_lock:
                user_states[user_id] = {"state": "owner_setting_order_link"}
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 انصراف و بازگشت", callback_data="manage_order"))
            bot.edit_message_text("➕ **افزودن سفارش دستی کانال:**\n\nفرمت: `@channel, تعداد`\nمثال:\n`@mychannel, 500`", chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")
            bot.answer_callback_query(call.id)
            return

        if call.data == "clear_orders":
            if user_id != OWNER_ID:
                return
            with state_lock:
                active_orders.clear()
                save_active_orders(active_orders)
            bot.answer_callback_query(call.id, "🗑 کلیه سفارشات پاکسازی شدند.")
            orders_text, orders_markup = get_manage_orders_view()
            bot.edit_message_text(orders_text, chat_id=chat_id, message_id=message_id, reply_markup=orders_markup, parse_mode="Markdown")
            return

        if call.data == "edit_rules":
            if user_id != OWNER_ID:
                return
            with state_lock:
                user_states[user_id] = {"state": "edit_rules_state"}
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 انصراف و بازگشت", callback_data="menu_member"))
            bot.edit_message_text("✏️ **ویرایش متن بخش ممبرگیری:**\n\nمتن راهنما و قوانین جدید را بفرستید:", chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")
            bot.answer_callback_query(call.id)
            return

        if call.data == "set_req_referral":
            if user_id != OWNER_ID:
                return
            with state_lock:
                user_states[user_id] = {"state": "waiting_for_req_referral_count"}
            req_cnt = max(1, int(referral_data.get("required_count", 10) or 10))
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 بازگشت به منوی استارز", callback_data="menu_referral"))
            bot.send_message(
                chat_id,
                f"✏️ **تنظیم تعداد زیرمجموعه لازم جهت پاداش:**\nتعداد فعلی: `{req_cnt}` نفر\n\nعدد جدید را ارسال کنید:",
                reply_markup=markup,
                parse_mode="Markdown"
            )
            bot.answer_callback_query(call.id)
            return

        if call.data == "menu_subscription":
            bot.answer_callback_query(call.id)
            if user_id == OWNER_ID:
                markup = types.InlineKeyboardMarkup(row_width=2)
                markup.add(
                    types.InlineKeyboardButton("✏️ ویرایش متن", callback_data="edit_sub_rules"),
                    types.InlineKeyboardButton("🗑 پاکسازی متن", callback_data="clear_sub_rules"),
                    types.InlineKeyboardButton("📦 مدیریت بسته‌ها", callback_data="admin_manage_sub_pkgs")
                )
                markup.add(types.InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_to_main"))
                bot.edit_message_text("💎 **مدیریت بخش اشتراک‌ها:**\n\nاز این بخش می‌توانید متون و پلن‌های اشتراک را ویرایش کنید.", chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")
                return

            sub_rules = sub_config.get("rules", "")
            has_sub = has_active_subscription(user_id)
            status_str = "\n\n🟢 **وضعیت حساب شما: اشتراک فعال می باشد.**" if has_sub else "\n\n🔴 **وضعیت حساب شما: فاقد اشتراک فعال.**"
            
            markup = types.InlineKeyboardMarkup(row_width=1)
            for pkg in subscription_packages:
                btn_text = f"💎 {pkg['title']} ({pkg['days']} روزه) — {pkg['price']}"
                markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"buy_sub_pkg_{pkg['id']}"))
            markup.add(types.InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main"))

            display_text = sub_rules if sub_rules and sub_rules.strip() else (
                "💎 **بسته‌های ویژه اشتراک ربات:**\n\nجهت استفاده از ابزار فوروارد خودکار، یکی از پلن‌های زیر را انتخاب کنید:"
            )
            bot.edit_message_text(display_text + status_str, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")
            return

        if call.data == "clear_sub_rules":
            if user_id != OWNER_ID:
                return
            with state_lock:
                sub_config["rules"] = ""
                save_subscription_config(sub_config)
            bot.answer_callback_query(call.id, "✅ پاک شد.")
            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.add(
                types.InlineKeyboardButton("✏️ ویرایش متن", callback_data="edit_sub_rules"),
                types.InlineKeyboardButton("🗑 پاکسازی متن", callback_data="clear_sub_rules"),
                types.InlineKeyboardButton("📦 مدیریت بسته‌ها", callback_data="admin_manage_sub_pkgs")
            )
            markup.add(types.InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_to_main"))
            bot.edit_message_text("💎 **مدیریت اشتراک:**", chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")
            return

        if call.data == "admin_manage_sub_pkgs":
            if user_id != OWNER_ID:
                return
            sub_pkgs_text = "📦 **لیست بسته‌های اشتراک ربات:**\n\n"
            markup = types.InlineKeyboardMarkup(row_width=2)
            for pkg in subscription_packages:
                sub_pkgs_text += f"🔹 {pkg['title']} (`{pkg['days']} روزه`) — قیمت: `{pkg['price']}`\n"
                markup.add(
                    types.InlineKeyboardButton(f"✏️ ویرایش {pkg['days']} روزه", callback_data=f"edit_sub_pkg_{pkg['id']}"),
                    types.InlineKeyboardButton(f"❌ حذف {pkg['days']} روزه", callback_data=f"del_sub_pkg_{pkg['id']}")
                )
            
            markup.add(
                types.InlineKeyboardButton("➕ افزودن بسته جدید", callback_data="add_new_sub_pkg"),
                types.InlineKeyboardButton("🔙 بازگشت به منوی اشتراک", callback_data="menu_subscription")
            )
            bot.edit_message_text(sub_pkgs_text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")
            bot.answer_callback_query(call.id)
            return

        if call.data.startswith("edit_sub_pkg_"):
            if user_id != OWNER_ID:
                return
            pkg_id = int(call.data.split("_")[3])
            with state_lock:
                user_states[user_id] = {"state": "waiting_for_edit_sub_pkg_input", "pkg_id": pkg_id}
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 انصراف و بازگشت", callback_data="admin_manage_sub_pkgs"))
            bot.edit_message_text("✏️ **ویرایش بسته اشتراک:**\n\nفرمت: `عنوان, روز, مبلغ_عددی, متن_نمایشی`\nمثال:\n`اشتراک ۱ ماهه, 30, 100000, ۱۰۰,۰۰۰ تومان`", chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")
            bot.answer_callback_query(call.id)
            return

        if call.data.startswith("del_sub_pkg_"):
            if user_id != OWNER_ID:
                return
            pkg_id = int(call.data.split("_")[3])
            with state_lock:
                subscription_packages = [p for p in subscription_packages if p["id"] != pkg_id]
                save_subscription_packages(subscription_packages)
            bot.answer_callback_query(call.id, "✅ حذف شد.")
            
            sub_pkgs_text = "📦 **لیست بسته‌های اشتراک ربات:**\n\n"
            markup = types.InlineKeyboardMarkup(row_width=2)
            for pkg in subscription_packages:
                sub_pkgs_text += f"🔹 {pkg['title']} (`{pkg['days']} روزه`) — قیمت: `{pkg['price']}`\n"
                markup.add(
                    types.InlineKeyboardButton(f"✏️ ویرایش {pkg['days']} روزه", callback_data=f"edit_sub_pkg_{pkg['id']}"),
                    types.InlineKeyboardButton(f"❌ حذف {pkg['days']} روزه", callback_data=f"del_sub_pkg_{pkg['id']}")
                )
            markup.add(
                types.InlineKeyboardButton("➕ افزودن بسته جدید", callback_data="add_new_sub_pkg"),
                types.InlineKeyboardButton("🔙 بازگشت به منوی اشتراک", callback_data="menu_subscription")
            )
            bot.edit_message_text(sub_pkgs_text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")
            return

        if call.data == "add_new_sub_pkg":
            if user_id != OWNER_ID:
                return
            with state_lock:
                user_states[user_id] = {"state": "waiting_for_new_sub_pkg_input"}
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 انصراف و بازگشت", callback_data="admin_manage_sub_pkgs"))
            bot.edit_message_text("➕ **افزودن بسته اشتراک جدید:**\n\nفرمت: `عنوان, روز, مبلغ_عددی, متن_نمایشی`\nمثال:\n`اشتراک ۶ ماهه, 180, 500000, ۵۰۰,۰۰۰ تومان`", chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")
            bot.answer_callback_query(call.id)
            return

        if call.data.startswith("buy_sub_pkg_"):
            pkg_id = int(call.data.split("_")[3])
            selected_pkg = next((p for p in subscription_packages if p["id"] == pkg_id), None)
            if not selected_pkg:
                bot.answer_callback_query(call.id, "❌ بسته یافت نشد!", show_alert=True)
                return

            with state_lock:
                user_states[user_id] = {"state": "waiting_for_sub_receipt", "pkg": selected_pkg}
            
            u_info = registered_users.get(user_id, {"wallet_balance": 0})
            balance = u_info.get("wallet_balance", 0)
            
            markup = types.InlineKeyboardMarkup(row_width=1)
            if balance >= selected_pkg.get("price_num", 0):
                markup.add(types.InlineKeyboardButton(f"⚡️ پرداخت آنی از کیف پول ({balance:,} تومان)", callback_data=f"wallet_buy_sub_{pkg_id}"))
            markup.add(types.InlineKeyboardButton("🔙 انصراف و بازگشت", callback_data="menu_subscription"))
            
            pay_msg = (
                f"💎 **پلن انتخابی:** {selected_pkg['title']} (`{selected_pkg['days']} روزه`)\n"
                f"💰 مبلغ: `{selected_pkg['price']}`\n\n"
                f"💳 **اطلاعات کارت جهت واریز:**\n`{CARD_NUMBER}`\nبه نام: {CARD_NAME}\n\n"
                f"📌 *پرداخت از کیف پول یا ارسال عکس فیش واریزی:*"
            )
            bot.edit_message_text(pay_msg, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")
            bot.answer_callback_query(call.id)
            return

        if call.data.startswith("approve_sub_"):
            if user_id != OWNER_ID:
                return
            parts = call.data.split("_")
            target_user_id = int(parts[2])
            days_count = int(parts[3])
            
            grant_subscription(target_user_id, days_count)
            bot.answer_callback_query(call.id, f"✅ اشتراک {days_count} روزه فعال شد.", show_alert=True)
            try:
                bot.edit_message_caption(caption=call.message.caption + f"\n\n✅ **اشتراک {days_count} روزه فعال شد.**", chat_id=chat_id, message_id=message_id, parse_mode="Markdown")
            except Exception:
                pass
            try:
                bot.send_message(target_user_id, f"🎉 **اشتراک `{days_count}` روزه شما فعال شد!**", reply_markup=get_main_keyboard(target_user_id), parse_mode="Markdown")
            except Exception:
                pass
            return

        if call.data == "edit_sub_rules":
            if user_id != OWNER_ID:
                return
            with state_lock:
                user_states[user_id] = {"state": "edit_sub_rules_state"}
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 انصراف و بازگشت", callback_data="menu_subscription"))
            bot.edit_message_text("✏️ **ویرایش متن بخش اشتراک:**\n\nمتن جدید راهنما را ارسال بفرمایید:", chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")
            bot.answer_callback_query(call.id)
            return

        cfg = get_user_config(user_id)

        if call.data == "menu_forward":
            if user_id != OWNER_ID and not has_active_subscription(user_id):
                bot.answer_callback_query(call.id, "❌ استفاده از این بخش نیاز به اشتراک فعال دارد!", show_alert=True)
                return
            forward_header = (
                "⚙️ **پنل مدیریت تنظیمات فوروارد خودکار:**\n\n"
                "از دکمه‌های زیر جهت تنظیم مقصد، مبدا، زمان‌بندی و فعال‌سازی ارسال پیام‌ها استفاده کنید."
            )
            bot.edit_message_text(forward_header, chat_id=chat_id, message_id=message_id, reply_markup=get_forward_keyboard(user_id), parse_mode="Markdown")

        elif call.data == "back_to_main":
            with state_lock:
                user_states[user_id] = None
            menu_text = (
                "🤖 **پنل مدیریت ارشد مالکان ربات**\n\n"
                "به منوی اصلی خوش آمدید."
                if user_id == OWNER_ID 
                else 
                "🤖 **به منوی اصلی خوش آمدید.**\n\nجهت استفاده، بخش مورد نظر را انتخاب کنید:"
            )
            bot.edit_message_text(menu_text, chat_id=chat_id, message_id=message_id, reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")

        elif call.data == "toggle_run":
            if not cfg.get("destination"):
                bot.answer_callback_query(call.id, "ابتدا کانال مقصد را تنظیم کنید.", show_alert=True)
                return
            if cfg.get("mode") == "forward" and (not cfg.get("from_chat_id") or not cfg.get("start_message_id")):
                bot.answer_callback_query(call.id, "ابتدا کانال مبدا و پست‌ها را تنظیم کنید.", show_alert=True)
                return
            if cfg.get("mode") == "text" and not cfg.get("message"):
                bot.answer_callback_query(call.id, "ابتدا متن دلخواه را تنظیم کنید.", show_alert=True)
                return
            with state_lock:
                cfg["is_running"] = not cfg["is_running"]
                save_user_configs()
            bot.answer_callback_query(call.id, "وضعیت تغییر کرد.")
            forward_header = "⚙️ **پنل مدیریت تنظیمات فوروارد خودکار:**"
            bot.edit_message_text(forward_header, chat_id=chat_id, message_id=message_id, reply_markup=get_forward_keyboard(user_id), parse_mode="Markdown")

        elif call.data == "set_dest":
            with state_lock:
                user_states[user_id] = {"state": "dest", "msg_id": message_id}
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 انصراف و بازگشت", callback_data="menu_forward"))
            bot.edit_message_text("🎯 **تنظیم کانال مقصد:**\n\nآیدی عمومی کانال مقصد را ارسال کنید (`@channel`):", chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")

        elif call.data == "toggle_mode":
            with state_lock:
                cfg["mode"] = "text" if cfg["mode"] == "forward" else "forward"
                save_user_configs()
            forward_header = "⚙️ **پنل مدیریت تنظیمات فوروارد خودکار:**"
            bot.edit_message_text(forward_header, chat_id=chat_id, message_id=message_id, reply_markup=get_forward_keyboard(user_id), parse_mode="Markdown")

        elif call.data == "set_forward":
            with state_lock:
                user_states[user_id] = {"state": "forward_source", "msg_id": message_id}
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 انصراف و بازگشت", callback_data="menu_forward"))
            bot.edit_message_text("🔗 **تنظیم کانال مبدا:**\n\nمثال ارسال:\n`@channel/15, 3`", chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")

        elif call.data == "set_text":
            with state_lock:
                user_states[user_id] = {"state": "text", "msg_id": message_id}
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 انصراف و بازگشت", callback_data="menu_forward"))
            bot.edit_message_text("✍️ **تنظیم متن سفارشی:**\n\nمتن مورد نظر برای ارسال خودکار را بفرستید:", chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")

        elif call.data == "change_time":
            with state_lock:
                user_states[user_id] = {"state": "time", "msg_id": message_id}
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 انصراف و بازگشت", callback_data="menu_forward"))
            bot.edit_message_text("⏱ **تنظیم فاصله زمانی ارسال:**\n\nفاصله زمانی بین هر ارسال را به دقیقه وارد کنید:", chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")

        elif call.data == "clear_forward_config":
            with state_lock:
                cfg["destination"] = None
                cfg["from_chat_id"] = None
                cfg["start_message_id"] = None
                cfg["count"] = 1
                cfg["message"] = None
                cfg["is_running"] = False
                cfg["last_sent"] = 0
                save_user_configs()
            bot.answer_callback_query(call.id, "🗑 تنظیمات فوروارد پاکسازی شد.")
            forward_header = "⚙️ **پنل مدیریت تنظیمات فوروارد خودکار:**"
            bot.edit_message_text(forward_header, chat_id=chat_id, message_id=message_id, reply_markup=get_forward_keyboard(user_id), parse_mode="Markdown")

        elif call.data == "show_status":
            status_info = (
                f"📊 **گزارش کامل وضعیت سیستم فوروارد خودکار:**\n\n"
                f"🔹 وضعیت فعالیت: {'🟢 روشن' if cfg['is_running'] else '🔴 متوقف'}\n"
                f"🎯 کانال مقصد: `{cfg['destination'] or 'تنظیم نشده'}`\n"
                f"🔗 کانال مبدا: `{cfg['from_chat_id'] or 'تنظیم نشده'}`\n"
                f"🔢 تعداد پیام‌ها: `{cfg['count']}`\n"
                f"⏱ فاصله زمان: `{cfg['interval_minutes']} دقیقه`\n"
                f"📨 مجموع ارسال‌های موفق: `{cfg['total_sent']}`"
            )
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 بازگشت به منوی قبلی", callback_data="menu_forward"))
            bot.edit_message_text(status_info, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")

    except Exception as ex:
        print(f"خطا در Callback Inline: {ex}")

    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass


@bot.message_handler(
    content_types=["text", "photo", "document", "video"],
    func=lambda message: message.chat.type == "private" and message.from_user.id in user_states and user_states[message.from_user.id] is not None
)
def handle_user_input(message):
    user_id = message.from_user.id
    if not check_membership(user_id):
        return

    with state_lock:
        state_data = user_states.get(user_id)
    chat_id = message.chat.id
    state = state_data.get("state") if isinstance(state_data, dict) else state_data

    if message.text and message.text.startswith("/"):
        with state_lock:
            user_states[user_id] = None
        send_welcome(message)
        return

    if user_id == OWNER_ID and state == "admin_waiting_for_wallet_amount":
        txt_val = message.text.strip() if message.text else ""
        digits = "".join(filter(str.isdigit, txt_val))
        amount = int(digits) if digits and int(digits) > 0 else 0
        
        target_user_id = state_data.get("target_id")
        with state_lock:
            user_states[user_id] = None
            if target_user_id:
                u_info = registered_users.get(target_user_id)
                if u_info:
                    u_info["wallet_balance"] = u_info.get("wallet_balance", 0) + amount
                    save_registered_users()
        
        if target_user_id and amount > 0:
            bot.send_message(chat_id, f"✅ کیف پول کاربر `{target_user_id}` به مبلغ `{amount:,} تومان` شارژ شد.", parse_mode="Markdown")
            try:
                bot.send_message(target_user_id, f"🎉 **کیف پول شما به مبلغ `{amount:,} تومان` توسط مدیریت شارژ شد!**", reply_markup=get_main_keyboard(target_user_id), parse_mode="Markdown")
            except Exception:
                pass
        else:
            bot.send_message(chat_id, "❌ مبلغ وارد شده نامعتبر است.")
        return

    if state == "waiting_for_wallet_receipt":
        with state_lock:
            user_states[user_id] = None
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("✅ تایید و ورود مبلغ", callback_data=f"approve_wallet_{user_id}_0"),
            types.InlineKeyboardButton("❌ رد", callback_data=f"reject_pay_{user_id}")
        )
        
        user_info = registered_users.get(user_id, {"name": message.from_user.first_name, "username": message.from_user.username})
        u_name = escape_markdown(user_info.get("name", "کاربر"))
        u_uname = f"@{user_info.get('username')}" if user_info.get("username") else "بدون آیدی"

        caption_msg = f"💳 **رسید شارژ کیف پول:**\n\n👤 [{u_name}](tg://user?id={user_id}) (`{u_uname}`)\n🆔 آیدی عددی: `{user_id}`"
        
        try:
            if message.photo:
                bot.send_photo(OWNER_ID, message.photo[-1].file_id, caption=caption_msg, reply_markup=markup, parse_mode="Markdown")
            else:
                bot.send_message(OWNER_ID, caption_msg, reply_markup=markup, parse_mode="Markdown")
                bot.forward_message(OWNER_ID, chat_id, message.message_id)
        except Exception as e:
            print(f"خطا در ارسال فیش کیف پول به ادمین: {e}")
        
        bot.send_message(chat_id, "✅ تصویر فیش شارژ کیف پول جهت بررسی به مدیریت ارسال شد.", reply_markup=get_main_keyboard(user_id))
        return

    if state == "waiting_for_exchange_channel_input":
        text_val = message.text.strip() if message.text else ""
        try:
            parts = text_val.split(",")
            if len(parts) == 2:
                raw_ch = parts[0].strip().lstrip("@")
                clean_ch = "@" + raw_ch.lower()
                members_cnt = int(parts[1].strip())
                
                with state_lock:
                    exch_id = int(time.time())
                    exchanges_data.append({
                        "id": exch_id,
                        "user_id": user_id,
                        "channel": clean_ch,
                        "members": members_cnt,
                        "is_active": True
                    })
                    save_exchanges(exchanges_data)
                    user_states[user_id] = None
                
                bot.send_message(chat_id, f"✅ کانال `{clean_ch}` با موفقیت برای تبادل ثبت شد!", reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")
                return
        except Exception:
            pass
        bot.send_message(chat_id, "❌ فرمت اشتباه است. لطفاً مطابق مثال ارسال کنید:\n`@mychannel, 1500`", parse_mode="Markdown")
        return

    if user_id == OWNER_ID and state == "waiting_for_req_referral_count":
        value = message.text.strip() if message.text else ""
        if not value.isdigit() or int(value) < 1 or int(value) > 100000:
            bot.send_message(chat_id, "❌ عددی معتبر بین ۱ تا ۱۰۰۰۰۰ وارد کنید.")
            return
        with state_lock:
            referral_data["required_count"] = int(value)
            save_referrals(referral_data)
            user_states[user_id] = None
        bot.send_message(chat_id, f"✅ حد نصاب دعوت روی `{value}` نفر تنظیم شد.", reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")
        return

    if state == "waiting_for_user_ticket":
        with state_lock:
            ticket_id = max([int(t.get("id", 1000)) for t in tickets_data if isinstance(t, dict)], default=1000) + 1
            new_ticket = {"id": ticket_id, "user_id": user_id, "status": "open"}
            tickets_data.append(new_ticket)
            save_tickets(tickets_data)
            user_states[user_id] = None

        u_info = registered_users.get(user_id, {})
        u_name = u_info.get("name", "کاربر")
        u_uname = f"@{u_info.get('username')}" if u_info.get("username") else "بدون آیدی"

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✍️ پاسخ", callback_data=f"reply_ticket_{ticket_id}"))

        caption_msg = f"📩 **تیکت جدید (#`{ticket_id}`)**\n\n👤 [{u_name}](tg://user?id={user_id}) ({u_uname})\n🆔 `{user_id}`"

        try:
            bot.send_message(OWNER_ID, caption_msg, reply_markup=markup, parse_mode="Markdown")
            bot.copy_message(OWNER_ID, chat_id, message.message_id)
        except Exception:
            pass

        bot.send_message(
            chat_id,
            f"✅ **تیکت شما با موفقیت ثبت شد!** (#`{ticket_id}`)\nبه محض پاسخ مدیریت، اطلاع داده خواهد شد.",
            reply_markup=get_main_keyboard(user_id),
            parse_mode="Markdown"
        )
        return

    if user_id == OWNER_ID and state == "admin_replying_ticket":
        ticket_id = state_data.get("ticket_id")
        target_ticket = next((t for t in tickets_data if t["id"] == ticket_id), None)
        with state_lock:
            user_states[user_id] = None

        if not target_ticket:
            bot.send_message(chat_id, "❌ تیکت یافت نشد.")
            return

        target_uid = target_ticket["user_id"]
        bot.send_message(chat_id, f"✅ پاسخ برای کاربر `{target_uid}` ارسال شد.", parse_mode="Markdown")

        try:
            bot.send_message(target_uid, f"📩 **پاسخ پشتیبانی تیکت `#{ticket_id}`:**", parse_mode="Markdown")
            bot.copy_message(target_uid, chat_id, message.message_id)
        except Exception:
            pass
        return

    if user_id == OWNER_ID and state == "admin_waiting_for_broadcast_msg":
        with state_lock:
            user_states[user_id] = None
        success_count = 0
        failed_count = 0
        
        bot.send_message(chat_id, "📢 در حال ارسال پیام همگانی...")
        
        for uid in list(registered_users.keys()):
            try:
                bot.copy_message(chat_id=uid, from_chat_id=chat_id, message_id=message.message_id)
                success_count += 1
                time.sleep(0.05)
            except Exception:
                failed_count += 1
                
        bot.send_message(
            chat_id,
            f"✅ **فرآیند ارسال همگانی به پایان رسید!**\n\nارسال موفق: `{success_count}` | ناموفق: `{failed_count}`",
            reply_markup=get_main_keyboard(user_id),
            parse_mode="Markdown"
        )
        return

    if user_id == OWNER_ID and state == "admin_waiting_for_lookup_id":
        with state_lock:
            user_states[user_id] = None
        text_val = message.text.strip() if message.text else ""
        
        if not text_val.isdigit():
            bot.send_message(chat_id, "❌ آیدی عددی نامعتبر است.")
            return
            
        target_uid = int(text_val)
        u_info = registered_users.get(target_uid)
        
        if not u_info:
            bot.send_message(chat_id, "❌ کاربر یافت نشد.", reply_markup=get_main_keyboard(user_id))
            return
            
        u_name = u_info.get("name", "بدون نام")
        u_uname = f"@{u_info.get('username')}" if u_info.get("username") else "بدون آیدی"
        has_sub = has_active_subscription(target_uid)
        invites_cnt = referral_data["invites"].get(str(target_uid), 0)
        wallet = u_info.get("wallet_balance", 0)
        
        lookup_info = (
            f"👤 **مشخصات جامع کاربر:**\n\n"
            f"📛 نام: `{u_name}`\n"
            f"🏷 یوزرنیم: `{u_uname}`\n"
            f"🆔 آیدی عددی: `{target_uid}`\n"
            f"💳 موجودی کیف پول: `{wallet:,} تومان`\n"
            f"💎 وضعیت اشتراک: `{'فعال 🟢' if has_sub else 'غیرفعال 🔴'}`\n"
            f"👥 تعداد دعوت‌ها: `{invites_cnt}`"
        )
        bot.send_message(chat_id, lookup_info, reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")
        return

    if state == "waiting_for_reward_post_link":
        post_link = message.text.strip() if message.text else ""
        request_id = int(time.time() * 1000)
        with state_lock:
            reward_requests.append({"request_id": request_id, "user_id": user_id, "link": post_link, "status": "pending"})
            save_reward_requests(reward_requests)
            user_states[user_id] = None
        
        bot.send_message(chat_id, "✅ **لینک پست شما جهت بررسی به مدیریت ارسال شد.**", reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")
        
        u_info = registered_users.get(user_id, {})
        u_name = u_info.get("name", "کاربر")
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("✅ تایید", callback_data=f"approve_stars_{request_id}"),
            types.InlineKeyboardButton("❌ رد", callback_data=f"reject_stars_{request_id}")
        )
        
        try:
            bot.send_message(
                OWNER_ID,
                f"⭐️ **درخواست پاداش استارز:**\n\n👤 [{u_name}](tg://user?id={user_id})\n🔗 `{post_link}`",
                reply_markup=markup,
                parse_mode="Markdown"
            )
        except Exception:
            pass
        return

    if user_id == OWNER_ID and state == "waiting_for_new_pkg_input":
        try:
            parts = message.text.split(",") if message.text else []
            if len(parts) == 3:
                cnt_val = int(parts[0].strip())
                price_num_val = int(parts[1].strip())
                price_val = parts[2].strip()
                with state_lock:
                    new_id = max([p["id"] for p in member_packages], default=0) + 1
                    member_packages.append({"id": new_id, "count": cnt_val, "price_num": price_num_val, "price": price_val})
                    save_member_packages(member_packages)
                    user_states[user_id] = None
                bot.send_message(chat_id, "✅ بسته جدید اضافه شد.", reply_markup=get_main_keyboard(user_id))
                return
        except Exception:
            pass
        bot.send_message(chat_id, "❌ فرمت اشتباه است. مثال:\n`2000, 500000, ۵۰۰,۰۰۰ تومان`", parse_mode="Markdown")
        return

    if user_id == OWNER_ID and state == "waiting_for_edit_pkg_input":
        try:
            pkg_id = state_data.get("pkg_id")
            parts = message.text.split(",") if message.text else []
            if len(parts) == 3:
                cnt_val = int(parts[0].strip())
                price_num_val = int(parts[1].strip())
                price_val = parts[2].strip()
                with state_lock:
                    for pkg in member_packages:
                        if pkg["id"] == pkg_id:
                            pkg["count"] = cnt_val
                            pkg["price_num"] = price_num_val
                            pkg["price"] = price_val
                            break
                    save_member_packages(member_packages)
                    user_states[user_id] = None
                bot.send_message(chat_id, "✅ ویرایش بسته با موفقیت انجام شد.", reply_markup=get_main_keyboard(user_id))
                return
        except Exception:
            pass
        bot.send_message(chat_id, "❌ فرمت اشتباه است. مثال:\n`500, 150000, ۱۵۰,۰۰۰ تومان`", parse_mode="Markdown")
        return

    if user_id == OWNER_ID and state == "waiting_for_new_sub_pkg_input":
        try:
            parts = message.text.split(",") if message.text else []
            if len(parts) == 4:
                title_val = parts[0].strip()
                days_val = int(parts[1].strip())
                price_num_val = int(parts[2].strip())
                price_val = parts[3].strip()
                with state_lock:
                    new_id = max([p["id"] for p in subscription_packages], default=0) + 1
                    subscription_packages.append({"id": new_id, "days": days_val, "price_num": price_num_val, "title": title_val, "price": price_val})
                    save_subscription_packages(subscription_packages)
                    user_states[user_id] = None
                bot.send_message(chat_id, "✅ بسته اشتراک جدید اضافه شد.", reply_markup=get_main_keyboard(user_id))
                return
        except Exception:
            pass
        bot.send_message(chat_id, "❌ فرمت اشتباه است. مثال:\n`اشتراک ۶ ماهه, 180, 500000, ۵۰۰,۰۰۰ تومان`", parse_mode="Markdown")
        return

    if user_id == OWNER_ID and state == "waiting_for_edit_sub_pkg_input":
        try:
            pkg_id = state_data.get("pkg_id")
            parts = message.text.split(",") if message.text else []
            if len(parts) == 4:
                title_val = parts[0].strip()
                days_val = int(parts[1].strip())
                price_num_val = int(parts[2].strip())
                price_val = parts[3].strip()
                with state_lock:
                    for pkg in subscription_packages:
                        if pkg["id"] == pkg_id:
                            pkg["title"] = title_val
                            pkg["days"] = days_val
                            pkg["price_num"] = price_num_val
                            pkg["price"] = price_val
                            break
                    save_subscription_packages(subscription_packages)
                    user_states[user_id] = None
                bot.send_message(chat_id, "✅ ویرایش بسته اشتراک انجام شد.", reply_markup=get_main_keyboard(user_id))
                return
        except Exception:
            pass
        bot.send_message(chat_id, "❌ فرمت اشتباه است. مثال:\n`اشتراک ۱ ماهه, 30, 100000, ۱۰۰,۰۰۰ تومان`", parse_mode="Markdown")
        return

    if user_id == OWNER_ID and state == "admin_rejecting_pay":
        reject_reason = message.text.strip() if message.text else "عدم تایید مشخصات فیش"
        target_uid = state_data.get("target_id")
        with state_lock:
            user_states[user_id] = None
        bot.send_message(chat_id, "✅ علت رد فیش ارسال گردید.")
        try:
            bot.send_message(target_uid, f"❌ **فیش واریزی شما رد شد.**\n💬 **علت:** {reject_reason}", parse_mode="Markdown")
        except Exception:
            pass
        return

    if user_id == OWNER_ID and state == "admin_waiting_for_sub_userinput":
        text_val = message.text.strip() if message.text else ""
        target_uid = None
        if text_val.isdigit():
            target_uid = int(text_val)
        else:
            clean_uname = text_val.replace("@", "").lower()
            for uid, info in registered_users.items():
                u_str = str(info.get("username", "")).lower()
                if u_str == clean_uname:
                    target_uid = uid
                    break

        if not target_uid:
            bot.send_message(chat_id, "❌ کاربر یافت نشد.")
            return

        with state_lock:
            owner_temp_data[f"sub_target_user_{user_id}"] = target_uid
            user_states[user_id] = {"state": "admin_waiting_for_sub_days"}
        bot.send_message(chat_id, f"✅ کاربر تایید شد (`{target_uid}`).\n⏳ لطفاً مدت زمان اشتراک (تعداد روز) را ارسال نمایید:", parse_mode="Markdown")
        return

    if user_id == OWNER_ID and state == "admin_waiting_for_sub_days":
        text_val = message.text.strip() if message.text else ""
        if text_val.isdigit() and int(text_val) > 0:
            days_val = int(text_val)
            target_uid = owner_temp_data.get(f"sub_target_user_{user_id}")
            with state_lock:
                user_states[user_id] = None

            grant_subscription(target_uid, days_val)

            bot.send_message(
                chat_id,
                f"✅ اشتراک `{days_val}` روزه برای کاربر `{target_uid}` فعال گردید.",
                reply_markup=get_main_keyboard(user_id),
                parse_mode="Markdown"
            )
            try:
                bot.send_message(target_uid, f"🎉 اشتراک `{days_val}` روزه ویژه برای شما فعال شد.", reply_markup=get_main_keyboard(target_uid), parse_mode="Markdown")
            except Exception:
                pass
            return

    if state == "waiting_for_payment_receipt":
        selected_pkg = state_data.get("pkg") if isinstance(state_data, dict) else None
        target_cnt = selected_pkg["count"] if selected_pkg else 100
        with state_lock:
            user_states[user_id] = None
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("✅ تایید", callback_data=f"approve_pay_{user_id}_{target_cnt}"),
            types.InlineKeyboardButton("❌ رد", callback_data=f"reject_pay_{user_id}")
        )
        
        user_info = registered_users.get(user_id, {"name": message.from_user.first_name, "username": message.from_user.username})
        u_name = escape_markdown(user_info.get("name", "کاربر"))
        u_uname = f"@{user_info.get('username')}" if user_info.get("username") else "بدون آیدی"

        caption_msg = f"💳 **رسید فیش ممبرگیری:**\n\n👤 [{u_name}](tg://user?id={user_id}) (`{u_uname}`)\n🆔 آیدی عددی: `{user_id}`\n📦 بسته: `{target_cnt}` ممبر"
        
        try:
            if message.photo:
                bot.send_photo(OWNER_ID, message.photo[-1].file_id, caption=caption_msg, reply_markup=markup, parse_mode="Markdown")
            else:
                bot.send_message(OWNER_ID, caption_msg, reply_markup=markup, parse_mode="Markdown")
                bot.forward_message(OWNER_ID, chat_id, message.message_id)
        except Exception as e:
            print(f"خطا در ارسال فیش ممبرگیری به ادمین: {e}")
        
        bot.send_message(chat_id, "✅ تصویر فیش جهت بررسی به مدیریت ارسال شد.", reply_markup=get_main_keyboard(user_id))
        return

    if state == "waiting_for_sub_receipt":
        selected_pkg = state_data.get("pkg") if isinstance(state_data, dict) else None
        days_count = selected_pkg["days"] if selected_pkg else 30
        sub_title = selected_pkg["title"] if selected_pkg else "اشتراک"
        with state_lock:
            user_states[user_id] = None
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("✅ تایید", callback_data=f"approve_sub_{user_id}_{days_count}"),
            types.InlineKeyboardButton("❌ رد", callback_data=f"reject_pay_{user_id}")
        )
        
        user_info = registered_users.get(user_id, {"name": message.from_user.first_name, "username": message.from_user.username})
        u_name = escape_markdown(user_info.get("name", "کاربر"))
        u_uname = f"@{user_info.get('username')}" if user_info.get("username") else "بدون آیدی"

        caption_msg = f"💎 **رسید فیش خرید اشتراک:**\n\n👤 [{u_name}](tg://user?id={user_id}) (`{u_uname}`)\n🆔 آیدی عددی: `{user_id}`\n📦 پلن: {sub_title} (`{days_count} روزه`)"
        
        try:
            if message.photo:
                bot.send_photo(OWNER_ID, message.photo[-1].file_id, caption=caption_msg, reply_markup=markup, parse_mode="Markdown")
            else:
                bot.send_message(OWNER_ID, caption_msg, reply_markup=markup, parse_mode="Markdown")
                bot.forward_message(OWNER_ID, chat_id, message.message_id)
        except Exception as e:
            print(f"خطا در ارسال فیش اشتراک به ادمین: {e}")
        
        bot.send_message(chat_id, "✅ تصویر فیش جهت بررسی به مدیریت ارسال شد.", reply_markup=get_main_keyboard(user_id))
        return

    if state == "waiting_for_channel_link":
        channel_link = message.text.strip() if message.text else ""
        if channel_link.startswith(("https://t.me/", "http://t.me/")):
            channel_link = channel_link.split("t.me/", 1)[1].strip("/").split("/", 1)[0]
        channel_link = channel_link.lstrip("@").strip()
        clean_link = "@" + channel_link.lower()

        with state_lock:
            for ord_item in active_orders:
                if ord_item.get("is_active", True) and ord_item.get("link", "").lower() == clean_link:
                    bot.send_message(chat_id, f"⚠️ کانال `{clean_link}` هم‌اکنون یک سفارش فعال دارد!", parse_mode="Markdown")
                    return

            target_cnt = state_data.get("count", 100) if isinstance(state_data, dict) else 100
            active_orders.append({"link": clean_link, "target_count": target_cnt, "current_count": 0, "counted_users": [], "user_id": user_id, "is_active": True})
            save_active_orders(active_orders)
            user_states[user_id] = None

        bot.send_message(chat_id, f"🎉 **سفارش شما فعال گردید!**\n\n📢 کانال: `{clean_link}`\n👥 تعداد: `{target_cnt}` ممبر", reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")
        try:
            bot.send_message(OWNER_ID, f"📢 سفارش جدید:\nکانال: `{clean_link}`\nتعداد: `{target_cnt}`", parse_mode="Markdown")
        except Exception:
            pass
        return

    if user_id == OWNER_ID and state == "edit_rules_state":
        save_member_rules(message.text or "")
        with state_lock:
            user_states[user_id] = None
        bot.send_message(chat_id, "✅ متن بخش ممبرگیری به روز شد.", reply_markup=get_main_keyboard(user_id))
        return

    if user_id == OWNER_ID and state == "edit_sub_rules_state":
        with state_lock:
            sub_config["rules"] = message.text or ""
            save_subscription_config(sub_config)
            user_states[user_id] = None
        bot.send_message(chat_id, "✅ متن بخش اشتراک به روز شد.", reply_markup=get_main_keyboard(user_id))
        return

    if user_id == OWNER_ID and state == "owner_setting_order_link":
        try:
            parts = message.text.split(",") if message.text else []
            if len(parts) == 2:
                raw_link = parts[0].strip().lstrip("@")
                clean_link = "@" + raw_link.lower()
                with state_lock:
                    active_orders.append({"link": clean_link, "target_count": int(parts[1].strip()), "current_count": 0, "counted_users": [], "user_id": OWNER_ID, "is_active": True})
                    save_active_orders(active_orders)
                    user_states[user_id] = None
                bot.send_message(chat_id, "✅ سفارش دستی اضافه شد.", reply_markup=get_main_keyboard(user_id))
                return
        except Exception:
            pass
        bot.send_message(chat_id, "❌ فرمت اشتباه است (`@channel, 100`):", parse_mode="Markdown")
        return

    success = False
    cfg = get_user_config(user_id)
    with state_lock:
        if state == "dest":
            value = message.text.strip() if message.text else ""
            cfg["destination"] = value
            user_states[user_id] = None
            success = True
        elif state == "forward_source":
            try:
                parts = message.text.rsplit(",", 1) if message.text else []
                if len(parts) == 2:
                    source_part = parts[0].strip().split("/")
                    if len(source_part) == 2:
                        cfg["from_chat_id"] = source_part[0].strip()
                        cfg["start_message_id"] = int(source_part[1].strip())
                        count_val = int(parts[1].strip())
                        cfg["count"] = max(1, min(4, count_val))
                        user_states[user_id] = None
                        success = True
            except Exception:
                pass
            if not success:
                bot.send_message(chat_id, "❌ فرمت اشتباه است (`@channel/15, 3`):", parse_mode="Markdown")
                return
        elif state == "text":
            cfg["message"] = message.text
            user_states[user_id] = None
            success = True
        elif state == "time":
            if message.text and message.text.isdigit() and int(message.text) > 0:
                cfg["interval_minutes"] = int(message.text)
                user_states[user_id] = None
                success = True

    if success:
        save_user_configs()
        forward_header = "⚙️ **پنل مدیریت تنظیمات فوروارد خودکار:**"
        bot.send_message(chat_id, forward_header, reply_markup=get_forward_keyboard(user_id), parse_mode="Markdown")


def multi_user_task_loop():
    while True:
        current_time = time.time()
        with state_lock:
            items = list(user_configs.items())
        
        for user_id, cfg in items:
            if not cfg.get("is_running", False) or not cfg.get("destination"):
                continue
            interval_seconds = cfg.get("interval_minutes", 5) * 60
            if current_time - cfg.get("last_sent", 0) >= interval_seconds:
                try:
                    if cfg["mode"] == "forward":
                        if cfg["from_chat_id"] and cfg["start_message_id"]:
                            total_count = cfg.get("count", 1)
                            start_id = cfg["start_message_id"]
                            for i in range(total_count):
                                bot.forward_message(
                                    chat_id=cfg["destination"], 
                                    from_chat_id=cfg["from_chat_id"], 
                                    message_id=start_id + i
                                )
                                time.sleep(1)
                    else:
                        if cfg.get("message"):
                            bot.send_message(cfg["destination"], cfg["message"])
                            
                    with state_lock:
                        cfg["last_sent"] = current_time
                        cfg["total_sent"] += 1
                        cfg["error_count"] = 0 
                        save_user_configs()
                except Exception as e:
                    print(f"خطا در ارسال خودکار کاربر {user_id}: {e}")
                    with state_lock:
                        cfg["error_count"] = cfg.get("error_count", 0) + 1
                        if cfg["error_count"] >= 3:
                            cfg["is_running"] = False
                            cfg["error_count"] = 0
                            try:
                                bot.send_message(
                                    user_id,
                                    "⚠️ **اخطار سیستم فوروارد خودکار:**\nفرآیند ارسال خودکار به دلیل بروز خطا متوقف شد.",
                                    parse_mode="Markdown"
                                )
                            except Exception:
                                pass
                        save_user_configs()
        time.sleep(5)


if __name__ == "__main__":
    if os.path.exists("user_lives.json"):
        try:
            os.remove("user_lives.json")
        except Exception:
            pass

    sender_thread = threading.Thread(target=multi_user_task_loop, daemon=True)
    sender_thread.start()

    # اجرای همزمان وب‌سرور Flask در یک ترد جداگانه
    flask_thread = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False, use_reloader=False),
        daemon=True
    )
    flask_thread.start()

    print("سرور ربات و وب‌سرور لابی رولت روسی آماده و در حال اجراست...")
    bot.infinity_polling(skip_pending=True)

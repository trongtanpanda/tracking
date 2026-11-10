import sys, os, time, json, asyncio
from datetime import datetime, timezone
import aiohttp
from aiohttp import web

sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)

CONFIG_FILE = 'config_paper_bot.json'
STATE_FILE = 'paper_bot_state.json'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Content-Type': 'application/json',
    'clienttype': 'web'
}

BASE_BINANCE_BAPI = 'https://www.binance.com/bapi/futures/v1/friendly/future/copy-trade'
BASE_BINANCE_FAPI = 'https://fapi.binance.com'

DEFAULT_CONFIG = {
  "bot_name": "Binance 9-Elite Scalper Paper Bot",
  "telegram": {
    "enabled": True,
    "bot_token": "1875915326:AAFDXKjjTGaDUGfxPbmqpGLxeKuscCg4mpE",
    "chat_id": "1411815277"
  },
  "slack": {
    "enabled": False,
    "webhook_url": ""
  },
  "capital_settings": {
    "initial_capital_usd": 200.0,
    "margin_per_trade_usd": 20.0,
    "max_concurrent_positions": 8,
    "max_safe_leverage": 20
  },
  "slippage_control": {
    "enabled": True,
    "max_slippage_pct": 0.25,
    "notify_on_rejected_slippage": True
  },
  "entry_filters": {
    "max_order_age_minutes": 5,
    "ignore_preexisting_positions": True
  },
  "exit_safety": {
    "consecutive_absence_confirmations": 3,
    "cooldown_after_close_seconds": 120
  },
  "monitoring": {
    "poll_interval_seconds": 1.5,
    "heartbeat_interval_hours": 6
  },
  "target_traders": [
    {
      "name": "海上方舟",
      "portfolio_id": "5121809002771580416",
      "score": 9.4,
      "style": "HFT 4 phút"
    },
    {
      "name": "短线的king",
      "portfolio_id": "5241753281755337728",
      "score": 9.2,
      "style": "Short Pump 48 phút"
    },
    {
      "name": "玄冥二老",
      "portfolio_id": "4908633203782592768",
      "score": 9.2,
      "style": "HFT 6 phút"
    },
    {
      "name": "ElroyMolly",
      "portfolio_id": "4995352820626030848",
      "score": 9.0,
      "style": "Day Trade 3.3h"
    },
    {
      "name": "星辰社区-意钦",
      "portfolio_id": "4788776444236355328",
      "score": 8.9,
      "style": "Day Trade 2.1h"
    },
    {
      "name": "Fomo-扫单之王",
      "portfolio_id": "5078808125094578945",
      "score": 8.7,
      "style": "HFT 7 phút"
    },
    {
      "name": "星辰社区-海",
      "portfolio_id": "5131925334830383361",
      "score": 8.5,
      "style": "Day Trade 1.6h"
    },
    {
      "name": "五路财神的小公主",
      "portfolio_id": "4662628079386208001",
      "score": 8.4,
      "style": "Scalp 5h"
    },
    {
      "name": "Diamond-Hamsters",
      "portfolio_id": "4300516091842181632",
      "score": 8.0,
      "style": "Swing 8.7h"
    }
  ]
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return DEFAULT_CONFIG

def load_state(initial_capital):
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)
                return state
        except Exception:
            pass
    return {
        'wallet_balance': initial_capital,
        'initial_capital': initial_capital,
        'realized_pnl': 0.0,
        'total_trades': 0,
        'winning_trades': 0,
        'losing_trades': 0,
        'active_positions': {},
        'closed_trades': []
    }

def save_state(state):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def format_duration(ms):
    if not ms or ms < 0:
        return "< 1 phút"
    secs = int(ms / 1000)
    mins = secs // 60
    hours = mins // 60
    days = hours // 24
    if days > 0:
        rem_hrs = hours % 24
        return f"{days} ngày {rem_hrs} giờ" if rem_hrs else f"{days} ngày"
    if hours > 0:
        rem_mins = mins % 60
        return f"{hours} giờ {rem_mins} phút" if rem_mins else f"{hours} giờ"
    if mins > 0:
        return f"{mins} phút"
    return f"{secs} giây"

class NotificationManager:
    def __init__(self, session, config):
        self.session = session
        self.tg_cfg = config.get('telegram', {})
        self.slack_cfg = config.get('slack', {})

    async def send_all(self, text_plain, text_html):
        tasks = []
        if self.tg_cfg.get('enabled') and self.tg_cfg.get('bot_token') and self.tg_cfg.get('chat_id'):
            tasks.append(self.send_telegram(text_html))
        if self.slack_cfg.get('enabled') and self.slack_cfg.get('webhook_url'):
            tasks.append(self.send_slack(text_plain))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def send_telegram(self, text_html):
        token = self.tg_cfg.get('bot_token')
        chat_id = self.tg_cfg.get('chat_id')
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': text_html,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True
        }
        try:
            async with self.session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=6)) as r:
                res = await r.json()
                if not res.get('ok'):
                    print(f"[Telegram Error] {res}")
        except Exception as e:
            print(f"[Telegram Send Exception] {e}")

    async def send_slack(self, text_plain):
        url = self.slack_cfg.get('webhook_url')
        if not url:
            return
        payload = {'text': text_plain}
        try:
            async with self.session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=6)) as r:
                pass
        except Exception as e:
            print(f"[Slack Send Exception] {e}")

class PaperCopyBot:
    def __init__(self, config):
        self.config = config
        self.cap_cfg = config.get('capital_settings', {})
        self.slip_cfg = config.get('slippage_control', {})
        self.entry_cfg = config.get('entry_filters', {})
        self.exit_cfg = config.get('exit_safety', {})
        self.traders = config.get('target_traders', [])
        self.poll_interval = config.get('monitoring', {}).get('poll_interval_seconds', 1.5)

        self.state = load_state(self.cap_cfg.get('initial_capital_usd', 200.0))
        save_state(self.state)
        # Keep track of trader positions from previous tick: {trader_pid: {pos_key: pos_data}}
        self.prev_trader_positions = {}
        self.absent_counter = {}  # pos_id -> int
        self.closed_cooldown = {}  # pos_id -> timestamp expiry
        self.ignored_positions = set()  # set of pos_id strings
        self.session = None
        self.notifier = None

    async def get_latest_order_time(self, pid, symbol):
        url = f"{BASE_BINANCE_BAPI}/lead-portfolio/order-history"
        payload = {'portfolioId': pid, 'pageNumber': 1, 'pageSize': 5}
        try:
            async with self.session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=4)) as r:
                res = await r.json()
                if res.get('code') == '000000':
                    for ord in res.get('data', {}).get('list', []):
                        if ord.get('symbol') == symbol:
                            return ord.get('orderTime') or ord.get('orderUpdateTime')
        except Exception:
            pass
        return None

    async def get_live_market_price(self, symbol):
        url = f"{BASE_BINANCE_FAPI}/fapi/v1/ticker/price?symbol={symbol}"
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as r:
                data = await r.json()
                if 'price' in data:
                    return float(data['price'])
        except Exception:
            pass
        return None

    async def fetch_trader_positions(self, trader):
        pid = trader['portfolio_id']
        url = f"{BASE_BINANCE_BAPI}/lead-data/positions?portfolioId={pid}"
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=4)) as r:
                res = await r.json()
                if res.get('code') == '000000':
                    # Only take active positions where amount != 0
                    active = {}
                    for p in res.get('data', []):
                        amt = float(p.get('positionAmount', 0))
                        if amt != 0:
                            sym = p.get('symbol')
                            side = p.get('positionSide', 'BOTH').upper()
                            if side == 'BOTH':
                                side = 'LONG' if amt > 0 else 'SHORT'
                            key = f"{sym}_{side}"
                            active[key] = p
                    return pid, trader['name'], active, True
        except Exception:
            pass
        return pid, trader['name'], {}, False

    async def process_new_position(self, trader_name, pid, pos_key, p_data):
        pos_id = f"{pid}_{pos_key}"
        if pos_id in self.state.get('active_positions', {}):
            return

        # Cooldown check after previous close
        if pos_id in self.closed_cooldown and time.time() < self.closed_cooldown[pos_id]:
            return

        # Ignore if marked as old or pre-existing
        if pos_id in self.ignored_positions:
            return

        sym = p_data.get('symbol')
        side = p_data.get('positionSide', 'BOTH').upper()
        amt = float(p_data.get('positionAmount', 0))
        if side == 'BOTH':
            side = 'LONG' if amt > 0 else 'SHORT'

        # CRITICAL FILTER: Verify order age vs current time!
        max_age_mins = self.entry_cfg.get('max_order_age_minutes', 5)
        order_time = await self.get_latest_order_time(pid, sym)
        if order_time:
            age_mins = (int(time.time() * 1000) - order_time) / (1000 * 60)
            if age_mins > max_age_mins:
                self.ignored_positions.add(pos_id)
                print(f"[SKIP OLD TRADE] Trader {trader_name} #{sym} opened {age_mins:.1f}m ago (> {max_age_mins}m). Ignored!")
                return

        trader_entry = float(p_data.get('entryPrice', 0))
        trader_lev = int(p_data.get('leverage', 1))
        # Cap leverage at safe maximum
        bot_lev = min(trader_lev, self.cap_cfg.get('max_safe_leverage', 20))
        margin_usd = self.cap_cfg.get('margin_per_trade_usd', 20.0)

        # Check capital availability
        current_active = self.state.get('active_positions', {})
        if len(current_active) >= self.cap_cfg.get('max_concurrent_positions', 8):
            print(f"[Skip] Reached max concurrent positions ({len(current_active)}). Skipping {sym} from {trader_name}.")
            return

        if self.state['wallet_balance'] < margin_usd:
            print(f"[Skip] Insufficient wallet balance (${self.state['wallet_balance']:.2f} < ${margin_usd}). Skipping.")
            return

        # 1. Fetch live market price & compute slippage
        live_price = await self.get_live_market_price(sym)
        if not live_price or live_price <= 0:
            live_price = trader_entry

        max_slip_pct = self.slip_cfg.get('max_slippage_pct', 0.25)
        is_rejected = False
        slip_pct = 0.0

        if trader_entry > 0 and live_price > 0:
            if side == 'LONG':
                slip_pct = ((live_price - trader_entry) / trader_entry) * 100.0
                if slip_pct > max_slip_pct:
                    is_rejected = True
            elif side == 'SHORT':
                slip_pct = ((trader_entry - live_price) / trader_entry) * 100.0
                if slip_pct > max_slip_pct:
                    is_rejected = True

        # Notification of Trader's Entry
        time_str = datetime.now().strftime('%H:%M:%S')

        if is_rejected and self.slip_cfg.get('enabled', True):
            # Slippage Exceeded -> Reject Order to Protect Capital
            msg_plain = f"[TRƯỢT GIÁ CAO - TỪ CHỐI LỆNH] Trader {trader_name} vừa {side} {sym} @ {trader_entry}. Giá sàn: {live_price} (Trượt: {slip_pct:+.2f}% > {max_slip_pct}%). Bot chặn lệnh bảo vệ vốn!"
            msg_html = f"""⚠️ <b>[CẢNH BÁO TRƯỢT GIÁ — CHẶN VÀO LỆNH]</b>
━━━━━━━━━━━━━━━━━━
👤 Trader: <b>{trader_name}</b>
⚡ Cặp: <b>{sym}</b> | Hướng: <b>{side} {trader_lev}x</b>
🎯 Giá vào Lead: <b>${trader_entry:,.4f}</b>
📍 Giá thị trường: <b>${live_price:,.4f}</b>
📉 Độ trượt giá: <b style="color:red;">{slip_pct:+.2f}%</b> (Ngưỡng tối đa: <b>{max_slip_pct}%</b>)
🛡️ <i>Hệ thống Slippage Guard đã tự động chặn lệnh để bảo vệ vốn!</i>
⏱️ Thời gian: <code>{time_str}</code>"""
            print(f"[SLIPPAGE REJECT] {sym} by {trader_name}: Slippage {slip_pct:+.2f}% > {max_slip_pct}%")
            if self.slip_cfg.get('notify_on_rejected_slippage', True):
                await self.notifier.send_all(msg_plain, msg_html)
            return

        # 2. Execute Paper Order
        size_coins = (margin_usd * bot_lev) / live_price

        self.state['wallet_balance'] -= margin_usd
        self.state['active_positions'][pos_id] = {
            'pos_id': pos_id,
            'trader_name': trader_name,
            'portfolio_id': pid,
            'pos_key': pos_key,
            'symbol': sym,
            'side': side,
            'trader_entry': trader_entry,
            'bot_entry': live_price,
            'leverage': bot_lev,
            'margin_usd': margin_usd,
            'size_coins': size_coins,
            'slippage_pct': round(slip_pct, 3),
            'opened_at': int(time.time() * 1000),
            'opened_time_str': time_str
        }
        save_state(self.state)

        # Notify Entry Success
        msg_plain = f"[BOT VÀO LỆNH GIẢ LẬP] Trader {trader_name} {side} {sym}. Bot khớp @ {live_price}. Đòn bẩy {bot_lev}x, Ký quỹ ${margin_usd:.1f}u, Ví còn: ${self.state['wallet_balance']:.2f}u."
        msg_html = f"""🚀 <b>[BOT SAO CHÉP — KHỚP LỆNH GIẢ LẬP THÀNH CÔNG]</b>
━━━━━━━━━━━━━━━━━━
👤 Lead Trader: <b>{trader_name}</b>
⚡ Cặp giao dịch: <b>#{sym}</b>
📊 Vị thế: <b>{side}</b> | Đòn bẩy Bot: <b>{bot_lev}x</b> (Lead: {trader_lev}x)
🎯 Giá vào của Lead: <b>${trader_entry:,.4f}</b>
📍 Giá Bot khớp giả lập: <b>${live_price:,.4f}</b>
⚖️ Độ trượt giá: <b>{slip_pct:+.2f}%</b> (Đạt chuẩn an toàn)
💵 Ký quỹ lệnh (Margin): <b>${margin_usd:.2f} USDT</b>
📦 Khối lượng: <b>{size_coins:,.4f} {sym.replace('USDT', '')}</b>
💰 Số dư ví còn lại: <b>${self.state['wallet_balance']:.2f} USDT</b>
⏱️ Thời gian khớp: <code>{time_str}</code>"""

        print(f"[PAPER ENTERED] {side} {sym} for {trader_name} @ {live_price} | Margin ${margin_usd}u")
        await self.notifier.send_all(msg_plain, msg_html)

    async def process_closed_position(self, pos_id, pos_info):
        sym = pos_info['symbol']
        side = pos_info['side']
        bot_entry = pos_info['bot_entry']
        margin_usd = pos_info['margin_usd']
        size_coins = pos_info['size_coins']
        lev = pos_info['leverage']
        trader_name = pos_info['trader_name']

        # Get live exit price
        exit_price = await self.get_live_market_price(sym)
        if not exit_price or exit_price <= 0:
            exit_price = bot_entry

        # Calculate PnL
        if side == 'LONG':
            raw_pnl = (exit_price - bot_entry) * size_coins
        else:
            raw_pnl = (bot_entry - exit_price) * size_coins

        # Deduct standard Taker fee 0.05% on entry + exit
        total_vol = (bot_entry * size_coins) + (exit_price * size_coins)
        fee = total_vol * 0.0005
        net_pnl = raw_pnl - fee
        roi_pct = (net_pnl / margin_usd) * 100.0

        # Holding duration
        opened_at = pos_info.get('opened_at', int(time.time() * 1000))
        closed_at = int(time.time() * 1000)
        dur_str = format_duration(closed_at - opened_at)

        # Update Wallet State
        self.state['wallet_balance'] += (margin_usd + net_pnl)
        self.state['realized_pnl'] += net_pnl
        self.state['total_trades'] += 1
        if net_pnl >= 0:
            self.state['winning_trades'] += 1
        else:
            self.state['losing_trades'] += 1

        del self.state['active_positions'][pos_id]
        self.state['closed_trades'].append({
            'pos_id': pos_id,
            'trader_name': trader_name,
            'symbol': sym,
            'side': side,
            'bot_entry': bot_entry,
            'exit_price': exit_price,
            'net_pnl': round(net_pnl, 2),
            'roi_pct': round(roi_pct, 2),
            'fee': round(fee, 3),
            'duration_str': dur_str,
            'closed_at': closed_at
        })
        save_state(self.state)

        win_rate = (self.state['winning_trades'] / self.state['total_trades']) * 100.0 if self.state['total_trades'] else 0
        pnl_icon = "🟢" if net_pnl >= 0 else "🔴"
        pnl_title = "CHỐT LỜI THÀNH CÔNG" if net_pnl >= 0 else "CẮT LỖ BẢO TOÀN VỐN"
        time_str = datetime.now().strftime('%H:%M:%S')

        msg_plain = f"[{pnl_title}] {sym} ({trader_name}). Lãi/Lỗ: {net_pnl:+.2f} USDT ({roi_pct:+.2f}%). Giữ: {dur_str}. Ví mới: ${self.state['wallet_balance']:.2f} USDT."
        msg_html = f"""{pnl_icon} <b>[TRADER ĐÓNG LỆNH — BOT {pnl_title}]</b>
━━━━━━━━━━━━━━━━━━
👤 Lead Trader: <b>{trader_name}</b>
⚡ Cặp giao dịch: <b>#{sym}</b> | Hướng: <b>{side} {lev}x</b>
🎯 Giá vào: <b>${bot_entry:,.4f}</b> | Giá đóng: <b>${exit_price:,.4f}</b>
⏱️ Thời gian giữ lệnh: <b>{dur_str}</b>
💵 Lãi/Lỗ ròng: <b>{net_pnl:+.2f} USDT ({roi_pct:+.2f}%)</b>
🏷️ Phí sàn tạm tính: <b>${fee:.3f} USDT</b>
━━━━━━━━━━━━━━━━━━
💰 <b>Số dư ví mới: ${self.state['wallet_balance']:.2f} USDT</b>
📊 Tổng lệnh đã đóng: <b>{self.state['total_trades']}</b> (Winrate: <b>{win_rate:.1f}%</b>)
⏱️ Thời gian đóng: <code>{time_str}</code>"""

        print(f"[PAPER CLOSED] {sym} by {trader_name} | Net PnL: {net_pnl:+.2f}u ({roi_pct:+.2f}%) | Bal: ${self.state['wallet_balance']:.2f}u")
        await self.notifier.send_all(msg_plain, msg_html)

    async def scan_once(self):
        tasks = [self.fetch_trader_positions(t) for t in self.traders]
        results = await asyncio.gather(*tasks)

        current_tick = {}
        success_map = {}
        for pid, name, active_dict, is_success in results:
            success_map[pid] = is_success
            if is_success:
                current_tick[pid] = active_dict
            else:
                # If network dropped temporarily, retain previous state to avoid false triggers
                current_tick[pid] = self.prev_trader_positions.get(pid, {})

        # First tick initialization
        if not self.prev_trader_positions:
            self.prev_trader_positions = current_tick
            if self.entry_cfg.get('ignore_preexisting_positions', True):
                for pid_snap, active_map in current_tick.items():
                    for k in active_map.keys():
                        self.ignored_positions.add(f"{pid_snap}_{k}")
            total_active = sum(len(v) for v in current_tick.values())
            print(f"[Init] Initial snapshot complete. Active positions across 9 traders: {total_active} (All blacklisted as pre-existing).")
            return

        # 1. Detect New Entries
        for t in self.traders:
            pid = t['portfolio_id']
            name = t['name']
            if not success_map.get(pid, False):
                continue
            current_pos = current_tick.get(pid, {})
            prev_pos = self.prev_trader_positions.get(pid, {})

            for pos_key, p_data in current_pos.items():
                if pos_key not in prev_pos:
                    # New position opened by trader!
                    await self.process_new_position(name, pid, pos_key, p_data)

        # 2. Detect Exits / Closed Positions (With Multi-Confirmation Against Network Glitches)
        active_copy_positions = list(self.state.get('active_positions', {}).items())
        required_confirmations = self.exit_cfg.get('consecutive_absence_confirmations', 3)
        cooldown_secs = self.exit_cfg.get('cooldown_after_close_seconds', 120)

        for pos_id, pos_info in active_copy_positions:
            pid = pos_info['portfolio_id']
            pos_key = pos_info['pos_key']
            # Only consider closed if the API call for this trader was successful
            if not success_map.get(pid, False):
                continue

            current_pos = current_tick.get(pid, {})
            if pos_key not in current_pos:
                self.absent_counter[pos_id] = self.absent_counter.get(pos_id, 0) + 1
                if self.absent_counter[pos_id] >= required_confirmations:
                    # Confirmed closed after 3 consecutive successful absence checks!
                    self.absent_counter[pos_id] = 0
                    self.closed_cooldown[pos_id] = time.time() + cooldown_secs
                    await self.process_closed_position(pos_id, pos_info)
            else:
                # Still active, reset counter
                if pos_id in self.absent_counter:
                    self.absent_counter[pos_id] = 0

        self.prev_trader_positions = current_tick

    async def start_web_server(self):
        app = web.Application()
        async def handle_home(request):
            total_trades = self.state.get('total_trades', 0)
            win_trades = self.state.get('winning_trades', 0)
            wr = (win_trades / total_trades * 100) if total_trades else 0
            active = self.state.get('active_positions', {})
            html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Binance 9-Elite Paper Copy Bot</title>
    <meta http-equiv="refresh" content="5">
    <style>
        body {{ background: #080c14; color: #f3f4f6; font-family: -apple-system, BlinkMacSystemFont, sans-serif; padding: 24px; }}
        .card {{ background: #111827; border: 1px solid #1f2937; border-radius: 12px; padding: 20px; max-width: 800px; margin: 0 auto; }}
        h1 {{ font-size: 20px; color: #fcd535; margin-bottom: 12px; }}
        .badge {{ background: #10b98125; color: #10b981; border: 1px solid #10b98140; padding: 4px 10px; border-radius: 999px; font-size: 11px; font-weight: bold; }}
        .grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 16px 0; }}
        .metric {{ background: #1f2937; padding: 12px; border-radius: 8px; }}
        .metric-label {{ font-size: 11px; color: #9ca3af; text-transform: uppercase; }}
        .metric-val {{ font-size: 20px; font-weight: bold; color: #fff; margin-top: 4px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 14px; font-size: 13px; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #374151; }}
        th {{ color: #9ca3af; }}
    </style>
</head>
<body>
    <div class="card">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <h1>🤖 Binance 9-Elite Scalper Paper Bot</h1>
            <span class="badge">● ONLINE LIVE</span>
        </div>
        <p style="color: #9ca3af; font-size: 13px;">Theo dõi 9 Lead Trader tinh hoa (&lt; 10h) với vốn giả lập $200 USDT &amp; Slippage Guard 0.25%.</p>
        
        <div class="grid">
            <div class="metric">
                <div class="metric-label">Số Dư Ví Giả Lập</div>
                <div class="metric-val" style="color:#10b981;">${self.state.get('wallet_balance', 200.0):.2f}u</div>
            </div>
            <div class="metric">
                <div class="metric-label">Lãi/Lỗ Tích Lũy</div>
                <div class="metric-val" style="color:{'#10b981' if self.state.get('realized_pnl', 0) >= 0 else '#f43f5e'};">
                    {self.state.get('realized_pnl', 0):+.2f}u
                </div>
            </div>
            <div class="metric">
                <div class="metric-label">Lệnh Đóng (Win Rate)</div>
                <div class="metric-val">{total_trades} ({wr:.1f}%)</div>
            </div>
        </div>

        <h3 style="font-size: 14px; margin-top: 16px; color:#fcd535;">Vị Thế Đang Mở ({len(active)})</h3>
        {"<table><thead><tr><th>Trader</th><th>Coin</th><th>Side</th><th>Entry</th><th>Margin</th></tr></thead><tbody>" + "".join([f"<tr><td>{p['trader_name']}</td><td>{p['symbol']}</td><td>{p['side']} {p['leverage']}x</td><td>${p['bot_entry']:,.4f}</td><td>${p['margin_usd']}u</td></tr>" for p in active.values()]) + "</tbody></table>" if active else "<p style='font-size:13px; color:#9ca3af; margin-top:8px;'>Hiện tại không có vị thế mở (100% USDT tiền mặt).</p>"}
    </div>
</body>
</html>"""
            return web.Response(text=html, content_type='text/html')

        app.router.add_get('/', handle_home)
        app.router.add_get('/health', lambda r: web.Response(text='OK'))

        port = int(os.environ.get('PORT', 7860))
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', port)
        try:
            await site.start()
            print(f"[Web Dashboard] Started on port {port} (Hugging Face / Cloud Ready)")
        except Exception as e:
            print(f"[Web Dashboard Warning] Port {port} in use or failed: {e}")

    async def start(self):
        connector = aiohttp.TCPConnector(limit=50, keepalive_timeout=60)
        async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
            self.session = session
            self.notifier = NotificationManager(session, self.config)

            # Start Lightweight Web Server for Cloud Keep-Alive
            await self.start_web_server()

            # Send Startup Notification to Telegram & Slack
            start_msg_plain = f"[BOT KHỞI CHẠY] Theo dõi 9 Trader lướt sóng (<10h) với vốn giả lập $200 USDT. Max Slippage: {self.slip_cfg.get('max_slippage_pct')}%. Sẵn sàng!"
            start_msg_html = f"""🤖 <b>[BINANCE 9-ELITE SCALPER BOT ĐÃ KHỞI CHẠY]</b>
━━━━━━━━━━━━━━━━━━
💰 Vốn giả lập ban đầu: <b>${self.state['wallet_balance']:.2f} USDT</b>
🎯 Ký quỹ mỗi lệnh: <b>${self.cap_cfg.get('margin_per_trade_usd', 20.0):.1f} USDT</b> (Tối đa {self.cap_cfg.get('max_concurrent_positions', 8)} lệnh cùng lúc)
🛡️ Kiểm soát trượt giá (Max Slippage): <b>{self.slip_cfg.get('max_slippage_pct', 0.25)}%</b>
⏱️ Chu kỳ quét: <b>{self.poll_interval}s / lần (Sub-second Async)</b>
━━━━━━━━━━━━━━━━━━
📋 <b>Danh sách 9 Trader được giám sát:</b>
1. <b>海上方舟</b> (9.4★ | Hold 4 phút | MDD 3.7%)
2. <b>短线的king</b> (9.2★ | Hold 48 phút | Đòn bẩy 5x)
3. <b>玄冥二老</b> (9.2★ | Hold 6 phút | Copier +$145k)
4. <b>ElroyMolly</b> (9.0★ | Hold 3.3h | Copier +$130k)
5. <b>星辰社区-意钦</b> (8.9★ | Hold 2.1h | Copier +$250k)
6. <b>Fomo-扫单之王</b> (8.7★ | Hold 7 phút | MDD 7.7%)
7. <b>星辰社区-海</b> (8.5★ | Hold 1.6h | Copier +$43k)
8. <b>五路财神的小公主</b> (8.4★ | Hold 5.0h | Win 99.8%)
9. <b>Diamond-Hamsters</b> (8.0★ | Hold 8.7h | MDD 14.7%)
━━━━━━━━━━━━━━━━━━
✅ <i>Bot đang chạy nền và sẽ tự động gửi thông báo ngay khi có lệnh mới!</i>"""

            print("Sending startup notification to Telegram & Slack...")
            await self.notifier.send_all(start_msg_plain, start_msg_html)
            print("="*80)
            print("BOT RUNNING CONTINUOUSLY... Press Ctrl+C to stop.")
            print("="*80)

            while True:
                t0 = time.time()
                try:
                    await self.scan_once()
                except Exception as e:
                    print(f"[Loop Exception] {e}")

                elapsed = time.time() - t0
                sleep_time = max(0.1, self.poll_interval - elapsed)
                await asyncio.sleep(sleep_time)

def main():
    config = load_config()
    bot = PaperCopyBot(config)
    if '--test-once' in sys.argv:
        async def run_once():
            connector = aiohttp.TCPConnector(limit=50, keepalive_timeout=60)
            async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
                bot.session = session
                bot.notifier = NotificationManager(session, config)
                print("[Test-Once] Scanning 9 traders once...")
                await bot.scan_once()
                print(f"[Test-Once] Done! Wallet Balance: ${bot.state['wallet_balance']:.2f} USDT")
        asyncio.run(run_once())
    else:
        asyncio.run(bot.start())

if __name__ == '__main__':
    main()

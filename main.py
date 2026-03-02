"""
GOLD ANALYZER BOT - Final Version
"""

from flask import Flask, jsonify, request, render_template_string
import requests
import os
import time
import threading
import logging
from datetime import datetime
from functools import wraps
import sys

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_IDS = os.getenv('TELEGRAM_CHAT_IDS', "").split(',')
ANALYSIS_INTERVAL = int(os.getenv('ANALYSIS_INTERVAL', '3600'))
PORT = int(os.environ.get('PORT', 5000))

TELEGRAM_CHAT_IDS = [id.strip() for id in TELEGRAM_CHAT_IDS if id.strip()]

class Statistics:
    def __init__(self):
        self.total_analyses = 0
        self.successful_analyses = 0
        self.failed_analyses = 0
        self.last_analysis_time = None
        self.last_signal = None
        self.start_time = datetime.now()
    
    def record_analysis(self, success=True, signal=None):
        self.total_analyses += 1
        if success:
            self.successful_analyses += 1
            self.last_signal = signal
        else:
            self.failed_analyses += 1
        self.last_analysis_time = datetime.now()
    
    def get_uptime(self):
        delta = datetime.now() - self.start_time        hours = delta.total_seconds() / 3600
        return f"{hours:.2f} hours"
    
    def get_success_rate(self):
        if self.total_analyses == 0:
            return "0%"
        rate = (self.successful_analyses / self.total_analyses) * 100
        return f"{rate:.1f}%"
    
    def to_dict(self):
        return {
            "total_analyses": self.total_analyses,
            "successful": self.successful_analyses,
            "failed": self.failed_analyses,
            "success_rate": self.get_success_rate(),
            "uptime": self.get_uptime(),
            "last_analysis": str(self.last_analysis_time) if self.last_analysis_time else "Never",
            "last_signal": self.last_signal or "None"
        }

stats = Statistics()

def retry_on_failure(max_attempts=3, delay=5):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    logger.warning(f"Attempt {attempt + 1}/{max_attempts} failed: {str(e)}")
                    if attempt == max_attempts - 1:
                        logger.error(f"All {max_attempts} attempts failed")
                        raise
                    time.sleep(delay)
        return wrapper
    return decorator

@retry_on_failure(max_attempts=3, delay=5)
def analyze_gold():
    logger.info("Starting Gold Analysis...")
    
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F"
        params = {'interval': '1h', 'range': '5d'}
        
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
                if 'chart' not in data or 'result' not in data['chart']:
            return {"error": "No data received from API"}
        
        if not data['chart']['result']:
            return {"error": "Empty result from API"}
        
        chart = data['chart']['result'][0]
        quotes = chart['indicators']['quote'][0]
        
        closes = quotes['close']
        highs = quotes['high']
        lows = quotes['low']
        
        if len(closes) < 20:
            return {"error": "Insufficient data for analysis"}
        
        current = closes[-1]
        prev = closes[-2]
        
        price_change = current - prev
        price_change_pct = (price_change / prev) * 100 if prev > 0 else 0
        
        sma_20 = sum(closes[-20:]) / 20
        sma_50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else sma_20
        
        gains = 0
        losses = 0
        
        for i in range(1, 15):
            if len(closes) > i:
                change = closes[-i] - closes[-i-1]
                if change > 0:
                    gains += change
                else:
                    losses += abs(change)
        
        avg_gain = gains / 14
        avg_loss = losses / 14 if losses > 0 else 0.001
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        resistance = max(highs[-20:])
        support = min(lows[-20:])
        resistance_2 = max(highs[-50:]) if len(highs) >= 50 else resistance
        support_2 = min(lows[-50:]) if len(lows) >= 50 else support
        
        signal = "WAIT"
        signal_strength = "NEUTRAL"
        reasons = []
                buy_conditions = 0
        if prev > sma_20:
            buy_conditions += 1
            reasons.append("Price > SMA20")
        if rsi > 50:
            buy_conditions += 1
            reasons.append("RSI > 50")
        if prev > resistance:
            buy_conditions += 1
            reasons.append("Breakout above Resistance")
        
        sell_conditions = 0
        if prev < sma_20:
            sell_conditions += 1
            reasons.append("Price < SMA20")
        if rsi < 50:
            sell_conditions += 1
            reasons.append("RSI < 50")
        if prev < support:
            sell_conditions += 1
            reasons.append("Breakdown below Support")
        
        if buy_conditions >= 3:
            signal = "STRONG BUY"
            signal_strength = "STRONG"
        elif buy_conditions >= 2:
            signal = "BUY"
            signal_strength = "MODERATE"
        elif sell_conditions >= 3:
            signal = "STRONG SELL"
            signal_strength = "STRONG"
        elif sell_conditions >= 2:
            signal = "SELL"
            signal_strength = "MODERATE"
        
        if "BUY" in signal:
            stop_loss = current * 0.98
            take_profit = current * 1.04
        elif "SELL" in signal:
            stop_loss = current * 1.02
            take_profit = current * 0.96
        else:
            stop_loss = 0
            take_profit = 0
        
        result = {
            "success": True,
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "price": {
                "current": round(current, 2),                "previous": round(prev, 2),
                "change": round(price_change, 2),
                "change_percent": round(price_change_pct, 2)
            },
            "indicators": {
                "rsi": round(rsi, 2),
                "rsi_status": "Overbought" if rsi > 70 else "Oversold" if rsi < 30 else "Neutral",
                "sma_20": round(sma_20, 2),
                "sma_50": round(sma_50, 2)
            },
            "levels": {
                "resistance_1": round(resistance, 2),
                "resistance_2": round(resistance_2, 2),
                "support_1": round(support, 2),
                "support_2": round(support_2, 2)
            },
            "signal": {
                "action": signal,
                "strength": signal_strength,
                "stop_loss": round(stop_loss, 2) if stop_loss > 0 else None,
                "take_profit": round(take_profit, 2) if take_profit > 0 else None
            },
            "analysis": {
                "reasons": reasons,
                "buy_conditions": buy_conditions,
                "sell_conditions": sell_conditions
            }
        }
        
        logger.info("Analysis completed successfully")
        return result
        
    except requests.exceptions.Timeout:
        logger.error("Request timeout")
        return {"error": "Request timeout"}
    except requests.exceptions.ConnectionError:
        logger.error("Connection error")
        return {"error": "Connection error"}
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return {"error": str(e)}

def send_telegram_message(message, parse_mode='HTML'):
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not configured")
        return False
    
    if not TELEGRAM_CHAT_IDS:
        logger.warning("No Chat IDs configured")
        return False    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    success_count = 0
    failed_count = 0
    
    for chat_id in TELEGRAM_CHAT_IDS:
        chat_id = chat_id.strip()
        if not chat_id:
            continue
        
        data = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': parse_mode
        }
        
        try:
            response = requests.post(url, data=data, timeout=10)
            if response.status_code == 200:
                logger.info(f"Message sent to {chat_id}")
                success_count += 1
            else:
                logger.error(f"Failed to send to {chat_id}: {response.status_code}")
                failed_count += 1
        except Exception as e:
            logger.error(f"Error sending to {chat_id}: {str(e)}")
            failed_count += 1
    
    logger.info(f"Messages: {success_count} sent, {failed_count} failed")
    return success_count > 0

def format_analysis_message(result):
    if "error" in result:
        return f"Error: {result['error']}"
    
    price = result['price']
    indicators = result['indicators']
    levels = result['levels']
    signal = result['signal']
    
    emoji = "🟢" if "BUY" in signal['action'] else "🔴" if "SELL" in signal['action'] else "⏳"
    
    message = f"""
Gold Analysis Report {emoji}

Price: ${price['current']}
Change: {price['change_percent']:+.2f}%

RSI: {indicators['rsi']} ({indicators['rsi_status']})SMA 20: ${indicators['sma_20']}

Resistance: ${levels['resistance_1']}
Support: ${levels['support_1']}

Signal: {signal['action']} ({signal['strength']})

Time: {result['timestamp']}
    """
    
    return message

def scheduled_analysis_task():
    logger.info("Scheduler started")
    time.sleep(60)
    
    while True:
        try:
            logger.info("=" * 60)
            logger.info("Scheduled analysis triggered")
            logger.info("=" * 60)
            
            result = analyze_gold()
            
            if "error" not in result:
                stats.record_analysis(success=True, signal=result.get('signal', {}).get('action', 'Unknown'))
                message = format_analysis_message(result)
                send_telegram_message(message)
                logger.info("Scheduled analysis completed")
            else:
                stats.record_analysis(success=False)
                logger.error(f"Analysis failed: {result.get('error', 'Unknown error')}")
            
            logger.info(f"Sleeping for {ANALYSIS_INTERVAL} seconds...")
            time.sleep(ANALYSIS_INTERVAL)
            
        except Exception as e:
            logger.error(f"Scheduler error: {str(e)}")
            time.sleep(300)

@app.route('/')
def home():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Gold Analyzer Bot</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; background: #1a1a2e; color: #eee; }
            h1 { color: #ffd700; }            .status { padding: 10px; background: #16213e; border-radius: 5px; margin: 20px 0; }
            .endpoint { background: #0f3460; padding: 15px; margin: 10px 0; border-radius: 5px; }
            code { background: #1a1a2e; padding: 2px 5px; border-radius: 3px; color: #00ff00; }
        </style>
    </head>
    <body>
        <h1>Gold Analyzer Bot</h1>
        <div class="status">
            <strong>Status:</strong> Running<br>
            <strong>Uptime:</strong> """ + stats.get_uptime() + """<br>
            <strong>Version:</strong> 3.0 Final<br>
            <strong>Chat IDs:</strong> """ + str(len(TELEGRAM_CHAT_IDS)) + """ configured
        </div>
        <h2>API Endpoints</h2>
        <div class="endpoint"><code>GET /analyze</code> - Run analysis manually</div>
        <div class="endpoint"><code>GET /status</code> - Health check</div>
        <div class="endpoint"><code>GET /stats</code> - View statistics</div>
        <div class="endpoint"><code>GET /telegram/test</code> - Test Telegram</div>
    </body>
    </html>
    """
    return render_template_string(html)

@app.route('/analyze', methods=['GET'])
def analyze_endpoint():
    logger.info("Manual analysis triggered")
    result = analyze_gold()
    if "error" not in result:
        stats.record_analysis(success=True, signal=result.get('signal', {}).get('action', 'Unknown'))
    else:
        stats.record_analysis(success=False)
    return jsonify(result)

@app.route('/status')
def health_check():
    return jsonify({
        "status": "healthy",
        "service": "Gold Analyzer Bot",
        "version": "3.0",
        "timestamp": datetime.now().isoformat(),
        "uptime": stats.get_uptime(),
        "chat_ids_configured": len(TELEGRAM_CHAT_IDS)
    })

@app.route('/stats')
def get_statistics():
    return jsonify(stats.to_dict())

@app.route('/telegram/test')
def test_telegram():    message = f"Telegram Test Successful! Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    success = send_telegram_message(message)
    return jsonify({
        "success": success,
        "message": "Message sent!" if success else "Failed",
        "chat_ids_count": len(TELEGRAM_CHAT_IDS)
    })

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found", "status": 404}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {str(error)}")
    return jsonify({"error": "Internal server error", "status": 500}), 500

if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("GOLD ANALYZER BOT - Starting...")
    logger.info("=" * 60)
    logger.info(f"Version: 3.0 Final")
    logger.info(f"Analysis Interval: {ANALYSIS_INTERVAL} seconds")
    logger.info(f"Port: {PORT}")
    logger.info(f"Chat IDs: {len(TELEGRAM_CHAT_IDS)} configured")
    logger.info("=" * 60)
    
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not set")
    if not TELEGRAM_CHAT_IDS:
        logger.warning("TELEGRAM_CHAT_IDS not set")
    
    scheduler_thread = threading.Thread(target=scheduled_analysis_task, daemon=True)
    scheduler_thread.start()
    logger.info("Background scheduler started")
    
    try:
        logger.info(f"Starting Flask server on 0.0.0.0:{PORT}")
        app.run(host='0.0.0.0', port=PORT, debug=False)
    except Exception as e:
        logger.error(f"Failed to start server: {str(e)}")
        sys.exit(1)
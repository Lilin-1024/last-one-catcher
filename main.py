import requests
import json
import time
import re
import os

# ================= 1. 读取本地配置 =================
def load_config():
    config_path = 'config.json'
    if not os.path.exists(config_path):
        print("error：找不到 config.json 文件！请复制 config.example.json 并修改。")
        exit(1)
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

# 初始化配置
CONFIG = load_config()
WEBHOOK_URL = CONFIG["webhook_url"]
COOKIE = CONFIG["cookie"]
MIN_PROFIT = CONFIG.get("min_profit", 0) # 默认盈利阈值为 0
ITEMS_TO_MONITOR = CONFIG["items"]

# 固定的请求头
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Cookie": COOKIE,
    "Accept": "application/json, text/plain, */*"
}

# ================= 2. 核心功能 =================

def send_feishu_msg(content):
    """发送消息到飞书"""
    payload = {"msg_type": "text", "content": {"text": f"【last赏预警】\n{content}"}}
    try:
        requests.post(WEBHOOK_URL, json=payload, timeout=5)
    except Exception as e:
        print(f"发送飞书失败: {e}")

def extract_item_id(url):
    """用正则表达式从长链接中提取 itemsId"""
    match = re.search(r'itemsId=(\d+)', url)
    if match:
        return match.group(1)
    return None

def monitor_item(item_config):
    """检测单个商品的状态"""
    url = item_config["url"]
    last_prize_value = item_config["last_prize_value"]
    
    item_id = extract_item_id(url)
    if not item_id:
        print(f"❌ 无法从链接提取商品 ID: {url[:30]}...")
        return False

    api_url = f"https://mall.bilibili.com/mall-magic-cup/demo/info?itemsId={item_id}"
    
    try:
        response = requests.get(api_url, headers=HEADERS, timeout=10)
        res_data = response.json()
        
        if res_data.get("success"):
            data = res_data["data"]
            stock = int(data["stock"])
            price = float(data["price"])
            name = data["name"]
            
            total_cost = stock * price
            profit = last_prize_value - total_cost  # 计算当前预估利润
            
            print(f"[{time.strftime('%H:%M:%S')}] {name[:10]}... | 剩余: {stock}张 | 成本: {total_cost}元 | 当前利润: {profit}元")
            
            # 利润大于等于设定阈值报警
            if profit >= MIN_PROFIT:
                msg = (f"商品：{name}\n"
                       f"当前剩余：{stock} 张\n"
                       f"全收成本：{total_cost} 元\n"
                       f"Last赏预估：{last_prize_value} 元\n"
                       f"预估净利润：{profit} 元\n"
                       f"快去抄底！")
                send_feishu_msg(msg)
                return True
        else:
            print(f"[{item_id}] 请求失败: {res_data.get('message')} (可能是Cookie失效)")
            
    except Exception as e:
        print(f"[{item_id}] 网络请求出错: {e}")
    
    return False

# ================= 3. 运行主循环 =================

if __name__ == "__main__":
    print(f"启动监控，目标利润阈值 >= {MIN_PROFIT}元")
    print(f"共加载 {len(ITEMS_TO_MONITOR)} 个监控任务")
    
    while True:
        for item in ITEMS_TO_MONITOR:
            monitor_item(item)
            # 在监控不同商品之间加一点延迟，防止一瞬间请求太多次被B站拦截
            time.sleep(3) 
            
        print("--- 一轮检测结束，休息 30 秒 ---")
        time.sleep(30)
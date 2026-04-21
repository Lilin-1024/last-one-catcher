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
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json;charset=utf-8",
    "Origin": "https://mall.bilibili.com",
    "Referer": "https://mall.bilibili.com/"
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
    # 从配置中读取价值计算门槛，配置默认 100 元
    min_val_threshold = CONFIG.get("min_prize_value_to_count", 100)
    
    item_id = extract_item_id(url)
    if not item_id:
        print(f"error: 无法从链接提取商品 ID: {url[:30]}...")
        return False

    api_url = f"https://mall.bilibili.com/mall-ichiban-kuji/merchant_items/info?itemsId={item_id}"

    payload = {
        "itemsId": int(item_id),
        "boxId": item_config.get("boxId", 0),
        "switchType": 2,
        "skuId": ""
    }
    
    try:
        response = requests.post(api_url, headers=HEADERS, json=payload, timeout=10)
        res_data = response.json()
        
        #print(f"DEBUG: {res_data}")
        
        if res_data.get("success") or res_data.get("code") == 0:
            data = res_data.get("data")
            
            # --- 新增：安全检查，防止 data 为空导致崩溃 ---
            if data is None:
                print(f"[{item_id}] 警告：B站返回了成功状态，但没有返回商品数据 (data 为 null)！")
                return False
            # -----------------------------------------------
            
            stock = int(data.get("stock", 0))        # 当前剩余总抽数
            if stock == 0:
                print(f"[{item_id}] 盒子已售空，跳过。")
                return False
            response = requests.post(api_url, headers=HEADERS, json=payload, timeout=10)
        res_data = response.json()
        
        if res_data.get("success") or res_data.get("code") == 0:
            data = res_data.get("data")
            
            # --- 🛡️ 新增：安全检查，防止 data 为空导致崩溃 ---
            if data is None:
                print(f"[{item_id}] ⚠️ 警告：B站返回了成功状态，但没有返回商品数据 (data 为 null)！")
                return False
            # -----------------------------------------------
            
            stock = int(data.get("stock", 0))        # 当前剩余总抽数
            if stock == 0:
                print(f"[{item_id}] 盒子已售空，跳过。")
                return False

            ticket_price = float(data["price"]) # 单抽价格
            name = data["name"]
            total_cost = stock * ticket_price   # 核心计算：全收需要多少钱
            
            # --- 动态价值计算 ---
            total_prize_value = 0
            valuable_items_info = [] # 剩余物品
            
            sku_list = data.get("skuBoxGroupList", [])
            for sku in sku_list:
                item_name = sku.get("name", "未知赏品")
                item_stock = int(sku.get("stock", 0))
                group_name = sku.get("groupName", "")
                
                # null安全处理
                item_price_str = sku.get("price")
                item_price = float(item_price_str) if item_price_str else 0.0

                # Last赏处理
                if group_name == "Last赏":
                    total_prize_value += item_price
                    valuable_items_info.append(f"[Last赏] {item_name} (官价:{item_price})")
                    continue

                # 其他高价值赏品处理
                if item_stock > 0 and item_price >= min_val_threshold:
                    total_prize_value += (item_stock * item_price)
                    valuable_items_info.append(f"[剩{item_stock}个] {item_name} (官价:{item_price}/个)")

            # --- 最终盈亏判定 ---
            profit = total_prize_value - total_cost
            
            print(f"[{time.strftime('%H:%M:%S')}] {name[:8]}... | 剩余{stock}抽(成本:{total_cost}) | 高价值残值:{total_prize_value} | 利润:{profit}")
            
            # 判断逻辑：只要利润大于等于我们设定的阈值，就报警
            if profit >= MIN_PROFIT:
                items_str = "\n  ".join(valuable_items_info) if valuable_items_info else "只有 Last 赏"
                msg = (f"商品：{name}\n"
                       f"当前剩余：{stock} 张 (全收成本 {total_cost} 元)\n"
                       f"高级赏品总价值：{total_prize_value} 元\n"
                       f"预估净利润：{profit} 元\n\n"
                       f"包含好货：\n  {items_str}\n\n"
                       f"快捷链接：{url}")
                send_feishu_msg(msg)
                return True
        else:
            print(f"[{item_id}] 请求失败: {res_data.get('message')} (检查Cookie是否过期)")
            
    except Exception as e:
        print(f"[{item_id}] 网络请求出错: {e}")
    
    return False

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
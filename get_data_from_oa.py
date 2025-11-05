import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs, urlunparse, urlencode # 确保有 urlencode
import json
import os
import time
from datetime import datetime, timedelta

# --- DeepSeek V3 配置 ---

DEEPSEEK_API_KEY = 您的 DeepSeek API Key 应在此处填写
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions" 
DEEPSEEK_MODEL = "deepseek-chat"

# 包含分类体系和约束的系统提示词 (已优化优先级)
CLASSIFICATION_SYSTEM_PROMPT = '''
**【角色设定与核心任务】**
你是一个**高效、严谨**的信息分类系统，专注于根据**全新的核心分类体系**和**动态标签提取规则**，对校园新闻标题进行结构化标记。
**你的唯一任务**是：接收一个新闻标题列表，并严格依据后续规则，为列表中的每一个标题提供准确的分类，并以指定的 JSON 格式输出。

**【核心分类体系（Primary TAGs）】**
请**严格采用**以下 6 个标签作为一级分类的**唯一选项**：
1. **竞赛/奖学金**
2. **学校公共设施运营**
3. **学校公共考试与缴费**
4. **讲座/社团活动/学校活动/项目**
5. **科研信息**
6. **其它信息** (用于包含所有不属于前五类的标题，例如：老师招聘、财政公示、党政、领导讲话等)

**【标签提取与约束规则（Constraints）】**
1. **完整性检查**：必须返回与输入列表数量**完全相同**的分类结果。
2. **匹配字段**：每个结果对象必须包含原始的 **"新闻标题"** 字段。
3. **一级分类（Primary TAG）**：
    * **必须且只能**从【核心分类体系】中选择**一个**最能代表标题主题的标签。
4. **二级分类（Secondary TAG）**：
    * **数量限制**：**必须**提取 **1 到 5 个** 标签。**期望数量在 2 到 4 个之间。**
    * **动态提取原则**：
        * **提取目标：** 从标题中动态提取**核心的、具有区分度和重要性**的关键词或短语作为二级标签。
        * **必要话题（Inclusion）：** 选择用户关注的**关键主题/实体**，例如：赛事名称（蓝桥杯）、特定校区（南岭校区）、知名外部机构/学校（清华大学、英国）、重要人物、特定设备或系统名称等。
        * **非核心信息（Exclusion）：** 避免提取**通用、低区分度或背景性信息**，例如：学校名称（吉林大学）、当前年份（2025年度）、常见地点（长春市）、部门名称（如“教务处通知”）、通知形式（如“关于...”）。

**【JSON 输出格式】**
请**严格**返回一个 JSON 数组（`array of objects`）。

```json
[
  {
    "新闻标题": "原始标题1",
    "一级分类": "您选择的核心分类名称",
    "二级分类": [
      "AI从标题提取的第一个核心关键词/短语",
      "第二个核心关键词/短语",
      "第三个核心关键词/短语"
    ]
  },
  {
    "新闻标题": "原始标题2",
    "一级分类": "您选择的核心分类名称",
    "二级分类": [
      "AI从标题提取的第一个核心关键词/短语",
      "第二个核心关键词/短语",
      "第三个核心关键词/短语",
      "第四个核心关键词/短语"
    ]
  }
]
'''


# --- 爬虫配置信息 ---
BASE_URL = "https://oa.jlu.edu.cn/defaultroot/"
LIST_URL_TEMPLATE = BASE_URL + "PortalInformation!jldxList.action?channelId=179577&startPage={0}" 
DEFAULT_FILE_NAME = "jlu_oa_data.json"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.75 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3'
}

# --- 辅助函数 ---

def load_existing_data(filename):
    """加载已有的 JSON 数据，并转换为以【简化链接】为键的字典"""
    # 假设 simplify_jlu_oa_link 函数在全局可见
    
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                
                if isinstance(data, list):
                    # 初始化新的字典，使用简化链接作为键
                    unified_data = {}
                    
                    for item in data:
                        # 假设旧数据的链接在 "链接" 字段中
                        full_link_key = item.get("链接", "")
                        
                        if full_link_key:
                            # ⚠️ 核心修改：对旧数据的链接也进行简化处理
                            simplified_link = simplify_jlu_oa_link(full_link_key)
                            
                            # 确保 item 内部保存的也是简化链接（如果有需要）
                            item["链接"] = simplified_link
                            
                            unified_data[simplified_link] = item
                            
                    return unified_data # 返回使用简化链接作为键的字典
                
                # 如果旧数据已经是字典形式，则假设其键已是简化链接，直接返回
                return data 
                
            except json.JSONDecodeError:
                print(f"⚠️ 警告：文件 {filename} 内容格式错误，将忽略旧数据。")
                return {}
    return {}

def save_data_to_json(data, filename):
    """将数据保存到 JSON 文件，格式为列表，包含分类TAG"""
    data_list = []
    for link, item in data.items():
        output_item = {
            "新闻发布时间戳": item.get("新闻发布时间戳"),
            "新闻标题": item.get("新闻标题"),
            "发布单位": item.get("发布单位"),
            "一级分类TAG": item.get("一级分类TAG", "未分类"), 
            "二级分类TAG": item.get("二级分类TAG", ["未分类"]),
            "链接": link # 方便用户定位原始文章
        }
        data_list.append(output_item)
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)
    print(f"\n✅ 数据成功保存到 {filename}，共 {len(data_list)} 条记录。")



def classify_news_batch(titles, api_key, max_retries=3):
    """调用 DeepSeek V3 API 对批量新闻标题进行分类，并返回分类结果列表"""
    if not api_key or not titles:
        # 如果没有 API Key 或标题列表为空，返回默认的失败标签列表
        return [
            {"新闻标题": title, "一级分类": "未分类", "二级分类": ["未分类"]} 
            for title in titles
        ]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # 构造用户查询：包含所有待分类的标题
    titles_list_str = "\n".join([f"- {title}" for title in titles])
    user_query = f"请为以下 {len(titles)} 个新闻标题提供分类，并严格按照系统提示词中的 JSON 数组格式返回:\n{titles_list_str}"

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_query}
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"} 
    }
    
    print(f"    ➡️ DeepSeek V3 批量分类中... (共 {len(titles)} 条)")

    for attempt in range(max_retries):
        try:
            response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=45) # 延长超时时间以适应批量请求
            response.raise_for_status()

            result = response.json()
            content = result['choices'][0]['message']['content']
            
            # 解析 JSON 字符串
            classification_results = json.loads(content)
            
            # 确保返回的是一个列表，并且数量合理（至少大于0）
            if isinstance(classification_results, list) and len(classification_results) > 0:
                print(f"    ✅ 批量分类成功，收到 {len(classification_results)} 条结果。")
                return classification_results

        except requests.exceptions.RequestException as e:
            print(f"    ❌ API 请求失败 (尝试 {attempt + 1}/{max_retries})。")
        except (json.JSONDecodeError, KeyError) as e:
            print(f"    ❌ LLM 返回数据解析失败 (尝试 {attempt + 1}/{max_retries})，可能格式错误。")
        except Exception as e:
            print(f"    ❌ 发生未知错误 (尝试 {attempt + 1}/{max_retries}): {e}")

        # 指数退避 (Exponential Backoff)
        if attempt < max_retries - 1:
            wait_time = 2 ** attempt
            time.sleep(wait_time)
            
    print(f"    ❌ 批量分类失败，已达到最大重试次数。将使用 '分类失败' 标签。")
    # 失败时返回与输入数量匹配的 "分类失败" 列表
    return [
        {"新闻标题": title, "一级分类": "分类失败", "二级分类": ["分类失败"]} 
        for title in titles
    ]
def parse_time_string(time_str):
    """尝试将新闻时间字符串转换为 datetime 对象，支持多种格式（新增对“昨天”的支持）"""
    time_str = time_str.strip().replace('\xa0', ' ').replace('\u200e', '').replace('&nbsp;', ' ')
    now = datetime.now(tz=None)
    
    # 尝试所有已知的格式
    try:
        # 1. 假设 '今天 HH:MM' 格式
        if '今天' in time_str:
            time_part = time_str.split(' ')[-1]
            return datetime.strptime(f"{now.strftime('%Y-%m-%d')} {time_part}", '%Y-%m-%d %H:%M')

        # 1.5. 假设 '昨天 HH:MM' 格式
        if '昨天' in time_str:
            yesterday = now - timedelta(days=1)
            time_part = time_str.split(' ')[-1]
            return datetime.strptime(f"{yesterday.strftime('%Y-%m-%d')} {time_part}", '%Y-%m-%d %H:%M')

        # 2. 完整的 '年-月-日 时:分' 格式
        parts = time_str.split(' ')
        if len(parts) >= 2 and ':' in parts[-1]:
             return datetime.strptime(time_str, '%Y-%m-%d %H:%M') 

        # 3. 只有日期 '年-月-日' 格式 (设置默认时间为中午12点)
        date_part = time_str.split(' ')[0]
        if len(date_part.split('-')) == 3: # 确保是完整的年-月-日
            return datetime.strptime(date_part, '%Y-%m-%d').replace(hour=12) 

        # 4. 只有日期 '年/月/日' 格式 (设置默认时间为中午12点)
        date_part = time_str.split(' ')[0]
        if len(date_part.split('/')) == 3: # 确保是完整的年/月/日
            return datetime.strptime(date_part, '%Y/%m/%d').replace(hour=12) 
            
        # 5. 只有日期 '月-日' 或 '月/日' 格式 (针对置顶旧通知)
        date_part = time_str.split(' ')[0].replace('/', '-')
        if len(date_part.split('-')) == 2: # 检查是否为 M-D 或 MM-DD 格式
            parsed_date = datetime.strptime(f"{now.year}-{date_part}", '%Y-%m-%d').replace(hour=12)
            
            # **针对跨年/旧数据的健壮性修正**：如果解析出的日期在未来，则减去一年。
            if parsed_date > now + timedelta(days=30):
                return parsed_date.replace(year=now.year - 1)
                
            return parsed_date
            
    except ValueError:
        # 如果任何解析尝试失败，都将跳过当前逻辑块。
        pass
        
    # 兜底：如果所有解析逻辑都失败，返回一个极老的时间，保证类型为 datetime
    return datetime(1970, 1, 1, tzinfo=None)

# --- 辅助函数：简化链接的核心逻辑（提取出来方便维护） ---
def simplify_jlu_oa_link(full_link_original):
    """移除 JLU OA 链接中的 channelId 参数，生成可直接访问的简化链接"""
    simplified_link = full_link_original
    
    if '?' in full_link_original:
        try:
            parsed_url = urlparse(full_link_original)
            # 使用 parse_qs 解析查询参数，返回一个字典，值是列表
            query_params = parse_qs(parsed_url.query)
            
            # 移除 'channelId' 参数
            if 'channelId' in query_params:
                del query_params['channelId']
            
            # 重新构建查询字符串 (doseq=True 确保参数被正确编码)
            new_query = urlencode(query_params, doseq=True)
            
            # 重新构建完整的 URL
            simplified_link = urlunparse(parsed_url._replace(query=new_query))
        except Exception as e:
            # 如果解析出错，则使用原始链接作为后备
            print(f"⚠️ 警告：链接简化失败 ({e})，使用原始链接。")
            simplified_link = full_link_original
            
    return simplified_link


def fetch_news_data(start_page, end_page, max_date=None, delay=0.5, existing_keys=None, max_no_new_pages=10):
    """
    核心爬虫函数：按页码范围抓取新闻，并以页为单位进行批量分类。
    已应用：链接简化提前，确保去重和输出都使用简化链接。
    """
    # 确保依赖的全局变量可用（此处假设它们在文件中的其他位置已定义）
    global BASE_URL, LIST_URL_TEMPLATE, HEADERS, DEEPSEEK_API_KEY, MAX_LLM_BATCH_SIZE, parse_time_string

    new_data = {}
    if existing_keys is None:
        existing_keys = set()
    
    consecutive_no_new = 0
    
    try:
        MIN_VALID_DATE # 检查是否已定义
    except NameError:
        MIN_VALID_DATE = datetime(2000, 1, 1, tzinfo=None)
    
    # 定义连续多少条旧新闻就判断为进入历史区域
    MAX_CONSECUTIVE_OLD = 5
    # LLM 批量处理的最大大小
    MAX_LLM_BATCH_SIZE = 15 # 假设这个值在全局或函数外定义
    
    for page_num in range(start_page, end_page + 1):
        
        url = LIST_URL_TEMPLATE.format(page_num)
        print(f"\n🔄 正在抓取第 {page_num} 页: {url}")
        
        try:
            response = requests.get(url, headers=HEADERS, timeout=15)
            response.raise_for_status() 
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
        except requests.exceptions.RequestException as e:
            print(f"❌ 严重错误: HTTP/网络请求失败 (页码: {page_num})。错误信息: {e}")
            return new_data 

        items = soup.select('.list_box ul.list_li .li, .sub_ul .li, .sub_ul div.li') 
        
        if len(items) < 5 and page_num > start_page:
            print(f"🛑 第 {page_num} 页只找到 {len(items)} 条新闻，判断已达列表末尾或无效页面，停止循环。")
            break 
        elif not items and page_num == start_page:
            print(f"🚨 爬虫中断：第 {page_num} 页没有抓取到任何新闻列表项。")
            return new_data 

        page_new_entries_list = [] 
        page_news_count = 0
        stop_crawling_early = False
        consecutive_old_on_page = 0 

        # --- 第一阶段：抓取和去重 ---
        for item in items:
            title_tag = item.select_one('a') 
            org_tag = item.select_one('.column') 
            time_tag = item.select_one('.time') or item.select_one('.date') or item.select_one('span[style*="color"]') 
            if not time_tag:
                time_tag = item.select_one('span[style*="color:gray"]') 
            
            if title_tag:
                title = title_tag.get('title', title_tag.get_text(strip=True)).strip()
                link_relative = title_tag.get('href', '')
                
                # 1. 原始链接 (包含 channelId)
                full_link_original = urljoin(BASE_URL, link_relative) 
                
                # 2. 【核心修改】生成用于去重和输出的简化链接
                simplified_link = simplify_jlu_oa_link(full_link_original)

                # 3. 【去重检查】现在使用简化链接
                if simplified_link in existing_keys:
                    consecutive_old_on_page += 1
                    continue 
                
                # --- 提取其他信息 (保持不变) ---
                time_str = time_tag.get_text(strip=True) if time_tag else None
                organization = org_tag.get_text(strip=True) if org_tag else None

                if not time_str or not organization:
                    print(f"    ⚠️ 警告：跳过新闻 ({title})，缺少时间或发布单位。")
                    continue 

                pub_time = parse_time_string(time_str)
                
                if pub_time < MIN_VALID_DATE:
                    print(f"    🛑 警告：新闻 ({title}) 时间解析异常 ({pub_time.strftime('%Y-%m-%d %H:%M')})，跳过此条。")
                    continue 
                
                timestamp = int(pub_time.timestamp())

                # --- 增量更新模式的停止条件判断 (保持不变) ---
                if max_date and pub_time < max_date:
                    print(f"    ⚠️ 新闻发布时间 {pub_time.strftime('%Y-%m-%d %H:%M')} 早于截止日期。")
                    consecutive_old_on_page += 1
                    
                    if consecutive_old_on_page >= MAX_CONSECUTIVE_OLD:
                        print(f"    🛑 已连续 {MAX_CONSECUTIVE_OLD} 条新闻早于截止日期，标记提前停止。")
                        stop_crawling_early = True
                        break 
                    
                    continue 

                consecutive_old_on_page = 0 # 发现新数据，重置计数


                # 4. 暂存数据，使用简化后的链接作为输出和 new_data 的键
                page_new_entries_list.append({
                    "新闻标题": title,
                    "新闻发布时间戳": timestamp,
                    "发布单位": organization,
                    "链接": simplified_link # <--- 使用简化后的链接
                })
                # 将简化链接加入去重集合，供后续新闻检查
                existing_keys.add(simplified_link) 
                page_news_count += 1 
                
        # --- 第二阶段：LLM 批量分类和数据合并 ---
        if page_new_entries_list:
            
            total_new_on_page = len(page_new_entries_list)
            all_classification_results = []
            
            # 循环分割成小批量 (<= MAX_LLM_BATCH_SIZE) 进行分类
            for i in range(0, total_new_on_page, MAX_LLM_BATCH_SIZE):
                batch = page_new_entries_list[i:i + MAX_LLM_BATCH_SIZE]
                titles_to_classify = [item["新闻标题"] for item in batch]
                
                # 调用批量分类函数
                batch_classification_results = classify_news_batch(titles_to_classify, DEEPSEEK_API_KEY) 
                all_classification_results.extend(batch_classification_results)
                
                # 增加延迟，防止 DeepSeek API 频率限制 (可选，但推荐)
                if len(batch) == MAX_LLM_BATCH_SIZE:
                    time.sleep(1.5) 

            
            classified_titles_map = {item['新闻标题']: item for item in all_classification_results}
            
            newly_added_count = 0
            for item in page_new_entries_list:
                simplified_link_key = item["链接"]
                title = item["新闻标题"]
                
                classification = classified_titles_map.get(title)
                
                if classification:
                    item["一级分类TAG"] = classification.get("一级分类", "分类失败")
                    item["二级分类TAG"] = classification.get("二级分类", ["分类失败"])
                else:
                    item["一级分类TAG"] = "分类失败"
                    item["二级分类TAG"] = ["分类失败"]
                
                # 键为 simplified_link_key，与 existing_keys 和 main 函数中的合并键保持一致
                new_data[simplified_link_key] = item
                
                newly_added_count += 1
            
            if DEEPSEEK_API_KEY:
                print(f"    ✅ DeepSeek V3 分类完成，本页新增 {newly_added_count} 条记录。")
            else:
                print(f"    ℹ️ 未启用 DeepSeek V3 分类。本页新增 {newly_added_count} 条记录。")


        elif page_news_count == 0:
            print("    ℹ️ 本页无新记录，无需分类。")
            
        # --- 第三阶段：停止逻辑 (保持不变) ---
        if page_news_count == 0:
            consecutive_no_new += 1
            if consecutive_no_new >= max_no_new_pages:
                print(f"🛑 已连续 {max_no_new_pages} 页无新增新闻（可能是列表末尾或旧数据），停止循环。")
                break
        else:
            consecutive_no_new = 0
            
        if stop_crawling_early:
            print(f"🛑 提前停止：由于遇到连续旧数据，停止下一页抓取。")
            break
            
        print(f"👍 第 {page_num} 页抓取完成，共新增 {page_news_count} 条记录。")

        # 模式 1 的最大页码限制
        if page_num >= 10 and max_date:
            print("🚨 自动模式已达到最大抓取页数（10页），停止循环。")
            break
            
        time.sleep(delay)

    return new_data

# --- 主程序入口 ---

# --- 主程序入口 ---

def main():
    print("--- 吉林大学校内通知爬虫程序 (含 DeepSeek V3 批量分类) ---")
    
    if not DEEPSEEK_API_KEY:
        print("\n🚨 警告：未设置 DEEPSEEK_API_KEY，新闻将不包含分类标签。")
    else:
        print("\n✅ DeepSeek V3 API Key 已加载，将启用批量分类功能。")

    print("\n请选择查询模式：")
    print("1. 自动模式：查询最近7天(不超过10页)内容，并增量更新到 jlu_oa_data.json")
    print("2. 自定义模式：自定义抓取范围和文件名")

    mode = '1'#input("请输入模式编号 (1 或 2)：")
    print("自动选择了自动模式！")

    if mode == '1':
        # --- 模式 1: 自动增量更新 ---
        filename = DEFAULT_FILE_NAME
        # ⚠️ load_existing_data 现在返回的是以简化链接为键的字典
        existing_news_dict = load_existing_data(filename)
        # ⚠️ existing_keys 集合现在包含的是简化链接，与 fetch_news_data 的去重逻辑一致
        existing_keys = set(existing_news_dict.keys()) 
        seven_days_ago = datetime.now(tz=None) - timedelta(days=7) 
        
        print(f"\n--- 模式 1: 自动增量更新 ---")
        print(f"目标文件: {filename} (包含 {len(existing_keys)} 条旧记录)")
        print(f"抓取范围: 追溯到 {seven_days_ago.strftime('%Y-%m-%d %H:%M')} 的新闻 (最多 10 页)")
        
        new_entries = fetch_news_data(
            start_page=1, 
            end_page=10, 
            max_date=seven_days_ago, 
            delay=1.0, 
            existing_keys=existing_keys
        ) 
        
        if new_entries is not None:
            # ⚠️ 合并时，由于 new_entries 和 existing_news_dict 的键都是简化链接，合并将准确无误。
            combined_data = {**existing_news_dict, **new_entries}
            print(f"\n✨ 本次执行新增新闻 {len(new_entries)} 条。")
            save_data_to_json(combined_data, filename)



    else:
        print("输入无效的模式编号，程序退出。")

if __name__ == "__main__":
    main()



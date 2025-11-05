import sqlite3
import json
import time
import os

# --- 配置文件 ---
DATABASE_NAME = 'jlu_oa_announcements.db'
JSON_FILE_PATH = 'jlu_oa_data.json' # 请确保此路径正确
TABLE_NAME = 'announcements'

# --- 1. 数据库表结构定义 ---
# 注意：我们将 '二级分类TAG' 存储为 JSON 字符串，方便查询和存储

CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    -- 1. 列定义
    timestamp INTEGER NOT NULL,  
    title TEXT NOT NULL,
    unit TEXT NOT NULL,
    tag_primary TEXT NOT NULL,
    tags_secondary_json TEXT,       
    link TEXT NOT NULL,            
    update_time INTEGER,            
    
    -- 2. 约束定义 (link 保证唯一性和主键性)
    PRIMARY KEY (link) 
);
"""

def get_db_connection():
    """建立数据库连接"""
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row # 允许以字典方式访问列
    return conn

def setup_database(conn):
    """创建表结构"""
    cursor = conn.cursor()
    cursor.execute(CREATE_TABLE_SQL)
    conn.commit()
    print(f"数据库 {DATABASE_NAME} 表 {TABLE_NAME} 准备就绪。")

def load_json_data(file_path):
    """从 JSON 文件加载数据"""
    if not os.path.exists(file_path):
        print(f"错误：未找到 JSON 文件：{file_path}")
        return None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except json.JSONDecodeError:
        print(f"错误：JSON 文件格式不正确：{file_path}")
        return None
    except Exception as e:
        print(f"加载 JSON 文件时发生未知错误: {e}")
        return None

def update_announcements(conn, json_data):
    """清空旧数据并插入新数据（全量更新模式）"""
    if not json_data:
        print("无数据或数据加载失败，跳过数据库更新。")
        return

    cursor = conn.cursor()
    
    # --- 开始事务 ---
    conn.execute("BEGIN TRANSACTION")
    try:
        # 1. 清空现有数据 (全量更新)
        cursor.execute(f"DELETE FROM {TABLE_NAME}")
        print("已清空旧数据。")

        # 2. 准备批量插入的数据
        records_to_insert = []
        current_time = int(time.time())
        
        for item in json_data:
            # 将二级 TAG 列表转换为 JSON 字符串以便存储
            tags_secondary_str = json.dumps(item.get("二级分类TAG", []), ensure_ascii=False)
            
            records_to_insert.append((
                item["新闻发布时间戳"],
                item["新闻标题"],
                item["发布单位"],
                item["一级分类TAG"],
                tags_secondary_str,
                item["链接"],
                current_time
            ))

        # 3. 批量插入新数据
        insert_sql = f"""
        INSERT INTO {TABLE_NAME} VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        cursor.executemany(insert_sql, records_to_insert)

        # 4. 提交事务
        conn.commit()
        print(f"成功导入 {len(records_to_insert)} 条新公告。")
        
    except sqlite3.Error as e:
        conn.rollback()
        print(f"数据库操作失败，已回滚事务: {e}")
    finally:
        cursor.close()

def main():
    """主执行函数"""
    print("--- 公告数据库更新脚本启动 ---")
    
    # 1. 建立数据库连接
    conn = get_db_connection()
    
    # 2. 确保表结构存在
    setup_database(conn)
    
    # 3. 加载最新的 JSON 数据
    data = load_json_data(JSON_FILE_PATH)
    
    # 4. 更新数据库
    update_announcements(conn, data)
    
    # 5. 关闭连接
    conn.close()
    print("--- 脚本执行完毕 ---")

if __name__ == "__main__":
    # --- ！！！ 模拟 JSON 文件生成 ！！！ ---
    # 仅为测试目的，如果您本地已有 jlu_oa_data.json，请注释掉这段
    if not os.path.exists(JSON_FILE_PATH):
        print("正在生成模拟 JSON 文件...")
        mock_data = [
            {
                "新闻发布时间戳": 1762246800,
                "新闻标题": "关于公示2025年度本科生“吉林银行奖（励）学金”拟获奖（资助）人员名单的通知",
                "发布单位": "党委学生工作部、党委武装部",
                "一级分类TAG": "竞赛/奖学金",
                "二级分类TAG": ["吉林银行奖学金", "本科生", "拟获奖人员"],
                "链接": "https://oa.jlu.edu.cn/link1"
            },
            {
                "新闻发布时间戳": 1762088400,
                "新闻标题": "2026年春季学期交换生项目选拔规则调整（教务）",
                "发布单位": "教务处",
                "一级分类TAG": "通知公告",
                "二级分类TAG": ["国际交流", "选拔", "在校生"],
                "链接": "https://oa.jlu.edu.cn/link2"
            }
        ]
        with open(JSON_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(mock_data, f, ensure_ascii=False, indent=4)
        print("模拟 JSON 文件已创建。")
    # --- ！！！ 模拟 JSON 文件生成 ！！！ ---
    
    main()

from flask import Flask, jsonify, request, render_template
import sqlite3
import json
import time
from flask_cors import CORS  # <--- 1. 导入 CORS

app = Flask(__name__)
CORS(app)  # <--- 2. 启用 CORS，允许所有源 (用于开发)

# --- 数据库配置 ---
DATABASE_NAME = 'jlu_oa_announcements.db'
TABLE_NAME = 'announcements'

def get_db_connection():
    """建立数据库连接，并设置行工厂为字典模式"""
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row # 使得查询结果可以像字典一样访问
    return conn

def date_from_timestamp(timestamp):
    """将时间戳转换为 YYYY-MM-DD 格式"""
    return time.strftime("%Y-%m-%d", time.localtime(timestamp))

def serialize_announcement(row):
    """将数据库行对象序列化为前端需要的格式"""
    return {
        "timestamp": row['timestamp'],
        "date": date_from_timestamp(row['timestamp']),
        "title": row['title'],
        "unit": row['unit'],
        "tag_primary": row['tag_primary'],
        "tags_secondary": json.loads(row['tags_secondary_json']), # 反序列化二级TAGs
        "link": row['link']
    }

# ====================================================================
# I. /api/announcements 核心接口实现
# ====================================================================

@app.route('/api/announcements', methods=['GET'])
def get_announcements():
    # --- 1. 获取请求参数 ---
    page = request.args.get('page', 1, type=int)
    size = request.args.get('size', 20, type=int)
    sort = request.args.get('sort', 'time_desc', type=str)
    unit = request.args.get('unit', type=str)
    tags = request.args.get('tags', type=str)
    keyword = request.args.get('keyword', type=str)

    conn = get_db_connection()
    cursor = conn.cursor()

    # --- 2. 构建 WHERE 查询条件和参数 ---
    where_clauses = []
    params = []

    # 关键词搜索：匹配标题或单位
    if keyword:
        where_clauses.append("(title LIKE ? OR unit LIKE ?)")
        params.extend([f"%{keyword}%", f"%{keyword}%"])

    # 单位筛选
    if unit:
        where_clauses.append("unit = ?")
        params.append(unit)

    # TAG 筛选：匹配一级TAG或二级TAG (模糊匹配 JSON 字符串)
    if tags:
        tag_list = tags.split(',')
        tag_conditions = []
        for tag in tag_list:
            # 匹配一级TAG 或 二级TAGs JSON 字符串 (OR 逻辑)
            tag_conditions.append(f"(tag_primary = ? OR tags_secondary_json LIKE ?)")
            params.extend([tag, f"%\"{tag}\"%"]) # 二级TAG在JSON中带有引号

        where_clauses.append("(" + " AND ".join(tag_conditions) + ")")


    where_sql = " AND ".join(where_clauses)
    if where_sql:
        where_sql = " WHERE " + where_sql

    # --- 3. 排序逻辑 ---
    order_sql = "ORDER BY timestamp DESC"
    if sort == 'time_asc':
        order_sql = "ORDER BY timestamp ASC"

    # --- 4. 分页逻辑 ---
    offset = (page - 1) * size
    limit_sql = f"LIMIT {size} OFFSET {offset}"

    # --- 5. 执行查询 ---
    # a. 查询总数
    count_query = f"SELECT COUNT(*) FROM {TABLE_NAME} {where_sql}"
    cursor.execute(count_query, params)
    total_items = cursor.fetchone()[0]

    # b. 查询当前页数据
    data_query = f"SELECT * FROM {TABLE_NAME} {where_sql} {order_sql} {limit_sql}"
    announcements_rows = cursor.execute(data_query, params).fetchall()

    conn.close()

    # --- 6. 整理和返回结果 ---
    announcements_list = [serialize_announcement(row) for row in announcements_rows]
    total_pages = (total_items + size - 1) // size

    return jsonify({
        "code": 200,
        "message": "Success",
        "data": {
            "currentPage": page,
            "pageSize": size,
            "totalPages": total_pages,
            "totalItems": total_items,
            "announcements": announcements_list
        }
    })

# ====================================================================
# II. /api/filters 筛选条件接口实现
# ====================================================================

@app.route('/api/filters', methods=['GET'])
def get_filters():
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. 统计发布单位 (Unit)
    # 按照单位分组，并计算每个单位的公告数量
    units_query = f"SELECT unit, COUNT(unit) as count FROM {TABLE_NAME} GROUP BY unit ORDER BY count DESC"
    units_result = cursor.execute(units_query).fetchall()
    
    units_list = [{"name": row['unit'], "count": row['count']} for row in units_result]

    # 2. 统计一级 TAG
    tags_primary_query = f"SELECT tag_primary, COUNT(tag_primary) as count FROM {TABLE_NAME} GROUP BY tag_primary ORDER BY count DESC"
    tags_primary_result = cursor.execute(tags_primary_query).fetchall()
    
    tags_primary_list = [{"name": row['tag_primary'], "count": row['count']} for row in tags_primary_result]
    
    # 3. 统计所有二级 TAG (复杂，需要先解析所有记录)
    secondary_tag_counts = {}
    all_secondary_tags_query = f"SELECT tags_secondary_json FROM {TABLE_NAME}"
    all_tags_rows = cursor.execute(all_secondary_tags_query).fetchall()
    
    for row in all_tags_rows:
        try:
            tags = json.loads(row['tags_secondary_json'])
            for tag in tags:
                secondary_tag_counts[tag] = secondary_tag_counts.get(tag, 0) + 1
        except json.JSONDecodeError:
            continue # 忽略格式错误
            
    # 排序并取 Top N 作为热门 TAG (假设取前 5 个)
    tags_secondary_sorted = sorted(secondary_tag_counts.items(), key=lambda item: item[1], reverse=True)
    tags_secondary_top = [{"name": tag[0], "count": tag[1]} for tag in tags_secondary_sorted] # 如果需要限制数量，在这里切片 [0:5]

    conn.close()

    return jsonify({
        "code": 200,
        "message": "Success",
        "data": {
            "units": units_list,
            "tags_primary": tags_primary_list,
            "tags_secondary_all": tags_secondary_top # 返回全部，前端决定如何显示 Top N
        }
    })

@app.route('/oa')
def announcements():
    # 查找 templates/announcements.html 并渲染它
    return render_template('announcements.html')

if __name__ == '__main__':
    # 生产环境中应使用 Gunicorn/uWSGI 等服务器
    # 仅用于本地开发测试：
    print("Flask API 服务器启动中...")
    # 默认运行在 http://127.0.0.1:5000/
    # 启动前请确保运行了 update_db.py 生成数据库文件
    app.run(debug=True)

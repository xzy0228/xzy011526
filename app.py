import streamlit as st
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
from tavily import TavilyClient
import openai


# --- 1. 初始化与北京时间修正 ---
def get_beijing_time():
    # 自动处理本地(Local)与云端(UTC)的时差
    return datetime.utcnow() + timedelta(hours=8)


CURRENT_DATE = get_beijing_time().strftime("%Y-%m-%d")
CURRENT_TIME = get_beijing_time().strftime("%H:%M:%S")

st.set_page_config(page_title="QuantMind Pro", page_icon="🔵", layout="wide")

# API 初始化
try:
    tavily = TavilyClient(api_key=st.secrets["TAVILY_API_KEY"])
    client = openai.OpenAI(api_key=st.secrets["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
except:
    st.error("API Key 未配置")

# --- 2. 核心 CSS 优化 (蓝色按钮、对齐布局) ---
st.markdown(f"""
    <style>
    /* 1. 蓝色大按钮 */
    div.stButton > button {{
        background-color: #0066FF !important;
        color: white !important;
        width: 100%;
        height: 50px;
        border-radius: 8px;
        font-weight: bold;
        border: none;
        font-size: 18px !important;
    }}
    /* 2. 研报卡片专业质感 */
    .report-card {{
        background: white;
        padding: 30px;
        border-radius: 15px;
        border: 1px solid #E5E7EB;
        line-height: 1.8;
        box-shadow: 0 4px 12px rgba(0,0,0,0.05);
    }}
    /* 3. 数据卡片布局 */
    .metric-card {{
        background: #F9FAFB;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #F3F4F6;
        text-align: center;
    }}
    .metric-label {{ color: #6B7280; font-size: 14px; }}
    .metric-value {{ color: #111827; font-size: 22px; font-weight: bold; }}
    </style>
    """, unsafe_allow_html=True)


# --- 3. 极速数据引擎 (本地慢的主要原因就在这) ---
@st.cache_data(ttl=86400)  # 股票代码表缓存一天，大幅提升本地速度
def load_code_map():
    try:
        # 获取个股名称的最快方式
        df = ak.stock_info_a_code_name()
        return dict(zip(df['code'], df['name']))
    except:
        return {}


def get_fast_stock_data(code):
    """优化后的极速数据调取"""
    try:
        # 1. 快速匹配名称 (优先从缓存读取)
        code_map = load_code_map()
        name = code_map.get(code, "未知个股")

        # 2. 仅获取最近的 K 线 (限制日期范围是加速关键)
        start_day = (datetime.now() - timedelta(days=90)).strftime("%Y%m%d")
        df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start_day, adjust="qfq")

        if df.empty: return None, "未能获取到数据，请检查代码"

        last = df.iloc[-1]
        df['MA5'] = df['收盘'].rolling(5).mean()
        df['MA10'] = df['收盘'].rolling(10).mean()

        return {
                   "name": name,
                   "price": last['收盘'],
                   "pct": last['涨跌幅'],
                   "vol": f"{last['成交额'] / 1e8:.2f}亿",
                   "df": df.tail(40)  # 只保留最近40天用于绘图
               }, None
    except Exception as e:
        return None, str(e)


# --- 4. 主界面布局 ---
st.markdown(f"## 🤖 QuantMind Pro <small style='font-size:14px; color:gray;'>北京时间: {CURRENT_TIME}</small>",
            unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["🔍 深度诊股", "🔥 宏观内参", "📂 历史记录"])

with tab1:
    if st.session_state.get('view_report'):
        # 回看历史
        rec = st.session_state['view_report']
        if st.button("⬅️ 返回搜索"):
            st.session_state['view_report'] = None
            st.rerun()
        st.markdown(f"### {rec['name']} ({rec['code']}) 历史研报")
        st.markdown(f'<div class="report-card">{rec["report"]}</div>', unsafe_allow_html=True)
    else:
        # 搜索框
        stock_code = st.text_input("输入股票代码 (如: 600519)", value="600519")

        # 按钮放在下方 + 蓝色样式
        if st.button("🚀 立即深度分析"):
            with st.status("🚀 正在极速连接交易所数据...", expanded=True) as status:
                data, err = get_fast_stock_data(stock_code)
                if err:
                    st.error(err)
                else:
                    st.markdown(f"### {data['name']} ({stock_code})")

                    # 1. 数据行
                    c1, c2, c3, c4 = st.columns(4)
                    metrics = [("最新价", f"¥{data['price']}"), ("涨跌幅", f"{data['pct']}%"),
                               ("成交额", data['vol']), ("更新时间", CURRENT_TIME)]
                    for i, (l, v) in enumerate(metrics):
                        with [c1, c2, c3, c4][i]:
                            st.markdown(
                                f'<div class="metric-card"><div class="metric-label">{l}</div><div class="metric-value">{v}</div></div>',
                                unsafe_allow_html=True)

                    # 2. 趋势图
                    st.line_chart(data['df'].set_index('日期')[['收盘', 'MA5', 'MA10']])

                    # 3. AI 研报 (使用优化后的 Prompt)
                    st.divider()
                    st.markdown("#### 📝 AI 深度投资研究报告")
                    report_placeholder = st.empty()
                    full_report = ""

                    status.update(label="🧠 AI 正在进行逻辑推演...", state="running")

                    # 联网搜索
                    search_query = f"{CURRENT_DATE} {data['name']} 核心基本面 深度分析"
                    search_res = tavily.search(query=search_query, max_results=3)
                    context = "\n".join([r['content'] for r in search_res['results']])

                    # 注入今日日期，防止 AI 穿越
                    prompt = f"""
                    今天是 {CURRENT_DATE}。你是资深首席分析师。针对 {data['name']}({stock_code})，现价{data['price']}元。
                    基于资讯：{context}
                    撰写一份极具洞察力的研报。拒绝废话和套话。
                    一、核心资讯解读：分析背后的深层战略意图。
                    二、利好与风险评估：对基本面的实质影响。
                    三、操作建议与逻辑：给出明确结论（增持/中性/减持）。
                    """

                    stream = client.chat.completions.create(
                        model="deepseek-chat",
                        messages=[{"role": "user", "content": prompt}],
                        stream=True
                    )

                    for chunk in stream:
                        if chunk.choices[0].delta.content:
                            full_report += chunk.choices[0].delta.content
                            report_placeholder.markdown(f'<div class="report-card">{full_report}</div>',
                                                        unsafe_allow_html=True)

                    # 存入历史
                    st.session_state['history'].insert(0, {
                        "name": data['name'], "code": stock_code, "report": full_report, "time": CURRENT_TIME
                    })
                    status.update(label="✅ 分析完成", state="complete")

# 后面两个 Tab 保持简洁结构...
with tab2:
    st.info("宏观数据将在每日 9:30 自动同步。")

with tab3:
    for i, item in enumerate(st.session_state.get('history', [])):
        col1, col2 = st.columns([4, 1])
        col1.write(f"**{item['name']}** - {item['time']}")
        if col2.button("回看", key=f"h_{i}"):
            st.session_state['view_report'] = item
            st.rerun()
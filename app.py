import streamlit as st
import akshare as ak
import pandas as pd
from datetime import datetime
from tavily import TavilyClient
import openai

# --- 1. 全局配置与状态初始化 ---
st.set_page_config(page_title="QuantMind Pro", page_icon="🔵", layout="wide")

# 初始化 session_state
if 'history' not in st.session_state:
    st.session_state['history'] = []
if 'view_report' not in st.session_state:
    st.session_state['view_report'] = None

# 初始化 API 客户端
try:
    tavily = TavilyClient(api_key=st.secrets["TAVILY_API_KEY"])
    client = openai.OpenAI(api_key=st.secrets["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
except Exception as e:
    st.error("⚠️ API Key 配置未找到，请在 secrets.toml 或部署后台中配置 TAVILY_API_KEY 和 DEEPSEEK_API_KEY")
    st.stop()

# --- 2. 增强型 CSS ---
st.markdown("""
    <style>
    /* 研报卡片 */
    .report-card { background-color: #ffffff; padding: 25px; border-radius: 15px; border: 1px solid #e2e8f0; line-height: 1.8; color: #1e293b; }
    /* 章节标题 */
    .section-title { color: #1e3a8a; border-left: 5px solid #1e3a8a; padding-left: 10px; margin: 20px 0 10px 0; font-weight: bold; }
    /* 每日推荐卡片 */
    .recommend-box { background-color: #f8fafc; border-radius: 12px; padding: 15px; border-left: 5px solid #10b981; margin-bottom: 20px; }
    /* 标签 */
    .policy-tag { background: #dbeafe; color: #1e40af; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }
    /* 历史记录条目 */
    .history-item { background: white; padding: 15px; border-radius: 10px; margin-bottom: 10px; border: 1px solid #f1f5f9; display: flex; align-items: center; justify-content: space-between; }

    /* 界面优化 */
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] { font-size: 18px; font-weight: 600; padding: 10px 20px; }
    .stTextInput input { font-size: 18px; padding: 12px; }
    </style>
    """, unsafe_allow_html=True)


# --- 3. 核心功能函数 ---
@st.cache_data(ttl=3600)
def get_stock_name(code):
    try:
        df = ak.stock_info_a_code_name()
        res = df[df['code'] == code]
        if not res.empty: return res['name'].values[0]
        # 兜底
        spot = ak.stock_zh_a_spot_em()
        res_spot = spot[spot['代码'] == code]
        if not res_spot.empty: return res_spot.iloc[0]['名称']
        return "未知股票"
    except:
        return "未知股票"


def get_stock_details(code):
    try:
        name = get_stock_name(code)
        df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date="20251001", adjust="qfq")
        if df.empty: return None, "未找到该股票数据"

        last = df.iloc[-1]
        return {
                   "名称": name,
                   "代码": code,
                   "价格": last['收盘'],
                   "涨跌幅": last['涨跌幅'],
                   "成交额": f"{last['成交额'] / 1e8:.1f}亿",
                   "历史": df
               }, None
    except:
        return None, "数据源繁忙或代码错误"


def get_deep_analysis_stream(name, code, price, context):
    prompt = f"""
    角色：资深量化策略分析师。
    任务：分析股票 {name}({code})，现价{price}元。
    资讯：{context}

    请输出一份专业研报，包含：
    1. 【核心逻辑】：分析资讯背后的深层战略或供需变化。
    2. 【利好/利空】：分点评估对基本面的影响。
    3. 【操作建议】：给出评级（买入/持有/卖出）及理由。
    """
    return client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        stream=True
    )


@st.cache_data(ttl=1800)
def get_macro_market_insight():
    try:
        query = "2026年1月15日 中国股市 宏观政策 行业利好 热点趋势"
        search = tavily.search(query=query, max_results=5)
        context = "\n".join([r['content'] for r in search['results']])

        prompt = f"基于以下资讯：{context}，请总结：\n1.今日核心政策解读(100字内)。\n2.三个最具潜力的行业板块及逻辑。"
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}]
        )
        return resp.choices[0].message.content, search
    except:
        return "暂时无法获取宏观数据", []


# --- 4. 页面布局 ---
st.markdown("<h1 style='color: #1e3a8a;'>🤖 QuantMind Pro 智能投研平台</h1>", unsafe_allow_html=True)
tab1, tab2, tab3 = st.tabs(["🔍 深度诊股", "🔥 宏观内参", "📂 历史记录"])

# === Tab 1: 深度诊疗 (核心逻辑) ===
# === Tab 1: 深度诊疗 ===
with tab1:
    if st.session_state['view_report']:
        record = st.session_state['view_report']
        st.info(f"🕒 您正在查看历史存档：生成于 {record['time']}")
        if st.button("⬅️ 返回搜索模式"):
            st.session_state['view_report'] = None
            st.rerun()

        st.markdown(f"### {record['name']} ({record['code']}) - 历史研报")
        st.markdown(f'<div class="report-card">{record["report"]}</div>', unsafe_allow_html=True)

    else:
        c1, c2 = st.columns([1, 2])
        with c1:
            stock_code = st.text_input("代码", value="600519", key="search_input", label_visibility="collapsed")
        with c2:
            analyze_btn = st.button("🚀 立即分析", use_container_width=False)

        if analyze_btn:
            res, err = get_stock_details(stock_code)
            if err:
                st.error(err)
            else:  # <--- 确保这里与 if err: 对齐
                st.markdown(f"### {res['名称']} ({stock_code})")
                cols = st.columns(4)
                cols[0].metric("最新价", f"¥{res['价格']}")
                cols[1].metric("涨跌幅", f"{res['涨跌幅']}%")
                cols[2].metric("成交额", res['成交额'])
                cols[3].metric("时间", datetime.now().strftime("%H:%M"))

                with st.expander("📈 价格走势图", expanded=True):
                    df_plot = res['历史'].tail(60).set_index('日期')
                    st.line_chart(df_plot[['收盘']])

                st.divider()
                st.markdown("#### 📝 AI 深度研报 (实时生成)")
                report_placeholder = st.empty()
                full_report = ""

                with st.status("AI 正在联网分析中...", expanded=True) as status:
                    search_res = tavily.search(query=f"2026年1月15日 {res['名称']} 深度分析", max_results=3)
                    ctx = "\n".join([r['content'] for r in search_res['results']])

                    stream = get_deep_analysis_stream(res['名称'], stock_code, res['价格'], ctx)
                    for chunk in stream:
                        if chunk.choices[0].delta.content:
                            content = chunk.choices[0].delta.content
                            full_report += content
                            report_placeholder.markdown(f'<div class="report-card">{full_report}</div>',
                                                        unsafe_allow_html=True)

                    # 存入历史
                    st.session_state['history'].insert(0, {
                        'code': stock_code,
                        'name': res['名称'],
                        'time': datetime.now().strftime("%m-%d %H:%M"),
                        'report': full_report
                    })
                    status.update(label="✅ 分析完成", state="complete")

# === Tab 2: 每日推荐 ===
with tab2:
    if st.button("🔄 获取今日市场宏观内参", type="primary"):
        with st.spinner("正在扫描全市场..."):
            insight, _ = get_macro_market_insight()

            c_left, c_right = st.columns([3, 2])
            with c_left:
                st.markdown("#### 📜 宏观与行业洞察")
                st.info(insight)

            with c_right:
                st.markdown("#### 🚀 今日异动热榜")
                top_df = ak.stock_zh_a_spot_em().sort_values(by='涨跌幅', ascending=False).head(3)
                for _, row in top_df.iterrows():
                    st.markdown(f"""
                    <div class="recommend-box">
                        <div style="font-weight:bold; color:#1e3a8a">{row['名称']} ({row['代码']})</div>
                        <div style="display:flex; justify-content:space-between; margin-top:5px">
                            <span>现价: ¥{row['最新价']}</span>
                            <span style="color:#ef4444; font-weight:bold">+{row['涨跌幅']}%</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

# === Tab 3: 历史记录 (修复版) ===
with tab3:
    st.markdown("### 📂 您的投研足迹")
    if not st.session_state['history']:
        st.write("暂无记录，请去【深度诊股】进行分析。")
    else:
        for i, item in enumerate(st.session_state['history']):
            # 使用 container 布局每一行
            with st.container():
                col1, col2, col3 = st.columns([2, 2, 1])
                col1.markdown(f"**{item['name']}**")
                col2.caption(f"生成时间: {item['time']}")
                # 关键：这里点击后更新 session_state 并 rerun
                if col3.button("📄 回看", key=f"hist_btn_{i}"):
                    st.session_state['view_report'] = item
                    st.rerun()  # 强制刷新，Tab 1 会捕捉到 view_report 状态
            st.divider()

# 侧边栏
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/10473/10473523.png", width=50)
    st.title("QuantMind Pro")
    st.info("版本: v1.0.0 (生产环境版)")
    if st.button("清除所有历史"):
        st.session_state['history'] = []
        st.rerun()
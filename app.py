import streamlit as st
import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from tavily import TavilyClient
import openai

# --- 1. 初始化 ---
if 'history' not in st.session_state:
    st.session_state['history'] = []
if 'view_report' not in st.session_state:
    st.session_state['view_report'] = None


def get_beijing_time():
    return datetime.utcnow() + timedelta(hours=8)


# 获取当前日期和时间
CURRENT_DATE = get_beijing_time().strftime("%Y-%m-%d")
CURRENT_TIME = get_beijing_time().strftime("%H:%M:%S")

st.set_page_config(page_title="QuantMind Pro", page_icon="🔵", layout="wide")

# API 初始化
try:
    tavily = TavilyClient(api_key=st.secrets["TAVILY_API_KEY"])
    client = openai.OpenAI(api_key=st.secrets["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
except:
    st.error("API Key 未配置，请检查 Streamlit Secrets")

# --- 2. 核心 CSS 样式 ---
st.markdown(f"""
    <style>
    div.stButton > button {{
        background-color: #0066FF !important;
        color: white !important;
        width: 100%;
        border-radius: 8px;
        font-weight: bold;
        border: none;
        height: 45px;
    }}
    .report-card {{
        background: white; padding: 25px; border-radius: 12px; border: 1px solid #E5E7EB;
        line-height: 1.8; box-shadow: 0 4px 10px rgba(0,0,0,0.05); color: #1F2937;
    }}
    .metric-card {{
        background: #F9FAFB; padding: 12px; border-radius: 10px; border: 1px solid #F3F4F6; text-align: center;
    }}
    .tech-label {{ color: #1E40AF; font-size: 14px; font-weight: bold; }}
    .tech-value {{ color: #B91C1C; font-size: 18px; font-weight: bold; }}
    </style>
    """, unsafe_allow_html=True)


# --- 3. 增强版极速数据引擎 ---
@st.cache_data(ttl=86400)
def load_code_map():
    try:
        df = ak.stock_info_a_code_name()
        return dict(zip(df['code'], df['name']))
    except:
        return {}


def calculate_technical_indicators(df):
    high = df['最高'].max()
    low = df['最低'].min()
    delta = df['收盘'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-9)
    rsi = 100 - (100 / (1 + rs)).iloc[-1]
    diff = high - low
    return {
        "支撑位": round(low + diff * 0.382, 2),
        "压力位": round(low + diff * 0.618, 2),
        "RSI": round(rsi, 2)
    }


def get_stock_data(code):
    try:
        code_map = load_code_map()
        name = code_map.get(code, "未知")
        start_day = (datetime.now() - timedelta(days=120)).strftime("%Y%m%d")
        df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start_day, adjust="qfq")
        if df.empty: return None, "无数据"
        last = df.iloc[-1]
        df['MA5'] = df['收盘'].rolling(5).mean()
        df['MA20'] = df['收盘'].rolling(20).mean()
        tech = calculate_technical_indicators(df)
        return {
                   "name": name, "price": last['收盘'], "pct": last['涨跌幅'],
                   "vol": f"{last['成交额'] / 1e8:.2f}亿", "df": df.tail(60), "tech": tech
               }, None
    except Exception as e:
        return None, str(e)


# --- 4. 主界面渲染 ---
st.markdown(f"## 🤖 QuantMind Pro <small style='font-size:14px; color:gray;'>实时版 | {CURRENT_TIME}</small>",
            unsafe_allow_html=True)

tab1, tab2, tab3, tab4, tab5 = st.tabs(["🔍 深度诊股", "⚡ 实时内参", "⚖️ 股票 PK", "🔥 宏观推荐", "📂 历史记录"])

# === Tab 1: 深度诊股 (保持不变) ===
with tab1:
    if st.session_state.get('view_report'):
        rec = st.session_state['view_report']
        if st.button("⬅️ 返回"): st.session_state['view_report'] = None; st.rerun()
        st.markdown(f"### {rec['name']} ({rec['code']}) 研报")
        st.markdown(f'<div class="report-card">{rec["report"]}</div>', unsafe_allow_html=True)
    else:
        stock_code = st.text_input("代码", value="600519")
        if st.button("🚀 开始深度分析", key="analyze"):
            data, err = get_stock_data(stock_code)
            if err:
                st.error(err)
            else:
                st.markdown(f"### {data['name']} ({stock_code})")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("现价", f"¥{data['price']}", f"{data['pct']}%")
                c2.metric("成交额", data['vol'])
                c3.markdown(
                    f'<div class="metric-card"><div class="tech-label">支撑 / 压力</div><div class="tech-value">{data["tech"]["支撑位"]} / {data["tech"]["压力位"]}</div></div>',
                    unsafe_allow_html=True)
                c4.markdown(
                    f'<div class="metric-card"><div class="tech-label">RSI(14)强弱</div><div class="tech-value">{data["tech"]["RSI"]}</div></div>',
                    unsafe_allow_html=True)
                st.line_chart(data['df'].set_index('日期')[['收盘', 'MA5', 'MA20']])

                report_area = st.empty()
                full_report = ""
                with st.spinner("AI 正在结合技术面与资讯推演..."):
                    # 搜索优化：限制结果数和搜索深度
                    search_res = tavily.search(query=f"{CURRENT_DATE} {data['name']} 最新利好利空分析", max_results=3,
                                               search_depth="basic")
                    ctx = "\n".join([r['content'] for r in search_res['results']])
                    prompt = f"你是首席分析师。股票{data['name']}, 现价{data['price']}, RSI为{data['tech']['RSI']}。资讯: {ctx}。请简要提供：1. 资讯深意；2. 技术面简评；3. 操盘建议。"

                    stream = client.chat.completions.create(model="deepseek-chat",
                                                            messages=[{"role": "user", "content": prompt}], stream=True)
                    for chunk in stream:
                        if chunk.choices[0].delta.content:
                            full_report += chunk.choices[0].delta.content
                            report_area.markdown(f'<div class="report-card">{full_report}</div>',
                                                 unsafe_allow_html=True)
                st.session_state['history'].insert(0, {"name": data['name'], "code": stock_code, "report": full_report,
                                                       "time": CURRENT_TIME})

# === Tab 2: ⚡ 实时内参 (极速优化版) ===
with tab2:
    st.markdown("### ⚡ 实时全网热点与行业趋势")
    industry_input = st.text_input("输入关注领域(如：低空经济、AI、半导体)", value="大盘")
    if st.button("🔍 抓取最新情报"):
        # 第一步：快速检索 (使用 basic 深度提高速度)
        with st.status("🚀 正在检索最新动态...", expanded=True) as s:
            q = f"{CURRENT_DATE} {industry_input} 行业利好 政策消息"
            res = tavily.search(query=q, max_results=3, search_depth="basic")
            ctx = "\n".join([r['content'] for r in res['results']])
            s.update(label="✅ 资讯检索完成，AI 正在分析中...", state="complete")

        # 第二步：流式输出
        st.markdown("#### 📑 核心资讯深度解析")
        report_p = st.empty()
        full_p = ""

        # 精简 Prompt 提升 AI 响应速度
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "user", "content": f"基于以下资讯，用 bullet points 总结{industry_input}的3个核心利好逻辑，并点名2只潜力股：\n{ctx}"}],
            stream=True
        )
        for chunk in resp:
            if chunk.choices[0].delta.content:
                full_p += chunk.choices[0].delta.content
                report_p.markdown(f'<div class="report-card">{full_p}</div>', unsafe_allow_html=True)

# === Tab 3: ⚖️ 股票 PK (流式增强版) ===
with tab3:
    st.markdown("### ⚖️ 股票对比分析")
    pc1, pc2 = st.columns(2)
    code_a = pc1.text_input("股票 A 代码", "600519", key="pk_a")
    code_b = pc2.text_input("股票 B 代码", "000858", key="pk_b")

    if st.button("🆚 开始对比"):
        with st.spinner("获取实时行情数据..."):
            da, erra = get_stock_data(code_a)
            db, errb = get_stock_data(code_b)

        if not erra and not errb:
            comparison_df = pd.DataFrame({
                "指标": ["现价", "涨跌幅", "成交额", "支撑位", "RSI"],
                da['name']: [da['price'], f"{da['pct']}%", da['vol'], da['tech']['支撑位'], da['tech']['RSI']],
                db['name']: [db['price'], f"{db['pct']}%", db['vol'], db['tech']['支撑位'], db['tech']['RSI']]
            })
            st.table(comparison_df)

            st.markdown("#### 🗣️ AI 首席点评")
            pk_area = st.empty()
            full_pk = ""

            # 使用流式输出，让对比逻辑一点点跳出来
            resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user",
                           "content": f"对比：{da['name']} (RSI:{da['tech']['RSI']}) 与 {db['name']} (RSI:{db['tech']['RSI']})。根据技术面和博弈角度，简短说明哪只更有性价比。"}],
                stream=True
            )
            for chunk in resp:
                if chunk.choices[0].delta.content:
                    full_pk += chunk.choices[0].delta.content
                    pk_area.markdown(f'<div class="report-card">{full_pk}</div>', unsafe_allow_html=True)
        else:
            st.error("无法获取对比数据，请检查代码输入是否正确")

# === Tab 4 & 5 (保持不变) ===
with tab4:
    st.info("💡 每日 9:30 同步 macro 简报。您也可以通过 '实时内参' 获取即时讯息。")
with tab5:
    for i, item in enumerate(st.session_state.get('history', [])):
        c1, c2 = st.columns([4, 1])
        c1.write(f"**{item['name']}** - {item['time']}")
        if c2.button("回看", key=f"hist_{i}"):
            st.session_state['view_report'] = item
            st.rerun()
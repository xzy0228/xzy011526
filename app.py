import streamlit as st
import akshare as ak
import pandas as pd
from datetime import datetime
from tavily import TavilyClient
import openai

# --- 1. 全局配置与状态初始化 ---
st.set_page_config(page_title="QuantMind Pro", page_icon="🔵", layout="wide")

# 初始化 Session State
if 'history' not in st.session_state:
    st.session_state['history'] = []
if 'view_report' not in st.session_state:
    st.session_state['view_report'] = None

# 初始化 API (异常处理)
try:
    tavily = TavilyClient(api_key=st.secrets["TAVILY_API_KEY"])
    client = openai.OpenAI(api_key=st.secrets["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
except Exception as e:
    st.error(f"⚠️ API Key 配置缺失: {e}")
    st.stop()

# --- 2. 深度专业版 Prompt (拒绝废话) ---
# 这是你觉得分析得最好的那个版本的逻辑核心
ANALYSIS_PROMPT = """
你是一位顶级券商（如中金、中信）的首席策略分析师。请针对股票 {name} ({code})，现价 {price} 元，结合以下资讯进行深度研判。

【分析原则】：
1. 拒绝空话：不要说“受市场波动影响”等通用废话，必须挖掘具体的供需变化、政策传导路径或企业战略意图。
2. 逻辑闭环：从“现象”推导“本质”。例如：削减渠道配额 -> 厂家回收利润 -> 增强品牌定价权。

【报告格式】（必须严格遵守）：
一、核心资讯解读
   [深度解析资讯背后的战略意图或宏观信号]
二、基本面与利空利好评估
   [利好]：...
   [利空]：...
三、估值与市场位置分析
   [结合现价分析PE/PB位置，以及安全边际]
四、综合结论与操作建议
   [给出明确评级（买入/增持/观望），并说明中长期逻辑]

【参考资讯】：
{context}
"""

# --- 3. 增强型 CSS (找回大气的 UI) ---
st.markdown("""
    <style>
    /* 全局背景 */
    .main { background-color: #f8fafc; }

    /* 研报卡片 - 模拟纸质质感 */
    .report-card { 
        background-color: #ffffff; 
        padding: 30px; 
        border-radius: 12px; 
        border: 1px solid #e2e8f0; 
        box-shadow: 0 4px 6px rgba(0,0,0,0.02);
        line-height: 1.8; 
        color: #1e293b; 
        font-size: 16px;
    }

    /* 指标卡片 - 顶部蓝条 */
    .metric-card {
        background-color: #ffffff; 
        padding: 20px; 
        border-radius: 10px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04); 
        border-top: 4px solid #1e3a8a;
        text-align: center;
    }
    .metric-value { color: #1e3a8a; font-size: 24px; font-weight: 800; margin-top: 4px; }
    .metric-label { color: #64748b; font-size: 14px; }

    /* 输入框与按钮放大 */
    .stTextInput input { font-size: 18px !important; padding: 12px !important; }
    div.stButton > button { font-size: 18px !important; padding: 10px 24px !important; font-weight: 600 !important; }

    /* Tabs 标签页放大 */
    .stTabs [data-baseweb="tab"] { font-size: 18px; font-weight: 600; padding: 10px 20px; }

    /* 推荐卡片 */
    .rec-box { background: white; padding: 20px; border-radius: 12px; border-left: 5px solid #10b981; margin-bottom: 15px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)


# --- 4. 核心数据函数 (带缓存与防错) ---
@st.cache_data(ttl=3600)
def get_stock_name(code):
    try:
        # 优先查实时接口，准确率高
        spot = ak.stock_zh_a_spot_em()
        res = spot[spot['代码'] == code]
        if not res.empty: return res.iloc[0]['名称']
        # 兜底
        df = ak.stock_info_a_code_name()
        res_cache = df[df['code'] == code]
        if not res_cache.empty: return res_cache['name'].values[0]
        return "未知股票"
    except:
        return "未知股票"


def get_stock_details(code):
    try:
        name = get_stock_name(code)
        # 获取 K 线数据
        df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date="20251001", adjust="qfq")
        if df.empty: return None, "未找到该股票行情数据"

        # 计算均线 (简单计算，无需额外库，手机兼容性好)
        df['MA5'] = df['收盘'].rolling(5).mean()
        df['MA10'] = df['收盘'].rolling(10).mean()

        last = df.iloc[-1]
        return {
                   "名称": name,
                   "代码": code,
                   "价格": last['收盘'],
                   "涨跌幅": last['涨跌幅'],
                   "成交额": f"{last['成交额'] / 1e8:.2f}亿",
                   "历史": df  # 返回完整 DF 供绘图用
               }, None
    except Exception as e:
        return None, f"数据源响应异常: {str(e)}"


# --- 5. 功能逻辑区 ---
@st.cache_data(ttl=1800)
def get_market_scan():
    """获取宏观政策与异动股"""
    try:
        # 1. 宏观政策搜索
        q = "2026年1月15日 中国股市 宏观利好 行业政策"
        search = tavily.search(query=q, max_results=4)
        ctx = "\n".join([r['content'] for r in search['results']])

        # 2. AI 总结
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": f"基于资讯简要总结今日A股核心宏观政策风向(100字内)：\n{ctx}"}]
        )
        policy = resp.choices[0].message.content

        # 3. 异动股抓取
        spot = ak.stock_zh_a_spot_em()
        top_3 = spot.sort_values(by='涨跌幅', ascending=False).head(3)

        return policy, top_3
    except:
        return "数据获取中...", pd.DataFrame()


# --- 6. 页面 UI 构建 ---
st.markdown("<h1 style='color: #1e3a8a; font-weight: 800;'>🤖 QuantMind Pro 智能投研</h1>", unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["🔍 深度诊股", "🔥 每日内参", "📂 历史记录"])

# === Tab 1: 深度诊疗 (你的核心诉求) ===
with tab1:
    # 逻辑分支：回看模式 vs 搜索模式
    if st.session_state['view_report']:
        # [回看模式]
        record = st.session_state['view_report']
        st.info(f"🕒 历史存档：生成于 {record['time']}")

        if st.button("⬅️ 返回搜索模式", type="secondary"):
            st.session_state['view_report'] = None
            st.rerun()

        st.markdown(f"### {record['name']} ({record['code']})")
        # 使用 markdown 渲染 HTML 样式的卡片
        st.markdown(f'<div class="report-card">{record["report"]}</div>', unsafe_allow_html=True)

    else:
        # [搜索模式]
        c1, c2 = st.columns([2, 1])
        with c1:
            stock_code = st.text_input("请输入股票代码", value="600519", label_visibility="collapsed", placeholder="例如 600519")
        with c2:
            st.markdown("<div style='height: 4px'></div>", unsafe_allow_html=True)  # 微调对齐
            analyze_btn = st.button("🚀 立即分析", use_container_width=True, type="primary")

        if analyze_btn:
            with st.spinner("正在连接交易所数据..."):
                res, err = get_stock_details(stock_code)

            if err:
                st.error(err)
            else:
                # 1. 基本面卡片 (4列布局)
                st.markdown(f"### {res['名称']} ({stock_code})")
                m1, m2, m3, m4 = st.columns(4)
                metrics = [
                    ("最新价", f"¥{res['价格']}"),
                    ("涨跌幅", f"{res['涨跌幅']}%"),
                    ("成交额", res['成交额']),
                    ("时间", datetime.now().strftime("%H:%M"))
                ]
                for i, (label, val) in enumerate(metrics):
                    with [m1, m2, m3, m4][i]:
                        st.markdown(f"""
                        <div class="metric-card">
                            <div class="metric-label">{label}</div>
                            <div class="metric-value">{val}</div>
                        </div>
                        """, unsafe_allow_html=True)

                # 2. 走势图 (防报错优化版)
                st.markdown("#### 📈 价格走势 (MA5/MA10)")
                with st.expander("点击展开/折叠图表", expanded=True):
                    # 仅选取必要的数值列进行绘图，避免复杂对象导致手机端 structuredClone 报错
                    chart_data = res['历史'].set_index('日期')[['收盘', 'MA5', 'MA10']]
                    st.line_chart(chart_data, color=["#1e3a8a", "#f59e0b", "#10b981"])

                # 3. AI 深度研报 (核心)
                st.divider()
                st.markdown("#### 📝 AI 深度投资研究报告")
                report_area = st.empty()
                full_report = ""

                with st.status("AI 正在全网检索深度资讯...", expanded=True) as status:
                    # 搜索
                    try:
                        q = f"2026年1月15日 {res['名称']} 深度研报 行业基本面"
                        search = tavily.search(query=q, max_results=4)
                        context = "\n".join([r['content'] for r in search['results']])

                        # 生成
                        stream = client.chat.completions.create(
                            model="deepseek-chat",
                            messages=[{"role": "user", "content": ANALYSIS_PROMPT.format(
                                name=res['名称'], code=stock_code, price=res['价格'], context=context
                            )}],
                            stream=True
                        )

                        for chunk in stream:
                            if chunk.choices[0].delta.content:
                                txt = chunk.choices[0].delta.content
                                full_report += txt
                                report_area.markdown(f'<div class="report-card">{full_report}</div>',
                                                     unsafe_allow_html=True)

                        # 自动归档
                        new_record = {
                            'code': stock_code, 'name': res['名称'],
                            'time': datetime.now().strftime("%m-%d %H:%M"),
                            'report': full_report
                        }
                        st.session_state['history'].insert(0, new_record)
                        status.update(label="✅ 深度研报生成完毕", state="complete")

                    except Exception as e:
                        st.error(f"AI 生成中断: {e}")

# === Tab 2: 每日内参 ===
with tab2:
    st.subheader("📢 市场宏观与机会")
    if st.button("🔄 刷新今日数据"):
        with st.spinner("AI 正在扫描全市场..."):
            policy, top_stocks = get_market_scan()

            # 政策部分
            st.info(f"📜 **今日宏观风向**：\n{policy}")

            # 异动个股
            st.markdown("#### 🚀 异动榜前三")
            cols = st.columns(3)
            for i, (idx, row) in enumerate(top_stocks.iterrows()):
                with cols[i]:
                    st.markdown(f"""
                    <div class="rec-box">
                        <h3 style="margin:0;color:#1e3a8a">{row['名称']}</h3>
                        <p style="color:#666">{row['代码']}</p>
                        <div style="font-size:20px;color:#ef4444;font-weight:bold">+{row['涨跌幅']}%</div>
                        <p>现价: {row['最新价']}</p>
                    </div>
                    """, unsafe_allow_html=True)

# === Tab 3: 历史记录 ===
with tab3:
    st.subheader("📂 您的投研足迹")
    if not st.session_state['history']:
        st.write("暂无记录，快去 Tab 1 体验深度分析吧！")
    else:
        for i, item in enumerate(st.session_state['history']):
            with st.container():
                c1, c2, c3 = st.columns([3, 2, 1])
                c1.markdown(f"**{item['name']}** ({item['code']})")
                c2.caption(item['time'])
                # 点击回看，触发 Rerun 跳转回 Tab 1
                if c3.button("📄 回看", key=f"h_{i}"):
                    st.session_state['view_report'] = item
                    st.rerun()
            st.divider()
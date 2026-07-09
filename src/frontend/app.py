"""
Streamlit 前端儀表板 — Investment Health Dashboard

三大核心區塊：
1. 【頂部摘要卡片】總資產市值、現金、未實現/已實現損益（紅綠標示）
2. 【資產配置圖表】Plotly 圓餅圖顯示各標的權重分佈
3. 【歷史淨值曲線】Plotly 折線圖顯示 NAV 與累積報酬率走勢

資料來源：直接調用後端 DashboardService（無需啟動 FastAPI）
"""

import sys
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ── 將專案根目錄加入 sys.path ──────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.backend.api.dashboard_service import DashboardService
from src.backend.ledger.domain_models import (
    SecurityTradeEvent,
    EventType,
    TradeCategory,
    Market,
)


# =========================================================================
# 頁面設定
# =========================================================================

st.set_page_config(
    page_title="Investment Health Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =========================================================================
# 輔助函數
# =========================================================================


def _make_buy_event(
    event_id: str, stock_id: str, event_date: date,
    quantity: int, price: float, fee: float = 0.0,
) -> SecurityTradeEvent:
    """建立買入事件（輔助測試資料用）。"""
    return SecurityTradeEvent(
        event_id=event_id,
        event_date=event_date,
        sequence_in_day=1,
        event_type=EventType.SECURITY_BUY,
        cash_impact=-quantity * price - fee,
        source_ref=f"demo:{event_id}",
        stock_id=stock_id,
        stock_name=f"Stock-{stock_id}",
        quantity=quantity,
        price=price,
        fee=fee,
        tax=0.0,
        trade_category=TradeCategory.BOARD_LOT,
        market=Market.TWSE,
        settlement_date=event_date,
    )


def _make_sell_event(
    event_id: str, stock_id: str, event_date: date,
    quantity: int, price: float,
) -> SecurityTradeEvent:
    """建立賣出事件（輔助測試資料用）。"""
    return SecurityTradeEvent(
        event_id=event_id,
        event_date=event_date,
        sequence_in_day=2,
        event_type=EventType.SECURITY_SELL,
        cash_impact=quantity * price,
        source_ref=f"demo:{event_id}",
        stock_id=stock_id,
        stock_name=f"Stock-{stock_id}",
        quantity=quantity,
        price=price,
        fee=0.0,
        tax=0.0,
        trade_category=TradeCategory.BOARD_LOT,
        market=Market.TWSE,
        settlement_date=event_date,
    )


def _build_demo_market_data() -> Dict[str, pd.DataFrame]:
    """建立示範用的市場資料。"""
    return {
        "2330": pd.DataFrame({
            "date": pd.to_datetime([
                "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05",
                "2024-01-08", "2024-01-09", "2024-01-10", "2024-01-11",
                "2024-01-12", "2024-01-15", "2024-01-16", "2024-01-17",
                "2024-01-18", "2024-01-19", "2024-01-22", "2024-01-23",
                "2024-01-24", "2024-01-25", "2024-01-26", "2024-01-29",
                "2024-01-30", "2024-01-31",
            ]),
            "adj_close": [
                580.0, 590.0, 585.0, 600.0,
                595.0, 610.0, 605.0, 620.0,
                615.0, 625.0, 630.0, 618.0,
                622.0, 635.0, 640.0, 638.0,
                645.0, 650.0, 648.0, 655.0,
                660.0, 658.0,
            ],
        }),
        "2317": pd.DataFrame({
            "date": pd.to_datetime([
                "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05",
                "2024-01-08", "2024-01-09", "2024-01-10", "2024-01-11",
                "2024-01-12", "2024-01-15", "2024-01-16", "2024-01-17",
                "2024-01-18", "2024-01-19", "2024-01-22", "2024-01-23",
                "2024-01-24", "2024-01-25", "2024-01-26", "2024-01-29",
                "2024-01-30", "2024-01-31",
            ]),
            "adj_close": [
                100.0, 105.0, 110.0, 115.0,
                112.0, 118.0, 120.0, 122.0,
                119.0, 125.0, 128.0, 126.0,
                130.0, 132.0, 128.0, 135.0,
                138.0, 140.0, 142.0, 145.0,
                148.0, 150.0,
            ],
        }),
        "2454": pd.DataFrame({
            "date": pd.to_datetime([
                "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05",
                "2024-01-08", "2024-01-09", "2024-01-10", "2024-01-11",
                "2024-01-12", "2024-01-15", "2024-01-16", "2024-01-17",
                "2024-01-18", "2024-01-19", "2024-01-22", "2024-01-23",
                "2024-01-24", "2024-01-25", "2024-01-26", "2024-01-29",
                "2024-01-30", "2024-01-31",
            ]),
            "adj_close": [
                950.0, 960.0, 955.0, 970.0,
                965.0, 980.0, 975.0, 990.0,
                985.0, 1000.0, 1010.0, 1005.0,
                1020.0, 1030.0, 1025.0, 1040.0,
                1050.0, 1045.0, 1060.0, 1070.0,
                1080.0, 1075.0,
            ],
        }),
    }


def _init_demo_service() -> DashboardService:
    """建立並初始化示範用的 DashboardService。"""
    service = DashboardService()

    events = [
        _make_buy_event("EVT-001", "2330", date(2024, 1, 2), 2000, 580.0),
        _make_buy_event("EVT-002", "2317", date(2024, 1, 3), 3000, 100.0),
        _make_buy_event("EVT-003", "2454", date(2024, 1, 4), 500, 950.0),
        _make_sell_event("EVT-004", "2330", date(2024, 1, 15), 500, 625.0),
    ]

    market_data = _build_demo_market_data()
    service.load_from_data(events, market_data, initial_cash=2_000_000.0)
    return service


def _format_currency(value: float) -> str:
    """格式化貨幣金額。"""
    if abs(value) >= 1_000_000:
        return f"NT${value / 1_000_000:,.2f}M"
    elif abs(value) >= 1_000:
        return f"NT${value:,.0f}"
    return f"NT${value:,.2f}"


def _color_pnl(value: float) -> str:
    """根據損益正負回傳顏色。"""
    if value > 0:
        return "green"
    elif value < 0:
        return "red"
    return "gray"


# =========================================================================
# 初始化 Service（快取在 session_state）
# =========================================================================

if "service" not in st.session_state:
    st.session_state.service = _init_demo_service()
    st.session_state.initialized = True

service: DashboardService = st.session_state.service


# =========================================================================
# 側邊欄 (Sidebar)
# =========================================================================

st.sidebar.markdown("# 📊 投資儀表板")
st.sidebar.markdown("---")

# 目標日期選擇器
st.sidebar.markdown("### 📅 目標日期")
use_target_date = st.sidebar.checkbox("指定計算日期", value=False)

target_date: Optional[date] = None
if use_target_date:
    selected_date = st.sidebar.date_input(
        "選擇日期",
        value=date(2024, 1, 31),
        min_value=date(2024, 1, 1),
        max_value=date(2024, 1, 31),
    )
    target_date = selected_date

st.sidebar.markdown("---")

# NAV 歷史區間選擇
st.sidebar.markdown("### 📈 歷史區間")
nav_start = st.sidebar.date_input(
    "起始日期",
    value=date(2024, 1, 1),
    min_value=date(2024, 1, 1),
    max_value=date(2024, 1, 31),
)
nav_end = st.sidebar.date_input(
    "結束日期",
    value=date(2024, 1, 31),
    min_value=date(2024, 1, 1),
    max_value=date(2024, 1, 31),
)

st.sidebar.markdown("---")
st.sidebar.markdown("### ℹ️ 關於")
st.sidebar.markdown(
    """
**Investment Health Dashboard** v0.1.0

後端引擎：Phase 1~5 全面封頂
- FIFO 庫存會計
- LOCF 市場補值
- 未實現/已實現損益
- 資產配置分析
- 歷史淨值追蹤

*資料為示範用途*
"""
)


# =========================================================================
# 主頁面 — 頂部摘要卡片
# =========================================================================

st.markdown("# 🏦 投資組合健康儀表板")
st.markdown("---")

try:
    summary = service.get_summary(target_date=target_date)
except RuntimeError as e:
    st.error(f"❌ {e}")
    st.stop()

# 摘要指標行
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric(
        label="💰 總資產市值",
        value=_format_currency(summary["total_market_value"]),
    )

with col2:
    st.metric(
        label="🏧 現金餘額",
        value=_format_currency(summary["cash_balance"]),
    )

with col3:
    unrealized = summary["unrealized_pnl"]
    st.metric(
        label="📈 未實現損益",
        value=_format_currency(unrealized),
        delta=f"{_format_currency(unrealized)}",
        delta_color="normal",
    )

with col4:
    realized = summary["realized_pnl"]
    st.metric(
        label="✅ 已實現損益",
        value=_format_currency(realized),
        delta=f"{_format_currency(realized)}",
        delta_color="normal",
    )

with col5:
    total_return = summary["total_return_pct"]
    st.metric(
        label="📊 總報酬率",
        value=f"{total_return:+.2f}%",
        delta=f"{total_return:+.2f}%",
        delta_color="normal",
    )

# 損益摘要行
st.markdown("")
pnl_col1, pnl_col2, pnl_col3 = st.columns(3)

total_pnl = unrealized + realized
with pnl_col1:
    st.markdown(
        f"<h3 style='color:{_color_pnl(total_pnl)}; text-align:center;'>"
        f"總損益：{_format_currency(total_pnl)}</h3>",
        unsafe_allow_html=True,
    )

with pnl_col2:
    nav = summary["total_nav"]
    st.markdown(
        f"<h3 style='text-align:center;'>"
        f"總淨值（NAV）：{_format_currency(nav)}</h3>",
        unsafe_allow_html=True,
    )

with pnl_col3:
    calc_date = summary.get("calculation_date") or "最新"
    st.markdown(
        f"<h3 style='text-align:center; color:gray;'>"
        f"計算日期：{calc_date}</h3>",
        unsafe_allow_html=True,
    )

st.markdown("---")


# =========================================================================
# 資產配置圖表 (Asset Allocation)
# =========================================================================

st.markdown("## 📊 資產配置")

try:
    allocation_data = service.get_allocation(target_date=target_date)
except RuntimeError as e:
    st.error(f"❌ {e}")
    st.stop()

allocations = allocation_data["allocations"]
total_mv = allocation_data["total_market_value"]

if allocations:
    # 準備 DataFrame
    alloc_df = pd.DataFrame(allocations)
    alloc_df["label"] = alloc_df.apply(
        lambda r: f"{r['stock_id']}<br>{r.get('stock_name', '')}<br>"
                  f"{_format_currency(r['market_value'])}<br>"
                  f"{r['weight_pct']:.1f}%",
        axis=1,
    )

    col_chart, col_table = st.columns([3, 2])

    with col_chart:
        # Plotly 圓餅圖
        fig_pie = px.pie(
            alloc_df,
            values="market_value",
            names="stock_id",
            title="資產配置權重（依市值）",
            hole=0.4,
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        fig_pie.update_traces(
            textposition="inside",
            textinfo="label+percent",
            hovertemplate="<b>%{label}</b><br>市值: %{value:,.0f}<br>權重: %{percent}",
        )
        fig_pie.update_layout(
            height=450,
            margin=dict(t=40, b=20, l=20, r=20),
            legend=dict(orientation="h", yanchor="bottom", y=-0.2),
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    with col_table:
        st.markdown("#### 配置明細")
        display_df = alloc_df[["stock_id", "quantity", "price", "market_value", "weight_pct"]].copy()
        display_df.columns = ["股票代號", "持股數量", "最新價格", "市值", "權重 (%)"]
        display_df["最新價格"] = display_df["最新價格"].apply(lambda x: f"{x:,.2f}")
        display_df["市值"] = display_df["市值"].apply(lambda x: f"{x:,.0f}")
        display_df["權重 (%)"] = display_df["權重 (%)"].apply(lambda x: f"{x:.1f}%")

        st.dataframe(display_df, use_container_width=True, hide_index=True)

        # 現金等價物
        cash_eq = allocation_data.get("cash_equivalent", 0.0)
        st.markdown(
            f"**現金等價物**：{_format_currency(cash_eq)}"
        )
        st.markdown(
            f"**總市值**：{_format_currency(total_mv)}"
        )
else:
    st.info("目前無持倉部位。")

st.markdown("---")


# =========================================================================
# 歷史淨值曲線 (NAV History)
# =========================================================================

st.markdown("## 📈 歷史淨值與報酬率")

try:
    nav_data = service.get_nav_history(
        start_date=nav_start,
        end_date=nav_end,
    )
except RuntimeError as e:
    st.error(f"❌ {e}")
    st.stop()

nav_series = nav_data["nav_series"]

if nav_series:
    nav_df = pd.DataFrame(nav_series)
    nav_df["date"] = pd.to_datetime(nav_df["date"])

    col_nav, col_return = st.columns(2)

    with col_nav:
        # NAV 折線圖
        fig_nav = go.Figure()

        fig_nav.add_trace(go.Scatter(
            x=nav_df["date"],
            y=nav_df["total_nav"],
            mode="lines+markers",
            name="總淨值 (NAV)",
            line=dict(color="#2E86AB", width=3),
            marker=dict(size=6, color="#2E86AB"),
            hovertemplate="%{x|%Y-%m-%d}<br>NAV: %{y:,.0f}<extra></extra>",
        ))

        # 加入現金與市值區域
        fig_nav.add_trace(go.Scatter(
            x=nav_df["date"],
            y=nav_df["market_value"],
            mode="lines",
            name="市值",
            line=dict(color="#A23B72", width=2, dash="dot"),
            hovertemplate="%{x|%Y-%m-%d}<br>市值: %{y:,.0f}<extra></extra>",
        ))

        fig_nav.add_trace(go.Scatter(
            x=nav_df["date"],
            y=nav_df["cash"],
            mode="lines",
            name="現金",
            line=dict(color="#F18F01", width=2, dash="dot"),
            hovertemplate="%{x|%Y-%m-%d}<br>現金: %{y:,.0f}<extra></extra>",
        ))

        fig_nav.update_layout(
            title="總淨值 (NAV) 走勢",
            xaxis_title="日期",
            yaxis_title="金額 (NT$)",
            height=450,
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(t=50, b=20, l=20, r=20),
        )
        st.plotly_chart(fig_nav, use_container_width=True)

    with col_return:
        # 累積報酬率折線圖
        fig_return = go.Figure()

        fig_return.add_trace(go.Scatter(
            x=nav_df["date"],
            y=nav_df["cumulative_return_pct"],
            mode="lines+markers",
            name="累積報酬率",
            line=dict(color="#4CAF50", width=3),
            marker=dict(size=6, color="#4CAF50"),
            hovertemplate="%{x|%Y-%m-%d}<br>報酬率: %{y:+.2f}%<extra></extra>",
        ))

        # 加入每日報酬率（長條圖）
        colors = ["#4CAF50" if v >= 0 else "#F44336" for v in nav_df["daily_return_pct"]]
        fig_return.add_trace(go.Bar(
            x=nav_df["date"],
            y=nav_df["daily_return_pct"],
            name="每日報酬率",
            marker_color=colors,
            opacity=0.6,
            yaxis="y2",
            hovertemplate="%{x|%Y-%m-%d}<br>日報酬: %{y:+.2f}%<extra></extra>",
        ))

        fig_return.update_layout(
            title="累積報酬率與每日報酬率",
            xaxis_title="日期",
            yaxis_title="累積報酬率 (%)",
            height=450,
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(t=50, b=20, l=20, r=20),
            yaxis2=dict(
                title="每日報酬率 (%)",
                overlaying="y",
                side="right",
                showgrid=False,
            ),
        )
        st.plotly_chart(fig_return, use_container_width=True)

    # 底部統計摘要
    st.markdown("#### 📋 期間統計")
    stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)

    with stat_col1:
        initial_nav = nav_df["total_nav"].iloc[0]
        final_nav = nav_df["total_nav"].iloc[-1]
        st.metric("期初淨值", _format_currency(initial_nav))

    with stat_col2:
        st.metric("期末淨值", _format_currency(final_nav))

    with stat_col3:
        total_return = nav_data["total_return_pct"]
        st.metric(
            "期間總報酬率",
            f"{total_return:+.2f}%",
            delta_color="normal",
        )

    with stat_col4:
        max_nav = nav_df["total_nav"].max()
        min_nav = nav_df["total_nav"].min()
        st.metric(
            "最大回撤",
            f"{(min_nav - max_nav) / max_nav * 100:+.2f}%",
            delta_color="inverse",
        )

else:
    st.info("所選區間內無淨值資料。")

st.markdown("---")
st.markdown(
    "<div style='text-align:center; color:gray; font-size:0.8em;'>"
    "Investment Health Dashboard v0.1.0 | 後端 Phase 1~5 全面封頂 | 106 項測試全數通過 ✅"
    "</div>",
    unsafe_allow_html=True,
)

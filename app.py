import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta, time
from supabase import create_client, Client

# ==========================================
# 1. ページ設定とSupabase接続
# ==========================================
st.set_page_config(page_title="アムネット 予定・稼働管理システム", layout="wide")

SUPABASE_URL = "https://xwvgbdkooawbnfemquyb.supabase.co"
SUPABASE_KEY = "sb_publishable_R_suRpkbQxM5cNWlmgjFoQ_-zX89IwR"

@st.cache_resource
def init_connection():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase: Client = init_connection()

def generate_time_options():
    times = []
    for h in range(24):
        for m in (0, 30):
            times.append(time(h, m).strftime('%H:%M'))
    return times

TIME_OPTIONS = generate_time_options()

# ==========================================
# 2. 認証・モード切替 (社内専用)
# ==========================================
if "role" not in st.session_state:
    st.session_state.role = "staff"

ADMIN_PASSWORD = "admin"

with st.sidebar:
    st.header("👑 管理者メニュー")
    if st.session_state.role == "staff":
        st.info("現在のモード: 👥 メンバー")
        st.caption("※店長・管理者はコードを入力してください")
        entered_pw = st.text_input("管理者コード", type="password")
        if st.button("管理者としてログイン"):
            if entered_pw == ADMIN_PASSWORD:
                st.session_state.role = "admin"
                st.rerun()
            else:
                st.error("コードが違います")
    else:
        st.info("現在のモード: 👑 管理者")
        if st.button("メンバー画面に戻る"):
            st.session_state.role = "staff"
            st.rerun()

# ==========================================
# 3. データ取得
# ==========================================
@st.cache_data(ttl=10) 
def load_data():
    try:
        users_response = supabase.table('users').select("*").execute()
        categories_response = supabase.table('categories').select("*").execute()
        schedules_response = supabase.table('schedules').select("*").execute()
    except Exception as e:
        st.error(f"データベース通信エラー: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    users_df = pd.DataFrame(users_response.data) if users_response.data else pd.DataFrame(columns=['user_id', 'member_name', 'tags'])
    categories_df = pd.DataFrame(categories_response.data) if categories_response.data else pd.DataFrame(columns=['category_id', 'category_name', 'color'])
    
    if schedules_response.data:
        schedules_df = pd.DataFrame(schedules_response.data)
        schedules_df['start_time'] = pd.to_datetime(schedules_df['start_time']).dt.tz_convert('Asia/Tokyo').dt.tz_localize(None)
        schedules_df['end_time'] = pd.to_datetime(schedules_df['end_time']).dt.tz_convert('Asia/Tokyo').dt.tz_localize(None)
    else:
        schedules_df = pd.DataFrame(columns=['id', 'user_id', 'category_id', 'start_time', 'end_time', 'memo'])
        
    return users_df, categories_df, schedules_df

users_df, categories_df, schedules_df = load_data()

if users_df.empty or categories_df.empty:
    st.warning("⚠ データベースに必須データが存在しません。")
    st.stop()

if not schedules_df.empty:
    merged_df = pd.merge(schedules_df, users_df, on='user_id', how='left')
    merged_df = pd.merge(merged_df, categories_df, on='category_id', how='left')
    merged_df['memo'] = merged_df['memo'].fillna("")
    merged_df['category_name'] = merged_df['category_name'].fillna("不明なカテゴリ")
    merged_df['display_memo'] = merged_df.apply(
        lambda row: f"✅ {row['memo']}" if row['category_name'] == 'シフト確定' else row['memo'], axis=1
    )
else:
    merged_df = pd.DataFrame()

try:
    confirmed_cat_id = int(categories_df[categories_df['category_name'] == 'シフト確定']['category_id'].values[0])
except IndexError:
    confirmed_cat_id = None

# ==========================================
# 4. 画面の表示 (権限別)
# ==========================================
st.title("アムネット 予定 ＆ シフト管理システム")
role = st.session_state.role

# 管理者モードの場合はタブを表示、メンバーモードの場合はコンテナのみ
if role == "admin":
    tabs = st.tabs(["👑 予定・シフトの直接登録・管理", "👥 メンバー画面（予定・シフト希望）", "✅ 承認待ち一覧・稼働分析"])
    tab_admin_manage = tabs[0]
    tab_member = tabs[1]
    tab_admin_dashboard = tabs[2]
else:
    tab_member = st.container()
    tab_admin_manage = None
    tab_admin_dashboard = None

# ------------------------------------------
# 👑 管理者専用：予定・シフトの直接登録・管理タブ
# ------------------------------------------
if role == "admin" and tab_admin_manage is not None:
    with tab_admin_manage:
        st.markdown("### 👑 予定・シフトの直接登録")
        st.caption("管理者は全メンバーの予定（現場作業、商談、シフト確定など）を直接登録・変更できます。")
        
        with st.form("admin_add_schedule_form"):
            col_a1, col_a2, col_a3 = st.columns(3)
            with col_a1:
                selected_user_admin = st.selectbox("メンバーを選択", users_df['member_name'].tolist(), key="admin_user")
                target_date_admin = st.date_input("日付", datetime.now().date(), key="admin_date")
            with col_a2:
                # 管理者は「シフト確定」を含むすべてのカテゴリを選択可能
                available_cats_admin = categories_df['category_name'].tolist()
                selected_cat_admin = st.selectbox("予定の種類", available_cats_admin, key="admin_cat")
                start_time_str_admin = st.selectbox("開始時間", TIME_OPTIONS, index=TIME_OPTIONS.index('09:00'), key="admin_start")
            with col_a3:
                memo_admin = st.text_input("詳細・案件名など", placeholder="例：〇〇現場 作業", key="admin_memo")
                end_time_str_admin = st.selectbox("終了時間", TIME_OPTIONS, index=TIME_OPTIONS.index('18:00'), key="admin_end")
            
            submit_btn_admin = st.form_submit_button("この内容で直接登録する")
            
            if submit_btn_admin:
                new_user_id = int(users_df[users_df['member_name'] == selected_user_admin]['user_id'].values[0])
                new_cat_id = int(categories_df[categories_df['category_name'] == selected_cat_admin]['category_id'].values[0])
                start_dt = datetime.combine(target_date_admin, datetime.strptime(start_time_str_admin, '%H:%M').time())
                end_dt = datetime.combine(target_date_admin, datetime.strptime(end_time_str_admin, '%H:%M').time())
                
                new_schedule_data = {
                    'user_id': new_user_id,
                    'category_id': new_cat_id,
                    'start_time': start_dt.isoformat() + '+09:00',
                    'end_time': end_dt.isoformat() + '+09:00',
                    'memo': memo_admin if memo_admin else "名称未設定"
                }
                response = supabase.table('schedules').insert(new_schedule_data).execute()
                if response.data:
                    st.success(f"{selected_user_admin} さんの {selected_cat_admin} を登録しました！")
                    st.cache_data.clear()
                    st.rerun()

        st.divider()
        st.markdown("### 🗑️ 登録済み予定の削除")
        st.caption("直近の予定を一覧表示しています。不要な予定を削除できます。")
        
        if not merged_df.empty:
            # 今日以降の予定を表示（過去の予定は誤って消さないように配慮）
            recent_df = merged_df[merged_df['start_time'].dt.date >= datetime.now().date()].sort_values('start_time')
            
            if not recent_df.empty:
                for index, row in recent_df.head(20).iterrows(): # 多すぎると見づらいので直近20件
                    col_del1, col_del2, col_del3, col_del4 = st.columns([1, 2, 3, 1])
                    with col_del1:
                        st.write(f"👤 {row['member_name']}")
                    with col_del2:
                        st.write(f"🕒 {row['start_time'].strftime('%m/%d %H:%M')} 〜 {row['end_time'].strftime('%H:%M')}")
                    with col_del3:
                        st.write(f"【{row['category_name']}】 {row['memo']}")
                    with col_del4:
                        if st.button("❌ 削除", key=f"delete_{row['id']}"):
                            supabase.table('schedules').delete().eq('id', int(row['id'])).execute()
                            st.warning(f"{row['member_name']} さんの予定を削除しました。")
                            st.cache_data.clear()
                            st.rerun()
            else:
                st.info("直近の予定はありません。")

# ------------------------------------------
# 👥 メンバー画面（タイムライン表示はここ）
# ------------------------------------------
with tab_member:
    if role == "staff":
        st.markdown(f"### 📝 スケジュール・シフト希望の提出")
        with st.form("add_schedule_form"):
            col_form1, col_form2, col_form3 = st.columns(3)
            with col_form1:
                selected_user = st.selectbox("メンバー", users_df['member_name'].tolist())
                target_date = st.date_input("日付", datetime.now().date())
            with col_form2:
                # メンバーは「シフト確定」を勝手に選べない
                available_cats = categories_df[categories_df['category_name'] != 'シフト確定']['category_name'].tolist()
                selected_cat = st.selectbox("予定の種類", available_cats)
                start_time_str = st.selectbox("開始時間", TIME_OPTIONS, index=TIME_OPTIONS.index('09:00'))
            with col_form3:
                memo = st.text_input("詳細・備考", placeholder="例：午後からなら出勤可能です")
                end_time_str = st.selectbox("終了時間", TIME_OPTIONS, index=TIME_OPTIONS.index('18:00'))
            
            submit_btn = st.form_submit_button("この内容で提出・登録する")
            
            if submit_btn:
                new_user_id = int(users_df[users_df['member_name'] == selected_user]['user_id'].values[0])
                new_cat_id = int(categories_df[categories_df['category_name'] == selected_cat]['category_id'].values[0])
                start_dt = datetime.combine(target_date, datetime.strptime(start_time_str, '%H:%M').time())
                end_dt = datetime.combine(target_date, datetime.strptime(end_time_str, '%H:%M').time())
                new_schedule_data = {
                    'user_id': new_user_id,
                    'category_id': new_cat_id,
                    'start_time': start_dt.isoformat() + '+09:00',
                    'end_time': end_dt.isoformat() + '+09:00',
                    'memo': memo if memo else "名称未設定"
                }
                response = supabase.table('schedules').insert(new_schedule_data).execute()
                if response.data:
                    st.success("予定を登録しました！")
                    st.cache_data.clear()
                    st.rerun()
        st.divider()
    
    # タイムラインは全権限共通で表示
    col_t1, col_t2 = st.columns([2, 2])
    with col_t1:
        view_mode = st.radio("表示期間", ["1日", "1週間", "1ヶ月"], horizontal=True)
    with col_t2:
        base_date = st.date_input("基準日を選択", datetime.now().date(), key="internal_date")
    
    if view_mode == "1日":
        start_date = pd.to_datetime(base_date)
        end_date = start_date + timedelta(days=1)
        view_title = f"📅 社内タイムライン ({start_date.strftime('%Y/%m/%d')})"
    elif view_mode == "1週間":
        start_date = pd.to_datetime(base_date - timedelta(days=base_date.weekday()))
        end_date = start_date + timedelta(days=7)
        view_title = f"📅 週間タイムライン ({start_date.strftime('%m/%d')} 〜)"
    else: # 1ヶ月
        start_date = pd.to_datetime(base_date.replace(day=1))
        if start_date.month == 12:
            end_date = pd.to_datetime(start_date.replace(year=start_date.year + 1, month=1))
        else:
            end_date = pd.to_datetime(start_date.replace(month=start_date.month + 1))
        view_title = f"🗓️ 月間タイムライン ({start_date.strftime('%Y年%m月')})"
    
    st.subheader(view_title)
    
    if not merged_df.empty:
        day_df = merged_df[(merged_df['start_time'] >= start_date) & (merged_df['start_time'] < end_date)]
        
        if not day_df.empty:
            all_members = users_df['member_name'].tolist()

            fig = px.timeline(
                day_df, x_start="start_time", x_end="end_time", y="member_name",
                color="category_name", text="display_memo",
                category_orders={"member_name": all_members},
                color_discrete_sequence=px.colors.qualitative.Pastel
            )
            fig.update_traces(textposition='inside', textfont_color="black", textangle=0)
            fig.update_yaxes(autorange="reversed", title="")
            fig.update_xaxes(
                range=[start_date, end_date],
                tickformat="%H:%M" if view_mode == "1日" else "%m/%d", 
                dtick=3600000 if view_mode == "1日" else 86400000
            )
            fig.update_layout(height=400, margin=dict(t=20, b=0))
            st.plotly_chart(fig, use_container_width=True)
            
            st.markdown(f"##### 📋 【{view_mode}間】スケジュール詳細一覧")
            display_df = day_df[['start_time', 'end_time', 'member_name', 'category_name', 'memo']].copy()
            display_df['日付'] = display_df['start_time'].dt.strftime('%m/%d (%a)')
            display_df['時間'] = display_df['start_time'].dt.strftime('%H:%M') + " 〜 " + display_df['end_time'].dt.strftime('%H:%M')
            display_df = display_df[['日付', '時間', 'member_name', 'category_name', 'memo']]
            display_df.columns = ['日付', '時間', 'メンバー', '種類', '詳細・案件名']
            
            st.dataframe(display_df.sort_values(['日付', '時間']), use_container_width=True, hide_index=True)
        else:
            st.info("この期間の予定はありません。")

# ------------------------------------------
# 👑 管理者専用：承認待ち一覧・稼働分析タブ
# ------------------------------------------
if role == "admin" and tab_admin_dashboard is not None:
    with tab_admin_dashboard:
        st.markdown("### 👑 承認待ちのシフト希望一覧")
        if not merged_df.empty and confirmed_cat_id is not None:
            pending_df = merged_df[merged_df['category_name'] == 'シフト希望'].sort_values('start_time')
            
            if not pending_df.empty:
                st.caption("「シフト確定する」を押すと正式なシフトとして登録・集計されます。")
                for index, row in pending_df.iterrows():
                    col_m1, col_m2, col_m3, col_m4 = st.columns([1.5, 2.5, 2.5, 1.5])
                    with col_m1:
                        st.write(f"👤 **{row['member_name']}**")
                    with col_m2:
                        st.write(f"🕒 {row['start_time'].strftime('%m/%d %H:%M')} 〜 {row['end_time'].strftime('%H:%M')}")
                    with col_m3:
                        st.write(f"📝 {row['memo']}")
                    with col_m4:
                        if st.button("✅ シフト確定する", key=f"approve_{row['id']}"):
                            supabase.table('schedules').update({'category_id': confirmed_cat_id}).eq('id', int(row['id'])).execute()
                            st.success(f"{row['member_name']} さんのシフトを確定しました！")
                            st.cache_data.clear()
                            st.rerun()
                    st.divider()
            else:
                st.info("現在、承認待ちのシフト希望はありません。")
        else:
            st.info("データがありません。")

        st.markdown("### 📊 稼働サマリー・コスト分析")
        if not merged_df.empty:
            summary_df = merged_df[merged_df['category_name'] != 'シフト確定'].copy()
            if not summary_df.empty:
                summary_df['duration_hours'] = (summary_df['end_time'] - summary_df['start_time']).dt.total_seconds() / 3600
                
                col_dash1, col_dash2 = st.columns(2)
                with col_dash1:
                    cat_summary = summary_df.groupby('category_name')['duration_hours'].sum().reset_index()
                    cat_summary.columns = ['予定の種類', '合計時間(h)']
                    fig_pie = px.pie(cat_summary, values='合計時間(h)', names='予定の種類', hole=0.3)
                    fig_pie.update_layout(margin=dict(t=0, b=0, l=0, r=0))
                    st.plotly_chart(fig_pie, use_container_width=True)
                with col_dash2:
                    member_summary = summary_df.groupby('member_name')['duration_hours'].sum().reset_index()
                    member_summary.columns = ['メンバー', '合計時間(h)']
                    fig_bar = px.bar(member_summary, x='合計時間(h)', y='メンバー', orientation='h')
                    fig_bar.update_yaxes(autorange="reversed")
                    fig_bar.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=300)
                    st.plotly_chart(fig_bar, use_container_width=True)
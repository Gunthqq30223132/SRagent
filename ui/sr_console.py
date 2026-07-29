"""D37 — SR Console: phân xử escalation + cổng consensus (Streamlit).

Chạy: streamlit run ui/sr_console.py   (hoặc `make sr-ui`)

Vì sao tách khỏi `ui/app.py` (D37 §0): app.py phục vụ tâm thế "duyệt bài lẻ"
(Approve→Notion). Console phục vụ tâm thế khác hẳn — so hai rater, đọc quote,
ra quyết định có hệ quả xuống consensus. Trộn hai tâm thế một chỗ = mời gọi
bấm nhầm.

Toàn bộ logic nằm ở `ui/console_logic.py` để test offline không cần Streamlit
runtime; file này chỉ là vỏ hiển thị + callback.
"""

from __future__ import annotations

import os

import streamlit as st

from sr_agent.store.staging import StagingStore
from sr_agent.store.writer_lock import holder
from tools.prisma_report import generate_prisma_report
from ui import console_logic as logic

st.set_page_config(page_title="SR Console", layout="wide")

# Cùng sẹo cross-thread với app.py (2026-07-11): mở connection mới mỗi rerun,
# tuyệt đối không cache store.
store = StagingStore()

lock_holder = holder()
disabled_writes = logic.is_write_disabled(lock_holder, os.getpid())
if disabled_writes:
    st.error(
        f"🔒 **Chế độ chỉ đọc**: tiến trình `{lock_holder.get('role')}` "
        f"(PID {lock_holder.get('pid')}) đang giữ writer lock. "
        "Mọi nút ghi bị vô hiệu hóa cho tới khi orchestrator chạy xong."
    )

st.title("SR Console — phân xử & cổng tổng hợp")

# --- Sidebar: chọn run ----------------------------------------------------------------

runs = logic.list_runs(store)
if not runs:
    st.warning(
        "Chưa có SR run nào. Tạo bằng: "
        "`python -m tools.sr_run run --query '...' --protocol <path>`"
    )
    st.stop()

open_runs = [r for r in runs if r["state"] == logic.STATE_OPEN]
default_idx = runs.index(open_runs[0]) if open_runs else 0

selected = st.sidebar.selectbox(
    "SR run",
    options=runs,
    index=default_idx,
    format_func=lambda r: f"{r['run_id']} · {r['state']} · {r['query'][:40]}",
)
run_id = selected["run_id"]
st.sidebar.caption(f"Trạng thái: **{selected['state']}**")

tab1, tab2, tab3 = st.tabs(
    ["① Phân xử RoB", "② Escalation khác", "③ Dashboard & cổng consensus"]
)

# --- Tab 1: phân xử RoB ---------------------------------------------------------------

with tab1:
    pending = logic.list_rob_escalations(store, run_id)
    st.subheader(f"{len(pending)} tài liệu chờ phân xử Risk-of-Bias")
    if not pending:
        st.success("Không còn escalation RoB nào cho run này.")

    for item in pending:
        uid = item["uid"]
        flag = "🚩 " if (item["n_pertinence_flags"] or 0) > 0 else ""
        with st.expander(
            f"{flag}{uid} — {item['title'] or '(không có tiêu đề)'} "
            f"· rubric {item['rubric_score']}"
        ):
            st.caption(f"Lý do escalate: {item['detail']}")
            if flag:
                st.warning(
                    "Có cờ pertinence: quote đúng nguồn nhưng có thể lạc domain "
                    "(D37 §4) — đọc kỹ quote trước khi phán."
                )

            pair = logic.rob_pair_view(store, uid)
            study_type = pair["study_type"] or "RCT"
            st.caption(f"Loại nghiên cứu: **{study_type}**")

            domains = [d for d in pair["domains"] if d != "__overall__"]
            verdicts: dict[str, str] = {}
            for domain in domains:
                st.markdown(f"**{domain}**")
                col_a, col_b, col_h = st.columns([2, 2, 1])
                a = pair["domains"][domain].get("rob_a", {})
                b = pair["domains"][domain].get("rob_b", {})
                col_a.markdown(f"A · `{a.get('verdict', '—')}`")
                col_a.caption(a.get("quote", ""))
                col_b.markdown(f"B · `{b.get('verdict', '—')}`")
                col_b.caption(b.get("quote", ""))
                choices = (
                    logic.ROB2_CHOICES
                    if study_type == "RCT"
                    else ["0", "1", "2", "VOID"]
                )
                verdicts[domain] = col_h.radio(
                    "Phán định", choices, key=f"{uid}:{domain}", label_visibility="collapsed"
                )

            if st.button("💾 Lưu phán định", key=f"save:{uid}", disabled=disabled_writes):
                # Kiểm lại lock NGAY trong callback (chống TOCTOU — sẹo OPS-1).
                try:
                    overall = logic.save_human_adjudication(
                        store, uid, study_type, verdicts, run_id
                    )
                    st.success(f"Đã lưu. Overall (máy tính): **{overall}**")
                    st.rerun()
                except (logic.WriteLocked, ValueError) as exc:
                    st.error(str(exc))

# --- Tab 2: escalation khác ----------------------------------------------------------

with tab2:
    others = logic.list_other_escalations(store, run_id)
    st.subheader(f"{len(others)} cảnh báo khác của run")
    st.caption(
        "v1 chỉ hiển thị + đánh dấu đã xem (D37 §1 Tab 2). Phân xử eligibility "
        "bằng tay là ca hiếm — chưa xây UI cho tới khi FL cho thấy tần suất thật."
    )
    for ev in others:
        mark = "✅" if ev["acked"] else "🔔"
        cols = st.columns([1, 3, 6, 2])
        cols[0].write(mark)
        cols[1].code(ev["event_type"])
        cols[2].write(f"`{ev['uid']}` {ev['detail']}")
        if not ev["acked"]:
            if cols[3].button(
                "Đã xem",
                key=f"ack:{ev['uid']}:{ev['created_at']}",
                disabled=disabled_writes,
            ):
                try:
                    logic.ack_escalation(store, ev["uid"], run_id)
                    st.rerun()
                except logic.WriteLocked as exc:
                    st.error(str(exc))

# --- Tab 3: dashboard + cổng consensus ------------------------------------------------

with tab3:
    funnel = logic.run_funnel(store, run_id)
    cols = st.columns(len(funnel))
    for col, (label, n) in zip(cols, funnel.items()):
        col.metric(label, n)

    with st.expander("PRISMA preview (per-run)"):
        st.code(generate_prisma_report(store, run_id=run_id), language="markdown")

    status = logic.consensus_gate_status(store, run_id)
    st.divider()
    st.subheader("Cổng tổng hợp (BS4.1)")
    st.write(
        f"Escalation RoB chưa phân xử: **{status['pending_escalations']}** · "
        f"quote chưa kiểm chứng: **{status['unverified_quotes']}** "
        "(thông tin, không chặn)"
    )

    if not status["can_approve"]:
        for reason in status["reasons"]:
            st.warning(reason)

    confirmed = st.checkbox(
        "Tôi xác nhận đã đọc và chịu trách nhiệm về tập bằng chứng này.",
        disabled=disabled_writes or not status["can_approve"],
    )
    if st.button(
        "✅ Chốt tập bằng chứng — cho phép tổng hợp",
        disabled=disabled_writes or not status["can_approve"] or not confirmed,
    ):
        try:
            logic.approve_consensus(store, run_id)
            st.success(
                "Đã chốt. Chạy tiếp: "
                f"`python -m tools.consensus_run --protocol <path> --run {run_id}`"
            )
            st.rerun()
        except (logic.WriteLocked, ValueError) as exc:
            st.error(str(exc))

    st.divider()
    with st.expander("⛔ Hủy run"):
        reason = st.text_input("Lý do hủy (bắt buộc)")
        if st.button("Hủy run này", disabled=disabled_writes):
            try:
                logic.abandon_run(store, run_id, reason)
                st.warning("Run đã bị hủy.")
                st.rerun()
            except (logic.WriteLocked, ValueError) as exc:
                st.error(str(exc))

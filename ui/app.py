"""QC UI — hàng đợi duyệt thủ công + dashboard sức khỏe hệ thống (Streamlit).

Chạy: streamlit run ui/app.py
Tab 1: tối đa WIP_LIMIT tài liệu QUEUED theo điểm rubric; Approve -> Notion
       (hoặc dry-run), Reject -> loại kèm lý do. Doc chưa qua tầng LLM có badge
       cảnh báo để người duyệt không nhầm "chưa phân tích" với "không có artifact".
Tab 2: health snapshot + alert đang mở — dashboard tối giản, không service mới.
"""

from __future__ import annotations

import streamlit as st

from sr_agent.config import TTL_HOURS, WIP_LIMIT
from sr_agent.models.schemas import DocStatus
from sr_agent.monitor import alerts as alerts_mod
from sr_agent.monitor import health as health_mod
from sr_agent.monitor import probes
from sr_agent.publish.notion_page import NotionPublisher
from sr_agent.store.staging import StagingStore

st.set_page_config(page_title="SR-Agent QC Queue", layout="wide")


@st.cache_resource
def get_store() -> StagingStore:
    return StagingStore()


store = get_store()
publisher = NotionPublisher()

st.title("SR-Agent — Quality Control Queue")
st.caption(
    f"AI truy xuất & lọc nhiễu — Con người duyệt & phân tích sâu. "
    f"WIP {WIP_LIMIT}/ngày · TTL {TTL_HOURS}h · "
    f"{'DRY-RUN (chưa có NOTION_TOKEN)' if publisher.dry_run else 'Notion: sẵn sàng'}"
)

purged = store.purge_expired()
if purged:
    st.info(f"TTL purge: đã giải phóng {len(purged)} bản ghi quá {TTL_HOURS}h.")

queue_tab, health_tab = st.tabs(["📋 Hàng đợi duyệt", "🩺 Sức khỏe hệ thống"])

# --- Tab 1: hàng đợi duyệt ------------------------------------------------------

with queue_tab:
    queue = store.get_wip_queue()
    if not queue:
        st.success(
            "Hàng đợi trống — chạy `python -m sr_agent.pipeline run --query ...` để nạp."
        )
    else:
        left, right = st.columns([1, 2])

        with left:
            st.subheader(f"Hàng đợi ({len(queue)}/{WIP_LIMIT})")
            escalated_uids = store.get_escalated_uids()
            labels = [
                f"{'⚠️ ' if d.tech_meta is None else ''}"
                f"{'🔶 ' if d.uid in escalated_uids else ''}"
                f"{d.rubric.total if d.rubric else '—'} · {d.title[:60]}"
                for d in queue
            ]
            idx = st.radio("Chọn tài liệu", range(len(queue)),
                           format_func=lambda i: labels[i], label_visibility="collapsed")
            doc = queue[idx]

        with right:
            st.subheader(doc.title)
            if doc.uid in escalated_uids:
                st.warning("🔶 **Screening bất đồng — cần người phân xử**")
            if doc.tech_meta is None:
                st.warning(
                    "⚠️ **Chưa phân tích LLM** — bản ghi này được xử lý heuristic-only "
                    "khi Ollama không hoạt động. Metadata kỹ thuật (code repo, benchmark, "
                    "hạn chế) và câu hỏi phản biện sẽ được bổ sung tự động khi Ollama "
                    "sống lại (`pipeline enrich`, chạy đêm). Thiếu artifact dưới đây "
                    "nghĩa là *chưa kiểm tra*, không phải *không có*."
                )
            st.markdown(
                f"**{doc.uid}** · tier {doc.authority_tier} · "
                f"{', '.join(doc.authors) or 'không rõ tác giả'} · "
                f"{doc.published_date.date() if doc.published_date else '—'}"
            )
            if doc.url:
                st.markdown(f"[Mở bản gốc]({doc.url})")

            if doc.rubric:
                with st.expander(f"Điểm Rubric: {doc.rubric.total}", expanded=True):
                    for c in doc.rubric.breakdown:
                        st.markdown(
                            f"- **{c.key}** (w={c.weight:g}): {c.sub_score:.0f} — {c.reason}"
                        )

            if doc.tech_meta:
                tm = doc.tech_meta
                with st.expander("Siêu dữ liệu kỹ thuật (LLM trích xuất)", expanded=True):
                    st.markdown(f"- Code repo: {tm.code_repo_url or ('có' if tm.has_code_repo else 'không thấy')}")
                    st.markdown(f"- Dataset: {tm.dataset_specification or 'không nêu'}")
                    st.markdown(f"- Benchmarks: {', '.join(tm.evaluated_benchmarks) or 'không nêu'}")
                    st.markdown(f"- Hạn chế tác giả thừa nhận: {tm.declared_limitations or 'không nêu'}")

            extractions = store.extractions(doc.uid, verified_only=False)
            if extractions:
                verified_count = sum(1 for e in extractions if e["verified"] == 1)
                denom = sum(1 for e in extractions if e["verified"] in (0, 1))
                score = verified_count / denom if denom > 0 else None
                score_str = f"{score:.2f}" if score is not None else "N/A"
                with st.expander(f"Minh chứng trích xuất (Grounding Score: {score_str})", expanded=True):
                    for e in extractions:
                        if e["verified"] == 1:
                            status = "✅ Khớp"
                        elif e["verified"] == 2:
                            status = "⚪ Không thể kiểm chứng"
                        else:
                            status = "❌ Bị hủy (không khớp)"
                        st.markdown(f"**{e['field']}**: `{e['value']}` ({status})")
                        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;*Quote*: \"{e['quote']}\" (in `{e['section']}`)")

            if doc.abstract:
                with st.expander("Abstract"):
                    st.write(doc.abstract)

            for role, section in doc.canonical_sections.items():
                if section is not None:
                    with st.expander(f"{role.value.title()} — {section.heading_raw or 'LLM gán'} "
                                     f"(confidence {section.confidence:.2f})"):
                        st.write(section.content)

            if doc.critique_questions:
                st.markdown("**Gợi ý phân tích (sẽ đổ vào Notion Q&A):**")
                for i, cq in enumerate(doc.critique_questions, 1):
                    st.markdown(f"{i}. {cq.question}")

            approve_col, reject_col = st.columns(2)
            with approve_col:
                if st.button("✅ Approve → Notion", type="primary", use_container_width=True):
                    page_id = publisher.publish(doc, store)
                    st.success(
                        f"Đã publish trang {page_id}" if page_id
                        else "DRY-RUN: payload đã in ra console, status = APPROVED_LOCAL"
                    )
                    st.rerun()
            with reject_col:
                reason = st.text_input("Lý do reject", placeholder="ví dụ: không liên quan đề tài")
                if st.button("❌ Reject", use_container_width=True):
                    doc.status = DocStatus.REJECTED
                    store.upsert(doc)
                    store.log_event(doc.uid, "REJECTED", reason or "không ghi lý do")
                    st.rerun()

# --- Tab 2: sức khỏe hệ thống -----------------------------------------------------

with health_tab:
    snap = health_mod.snapshot(store)
    ollama_up = probes.probe_ollama()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ollama", "🟢 sống" if ollama_up else "🔴 sập")
    c2.metric("DLQ chờ retry", snap.dlq_retry_eligible)
    c3.metric("Chưa phân tích LLM", snap.degraded_count)
    c4.metric(
        "Batch gần nhất",
        f"{snap.hours_since_last_run:.0f}h trước"
        if snap.hours_since_last_run is not None else "chưa có",
    )

    # M6: Screening and extraction metrics row
    c5, c6, c7, c8 = st.columns(4)
    kappa_val = f"{snap.screen_kappa_recent:.2f}" if snap.screen_kappa_recent is not None else "N/A"
    c5.metric("Cohen's κ (gần nhất)", kappa_val)
    stats = store.screening_stats(hours=24)
    c6.metric("Screening đồng thuận (24h)", stats.get("agreement", 0))
    c7.metric("Bất đồng đã phân xử (24h)", stats.get("disagreement_resolved", 0))
    c8.metric("Chờ người phân xử", snap.screen_escalated_count)

    c9, c10, = st.columns(2)
    grounding_val = f"{snap.grounding_avg_24h * 100:.1f}%" if snap.grounding_avg_24h is not None else "N/A"
    c9.metric("Grounding Avg (24h)", grounding_val)
    c10.metric("Tài liệu trích xuất (24h)", snap.extraction_docs_count_24h)

    desired = alerts_mod.desired_alerts(snap, ollama_up=ollama_up)
    stored_open = alerts_mod.open_alerts(store)
    if desired or stored_open:
        st.subheader("🔴 Sự cố")
        for key, detail in desired.items():
            st.error(f"**{key}** — {detail}")
        for row in stored_open:
            if row["key"] not in desired:
                st.warning(f"**{row['key']}** — đang mở, chờ heal xác nhận hồi phục "
                           f"(từ {row['first_seen'][:16]})")
    else:
        st.success("🟢 Không có sự cố. Heal chạy nền mỗi 15 phút qua launchd.")

    if snap.sources_down:
        st.error(f"Nguồn nghi sập trong 24h: {', '.join(snap.sources_down)}")

    left_h, right_h = st.columns(2)
    with left_h:
        st.subheader("DLQ theo loại lỗi")
        if snap.dlq_by_error:
            st.table([{"lỗi": k, "số entry": v} for k, v in snap.dlq_by_error.items()])
        else:
            st.caption("DLQ trống.")
        if snap.dlq_permanent:
            st.warning(f"{snap.dlq_permanent} entry chạm trần retry (5 lần) — cần xem tay.")
    with right_h:
        st.subheader("Documents theo trạng thái")
        if snap.status_counts:
            st.table([{"status": k, "số doc": v} for k, v in snap.status_counts.items()])
        else:
            st.caption("Chưa có tài liệu nào.")
        if snap.last_run is not None:
            st.caption(f"Standing query gần nhất: `{snap.last_run['query']}`")

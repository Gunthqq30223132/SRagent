"""QC UI — hàng đợi duyệt thủ công của SR-Agent (Streamlit).

Chạy: streamlit run ui/app.py
Hiển thị tối đa WIP_LIMIT tài liệu QUEUED xếp theo điểm rubric giảm dần;
Approve -> Notion (hoặc dry-run), Reject -> loại kèm lý do.
"""

from __future__ import annotations

import streamlit as st

from sr_agent.config import TTL_HOURS, WIP_LIMIT
from sr_agent.models.schemas import DocStatus
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

queue = store.get_wip_queue()
if not queue:
    st.success("Hàng đợi trống — chạy `python -m sr_agent.pipeline run --query ...` để nạp.")
    st.stop()

left, right = st.columns([1, 2])

with left:
    st.subheader(f"Hàng đợi ({len(queue)}/{WIP_LIMIT})")
    labels = [f"{d.rubric.total if d.rubric else '—'} · {d.title[:60]}" for d in queue]
    idx = st.radio("Chọn tài liệu", range(len(queue)),
                   format_func=lambda i: labels[i], label_visibility="collapsed")
    doc = queue[idx]

with right:
    st.subheader(doc.title)
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
                st.markdown(f"- **{c.key}** (w={c.weight:g}): {c.sub_score:.0f} — {c.reason}")

    if doc.tech_meta:
        tm = doc.tech_meta
        with st.expander("Siêu dữ liệu kỹ thuật (LLM trích xuất)", expanded=True):
            st.markdown(f"- Code repo: {tm.code_repo_url or ('có' if tm.has_code_repo else 'không thấy')}")
            st.markdown(f"- Dataset: {tm.dataset_specification or 'không nêu'}")
            st.markdown(f"- Benchmarks: {', '.join(tm.evaluated_benchmarks) or 'không nêu'}")
            st.markdown(f"- Hạn chế tác giả thừa nhận: {tm.declared_limitations or 'không nêu'}")

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

"""Trích xuất số liệu song thẩm (M8 Result B, D33 §3) — hai agent độc lập + arbiter.

Kiến trúc mirror M6 screening kép: 2 agent (model A ≠ model B, temp 0, structured
output) trích CÙNG một form; đồng thuận so sánh BYTE-EXACT trên giá trị số; lệch →
arbiter ẨN DANH; arbiter không phân xử được bằng chứng cứ ⇒ HUMAN_REVIEW — hệ không
bao giờ đoán số hộ bài báo.

Zero-trust từng claim:
- value luôn là CHUỖI nguyên văn (byte-exact, "0.030" ≠ "0.03");
- quote bắt buộc khi value != None và PHẢI qua verify_quote (tái dùng M6, không chép);
- claim có quote bịa = VOID (như không tồn tại), không phải "sửa lại cho khớp".

Form trích xuất do PROTOCOL định nghĩa (FieldSpec) — code không chứa ngữ nghĩa miền.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tools.evidence.schemas import (
    AgentExtraction,
    ArbiterChoice,
    ConsensusOutcome,
    FieldSpec,
    StatClaim,
)
from tools.screen_run import verify_quote

# Form mặc định cho nghiên cứu định lượng — protocol thay được toàn bộ.
DEFAULT_FORM: list[FieldSpec] = [
    FieldSpec(name="sample_size", description="tổng số đơn vị/đối tượng trong nghiên cứu",
              kind="numeric", required=True),
    FieldSpec(name="primary_outcome_mean", description="giá trị trung bình của outcome chính",
              kind="numeric"),
    FieldSpec(name="primary_outcome_sd", description="độ lệch chuẩn của outcome chính",
              kind="numeric"),
    FieldSpec(name="p_value", description="p-value của so sánh chính", kind="numeric"),
]

EXTRACTOR_SYSTEM_PROMPT = """Bạn là nhân viên trích xuất dữ liệu cho một systematic review.
LUẬT TUYỆT ĐỐI:
1. CHỈ trích thông tin xuất hiện NGUYÊN VĂN trong văn bản được cung cấp.
2. Giá trị số phải chép CHÍNH XÁC TỪNG KÝ TỰ như trong bài (kể cả số chữ số thập phân).
3. Mỗi giá trị phải kèm "quote": câu nguyên văn trong bài chứa giá trị đó.
4. Bài không báo cáo trường nào thì trả value=null cho trường đó — CẤM suy diễn,
   CẤM tính toán hộ, CẤM lấy số từ bài khác hoặc từ kiến thức của bạn.
5. Trả về JSON đúng schema, không thêm bất kỳ văn bản nào khác."""

ARBITER_SYSTEM_PROMPT = """Bạn là trọng tài đối chiếu dữ liệu trích xuất. Hai bản trích
(a) và (b) LỆCH NHAU về một trường. Nhiệm vụ: đọc văn bản nguồn và chọn:
- "a" nếu giá trị (a) đúng nguyên văn theo bài;
- "b" nếu giá trị (b) đúng nguyên văn theo bài;
- "neither" nếu không xác định được từ văn bản (mơ hồ, cả hai sai, bài không nói rõ).
Khi chọn "a" hoặc "b" phải kèm "quote" nguyên văn từ bài chứng minh. Trả JSON đúng schema."""


def build_extractor_user_prompt(doc_text: str, form: list[FieldSpec]) -> str:
    spec = json.dumps(
        [{"field": f.name, "description": f.description, "kind": f.kind} for f in form],
        ensure_ascii=False, indent=2,
    )
    return f"CÁC TRƯỜNG CẦN TRÍCH:\n{spec}\n\nVĂN BẢN NGUỒN:\n{doc_text}"


def _verified(claim: StatClaim, doc_text: str) -> StatClaim | None:
    """Zero-trust: claim có giá trị mà thiếu quote / quote bịa / quote không chứa giá trị
    ⇒ VOID (None). Claim value=None (không báo cáo) là hợp lệ, giữ nguyên."""
    if claim.value is None:
        return claim
    if not claim.quote or not verify_quote(doc_text, claim.quote):
        return None
    if claim.value not in claim.quote:
        return None                      # số không nằm nguyên văn trong chính quote
    return claim


def _norm_num(value: str) -> str:
    """So sánh đồng thuận: chỉ tha khác biệt trình bày vô hại (khoảng trắng, dấu %/đơn vị
    dính liền). KHÔNG tha khác biệt chữ số: '0.030' != '0.03'."""
    return "".join(value.split())


def reconcile_field(
    field: FieldSpec,
    claim_a: StatClaim | None,
    claim_b: StatClaim | None,
    doc_text: str,
    arbiter_call,                       # (system, user, schema) -> ArbiterChoice — tiêm vào
) -> ConsensusOutcome:
    """Đồng thuận một trường. arbiter_call chỉ được gọi khi hai bên LỆCH giá trị."""
    a = _verified(claim_a, doc_text) if claim_a else None
    b = _verified(claim_b, doc_text) if claim_b else None
    va = a.value if a else None
    vb = b.value if b else None

    # Cả hai xác nhận "bài không báo cáo"
    if a is not None and b is not None and va is None and vb is None:
        return ConsensusOutcome(field=field.name, status="NOT_REPORTED")

    # Khớp byte-exact (sau chuẩn hóa trình bày)
    if va is not None and vb is not None and _norm_num(va) == _norm_num(vb):
        return ConsensusOutcome(
            field=field.name, status="AGREED", value_final=va,
            unit=a.unit or b.unit, quote_final=a.quote,
            value_a=va, value_b=vb,
        )

    # Một bên có giá trị verified, bên kia void/không báo cáo → bảo thủ: người xem
    if (va is None) != (vb is None):
        return ConsensusOutcome(
            field=field.name, status="HUMAN_REVIEW", value_a=va, value_b=vb,
            detail="chỉ một agent trích được giá trị đã kiểm chứng — cần người đối chiếu",
        )

    # Cả hai void (quote bịa cả đôi) → người xem
    if va is None and vb is None:
        return ConsensusOutcome(
            field=field.name, status="HUMAN_REVIEW",
            detail="cả hai claim đều không qua được verifier quote",
        )

    # LỆCH GIÁ TRỊ THẬT → arbiter ẩn danh
    user = (
        f"TRƯỜNG: {field.name} ({field.description})\n"
        f"(a) = {va!r} — quote: {a.quote!r}\n(b) = {vb!r} — quote: {b.quote!r}\n\n"
        f"VĂN BẢN NGUỒN:\n{doc_text}"
    )
    try:
        choice: ArbiterChoice = arbiter_call(ARBITER_SYSTEM_PROMPT, user, ArbiterChoice)
    except Exception:
        choice = ArbiterChoice(choice="neither")          # arbiter chết = không phân xử

    if choice.choice in ("a", "b") and choice.quote and verify_quote(doc_text, choice.quote):
        winner = a if choice.choice == "a" else b
        if winner and winner.value and winner.value in choice.quote:
            return ConsensusOutcome(
                field=field.name, status="RESOLVED_BY_ARBITER",
                value_final=winner.value, unit=winner.unit, quote_final=choice.quote,
                value_a=va, value_b=vb,
            )
    return ConsensusOutcome(
        field=field.name, status="HUMAN_REVIEW", value_a=va, value_b=vb,
        detail="arbiter không phân xử được bằng chứng cứ nguyên văn",
    )


def extract_dual(
    doc_text: str,
    form: list[FieldSpec],
    call_a,                              # (system, user, schema) -> AgentExtraction
    call_b,
    call_arbiter,
) -> list[ConsensusOutcome]:
    """Chạy 2 extractor độc lập trên cùng form rồi đồng thuận từng trường.

    call_* tiêm vào theo signature OllamaClient.generate_structured (LLM thật ở runtime,
    hàm giả trong test) — module này không mở kết nối nào, test offline không cần mock HTTP.
    Extractor lỗi/không qua schema ⇒ coi như KHÔNG có claim (void toàn bộ phía đó).
    """
    user = build_extractor_user_prompt(doc_text, form)

    def _claims(call) -> dict[str, StatClaim]:
        try:
            result: AgentExtraction = call(EXTRACTOR_SYSTEM_PROMPT, user, AgentExtraction)
            return {c.field: c for c in result.claims}
        except Exception:
            return {}

    claims_a = _claims(call_a)
    claims_b = _claims(call_b)
    return [
        reconcile_field(f, claims_a.get(f.name), claims_b.get(f.name), doc_text, call_arbiter)
        for f in form
    ]

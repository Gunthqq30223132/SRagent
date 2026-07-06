"""Lớp giám sát & tự phục hồi (M4) — hoàn toàn additive, không đụng Pipeline.

- probes  : nguồn sự thật duy nhất về "hạ tầng sống chưa" (mạng nguồn, Ollama)
- health  : snapshot trạng thái hệ thống đọc thuần từ SQLite
- alerts  : máy trạng thái báo động — chỉ notify khi CHUYỂN trạng thái
- recover : heal (retry DLQ khi hạ tầng hồi phục) + enrich (tái xử lý LLM ban đêm)
"""

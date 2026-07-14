import os
from pathlib import Path

# Paths config via env vars with default fallbacks
WAREHOUSE_DB_PATH = Path(os.getenv("WAREHOUSE_DB_PATH", "./staging/warehouse.db")).resolve()
CORPUS_BASE_PATH = Path(os.getenv("CORPUS_BASE_PATH", "/Volumes/Gun SSD/1. STUDY")).resolve()

# Specialty mapping config
SPECIALTY_MAPPING = {
    "folders": [
        ("1. nôi khoa", "Nội khoa"),
        ("1. nội khoa", "Nội khoa"),
        ("nọi khoa", "Nội khoa"),
        ("nội khoa", "Nội khoa"),
        ("2. nhi khoa", "Nhi khoa"),
        ("nhi khoa", "Nhi khoa"),
        ("16. sản - phụ khoa", "Sản phụ khoa"),
        ("san - phu", "Sản phụ khoa"),
        ("sản/phụ", "Sản phụ khoa"),
        ("sản phụ khoa", "Sản phụ khoa"),
        ("obstetric", "Sản phụ khoa"),
        ("gynecology", "Sản phụ khoa"),
        ("7. ngoại khoa", "Ngoại khoa"),
        ("ngoai khoa", "Ngoại khoa"),
        ("ngoại khoa", "Ngoại khoa"),
        ("surgery", "Ngoại khoa"),
        ("surgical", "Ngoại khoa"),
        ("0. gây mê hồi sức - cấp cứu", "Gây mê hồi sức - Cấp cứu"),
        ("gây mê", "Gây mê hồi sức - Cấp cứu"),
        ("gây mê", "Gây mê hồi sức - Cấp cứu"),
        ("anesthesia", "Gây mê hồi sức - Cấp cứu"),
        ("anaesthesia", "Gây mê hồi sức - Cấp cứu"),
        ("anesthesiology", "Gây mê hồi sức - Cấp cứu"),
        ("icu", "Gây mê hồi sức - Cấp cứu"),
        ("critical care", "Gây mê hồi sức - Cấp cứu"),
        ("cấp cứu", "Gây mê hồi sức - Cấp cứu"),
        ("cấp cứu", "Gây mê hồi sức - Cấp cứu"),
        ("18 huyết học - miễn dịch", "Huyết học - Miễn dịch"),
        ("huyet hoc", "Huyết học - Miễn dịch"),
        ("huyết học", "Huyết học - Miễn dịch"),
        ("hematology", "Huyết học - Miễn dịch"),
        ("immunology", "Huyết học - Miễn dịch"),
        ("15. cận lâm sàng - hoá sinh", "Cận lâm sàng - Hóa sinh"),
        ("hoa sinh", "Cận lâm sàng - Hóa sinh"),
        ("hóa sinh", "Cận lâm sàng - Hóa sinh"),
        ("biochemistry", "Cận lâm sàng - Hóa sinh"),
        ("5. sinh học - di truyền", "Sinh học - Di truyền"),
        ("sinh hoc", "Sinh học - Di truyền"),
        ("sinh học", "Sinh học - Di truyền"),
        ("di truyền", "Sinh học - Di truyền"),
        ("di truyền", "Sinh học - Di truyền"),
        ("genetics", "Sinh học - Di truyền"),
        ("biology", "Sinh học - Di truyền"),
        ("3. sinh lý - giải phẫu", "Sinh lý - Giải phẫu"),
        ("4. sách giải phẫu", "Sinh lý - Giải phẫu"),
        ("3. sinh lý", "Sinh lý - Giải phẫu"),
        ("sinh ly", "Sinh lý - Giải phẫu"),
        ("giải phẫu", "Sinh lý - Giải phẫu"),
        ("anatomy", "Sinh lý - Giải phẫu"),
        ("physiology", "Sinh lý - Giải phẫu"),
        ("6. dược lý - thủ thuật", "Dược lý - Thủ thuật"),
        ("duoc ly", "Dược lý - Thủ thuật"),
        ("dược lý", "Dược lý - Thủ thuật"),
        ("pharmacology", "Dược lý - Thủ thuật"),
        ("13. khám", "Khám lâm sàng"),
        ("kham", "Khám lâm sàng"),
        ("clinical exam", "Khám lâm sàng"),
        ("5. luật khám chữa bệnh", "Pháp luật y tế & Quy chế"),
        ("8. quy chế bệnh viện", "Pháp luật y tế & Quy chế"),
        ("luật", "Pháp luật y tế & Quy chế"),
        ("quy chế", "Pháp luật y tế & Quy chế"),
        ("regulation", "Pháp luật y tế & Quy chế")
    ],
    "keywords": {
        "nhi": "Nhi khoa",
        "nội": "Nội khoa",
        "nôi": "Nội khoa",
        "ngoại": "Ngoại khoa",
        "ngoai": "Ngoại khoa",
        "sản": "Sản phụ khoa",
        "san": "Sản phụ khoa",
        "dược": "Dược lý - Thủ thuật",
        "duoc": "Dược lý - Thủ thuật",
        "gmhs": "Gây mê hồi sức - Cấp cứu",
        "icu": "Gây mê hồi sức - Cấp cứu",
        "anesthesia": "Gây mê hồi sức - Cấp cứu",
        "sinh lý": "Sinh lý - Giải phẫu",
        "sinh ly": "Sinh lý - Giải phẫu",
        "giải phẫu": "Sinh lý - Giải phẫu",
        "giai phau": "Sinh lý - Giải phẫu",
        "di truyền": "Sinh học - Di truyền",
        "di truyen": "Sinh học - Di truyền",
        "hóa sinh": "Cận lâm sàng - Hóa sinh",
        "hoa sinh": "Cận lâm sàng - Hóa sinh"
    }
}

# Authority tier mapping config
AUTHORITY_TIER_MAPPING = {
    "t3_keywords": [
        "slide", "đề", "plan", "ôn thi", "pretest", "cbl", "bài soạn", "bảng chia", 
        "y lệnh", "bệnh án", "review", "lượng giá", "quy chế", "kinh nghiệm"
    ],
    "t3_file_keywords": [
        "pretest", "đề", "cbl", "lương giá", "thi", "chữa đề", "slide", "handout", 
        "bài giảng", "bài báo cáo", "phiên", "phiếu gây mê", "bệnh án", "y lệnh", 
        "kinh nghiệm", "câu hỏi"
    ],
    "t1_file_keywords": [
        "guideline", "huong-dan", "phac-do", "phác đồ", "hướng dẫn", "quyết định", 
        "byt", "bộ y tế", "lancet", "ssc", "asa", "aha", "esc", "acr", "uptodate"
    ],
    "t1_folder_keywords": [
        "guidelines", "hướng dẫn", "phác đồ", "phac-do", "huong-dan", "luật khám chữa bệnh", "uptodate"
    ],
    "t2_folder_keywords": [
        "sách", "sách", "textbook", "book", "atlas", "chestnut", "miller", "barash", 
        "guyton", "marino", "costanzo", "zollinger", "schwartz", "hadzic", "kaplan", 
        "morgan", "hagberg", "silbernagl", "berne", "stanton"
    ],
    "t2_file_keywords": [
        "chapter", "section", "part", "tập", "textbook", "manual", "handbook", 
        "atlas", "guidelines in practice"
    ]
}

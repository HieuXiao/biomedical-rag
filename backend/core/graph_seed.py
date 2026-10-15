"""
Dữ liệu seed cho Knowledge Graph y khoa (tự curate, KHÔNG dùng SNOMED/UMLS để
tránh vướng bản quyền). Tập trung quanh Đái tháo đường (khớp phác đồ có sẵn) +
một số mã ICD-10 (miễn phí, của WHO).

Mỗi triple: (subject, relation, object). Relation dùng tiếng Việt cho dễ đọc khi
textualize vào prompt.
"""

# Thực thể: tên -> {type, icd10 (nếu có), synonyms}
ENTITIES = {
    "Đái tháo đường týp 2": {"type": "Bệnh", "icd10": "E11", "synonyms": ["tiểu đường týp 2", "đái tháo đường type 2", "dtd týp 2"]},
    "Đái tháo đường týp 1": {"type": "Bệnh", "icd10": "E10", "synonyms": ["tiểu đường týp 1", "đái tháo đường type 1"]},
    "Metformin": {"type": "Thuốc", "synonyms": ["glucophage"]},
    "Insulin": {"type": "Thuốc", "synonyms": []},
    "Sulfonylurea": {"type": "Nhóm thuốc", "synonyms": ["gliclazid", "glimepirid"]},
    "Ức chế SGLT2": {"type": "Nhóm thuốc", "synonyms": ["sglt2", "empagliflozin", "dapagliflozin"]},
    "Ức chế DPP-4": {"type": "Nhóm thuốc", "synonyms": ["dpp4", "sitagliptin"]},
    "Hạ đường huyết": {"type": "Tác dụng phụ", "icd10": "E16.2", "synonyms": ["tụt đường huyết"]},
    "Toan chuyển hoá lactic": {"type": "Tác dụng phụ", "synonyms": ["nhiễm toan lactic"]},
    "Suy thận": {"type": "Bệnh", "icd10": "N18", "synonyms": ["bệnh thận mạn", "suy thận mạn"]},
    "Biến chứng thận do đái tháo đường": {"type": "Biến chứng", "icd10": "E11.2", "synonyms": ["bệnh thận đái tháo đường"]},
    "Biến chứng mắt do đái tháo đường": {"type": "Biến chứng", "icd10": "E11.3", "synonyms": ["bệnh võng mạc đái tháo đường"]},
    "HbA1c": {"type": "Xét nghiệm", "synonyms": ["a1c"]},
    "Tăng huyết áp": {"type": "Bệnh", "icd10": "I10", "synonyms": ["cao huyết áp"]},
    "Cồn": {"type": "Yếu tố", "synonyms": ["rượu", "bia", "ethanol"]},
}

# Quan hệ giữa các thực thể.
TRIPLES = [
    ("Đái tháo đường týp 2", "điều trị bước đầu bằng", "Metformin"),
    ("Đái tháo đường týp 2", "có thể điều trị bằng", "Ức chế SGLT2"),
    ("Đái tháo đường týp 2", "có thể điều trị bằng", "Ức chế DPP-4"),
    ("Đái tháo đường týp 2", "có thể điều trị bằng", "Sulfonylurea"),
    ("Đái tháo đường týp 1", "điều trị bằng", "Insulin"),
    ("Metformin", "có tác dụng phụ", "Toan chuyển hoá lactic"),
    ("Metformin", "chống chỉ định khi", "Suy thận"),
    ("Sulfonylurea", "có tác dụng phụ", "Hạ đường huyết"),
    ("Insulin", "có tác dụng phụ", "Hạ đường huyết"),
    ("Cồn", "làm tăng nguy cơ", "Hạ đường huyết"),
    ("Cồn", "tương tác với", "Metformin"),
    ("Ức chế SGLT2", "có lợi ích trên", "Suy thận"),
    ("Đái tháo đường týp 2", "gây biến chứng", "Biến chứng thận do đái tháo đường"),
    ("Đái tháo đường týp 2", "gây biến chứng", "Biến chứng mắt do đái tháo đường"),
    ("Đái tháo đường týp 2", "thường đi kèm", "Tăng huyết áp"),
    ("HbA1c", "dùng để theo dõi", "Đái tháo đường týp 2"),
    ("Suy thận", "cần chỉnh liều", "Metformin"),
]

import random
import re
from typing import List, Optional

# Kho Hashtag Đạo Lý, Phật Pháp, Lối Sống Đẹp chuẩn xu hướng
HASHTAG_CATEGORIES = {
    "phat_phap_nhan_qua": [
        "#luatnhanqua", "#loiphatday", "#nhanqua", "#phatphap", 
        "#phatphapnhiemmau", "#daophat", "#loivangphatday", "#nhanquabaoung",
        "#phatgiao", "#trietlyphatgiao", "#loiphatdaymoingay"
    ],
    "tu_tap_tam_hon": [
        "#tutaptaigia", "#tutap", "#tinhtam", "#tamhon", 
        "#tinhthuc", "#anlac", "#chualanh", "#binhyen", 
        "#thien", "#songtinhthuc", "#chualanhnoitam"
    ],
    "dao_duc_bai_hoc": [
        "#daoduc", "#baihoccuocsong", "#songdep", "#nhancach", 
        "#trietlycuocsong", "#loikhuyencuocsong", "#hoclamnguoi", 
        "#songcogiatri", "#gocnhincuocsong", "#loikhuyenhay"
    ],
    "tinh_thuong_gia_dinh": [
        "#yeuthuong", "#giadinh", "#daycon", "#hieuthuan", 
        "#longtrian", "#tuthien", "#thaothu", "#tamlongnhanai"
    ],
    "xu_huong": [
        "#xuhuong", "#videohay", "#ynghiacuocsong", "#viralvideo"
    ]
}

# Danh sách hashtag cốt lõi luôn được ưu tiên
CORE_HASHTAGS = ["#luatnhanqua", "#loiphatday", "#tutaptaigia", "#baihoccuocsong", "#songdep", "#trietlycuocsong"]

class HashtagManager:
    def __init__(self):
        self.categories = HASHTAG_CATEGORIES
        self.core = CORE_HASHTAGS

    def generate_random_hashtags(self, script_text: str = "", count: int = 5) -> str:
        """Tự động phân tích nội dung và chọn ngẫu nhiên bộ hashtag đạo lý phù hợp nhất"""
        selected = []

        # 1. Luôn chọn 2 hashtag cốt lõi (luatnhanqua, loiphatday, tutaptaigia, ...)
        core_samples = random.sample(self.core, min(2, len(self.core)))
        selected.extend(core_samples)

        # 2. Phân tích nội dung văn bản để ưu tiên hashtag theo chủ đề
        text_lower = (script_text or "").lower()
        
        # Nếu có từ khóa về gia đình, cha mẹ, con cái
        if any(w in text_lower for w in ["cha mẹ", "con cái", "gia đình", "hiếu thuận", "dạy con", "mẹ", "cha"]):
            fam_tags = random.sample(self.categories["tinh_thuong_gia_dinh"], min(2, len(self.categories["tinh_thuong_gia_dinh"])))
            selected.extend(fam_tags)

        # Nếu có từ khóa về từ bi, lỗi lầm, tha thứ, tâm
        if any(w in text_lower for w in ["từ bi", "yêu thương", "lỗi lầm", "tha thứ", "tâm", "tĩnh tâm"]):
            peace_tags = random.sample(self.categories["tu_tap_tam_hon"], min(2, len(self.categories["tu_tap_tam_hon"])))
            selected.extend(peace_tags)

        # 3. Bổ sung thêm các hashtag từ nhóm đạo đức & bài học cuộc sống
        lesson_tags = random.sample(self.categories["dao_duc_bai_hoc"], min(2, len(self.categories["dao_duc_bai_hoc"])))
        selected.extend(lesson_tags)

        # 4. Lấy ngẫu nhiên từ nhóm Phật pháp
        dharma_tags = random.sample(self.categories["phat_phap_nhan_qua"], min(2, len(self.categories["phat_phap_nhan_qua"])))
        selected.extend(dharma_tags)

        # Loại bỏ trùng lặp và lấy đúng số lượng mong muốn (mặc định 4-5 tags)
        unique_selected = list(dict.fromkeys(selected))
        final_tags = unique_selected[:count]

        return " ".join(final_tags)

hashtag_mgr = HashtagManager()

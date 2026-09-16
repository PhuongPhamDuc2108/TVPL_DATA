-- ============================================================================
--  Lưu CÂU TRẢ LỜI CỦA AI theo từng câu hỏi, ngay trong DB.
--
--  Trước đây ô "AI trả lời & đối chiếu căn cứ" ở public/index.html chỉ lưu vào
--  localStorage của trình duyệt. Nghĩa là nội dung dán vào đó:
--    * mất khi xoá site data, dùng cửa sổ ẩn danh, hoặc đổi máy;
--    * KHÔNG thấy được khi mở app bằng địa chỉ khác — localStorage tính theo
--      origin, nên http://localhost:8002 và http://10.110.40.37:8002 là hai
--      kho tách biệt. Đây là lý do hay gặp nhất khiến "lần sau load lên bị rỗng".
--
--  Hai cột dưới đây đưa nội dung đó về DB, dùng chung cho mọi máy, mọi origin.
--  localStorage vẫn giữ làm bản dự phòng cho bản ghi nạp từ file JSON (chưa có
--  cau_hoi_id nên không có chỗ trong DB để ghi).
--
--  Chạy:  venv\Scripts\python.exe -c "..." hoặc dán vào DataGrip.
--  Idempotent — chạy lại bao nhiêu lần cũng được.
-- ============================================================================

ALTER TABLE cau_hoi ADD COLUMN IF NOT EXISTS ai_tra_loi   text;
ALTER TABLE cau_hoi ADD COLUMN IF NOT EXISTS ai_cap_nhat  timestamptz;

COMMENT ON COLUMN cau_hoi.ai_tra_loi IS
  'Câu trả lời của AI dán ở trang /, để đối chiếu căn cứ với dap_an. '
  'NULL = chưa dán gì. Xoá trắng ô trên giao diện cũng đặt về NULL.';
COMMENT ON COLUMN cau_hoi.ai_cap_nhat IS
  'Lần cuối ai_tra_loi được ghi. Dùng để biết câu nào đã chấm, chấm lúc nào.';

-- Câu nào đã dán câu trả lời AI — để lọc nhanh khi chấm.
CREATE INDEX IF NOT EXISTS ix_cau_hoi_co_ai
    ON cau_hoi (cau_hoi_id) WHERE ai_tra_loi IS NOT NULL;

-- Tiến độ chấm: đã dán bao nhiêu / còn bao nhiêu, theo chủ đề.
CREATE OR REPLACE VIEW v_tien_do_ai AS
SELECT coalesce(d.ten, '(chưa gán chủ đề)') AS chu_de,
       count(*)                                        AS tong_cau,
       count(*) FILTER (WHERE c.ai_tra_loi IS NOT NULL) AS da_dan,
       count(*) FILTER (WHERE c.ai_tra_loi IS NULL)     AS chua_dan,
       max(c.ai_cap_nhat)                               AS lan_dan_gan_nhat
FROM cau_hoi c
LEFT JOIN chu_de d ON d.chu_de_id = c.chu_de_id
GROUP BY 1;

-- Lưu kết quả CHẤM BẰNG LLM (cham_llm.py). Idempotent, chạy lại được.
ALTER TABLE cau_hoi ADD COLUMN IF NOT EXISTS ai_cham     jsonb;
ALTER TABLE cau_hoi ADD COLUMN IF NOT EXISTS ai_cham_luc timestamptz;

COMMENT ON COLUMN cau_hoi.ai_cham IS
  'Kết quả chấm ai_tra_loi bằng LLM (cham_llm.py): ket_luan, diem_noi_dung, '
  'diem_can_cu, y_dung/y_thieu/y_sai, can_cu_sai, nhan_xet, model. '
  'Lưu lại để mở trang không phải gọi API lần nữa.';
COMMENT ON COLUMN cau_hoi.ai_cham_luc IS 'Lần cuối chấm bằng LLM';

CREATE INDEX IF NOT EXISTS ix_cau_hoi_ket_luan_cham
    ON cau_hoi ((ai_cham->>'ket_luan')) WHERE ai_cham IS NOT NULL;

-- Tiến độ + kết quả chấm theo chủ đề
CREATE OR REPLACE VIEW v_ket_qua_cham AS
SELECT coalesce(d.ten,'(chưa gán chủ đề)') AS chu_de,
       count(*)                                          AS tong_cau,
       count(*) FILTER (WHERE c.ai_tra_loi IS NOT NULL)   AS da_dan,
       count(*) FILTER (WHERE c.ai_cham IS NOT NULL)      AS da_cham,
       count(*) FILTER (WHERE c.ai_cham->>'ket_luan'='khop')          AS khop,
       count(*) FILTER (WHERE c.ai_cham->>'ket_luan'='mot_phan')      AS mot_phan,
       count(*) FILTER (WHERE c.ai_cham->>'ket_luan'='trai_nguoc')    AS trai_nguoc,
       count(*) FILTER (WHERE c.ai_cham->>'ket_luan'='khong_tra_loi') AS khong_tra_loi,
       round(avg((c.ai_cham->>'diem_noi_dung')::numeric),1) AS tb_noi_dung,
       round(avg((c.ai_cham->>'diem_can_cu')::numeric),1)   AS tb_can_cu
FROM cau_hoi c LEFT JOIN chu_de d ON d.chu_de_id=c.chu_de_id
GROUP BY 1;

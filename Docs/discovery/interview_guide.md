# Kịch bản phỏng vấn HLV — tìm hiểu nhu cầu (P1.01)

| Mục | Nội dung |
| --- | -------- |
| Phiên bản | v0.2, ngày 2026-11-15 (v0.1 sửa theo lần chạy thử với 3 hồ sơ mô phỏng, BUG-0037) |
| Người giữ bản chính | O (chủ dự án) |
| Trạng thái | Đã chạy thử trên hồ sơ mô phỏng (không phải HLV thật). Buổi phỏng vấn thật đầu tiên là lần đọc thử thật; sau đó sửa lại trước buổi tiếp theo |
| Thời lượng | khoảng 62 phút |
| Dùng cùng | mẫu biên bản `Docs/discovery/notes/_TEMPLATE.md` (soạn ở P1.02) |

## Dành cho người phỏng vấn

**Mục đích:** hiểu HLV đang xem và nhận xét video bài Thái cực quyền như thế nào, mất bao lâu, vướng ở đâu, rồi mới hỏi
ý kiến về ba số đo dự kiến. Kết quả dùng cho bản tổng hợp nhu cầu (P1.03), mục tiêu của đợt thử nghiệm (P1.08) và danh
mục động tác (P1.04).

**Nguyên tắc:**

1. Hỏi theo đúng thứ tự. Không nhắc đến số đo hay công cụ trước phần 6, để câu trả lời không bị dẫn dắt.
2. Hỏi về một lần làm cụ thể ("lần gần nhất thầy/cô…") thay vì hỏi chung chung.
3. Ghi thời gian bằng con số (phút). Nếu HLV nói một khoảng, ghi cả mức thấp và mức cao.
4. Không gợi ý câu trả lời, không tranh luận. Nếu HLV hỏi "bao nhiêu là tốt", trả lời rằng chưa có mức chuẩn nào; nếu
   sau này cần, mức đó do HLV quyết định sau khi đã đo.
5. Không ghi tên thật của HLV, tên học viên, tên câu lạc bộ hay nơi dạy, số điện thoại, địa chỉ. HLV được gọi bằng mã
   (H1, H2…). Bảng đối chiếu mã với người thật do O giữ, ngoài kho mã nguồn.
6. Chỉ ghi chép, không ghi âm.
7. Viết biên bản theo mẫu trong vòng 24 giờ sau buổi phỏng vấn.

**Chuẩn bị:** bản in kịch bản này; ba thẻ phác thảo ở Phụ lục A, mỗi thẻ in một trang; bảng ghi thời gian ở Phụ lục B;
mẫu biên bản; đồng hồ.

## Phần 0 — Mở đầu (5 phút)

Lời mở đầu gợi ý (đọc nguyên văn hoặc nói theo ý):

> Cảm ơn thầy/cô đã dành thời gian. Chúng tôi đang tìm hiểu cách các huấn luyện viên xem và nhận xét bài tập Thái cực
> quyền qua video, để biết một công cụ đo có giúp được gì không. Buổi nói chuyện khoảng một giờ. Chúng tôi chỉ ghi chép,
> không ghi âm. Trong ghi chép, thầy/cô được gọi bằng một mã, không có tên thầy/cô, tên học viên hay nơi dạy. Thầy/cô có
> thể bỏ qua bất kỳ câu hỏi nào và dừng lúc nào cũng được. Không có câu trả lời đúng hay sai: chúng tôi muốn biết
> thầy/cô đang làm thế nào trong thực tế.

Hỏi: "Thầy/cô đồng ý để chúng tôi ghi chép buổi nói chuyện này chứ?" Ghi lại câu trả lời. Nếu HLV không đồng ý, cảm ơn
và kết thúc buổi gặp.

## Phần 1 — Thông tin chung (7 phút)

- **1.1** Thầy/cô dạy Thái cực quyền được bao lâu? (ghi theo khoảng: dưới 5 năm, 5–10, 10–20, trên 20)
- **1.2** Thầy/cô dạy những trình độ nào (mới tập, tập phong trào, thi đấu)? Một lớp thường có bao nhiêu người?
- **1.3** Hiện nay ai quay video bài tập? (HLV quay học viên, học viên tự quay rồi gửi, quay ở giải…)
- **1.4** Bài 24 thức thầy/cô dạy là phiên bản nào? Cách chia bài thành các thức, cách gọi tên và cách đếm số lần lặp
  của thầy/cô có chỗ nào khác với cách gọi và cách chia phổ biến không? *(Chỉ hỏi phiên bản và những chỗ khác biệt. Nếu
  HLV cần hơn 7 phút để đi qua từng thức, hẹn một buổi riêng khoảng 30 phút để xác nhận danh mục thức: đây là đầu vào cho
  danh mục động tác P1.04. Nếu HLV có tài liệu về bài, hỏi xem có thể cho xem không.)*

## Phần 2 — Cách xem và nhận xét video hiện nay (15 phút)

Câu mở: "Thầy/cô kể lại giúp lần gần nhất thầy/cô xem video bài tập của một học viên và nhận xét, từ lúc nhận video
đến lúc học viên nhận được nhận xét."

- **2.1** Video đến tay thầy/cô bằng cách nào?
- **2.2** Thầy/cô xem trên thiết bị gì, bằng phần mềm nào? Có tua chậm, dừng hình, xem từng khung hình, vẽ lên hình,
  hoặc đặt hai video cạnh nhau không?
- **2.3** Liệt kê từng bước, và mỗi bước mất bao nhiêu phút (điền Bảng ở Phụ lục B).
- **2.4** Với một lần tập trọn bài khoảng 6 phút, tổng cộng thầy/cô mất bao nhiêu phút để xem và nhận xét? (ghi con
  số; nếu dao động, ghi mức thấp nhất và cao nhất)
- **2.5** Nhận xét được gửi dưới dạng nào: nói trực tiếp, tin nhắn, ghi chú theo mốc thời gian trong video, bảng điểm?
- **2.6** Mỗi tuần thầy/cô xem khoảng bao nhiêu video như vậy?
- **2.7** Thầy/cô có so sánh với một video mẫu không? Mẫu là ai thực hiện, và thầy/cô so sánh thế nào?

## Phần 3 — HLV nhìn vào điều gì (5 phút)

- **3.1** Khi xem một lần tập 24 thức, thầy/cô kiểm tra điều gì đầu tiên?
- **3.2** Học viên hay mắc những lỗi nào nhất?
- **3.3** Phần nào trong bài khó nhận xét qua video nhất? Vì sao (góc quay, tốc độ, bị che khuất, quay lưng…)?

## Phần 4 — Điểm vướng (5 phút)

- **4.1** Trong việc nhận xét qua video, việc gì tốn thời gian nhất?
- **4.2** Việc gì hay bị sai, hoặc hay khiến học viên chưa hiểu, chưa đồng ý với nhận xét?
- **4.3** Có khi nào hai HLV nhận xét khác nhau về cùng một lần tập không? Thầy/cô kể giúp một ví dụ.

## Phần 5 — Mong muốn (5 phút, trước khi đưa phác thảo)

- **5.1** Nếu có một công cụ hỗ trợ xem video, thầy/cô muốn nó giúp việc gì nhất?
- **5.2** Có điều gì thầy/cô muốn đo được bằng con số mà hiện nay chỉ ước lượng bằng mắt?
- **5.3** Điều gì sẽ khiến thầy/cô không dùng một công cụ như vậy?

## Phần 6 — Ba phác thảo số đo (15 phút)

Lần lượt đưa từng thẻ ở Phụ lục A, đọc nội dung thẻ, không giải thích thêm. Với mỗi thẻ hỏi đúng bốn câu:

- **a)** Thầy/cô có dùng số đo này khi nhận xét không? Dùng ở đoạn nào của bài?
- **b)** Trường hợp nào nó sẽ sai hoặc làm hiểu nhầm?
- **c)** Kết quả, đường hay số lần nào trong thẻ này thầy/cô sẽ không tin?
- **d)** Thầy/cô muốn giữ nguyên, sửa (sửa thế nào) hay bỏ?

Ghi câu trả lời riêng cho từng thẻ. Nếu HLV hỏi mức bao nhiêu là tốt: chưa có mức nào; nếu sau này cần, mức đó do HLV
quyết định sau khi đo.

## Phần 7 — Điều kiện quay (3 phút)

- **7.1** Thầy/cô thường tập và dạy ở đâu (trong nhà hay ngoài trời; không cần tên địa điểm)? Có đủ chỗ đặt hai điện
  thoại cách người tập vài mét, một ở phía trước và một ở bên cạnh không?
- **7.2** Học viên thường quay bằng điện thoại gì? Có chân máy không?
- **7.3** Ánh sáng, phông nền và người qua lại ở đó thế nào?

## Phần 8 — Thời gian cho đợt thử nghiệm (2 phút)

- **8.1** Nếu có một đợt thử nghiệm, mỗi tháng thầy/cô có thể dành khoảng bao nhiêu giờ (chia đoạn video, chấm, góp ý)?
- **8.2** Thời gian nào trong năm thuận tiện, thời gian nào không?

## Kết thúc

Cảm ơn HLV. Hỏi thầy/cô có muốn nhận bản tổng hợp (chỉ dùng mã, không có tên) không. Không hứa hẹn về kết quả hay lịch.

## Phụ lục A — Ba thẻ phác thảo

In mỗi thẻ trên một trang. Thẻ không có con số nào: hình minh họa chỉ là hình vẽ, không ghi giá trị.

### Thẻ 1 — Độ cao hông thay đổi

- **Đo gì:** trong một đoạn mà thầy/cô cho là độ cao hông cần giữ ổn định, hông lên xuống bao nhiêu. Số đo tính theo
  chiều dài thân của chính người tập, để người cao và người thấp so được với nhau.
- **Thấy gì:** một đường theo thời gian cho thấy hông lên xuống trong đoạn đó, và độ dao động của nó (bỏ qua vài khoảnh
  khắc ngoại lệ).
- **Không cho biết:** độ cao thật tính bằng xăng-ti-mét. Số đo kém tin cậy khi người tập tiến lại gần hoặc lùi xa camera
  nhiều. Chỉ đo từ một camera.
- **Hình minh họa:** một đường lượn lên xuống nhẹ theo thời gian, không ghi số.

### Thẻ 2 — Thân nghiêng trên hình

- **Đo gì:** góc giữa trục thân (từ giữa hông lên giữa vai) và đường thẳng đứng, đo trên hình, sau khi trừ độ nghiêng
  của chính điện thoại.
- **Chỉ dùng được khi:** camera chính diện, để xem nghiêng sang trái hoặc sang phải; camera đặt ngang, để xem nghiêng ra
  trước hoặc ra sau.
- **Thấy gì:** góc nghiêng theo thời gian, góc thường gặp trong đoạn, và mức nghiêng lớn trong đoạn (bỏ qua vài khoảnh
  khắc ngoại lệ).
- **Không cho biết:** góc thật trong không gian khi người tập xoay chéo so với camera. Không phân biệt được nghiêng do
  động tác yêu cầu hay nghiêng do lỗi: việc này HLV quyết định.
- **Hình minh họa:** hình người với một đường thẳng đứng và trục thân, góc giữa hai đường được tô đậm, không ghi số.

### Thẻ 3 — Nhịp và độ liên tục

- **Đo gì:** tay, hông và chân chuyển động nhanh hay chậm theo thời gian thật (tính bằng số lần chiều dài thân mỗi
  giây), và những khoảng gần như dừng hẳn.
- **Thấy gì:** đường tốc độ của từng nhóm (tay, hông, chân), số lần dừng và độ dài mỗi lần dừng, tốc độ có đều hay
  không.
- **Không cho biết:** lúc nào thì được phép dừng. Mức "coi là dừng" không có giá trị chung; nó sẽ được rút ra từ những
  đoạn HLV đánh dấu cho từng loại động tác. Chuyển động hướng thẳng về phía camera hoặc ra xa camera bị đo thiếu.
- **Hình minh họa:** một đường tốc độ lên xuống, có vài khoảng gần chạm đáy được tô màu, không ghi số.

## Phụ lục B — Bảng ghi thời gian (phần 2)

| Bước | Việc làm | Phút (thấp – cao) | Công cụ |
| ---- | -------- | ----------------- | ------- |
| 1 | | | |
| 2 | | | |
| 3 | | | |
| 4 | | | |
| 5 | | | |
| 6 | | | |
| 7 | | | |
| 8 | | | |
| Tổng cho một lần tập trọn bài khoảng 6 phút | | | |

Thêm dòng nếu HLV có nhiều hơn 8 bước.

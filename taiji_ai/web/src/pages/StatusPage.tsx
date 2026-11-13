import { ApiError } from "../api/client";
import { useHealth } from "../api/health";

const ROLE_LABEL: Record<string, string> = { det: "Phát hiện người", pose: "Ước lượng pose" };

export function StatusPage() {
  const { data, error, isPending } = useHealth();

  if (isPending) return <p role="status">Đang kiểm tra hệ thống…</p>;
  if (error) {
    const code = error instanceof ApiError ? error.code : "unknown_error";
    return (
      <section>
        <h1>Trạng thái hệ thống</h1>
        <p role="alert" className="bad">
          Không lấy được trạng thái ({code}): {error.message}
        </p>
      </section>
    );
  }

  const ok = data.status === "ok";
  return (
    <section>
      <h1>Trạng thái hệ thống</h1>
      <p data-testid="overall" className={ok ? "good" : "bad"}>
        {ok ? "Hoạt động bình thường" : "Có vấn đề cần xử lý"} · phiên bản {data.version}
      </p>

      <h2>Model</h2>
      {data.models.ok ? (
        <ul>
          {data.models.entries.map((m) => (
            <li key={m.name}>
              {ROLE_LABEL[m.role] ?? m.role}: <code>{m.name}</code> · sha256 <code>{m.sha256_prefix}</code>
            </li>
          ))}
        </ul>
      ) : (
        <p className="bad">Lỗi model: {data.models.error}</p>
      )}

      <h2>Cơ sở dữ liệu</h2>
      {data.database.ok ? (
        <p>Migration đã áp dụng: {data.database.migrations.join(", ") || "không có"}</p>
      ) : (
        <p className="bad">Lỗi cơ sở dữ liệu: {data.database.error}</p>
      )}
    </section>
  );
}

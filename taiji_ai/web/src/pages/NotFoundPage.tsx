import { Link } from "react-router";

export function NotFoundPage() {
  return (
    <section>
      <h1>Không tìm thấy trang</h1>
      <p>
        <Link to="/">Về trang trạng thái</Link>
      </p>
    </section>
  );
}

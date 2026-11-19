import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";

export function Footer() {
  return (
    <footer>
      <div className="container footer-inner">
        <Link className="brand" to="/">
          <span className="brand-mark">✳</span>
          <span>сириус.еда</span>
        </Link>
        <span>Больше времени на жизнь. Меньше — на выбор обеда.</span>
        <Link to="/help">
          Как это работает <ArrowRight size={14} />
        </Link>
        <span className="small">Тестовый режим</span>
      </div>
    </footer>
  );
}

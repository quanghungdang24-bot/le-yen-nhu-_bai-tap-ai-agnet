import sys
import urllib.parse
from pathlib import Path

# Đảm bảo thư mục gốc dự án nằm trong sys.path khi chạy trên Vercel Serverless
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from server import B2BAgentHttpHandler


class handler(B2BAgentHttpHandler):
    """Vercel Python Serverless entrypoint kế thừa toàn bộ API từ B2BAgentHttpHandler."""

    _GENERIC_ENTRYPOINTS = {"", "/", "/api", "/index.py", "/api/index", "/api/index.py"}

    @classmethod
    def _normalize_api_path(cls, raw_path: str):
        if not raw_path:
            return None
        clean = urllib.parse.unquote(str(raw_path)).strip()
        if not clean:
            return None
        clean = urllib.parse.urlparse(clean).path.strip()
        if not clean:
            return None
        clean_no_slash = clean.rstrip("/")
        if clean_no_slash in cls._GENERIC_ENTRYPOINTS:
            return None
        # Bỏ qua placeholder chưa được thay thế (vd: $1, :path*)
        stripped_leading = clean_no_slash.lstrip("/")
        if not stripped_leading or stripped_leading.startswith(("$", ":")):
            return None
        if stripped_leading in ("index", "index.py", "api/index", "api/index.py"):
            return None
        if not clean_no_slash.startswith("/"):
            clean_no_slash = "/" + clean_no_slash
        if not clean_no_slash.startswith("/api/"):
            clean_no_slash = "/api" + clean_no_slash
        return clean_no_slash

    def _extract_from_vercel_headers(self):
        for hdr in (
            "x-vercel-original-path",
            "x-invoke-path",
            "x-matched-path",
            "x-original-url",
            "x-rewrite-url",
            "x-forwarded-uri",
        ):
            candidate = self._normalize_api_path(self.headers.get(hdr) or "")
            if candidate:
                return candidate

        route_matches = (self.headers.get("x-now-route-matches") or "").strip()
        if route_matches:
            matched_qs = urllib.parse.parse_qs(route_matches, keep_blank_values=False)
            for key in ("path", "1", "0"):
                vals = matched_qs.get(key)
                if vals:
                    candidate = self._normalize_api_path(vals[0])
                    if candidate:
                        return candidate
        return None

    def _restore_api_path(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        q_api_path = (qs.pop("_api_path", [None])[0] or "").strip()
        q_legacy_subpath = (qs.pop("__api_path", [None])[0] or "").strip()
        new_query = urllib.parse.urlencode(qs, doseq=True)

        # 1. Nếu Vercel đã giữ nguyên đường dẫn thực (vd /api/login), dùng luôn
        resolved = self._normalize_api_path(parsed.path)

        # 2. Ưu tiên header X-Api-Path do frontend app.js đính kèm
        if not resolved:
            resolved = self._normalize_api_path(self.headers.get("X-Api-Path") or "")

        # 3. Khôi phục từ query param _api_path hoặc __api_path
        if not resolved and q_api_path:
            resolved = self._normalize_api_path(q_api_path)
        if not resolved and q_legacy_subpath:
            resolved = self._normalize_api_path(q_legacy_subpath)

        # 4. Fallback qua các header định tuyến của Vercel
        if not resolved:
            resolved = self._extract_from_vercel_headers()

        if resolved:
            self.path = f"{resolved}?{new_query}" if new_query else resolved

    def do_OPTIONS(self):
        return super().do_OPTIONS()

    def do_GET(self):
        self._restore_api_path()
        return super().do_GET()

    def do_POST(self):
        self._restore_api_path()
        return super().do_POST()

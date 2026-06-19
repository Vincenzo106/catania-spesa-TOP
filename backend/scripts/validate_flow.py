import json
import os
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

warnings.filterwarnings(
    "ignore",
    message="Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.",
)

from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from scripts.generate_sample_flyer import create_sample_flyer  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
        temp_root = Path(temp_dir)
        flyer_path = create_sample_flyer(temp_root / "validation-flyer.png")
        payload_path = temp_root / "offers.json"
        db_path = temp_root / "offers.db"
        upload_dir = temp_root / "uploads"

        settings = Settings(
            _env_file=None,
            database_path=db_path,
            upload_dir=upload_dir,
            seed_demo_data=False,
            vision_provider="mock",
        )
        app = create_app(settings)

        with TestClient(app) as client:
            with flyer_path.open("rb") as handle:
                response = client.post(
                    "/offers/ingest",
                    data={"store": "Coop", "replace_existing": "true"},
                    files={"file": (flyer_path.name, handle, "image/png")},
                )
            if response.status_code != 200:
                raise SystemExit(f"Ingest failed: {response.status_code} {response.text}")

            offers_response = client.get("/offers", params={"store": "Coop"})
            if offers_response.status_code != 200:
                raise SystemExit(
                    f"Offer listing failed: {offers_response.status_code} {offers_response.text}"
                )

        offers = offers_response.json()["items"]
        payload_path.write_text(json.dumps(offers), encoding="utf-8")

        node_binary = os.environ.get("NODE_BINARY", "node")
        verify_script = ROOT_DIR / "frontend" / "scripts" / "verifyFrontendContract.js"
        verification = subprocess.run(
            [node_binary, str(verify_script), str(payload_path)],
            capture_output=True,
            encoding="utf-8",
            text=True,
            check=False,
        )
        if verification.returncode != 0:
            message = verification.stderr.strip() or verification.stdout.strip()
            raise SystemExit(f"Frontend contract verification failed: {message}")

        print("Validation passed.")
        print(verification.stdout.strip())
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

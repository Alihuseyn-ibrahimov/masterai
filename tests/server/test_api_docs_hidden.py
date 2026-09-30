"""API sənədləşməsi produksiyada AÇIQ OLMAMALIDIR (Faza 9 hücum yoxlaması).

`api.masterai.prdostu.com` bloku hər yolu backend-ə ötürür (`location /`).
FastAPI isə default olaraq `/docs`, `/redoc` və `/openapi.json` verir — yəni
istənilən tələbə bütün endpoint-lərin, o cümlədən `/owner/*` panelinin və
bütün sorğu sxemlərinin xəritəsini bir kliklə görə bilərdi. Hücumçu üçün
hazır bələdçi. Client bu fayllardan istifadə etmir.
"""

import pytest
from fastapi.testclient import TestClient

from server.app import app


@pytest.mark.parametrize("path", ["/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect"])
def test_api_docs_not_served(path):
    assert TestClient(app).get(path).status_code == 404

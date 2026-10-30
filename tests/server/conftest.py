"""Server testləri üçün ortaq fixture-lar."""

import pytest

from server.app import (
    LOGIN_MAX_FAILURES,
    LOGIN_WINDOW_SECONDS,
    PIN_MAX_FAILURES,
    app,
    get_material_store,
    get_question_set_store,
)
from server.material_store import MaterialStore
from server.question_set_store import QuestionSetStore
from server.rate_limit import RateLimiter


@pytest.fixture(autouse=True)
def _fresh_rate_limiters():
    """Sürət limiti sayğacları proses-daxilidir (`app.state`) və testlər
    arasında DAŞINIR. Bir testin səhv girişləri başqa testdə eyni e-poçt
    üçün təsadüfi 429 verərdi - nəticə testlərin SIRASINDAN asılı olardı.
    Hər test təzə sayğacla başlayır; override edən testlər öz nüsxəsini
    `dependency_overrides` ilə verməyə davam edir."""
    app.state.join_rate_limiter = RateLimiter()
    app.state.register_rate_limiter = RateLimiter()
    app.state.login_rate_limiter = RateLimiter(LOGIN_MAX_FAILURES, LOGIN_WINDOW_SECONDS)
    app.state.pin_rate_limiter = RateLimiter(PIN_MAX_FAILURES, 60)
    yield


@pytest.fixture(autouse=True)
def _isolated_quota_stores():
    """Gündəlik yükləmə limiti (spec §4.5) HƏR yükləmədə materialları VƏ
    bankları sayır. Yalnız birini override edən test o biri üçün
    `app.state`-in REAL faylını (`materials.db` / `question_sets.db`,
    iş qovluğunda) oxuyardı - nəticə tərtibatçının kompüterindəki dataya
    bağlı olardı. Autouse fixture-lar əvvəl işləyir, yəni öz nüsxəsini
    verən test bunu əvəz edir."""
    materials = MaterialStore(":memory:")
    question_sets = QuestionSetStore(":memory:")
    app.dependency_overrides[get_material_store] = lambda: materials
    app.dependency_overrides[get_question_set_store] = lambda: question_sets
    yield
    app.dependency_overrides.pop(get_material_store, None)
    app.dependency_overrides.pop(get_question_set_store, None)

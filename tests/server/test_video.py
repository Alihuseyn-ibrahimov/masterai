"""LiveKit token köməkçiləri (Classroom, gün 2)."""

import jwt

from server.video import LiveKitConfig, livekit_config, make_join_token


def test_config_needs_all_three_keys():
    full = {"LIVEKIT_URL": "wss://x", "LIVEKIT_API_KEY": "k", "LIVEKIT_API_SECRET": "s"}
    assert livekit_config(full) == LiveKitConfig("wss://x", "k", "s")
    for missing in full:
        assert livekit_config({k: v for k, v in full.items() if k != missing}) is None
    assert livekit_config({**full, "LIVEKIT_URL": "  "}) is None


def test_token_lifetime_and_grants():
    cfg = LiveKitConfig("wss://x", "key", "secret-" * 6)
    token = make_join_token(cfg, room="r1", identity="user-7", name="Səbinə",
                            is_host=False, ttl_seconds=600, now=1_000_000)
    claims = jwt.decode(token, cfg.api_secret, algorithms=["HS256"], options={"verify_exp": False, "verify_nbf": False})
    assert claims["exp"] - 1_000_000 == 600
    assert claims["video"] == {"room": "r1", "roomJoin": True, "canPublish": True, "canSubscribe": True,
                               "canPublishData": True, "roomAdmin": False}
    assert claims["metadata"] == '{"role": "student"}'

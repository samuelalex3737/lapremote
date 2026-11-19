"""AI planner, providers and executor. A scripted provider stands in for the model."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from lapremote.ai.planner import (
    NOT_UNDERSTOOD,
    Planner,
    PlannerContext,
    build_system_prompt,
    needs_confirm,
    validate_actions,
)
from lapremote.ai.providers import (
    GeminiProvider,
    GroqProvider,
    OllamaProvider,
    create_provider,
    recommended_ollama_model,
)
from lapremote.config import AiConfig
from lapremote.protocol import AI_ACTION_TYPES, AI_PAYLOADS, AiAction
from lapremote.router import ActionError

from .fakes import (
    FakeLauncher,
    FakeMediaBackend,
    FakePower,
    FakeVolume,
    ScriptedProvider,
    session,
)
from .test_input import recorder_devices
from .wsclient import Phone, make_app, pair_new, phone


def plan(reply: str, *actions: dict[str, Any]) -> str:
    return json.dumps({"reply": reply, "actions": list(actions)})


def ctx(**overrides: Any) -> PlannerContext:
    base: dict[str, Any] = {
        "shortcuts": [
            {"id": "youtube", "name": "YouTube", "kind": "url"},
            {"id": "vlc", "name": "VLC", "kind": "app"},
        ],
        "scenes": [{"id": "movie-night", "name": "Movie Night"}],
        "media": [{"id": "w1", "app": "Spotify"}],
    }
    base.update(overrides)
    return PlannerContext(**base)


# ---------------------------------------------------------------- validation


def test_every_allowlisted_action_has_a_payload_model() -> None:
    assert set(AI_PAYLOADS) == set(AI_ACTION_TYPES)


def test_unknown_and_invalid_actions_are_dropped() -> None:
    kept, dropped = validate_actions(
        [
            {"type": "volume.set", "payload": {"level": 30}},
            {"type": "shell.run", "payload": {"cmd": "rm -rf /"}},
            {"type": "volume.set", "payload": {"level": 300}},
            {"type": "launch.open", "payload": {"shortcutId": "evil"}},
            {"type": "scene.run", "payload": {"sceneId": "nope"}},
            {"type": "media.pause", "payload": {"sessionId": "gone"}},
            {"type": "key.press", "payload": {"key": "rm"}},
            {"type": "input.move", "payload": {"dx": 1, "dy": 1}},
            "pause",
            {"type": "brightness.set", "level": 50},
        ],
        ctx(),
    )
    assert [(a.type, a.payload) for a in kept] == [
        ("volume.set", {"level": 30}),
        ("brightness.set", {"level": 50}),
    ]
    assert dropped == [
        "shell.run (not allowed)",
        "volume.set (bad details)",
        "launch.open (there is no shortcut 'evil')",
        "scene.run (there is no scene 'nope')",
        "media.pause (that player isn't open)",
        "key.press (bad details)",
        "input.move (not allowed)",
        "a step that wasn't an action",
    ]


def test_power_from_the_planner_needs_no_token_and_extra_fields_are_refused() -> None:
    kept, dropped = validate_actions(
        [
            {"type": "power.action", "payload": {"action": "sleep"}},
            {"type": "power.action", "payload": {"action": "format"}},
            {"type": "wait", "payload": {"ms": 120_000}},
        ],
        ctx(),
    )
    assert [a.payload for a in kept] == [{"action": "sleep"}]
    assert dropped == ["power.action (bad details)", "wait (bad details)"]


def test_plans_are_capped() -> None:
    kept, dropped = validate_actions([{"type": "media.toggle"}] * 20, ctx())
    assert len(kept) == 12
    assert dropped == ["steps after the first 12"]


def test_confirmation_rules() -> None:
    def needs(*actions: dict[str, Any]) -> bool:
        return needs_confirm([AiAction.model_validate(a) for a in actions], ctx())

    assert needs({"type": "power.action", "payload": {"action": "lock"}})
    assert needs({"type": "key.text", "payload": {"text": "x" * 201}})
    assert not needs({"type": "key.text", "payload": {"text": "x" * 200}})
    assert needs({"type": "launch.open", "payload": {"shortcutId": "vlc"}})
    assert not needs({"type": "launch.open", "payload": {"shortcutId": "youtube"}})
    assert not needs({"type": "volume.set", "payload": {"level": 10}})


def test_system_prompt_lists_the_allowlist_and_context_but_no_window_title() -> None:
    prompt = build_system_prompt(
        ctx(foreground={"app": "Chrome", "category": "browser", "site": "youtube"})
    )
    for action_type in AI_ACTION_TYPES:
        assert f"- {action_type} {{" in prompt
    assert '"movie-night"' in prompt
    assert '"youtube"' in prompt
    assert "windowTitle" not in prompt
    assert "shell" not in prompt


# ---------------------------------------------------------------- planner


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_planner_retries_once_on_malformed_json() -> None:
    provider = ScriptedProvider(
        ["Sure! I'll pause it.", plan("Paused.", {"type": "media.pause", "payload": {}})]
    )
    draft = run(Planner(provider).plan("pause", ctx()))
    assert draft.reply == "Paused."
    assert [a.type for a in draft.actions] == ["media.pause"]
    assert len(provider.calls) == 2
    retry = provider.calls[1][1]
    assert [m.role for m in retry] == ["user", "assistant", "user"]


def test_planner_gives_up_after_two_bad_answers() -> None:
    provider = ScriptedProvider(["nope", "[1, 2]"])
    with pytest.raises(ActionError) as err:
        run(Planner(provider).plan("pause", ctx()))
    assert err.value.message == NOT_UNDERSTOOD


def test_planner_accepts_fenced_json_and_reports_dropped_steps() -> None:
    raw = (
        "```json\n"
        + plan(
            "On it.",
            {"type": "volume.set", "payload": {"level": 20}},
            {"type": "exec", "payload": {}},
        )
        + "\n```"
    )
    draft = run(Planner(ScriptedProvider([raw])).plan("quieter", ctx()))
    assert draft.reply == "On it. I left out 1 step I can't do."
    assert draft.dropped == ["exec (not allowed)"]


def test_provider_errors_become_friendly_action_errors() -> None:
    with pytest.raises(ActionError) as err:
        run(Planner(ScriptedProvider([])).plan("pause", ctx()))
    assert err.value.message == "The AI model isn't answering."


# ---------------------------------------------------------------- providers


def mock_client(handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_ollama_request_shape_and_model_check() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen2.5:7b"}]})
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "{}"}})

    async def go() -> tuple[str | None, str, str | None]:
        async with mock_client(handler) as client:
            ready = await OllamaProvider("http://127.0.0.1:11434", "qwen2.5:7b", client).check()
            other = OllamaProvider("http://127.0.0.1:11434", "llama3", client)
            missing = await other.check()
            answer = await OllamaProvider("http://127.0.0.1:11434/", "qwen2.5:7b", client).complete(
                "system", []
            )
            return ready, answer, missing

    ready, answer, missing = run(go())
    assert ready is None
    assert missing == "The model llama3 isn't installed. Run: ollama pull llama3"
    assert answer == "{}"
    body = json.loads(seen[-1].content)
    assert str(seen[-1].url) == "http://127.0.0.1:11434/api/chat"
    assert body["format"] == "json"
    assert body["options"] == {"temperature": 0}
    assert body["stream"] is False
    assert body["messages"][0] == {"role": "system", "content": "system"}


def test_ollama_not_running_is_reported() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    async def go() -> str | None:
        async with mock_client(handler) as client:
            return await OllamaProvider("http://127.0.0.1:1", "qwen2.5:7b", client).check()

    assert run(go()) == "Ollama isn't running on the laptop. Start it, or see the README for setup."


def test_gemini_key_goes_in_a_header_not_the_url() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": '{"actions": []}'}]}}]}
        )

    async def go() -> str:
        async with mock_client(handler) as client:
            provider = GeminiProvider("secret-key", "gemini-2.0-flash", client)
            return await provider.complete("sys", [])

    assert run(go()) == '{"actions": []}'
    request = seen[0]
    assert "secret-key" not in str(request.url)
    assert request.headers["x-goog-api-key"] == "secret-key"
    body = json.loads(request.content)
    assert body["generationConfig"] == {"temperature": 0, "responseMimeType": "application/json"}


def test_groq_request_shape() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    async def go() -> str:
        async with mock_client(handler) as client:
            return await GroqProvider("k", "llama-3.3-70b-versatile", client).complete("sys", [])

    assert run(go()) == "{}"
    assert seen[0].headers["authorization"] == "Bearer k"
    assert json.loads(seen[0].content)["response_format"] == {"type": "json_object"}


def test_provider_choice_and_keys_come_from_the_environment() -> None:
    async def go() -> None:
        async with httpx.AsyncClient() as client:
            groq = create_provider(AiConfig(provider="groq"), client, env={})
            assert isinstance(groq, GroqProvider)
            assert groq.model == "llama-3.3-70b-versatile"
            assert await groq.check() == "Set GROQ_API_KEY on the laptop to use Groq."
            gemini = create_provider(
                AiConfig(provider="gemini", model="gemini-1.5-flash"),
                client,
                env={"GEMINI_API_KEY": "x"},
            )
            assert gemini.model == "gemini-1.5-flash"
            assert await gemini.check() is None
            assert isinstance(create_provider(AiConfig(), client, env={}), OllamaProvider)

    run(go())


def test_model_by_memory() -> None:
    gib = 2**30
    assert recommended_ollama_model(int(15.7 * gib)) == "qwen2.5:7b"
    assert recommended_ollama_model(32 * gib) == "qwen2.5:7b"
    assert recommended_ollama_model(int(7.8 * gib)) == "qwen2.5:3b"


# ---------------------------------------------------------------- over the socket


class Rig:
    def __init__(self, home: Path, answers: list[str], sessions: list[Any] | None = None) -> None:
        self.provider = ScriptedProvider(answers)
        self.media = FakeMediaBackend(sessions or [])
        self.volume = FakeVolume(level=50)
        self.launcher = FakeLauncher()
        self.power = FakePower()
        self.devices, self.keys = recorder_devices()
        self.sleeps: list[float] = []
        self.app = make_app(
            home,
            ai_provider=self.provider,
            media_backend=self.media,
            volume_backend=self.volume,
            launcher=self.launcher,
            power_backend=self.power,
            input_devices=self.devices,
        )

    def install_sleep(self) -> None:
        async def fake_sleep(seconds: float) -> None:
            self.sleeps.append(seconds)

        services = self.app.state.services
        assert services.ai is not None
        services.ai.runner.sleep = fake_sleep


def ask(p: Phone, text: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Send ai.command; return the ai.plan payload and, when it ran, the ai.result payload."""
    p.send("ai.command", {"text": text})
    plan_msg = p.recv_type("ai.plan", limit=40)["payload"]
    if plan_msg["needsConfirm"] or not plan_msg["actions"]:
        return plan_msg, None
    result = p.recv_type("ai.result", limit=40)["payload"]
    assert result["planId"] == plan_msg["planId"]
    return plan_msg, result


SPEC_EXAMPLES = [
    (
        "pause everything",
        plan("Paused everything.", {"type": "media.pause", "payload": {}}),
    ),
    (
        "next episode and volume 30",
        plan(
            "Next one, volume 30.",
            {"type": "media.next", "payload": {}},
            {"type": "volume.set", "payload": {"level": 30}},
        ),
    ),
    (
        "open youtube and search lofi beats",
        plan(
            "Searching YouTube for lofi beats.",
            {"type": "launch.open", "payload": {"shortcutId": "youtube"}},
            {"type": "wait", "payload": {"ms": 4000}},
            {"type": "key.press", "payload": {"key": "/"}},
            {"type": "key.text", "payload": {"text": "lofi beats"}},
            {"type": "key.press", "payload": {"key": "enter"}},
        ),
    ),
    (
        "sleep the laptop in 40 minutes",
        plan(
            "The laptop will sleep in 40 minutes.",
            {
                "type": "timer.set",
                "payload": {"mode": "minutes", "minutes": 40, "then": "pause_sleep"},
            },
        ),
    ),
    (
        "go back 2 minutes",
        plan("Back 2 minutes.", {"type": "media.seek", "payload": {"by": -120}}),
    ),
]


def test_spec_examples_plan_and_run(isolated_home: Path) -> None:
    sessions = [
        session("w1", position=300.0, duration=600.0),
        session("w2", title="Podcast", position=50.0),
    ]
    rig = Rig(isolated_home, [answer for _, answer in SPEC_EXAMPLES], sessions)
    rig.install_sleep()
    with TestClient(rig.app) as client:
        device_id, token, _ = pair_new(client, rig.app)
        with phone(client) as p:
            p.resume(device_id, token)
            results = {}
            for text, _ in SPEC_EXAMPLES:
                plan_msg, result = ask(p, text)
                assert plan_msg["needsConfirm"] is False
                assert result is not None
                results[text] = (plan_msg, result)
                assert all(step["ok"] for step in result["steps"]), (text, result)
            # Checked before the agent shuts down, which cancels the timer.
            timer = rig.app.state.services.timer.state()

    assert results["pause everything"][1]["steps"] == [
        {"type": "media.pause", "ok": True, "error": None}
    ]
    # Both playing players were paused, not just the current one.
    assert ("w1", "pause") in rig.media.commands
    assert ("w2", "pause") in rig.media.commands
    assert ("w1", "next") in rig.media.commands
    assert rig.volume.sets[-1] == 30
    assert rig.launcher.urls == ["https://www.youtube.com/"]
    assert rig.sleeps == [4.0]
    assert ("type", "lofi beats") in rig.keys.calls
    assert ("press", "/") in rig.keys.calls
    assert ("press", "enter") in rig.keys.calls
    assert timer.active
    assert timer.then == "pause_sleep"
    assert len(rig.media.seeks) == 1
    sid, to = rig.media.seeks[0]
    assert sid == "w1"
    assert to == pytest.approx(180, abs=2)
    # The system prompt for each request carried the live context.
    system, messages = rig.provider.calls[0]
    assert '"w2"' in system
    assert messages[0].content == "pause everything"
    assert rig.power.actions == []


def test_power_waits_for_confirmation(isolated_home: Path) -> None:
    answer = plan("Locking the laptop.", {"type": "power.action", "payload": {"action": "lock"}})
    rig = Rig(isolated_home, [answer, answer, answer])
    with TestClient(rig.app) as client:
        device_id, token, _ = pair_new(client, rig.app)
        with phone(client) as p:
            p.resume(device_id, token)
            plan_msg, result = ask(p, "lock my laptop")
            assert plan_msg["needsConfirm"] is True
            assert result is None
            assert rig.power.actions == []

            # Declining throws the plan away.
            ack = p.ack_for(p.send("ai.confirm", {"planId": plan_msg["planId"], "approve": False}))
            assert ack["ok"] is True
            again = p.ack_for(p.send("ai.confirm", {"planId": plan_msg["planId"], "approve": True}))
            assert again["error"] == "That plan isn't waiting anymore. Ask again."
            assert rig.power.actions == []

            plan_msg, _ = ask(p, "lock my laptop")
            ack = p.ack_for(p.send("ai.confirm", {"planId": plan_msg["planId"], "approve": True}))
            assert ack["ok"] is True
            result = p.recv_type("ai.result", limit=40)["payload"]
            assert result == {
                "planId": plan_msg["planId"],
                "steps": [{"type": "power.action", "ok": True, "error": None}],
            }
    assert rig.power.actions == ["lock"]


def test_confirmation_is_bound_to_the_device(isolated_home: Path) -> None:
    answer = plan("Locking.", {"type": "power.action", "payload": {"action": "lock"}})
    rig = Rig(isolated_home, [answer])
    with TestClient(rig.app) as client:
        first = pair_new(client, rig.app, "Phone A")
        second = pair_new(client, rig.app, "Phone B")
        with phone(client) as a, phone(client) as b:
            a.resume(first[0], first[1])
            b.resume(second[0], second[1])
            plan_msg, _ = ask(a, "lock")
            ack = b.ack_for(b.send("ai.confirm", {"planId": plan_msg["planId"], "approve": True}))
            assert ack["ok"] is False
    assert rig.power.actions == []


def test_failed_steps_are_reported_and_the_rest_still_run(isolated_home: Path) -> None:
    answer = plan(
        "Done.",
        {"type": "brightness.set", "payload": {"level": 50}},
        {"type": "volume.set", "payload": {"level": 20}},
    )
    rig = Rig(isolated_home, [answer])
    with TestClient(rig.app) as client:
        device_id, token, _ = pair_new(client, rig.app)
        with phone(client) as p:
            p.resume(device_id, token)
            _, result = ask(p, "next and volume 20")
    assert result is not None
    assert result["steps"][1] == {"type": "volume.set", "ok": True, "error": None}
    assert result["steps"][0] == {
        "type": "brightness.set",
        "ok": False,
        "error": "Brightness control isn't available.",
    }
    assert rig.volume.sets[-1] == 20


def test_slow_planning_does_not_block_other_messages(isolated_home: Path) -> None:
    rig = Rig(isolated_home, [plan("Ok.")])
    gate = asyncio.Event()
    original = rig.provider.complete

    async def slow(system: str, messages: list[Any]) -> str:
        await gate.wait()
        return await original(system, messages)

    rig.provider.complete = slow  # type: ignore[method-assign]
    with TestClient(rig.app) as client:
        device_id, token, _ = pair_new(client, rig.app)
        with phone(client) as p:
            p.resume(device_id, token)
            p.send("ai.command", {"text": "anything"})
            # The ping is answered while the planner is still waiting on the model.
            p.send("ping", {"t": 1})
            assert p.recv_type("pong")["payload"] == {"t": 1}
            client.portal.call(gate.set)  # type: ignore[union-attr]
            assert p.recv_type("ai.plan")["payload"]["reply"] == "Ok."


def test_ai_feature_reflects_provider_readiness(isolated_home: Path) -> None:
    rig = Rig(isolated_home, [])
    rig.provider.ready = "Ollama isn't running on the laptop."
    with TestClient(rig.app) as client:
        device_id, token, _ = pair_new(client, rig.app)
        with phone(client) as p:
            ok = p.resume(device_id, token)
    assert ok["payload"]["features"]["ai"] == {
        "available": False,
        "reason": "Ollama isn't running on the laptop.",
    }


def test_guests_cannot_use_ai(isolated_home: Path) -> None:
    rig = Rig(isolated_home, [plan("Ok.")])
    with TestClient(rig.app) as client:
        pair_new(client, rig.app, "Owner")
        device_id, token, role = pair_new(client, rig.app, "Guest")
        assert role == "guest"
        with phone(client) as p:
            p.resume(device_id, token)
            ack = p.ack_for(p.send("ai.command", {"text": "pause"}))
    assert ack["error"] == "Only the owner can do that."
    assert rig.provider.calls == []


def test_invalid_steps_get_one_retry_with_the_reasons() -> None:
    first = plan("Ok.", {"type": "timer.set", "payload": {"minutes": 40, "then": "sleep_lock"}})
    second = plan(
        "Ok.",
        {"type": "timer.set", "payload": {"mode": "minutes", "minutes": 40, "then": "pause_sleep"}},
    )
    provider = ScriptedProvider([first, second])
    draft = run(Planner(provider).plan("sleep in 40", ctx()))
    assert [a.payload for a in draft.actions] == [
        {"minutes": 40.0, "mode": "minutes", "then": "pause_sleep"}
    ]
    assert draft.dropped == []
    feedback = provider.calls[1][1][-1].content
    assert feedback.startswith("Some actions were not valid: timer.set: then:")


def test_a_worse_retry_keeps_the_first_answer() -> None:
    first = plan(
        "Ok.",
        {"type": "volume.set", "payload": {"level": 30}},
        {"type": "exec", "payload": {}},
    )
    provider = ScriptedProvider([first, "still not json"])
    draft = run(Planner(provider).plan("volume 30", ctx()))
    assert [a.type for a in draft.actions] == ["volume.set"]
    assert draft.dropped == ["exec (not allowed)"]


def test_timer_minutes_without_mode_defaults_to_minutes() -> None:
    kept, dropped = validate_actions(
        [{"type": "timer.set", "payload": {"minutes": 15, "then": "pause"}}], ctx()
    )
    assert dropped == []
    assert kept[0].payload == {"minutes": 15.0, "mode": "minutes", "then": "pause"}

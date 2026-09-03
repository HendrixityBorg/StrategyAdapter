from __future__ import annotations

import json
import math
from decimal import Decimal
from hashlib import sha256

import numpy as np

from psrc.contract.models import ActionKind, DataKind, StrategyKind, TrainingMode
from psrc.domain.account import AccountSnapshot
from psrc.domain.actions import Action, NoOp, SubmitOrder, TargetPosition, TargetWeight
from psrc.domain.market import BarPayload, BookSnapshotL2Payload, MarketEvent
from psrc.runtime.artifacts import ArtifactManifest, ArtifactStore
from psrc.runtime.training import RLTransition, TrainingRequest
from psrc.strategies.common import bar_requirement, event_requirement, make_manifest


def _state_key(state: tuple[float, ...]) -> str:
    return ",".join(str(max(-2, min(2, round(value)))) for value in state)


def _position(account: AccountSnapshot, instrument_id: str) -> Decimal:
    match = next(
        (position for position in account.positions if position.instrument_id == instrument_id),
        None,
    )
    return match.quantity if match is not None else Decimal("0")


class _RLStrategy:
    manifest = make_manifest(
        strategy_id="reinforcement_learning.abstract",
        kind=StrategyKind.REINFORCEMENT_LEARNING,
        entrypoint="invalid",
        profiles=frozenset({"training.rl.v1"}),
        data=(bar_requirement(interval="P1D", symbols=("SYNTH.DAILY",), lookback=2),),
        actions=frozenset({ActionKind.NO_OP}),
        training=TrainingMode.REQUIRED,
    )

    def __init__(self) -> None:
        self.policy: dict[str, object] | None = None
        self.artifact_id: str | None = None

    def _transitions(self, request: TrainingRequest) -> tuple[RLTransition, ...]:
        transitions = request.transitions
        if len(transitions) < 9:
            raise ValueError("RL training requires at least nine transitions")
        if any(
            len(item.state) != 3 or len(item.next_state) != 3 or item.action not in {0, 1, 2}
            for item in transitions
        ):
            raise ValueError("RL transition requires 3-D states and actions in {0,1,2}")
        return transitions

    def _save(
        self, request: TrainingRequest, store: ArtifactStore, policy: dict[str, object]
    ) -> ArtifactManifest:
        payload = json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()
        artifact_id = f"sha256-{sha256(payload).hexdigest()}"
        return store.save_bytes(
            run_id=request.run_id,
            artifact_id=artifact_id,
            strategy_id=self.manifest.strategy_id,
            strategy_version=self.manifest.strategy_version,
            artifact_kind="policy",
            framework="numpy-json",
            logical_name="policy.json",
            media_type="application/json",
            payload=payload,
            training_dataset_id=request.dataset_id,
            seed=request.seed,
            metadata={"algorithm": str(policy["algorithm"])},
        )

    def load(self, manifest: ArtifactManifest, store: ArtifactStore, *, run_id: str) -> None:
        if manifest.strategy_id != self.manifest.strategy_id:
            raise ValueError("policy strategy_id does not match strategy")
        payload = store.load_bytes(
            run_id=run_id, strategy_id=self.manifest.strategy_id, manifest=manifest
        )["policy.json"]
        value = json.loads(payload)
        if not isinstance(value, dict):
            raise ValueError("policy artifact root must be an object")
        self.policy = value
        self.artifact_id = manifest.artifact_id

    def _require_policy(self) -> dict[str, object]:
        if self.policy is None:
            raise RuntimeError("policy artifact has not been loaded")
        return self.policy

    @staticmethod
    def _q_action(policy: dict[str, object], state: tuple[float, ...], table_name: str) -> int:
        table = policy[table_name]
        assert isinstance(table, dict)
        values = table.get(_state_key(state))
        if values is None:
            # Tabular policies use a deterministic nearest-state projection for
            # previously unseen observations; the policy artifact records this rule.
            target = tuple(max(-2, min(2, round(value))) for value in state)

            def distance(key: str) -> tuple[float, str]:
                candidate = tuple(float(value) for value in key.split(","))
                return (
                    sum(
                        (left - right) ** 2
                        for left, right in zip(target, candidate, strict=True)
                    ),
                    key,
                )

            nearest = min(table, key=distance)
            values = table[nearest]
        assert isinstance(values, list)
        return int(np.argmax(np.asarray(values, dtype=float)))

    def on_start(self) -> None:
        pass

    def on_finish(self) -> None:
        pass


class TabularQInventoryStrategy(_RLStrategy):
    manifest = make_manifest(
        strategy_id="reinforcement_learning.tabular_q_inventory",
        kind=StrategyKind.REINFORCEMENT_LEARNING,
        entrypoint="psrc.strategies.reinforcement_learning:TabularQInventoryStrategy",
        profiles=frozenset({"core.bar.v1", "execution.basic.v1", "training.rl.v1"}),
        data=(bar_requirement(interval="P1D", symbols=("SYNTH.DAILY",), lookback=2),),
        actions=frozenset({ActionKind.NO_OP, ActionKind.TARGET_POSITION}),
        training=TrainingMode.REQUIRED,
        max_position=Decimal("1"),
    )

    def train(self, request: TrainingRequest, store: ArtifactStore) -> ArtifactManifest:
        transitions = self._transitions(request)
        q: dict[str, list[float]] = {}
        for _ in range(25):
            for item in transitions:
                state = _state_key(item.state)
                next_state = _state_key(item.next_state)
                q.setdefault(state, [0.0, 0.0, 0.0])
                q.setdefault(next_state, [0.0, 0.0, 0.0])
                bootstrap = 0.0 if item.terminated else 0.9 * max(q[next_state])
                target = item.reward + bootstrap
                q[state][item.action] += 0.2 * (target - q[state][item.action])
        return self._save(
            request,
            store,
            {
                "algorithm": "tabular-q-learning-v1",
                "q": q,
                "unseen_action": "nearest-state-v1",
            },
        )

    def on_event(self, event: MarketEvent, account: AccountSnapshot) -> tuple[Action, ...]:
        if not isinstance(event.payload, BarPayload):
            return (NoOp(reason_code="event.not_bar", explanation="requires daily bars"),)
        bar = event.payload
        momentum = float((bar.close - bar.open) / bar.open * 100)
        inventory = float(_position(account, event.instrument_id))
        range_state = float((bar.high - bar.low) / bar.open * 100)
        action = self._q_action(self._require_policy(), (momentum, inventory, range_state), "q")
        return (
            TargetPosition(
                instrument_id=event.instrument_id,
                quantity=Decimal(action - 1),
                reason_code="policy.tabular_q_inventory",
            ),
        )


class SarsaTrendStrategy(_RLStrategy):
    manifest = make_manifest(
        strategy_id="reinforcement_learning.sarsa_trend",
        kind=StrategyKind.REINFORCEMENT_LEARNING,
        entrypoint="psrc.strategies.reinforcement_learning:SarsaTrendStrategy",
        profiles=frozenset({"core.bar.v1", "execution.basic.v1", "training.rl.v1"}),
        data=(bar_requirement(interval="PT1M", symbols=("SYNTH.TEST",), lookback=3),),
        actions=frozenset({ActionKind.NO_OP, ActionKind.TARGET_POSITION}),
        training=TrainingMode.REQUIRED,
        max_position=Decimal("2"),
    )

    def train(self, request: TrainingRequest, store: ArtifactStore) -> ArtifactManifest:
        transitions = self._transitions(request)
        q: dict[str, list[float]] = {}
        for _ in range(20):
            for item in transitions:
                state = _state_key(item.state)
                next_state = _state_key(item.next_state)
                q.setdefault(state, [0.0, 0.0, 0.0])
                q.setdefault(next_state, [0.0, 0.0, 0.0])
                next_action = item.next_action if item.next_action is not None else 1
                bootstrap = 0.0 if item.terminated else 0.85 * q[next_state][next_action]
                q[state][item.action] += 0.15 * (item.reward + bootstrap - q[state][item.action])
        return self._save(
            request,
            store,
            {
                "algorithm": "on-policy-sarsa-v1",
                "q": q,
                "unseen_action": "nearest-state-v1",
            },
        )

    def on_event(self, event: MarketEvent, account: AccountSnapshot) -> tuple[Action, ...]:
        if not isinstance(event.payload, BarPayload):
            return (NoOp(reason_code="event.not_bar", explanation="requires minute bars"),)
        bar = event.payload
        state = (
            float((bar.close - bar.open) / bar.open * 100),
            float((bar.high - bar.low) / bar.open * 100),
            float(_position(account, event.instrument_id)),
        )
        action = self._q_action(self._require_policy(), state, "q")
        return (
            TargetPosition(
                instrument_id=event.instrument_id,
                quantity=Decimal((action - 1) * 2),
                reason_code="policy.sarsa_trend",
            ),
        )


class ContextualBanditExecutionStrategy(_RLStrategy):
    manifest = make_manifest(
        strategy_id="reinforcement_learning.contextual_bandit_execution",
        kind=StrategyKind.REINFORCEMENT_LEARNING,
        entrypoint=("psrc.strategies.reinforcement_learning:ContextualBanditExecutionStrategy"),
        profiles=frozenset({"core.bar.v1", "execution.basic.v1", "training.rl.v1"}),
        data=(bar_requirement(interval="PT1M", symbols=("SYNTH.TWAP",), lookback=1),),
        actions=frozenset({ActionKind.NO_OP, ActionKind.SUBMIT_ORDER}),
        training=TrainingMode.REQUIRED,
        max_position=None,
        max_order=Decimal("2"),
    )

    def __init__(self) -> None:
        super().__init__()
        self.counter = 0

    def train(self, request: TrainingRequest, store: ArtifactStore) -> ArtifactManifest:
        transitions = self._transitions(request)
        weights: list[list[float]] = []
        for action in range(3):
            rows = [item.state for item in transitions if item.action == action]
            rewards = [item.reward for item in transitions if item.action == action]
            if not rows:
                weights.append([0.0, 0.0, 0.0])
                continue
            x = np.asarray(rows)
            y = np.asarray(rewards)
            ridge = np.eye(3) * 0.5
            weights.append(np.linalg.solve(x.T @ x + ridge, x.T @ y).tolist())
        return self._save(
            request,
            store,
            {"algorithm": "disjoint-linear-contextual-bandit-v1", "weights": weights},
        )

    def on_start(self) -> None:
        self.counter = 0

    def on_event(self, event: MarketEvent, account: AccountSnapshot) -> tuple[Action, ...]:
        del account
        if not isinstance(event.payload, BarPayload):
            return (NoOp(reason_code="event.not_bar", explanation="requires minute bars"),)
        self.counter += 1
        policy = self._require_policy()
        weights = np.asarray(policy["weights"], dtype=float)
        bar = event.payload
        context = np.asarray(
            [
                self.counter / 10,
                float((bar.close - bar.open) / bar.open),
                math.log1p(float(bar.volume)) / 10,
            ]
        )
        action = int(np.argmax(weights @ context))
        if action == 0:
            return (NoOp(reason_code="policy.bandit_wait", explanation="zero participation"),)
        return (
            SubmitOrder(
                client_order_id=f"bandit:{self.counter}",
                instrument_id=event.instrument_id,
                side="buy",
                order_type="market",
                quantity=Decimal(action),
                reason_code="policy.bandit_aggressiveness",
            ),
        )


class DoubleQBookInventoryStrategy(_RLStrategy):
    manifest = make_manifest(
        strategy_id="reinforcement_learning.double_q_book_inventory",
        kind=StrategyKind.REINFORCEMENT_LEARNING,
        entrypoint="psrc.strategies.reinforcement_learning:DoubleQBookInventoryStrategy",
        profiles=frozenset({"event.l2.v1", "execution.basic.v1", "training.rl.v1"}),
        data=(
            event_requirement(
                stream_id="book",
                kind=DataKind.BOOK_SNAPSHOT_L2,
                symbols=("SYNTH.L2",),
                fields=frozenset({"bids.price", "bids.size", "asks.price", "asks.size"}),
                depth=3,
            ),
        ),
        actions=frozenset({ActionKind.NO_OP, ActionKind.TARGET_POSITION}),
        training=TrainingMode.REQUIRED,
        max_position=Decimal("1"),
    )

    def train(self, request: TrainingRequest, store: ArtifactStore) -> ArtifactManifest:
        transitions = self._transitions(request)
        q1: dict[str, list[float]] = {}
        q2: dict[str, list[float]] = {}
        for epoch in range(20):
            for index, item in enumerate(transitions):
                state, next_state = _state_key(item.state), _state_key(item.next_state)
                q1.setdefault(state, [0.0] * 3)
                q1.setdefault(next_state, [0.0] * 3)
                q2.setdefault(state, [0.0] * 3)
                q2.setdefault(next_state, [0.0] * 3)
                left, right = (q1, q2) if (epoch + index) % 2 == 0 else (q2, q1)
                greedy = int(np.argmax(left[next_state]))
                bootstrap = 0.0 if item.terminated else 0.9 * right[next_state][greedy]
                left[state][item.action] += 0.18 * (
                    item.reward + bootstrap - left[state][item.action]
                )
        combined = {
            state: [q1[state][index] + q2[state][index] for index in range(3)] for state in q1
        }
        return self._save(
            request,
            store,
            {
                "algorithm": "double-q-learning-v1",
                "q": combined,
                "unseen_action": "nearest-state-v1",
            },
        )

    def on_event(self, event: MarketEvent, account: AccountSnapshot) -> tuple[Action, ...]:
        if not isinstance(event.payload, BookSnapshotL2Payload):
            return (NoOp(reason_code="event.not_l2", explanation="requires L2 book"),)
        book = event.payload
        bids = sum(level.size for level in book.bids)
        asks = sum(level.size for level in book.asks)
        state = (
            float((bids - asks) / max(bids + asks, Decimal("1")) * 2),
            float(_position(account, event.instrument_id)),
            float((book.asks[0].price - book.bids[0].price) * 10),
        )
        action = self._q_action(self._require_policy(), state, "q")
        return (
            TargetPosition(
                instrument_id=event.instrument_id,
                quantity=Decimal(action - 1),
                reason_code="policy.double_q_book_inventory",
            ),
        )


class DynaQPairsStrategy(_RLStrategy):
    manifest = make_manifest(
        strategy_id="reinforcement_learning.dyna_q_pairs",
        kind=StrategyKind.REINFORCEMENT_LEARNING,
        entrypoint="psrc.strategies.reinforcement_learning:DynaQPairsStrategy",
        profiles=frozenset({"core.bar.v1", "execution.basic.v1", "training.rl.v1"}),
        data=(
            bar_requirement(interval="P1D", symbols=("SYNTH.PAIR-A", "SYNTH.PAIR-B"), lookback=2),
        ),
        actions=frozenset({ActionKind.NO_OP, ActionKind.TARGET_POSITION}),
        training=TrainingMode.REQUIRED,
        max_position=Decimal("1"),
    )

    def __init__(self) -> None:
        super().__init__()
        self.symbols = ("SYNTH.PAIR-A", "SYNTH.PAIR-B")
        self.latest: dict[str, tuple[object, Decimal]] = {}

    def train(self, request: TrainingRequest, store: ArtifactStore) -> ArtifactManifest:
        transitions = self._transitions(request)
        q: dict[str, list[float]] = {}
        model: dict[str, tuple[float, str, bool]] = {}

        def update(state: str, action: int, reward: float, next_state: str, terminal: bool) -> None:
            q.setdefault(state, [0.0] * 3)
            q.setdefault(next_state, [0.0] * 3)
            target = reward if terminal else reward + 0.88 * max(q[next_state])
            q[state][action] += 0.17 * (target - q[state][action])

        for item in transitions:
            state, next_state = _state_key(item.state), _state_key(item.next_state)
            update(state, item.action, item.reward, next_state, item.terminated)
            model[f"{state}|{item.action}"] = (item.reward, next_state, item.terminated)
        for _ in range(30):
            for key in sorted(model):
                state, action_text = key.rsplit("|", maxsplit=1)
                reward, next_state, terminal = model[key]
                update(state, int(action_text), reward, next_state, terminal)
        return self._save(
            request,
            store,
            {
                "algorithm": "dyna-q-deterministic-planning-v1",
                "q": q,
                "model_entries": len(model),
                "unseen_action": "nearest-state-v1",
            },
        )

    def on_start(self) -> None:
        self.latest.clear()

    def on_event(self, event: MarketEvent, account: AccountSnapshot) -> tuple[Action, ...]:
        if not isinstance(event.payload, BarPayload):
            return (NoOp(reason_code="event.not_bar", explanation="requires pair bars"),)
        self.latest[event.instrument_id] = (event.available_time, event.payload.close)
        if any(symbol not in self.latest for symbol in self.symbols):
            return (NoOp(reason_code="pair.awaiting_peer", explanation="pair batch incomplete"),)
        if self.latest[self.symbols[0]][0] != self.latest[self.symbols[1]][0]:
            return (NoOp(reason_code="pair.not_synchronized", explanation="bar times differ"),)
        spread = self.latest[self.symbols[0]][1] - 2 * self.latest[self.symbols[1]][1]
        inventory = _position(account, self.symbols[0])
        state = (float(spread / Decimal("5")), float(inventory), 0.0)
        action = self._q_action(self._require_policy(), state, "q")
        direction = Decimal(action - 1)
        return (
            TargetPosition(
                instrument_id=self.symbols[0],
                quantity=direction,
                reason_code="policy.dyna_q_pair_left",
            ),
            TargetPosition(
                instrument_id=self.symbols[1],
                quantity=-direction,
                reason_code="policy.dyna_q_pair_right",
            ),
        )


class LinearActorCriticAllocationStrategy(_RLStrategy):
    manifest = make_manifest(
        strategy_id="reinforcement_learning.linear_actor_critic_allocation",
        kind=StrategyKind.REINFORCEMENT_LEARNING,
        entrypoint=("psrc.strategies.reinforcement_learning:LinearActorCriticAllocationStrategy"),
        profiles=frozenset({"core.bar.v1", "portfolio.batch.v1", "training.rl.v1"}),
        data=(bar_requirement(interval="P1D", symbols=("SYNTH.DAILY",), lookback=2),),
        actions=frozenset({ActionKind.NO_OP, ActionKind.TARGET_WEIGHT}),
        training=TrainingMode.REQUIRED,
        max_position=None,
    )

    def train(self, request: TrainingRequest, store: ArtifactStore) -> ArtifactManifest:
        transitions = self._transitions(request)
        actor = np.zeros(3)
        critic = np.zeros(3)
        for _ in range(30):
            for item in transitions:
                state = np.asarray(item.state)
                next_state = np.asarray(item.next_state)
                value = float(critic @ state)
                next_value = 0.0 if item.terminated else float(critic @ next_state)
                delta = item.reward + 0.9 * next_value - value
                critic += 0.05 * delta * state
                chosen_weight = float(item.action - 1)
                predicted_weight = math.tanh(float(actor @ state))
                actor += 0.02 * delta * (chosen_weight - predicted_weight) * state
        return self._save(
            request,
            store,
            {
                "algorithm": "linear-actor-critic-v1",
                "actor_weights": actor.tolist(),
                "critic_weights": critic.tolist(),
            },
        )

    def on_event(self, event: MarketEvent, account: AccountSnapshot) -> tuple[Action, ...]:
        del account
        if not isinstance(event.payload, BarPayload):
            return (NoOp(reason_code="event.not_bar", explanation="requires daily bars"),)
        policy = self._require_policy()
        weights = np.asarray(policy["actor_weights"], dtype=float)
        bar = event.payload
        state = np.asarray(
            [
                float((bar.close - bar.open) / bar.open * 10),
                float((bar.high - bar.low) / bar.open * 10),
                math.log1p(float(bar.volume)) / 10,
            ]
        )
        weight = max(-0.8, min(0.8, math.tanh(float(weights @ state))))
        return (
            TargetWeight(
                instrument_id=event.instrument_id,
                weight=Decimal(str(weight)),
                reason_code="policy.linear_actor_allocation",
            ),
        )

#!/usr/bin/env python3
"""Fail-closed audit for an Actor-driven rolling Visual Novel checkpoint."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agents.writer_agent import WriterAgent  # noqa: E402
from agents.producer_agent import ProducerAgent  # noqa: E402


REQUIRED_CLOSURE_FIELDS = (
    "conflict_resolved",
    "consequences_shown",
    "character_arcs_paid_off",
    "new_equilibrium_established",
    "finality_signal_present",
)


def expected_node_ids(node_count: int) -> list[str]:
    return ["root", *(f"node{index}" for index in range(1, node_count))]


def _quoted_evidence_is_present(evidence: Any, script: str) -> bool:
    return (
        isinstance(evidence, list)
        and bool(evidence)
        and all(
            isinstance(quote, str) and quote.strip() and quote.strip() in script
            for quote in evidence
        )
    )


def audit_rolling_state(
    state: dict[str, Any],
    story_text: str,
    node_count: int = 5,
    character_count: int = 4,
) -> list[str]:
    """Return every completion error; an empty list is the only PASS state."""
    errors: list[str] = []
    node_ids = expected_node_ids(node_count)

    if state.get("schema_version") != "rolling-state/3.2":
        errors.append("checkpoint schema 必须是 rolling-state/3.2")
    if state.get("generation_architecture") != "actor-driven-node-goals":
        errors.append("generation_architecture 必须是 actor-driven-node-goals")

    core_gdd = state.get("core_gdd", {})
    characters = core_gdd.get("characters", [])
    if len(characters) != character_count:
        errors.append(f"主要角色必须恰好 {character_count} 名，当前为 {len(characters)}")

    collections = ("scripts", "goals", "reviews", "performances", "summaries")
    for field in collections:
        value = state.get(field)
        if not isinstance(value, dict):
            errors.append(f"{field} 必须是对象")
            continue
        actual_ids = list(value)
        if actual_ids != node_ids:
            errors.append(f"{field} 节点必须依次为 {node_ids}，当前为 {actual_ids}")

    scripts = state.get("scripts", {})
    goals = state.get("goals", {})
    reviews = state.get("reviews", {})
    performances = state.get("performances", {})

    graph = state.get("story_graph", {})
    graph_nodes = graph.get("nodes", {}) if isinstance(graph, dict) else {}
    if list(graph_nodes) != node_ids:
        errors.append(f"story_graph.nodes 必须依次为 {node_ids}")
    expected_edges = [
        {
            "from": node_ids[index],
            "to": node_ids[index + 1],
            "choice_text": None,
            "discourse_relation": goals.get(node_ids[index + 1], {})
            .get("transition_contract", {})
            .get("relation_to_previous"),
            "source_anchor": goals.get(node_ids[index + 1], {})
            .get("transition_contract", {})
            .get("source_anchor"),
        }
        for index in range(node_count - 1)
    ]
    if graph.get("edges") != expected_edges:
        errors.append("story_graph.edges 必须构成带话语关系的五节点无分支线性链")

    writer = WriterAgent.__new__(WriterAgent)
    previous_compiled_script = ""
    for index, node_id in enumerate(node_ids):
        script = scripts.get(node_id)
        turns = performances.get(node_id)
        goal = goals.get(node_id)
        review = reviews.get(node_id)
        if not isinstance(script, str) or not script.strip():
            errors.append(f"{node_id}: 缺少剧本")
            continue
        if not isinstance(turns, list) or not turns:
            errors.append(f"{node_id}: 缺少 Actor 表演记录")
            continue
        if not isinstance(goal, dict):
            errors.append(f"{node_id}: 缺少 NodeGoal")
        if not isinstance(review, dict):
            errors.append(f"{node_id}: 缺少 Producer review")
        else:
            if review.get("decision") != "PASS" or review.get("goal_completed") is not True:
                errors.append(f"{node_id}: Producer review 未 PASS 或 goal_completed 不为 true")

        transition = goal.get("transition_contract", {}) if isinstance(goal, dict) else {}
        if index == 0:
            if transition.get("relation_to_previous") != "root":
                errors.append("root: transition_contract 必须声明 relation_to_previous=root")
        else:
            previous_script = scripts.get(node_ids[index - 1], "")
            previous_scenes = re.findall(
                r"<scene>(.*?)</scene>", previous_script, flags=re.DOTALL
            )
            previous_contents = re.findall(
                r'<content\s+id="([^"]+)">(.*?)</content>',
                previous_script,
                flags=re.DOTALL,
            )
            previous_speaker, previous_anchor = (
                previous_contents[-1] if previous_contents else ("", "")
            )
            expected_scene = previous_scenes[-1].strip() if previous_scenes else ""
            if not isinstance(transition, dict):
                errors.append(f"{node_id}: 缺少 transition_contract")
                transition = {}
            if transition.get("relation_to_previous") in {None, "", "root"}:
                errors.append(f"{node_id}: 缺少有效的跨节点话语关系")
            if str(transition.get("source_scene", "")).strip() != expected_scene:
                errors.append(f"{node_id}: transition_contract.source_scene 与上一节点不一致")
            if str(transition.get("source_speaker", "")).strip() != previous_speaker.strip():
                errors.append(f"{node_id}: transition_contract.source_speaker 与上一节点不一致")
            if str(transition.get("source_anchor", "")).strip() != previous_anchor.strip():
                errors.append(f"{node_id}: transition_contract.source_anchor 不是上一节点最后内容")
            if not str(transition.get("bridge_requirement", "")).strip():
                errors.append(f"{node_id}: transition_contract 缺少 bridge_requirement")

            continuity = review.get("continuity_check", {}) if isinstance(review, dict) else {}
            for field in (
                "applicable",
                "source_anchor_acknowledged",
                "discourse_relation_realized",
                "action_continuity_preserved",
                "scene_transition_grounded",
            ):
                if continuity.get(field) is not True:
                    errors.append(f"{node_id}: continuity_check.{field} 必须为 true")
            if continuity.get("relation_to_previous") != transition.get(
                "relation_to_previous"
            ):
                errors.append(f"{node_id}: continuity_check 的关系类型与契约不一致")
            if not _quoted_evidence_is_present(continuity.get("evidence"), script):
                errors.append(f"{node_id}: continuity_check 缺少当前剧本逐字证据")

        valid, detail = writer.validate_actor_fidelity(script, turns)
        if not valid:
            errors.append(f"{node_id}: Actor 保真失败：{detail}")

        compiled = writer.synthesize_actor_performances(
            turns=turns,
            node_goal=goal or {},
            story_context=previous_compiled_script,
            core_gdd=core_gdd,
        ).strip()
        if index < node_count - 1:
            compiled += f'\n\n<jump target="{node_ids[index + 1]}"/>'
        if script.strip() != compiled:
            errors.append(f"{node_id}: 剧本不是当前 Writer 对 Actor 记录的确定性编译结果")
        previous_compiled_script = compiled

    expected_story = "\n\n".join(
        f"=== Node: {node_id} ===\n{scripts[node_id].strip()}"
        for node_id in node_ids
        if isinstance(scripts.get(node_id), str)
    )
    if story_text.strip() != expected_story.strip():
        errors.append("story.txt 与 rolling_state.json 中的节点剧本不一致")

    final_id = node_ids[-1]
    final_script = scripts.get(final_id, "")
    final_goal = goals.get(final_id, {})
    if final_goal.get("narrative_phase") != "resolution":
        errors.append(f"{final_id}: 最终 NodeGoal 的 narrative_phase 必须是 resolution")
    if '<jump target=' in final_script:
        errors.append(f"{final_id}: 最终节点不得包含 jump")

    final_review = reviews.get(final_id, {})
    terminal_conditions = core_gdd.get("global_goal", {}).get("terminal_conditions", [])
    terminal_checks = final_review.get("terminal_condition_checks", [])
    checks_by_condition = {
        check.get("condition"): check
        for check in terminal_checks
        if isinstance(check, dict)
    }
    if len(terminal_checks) != len(terminal_conditions):
        errors.append(f"{final_id}: terminal_condition_checks 必须与终局条件一一对应")
    for condition in terminal_conditions:
        check = checks_by_condition.get(condition, {})
        if check.get("satisfied") is not True:
            errors.append(f"{final_id}: 终局条件未满足：{condition}")
        if not _quoted_evidence_is_present(check.get("evidence"), final_script):
            errors.append(f"{final_id}: 终局条件缺少剧本逐字证据：{condition}")
        if (
            re.search(r"(?:警察|警方)抵达", condition)
            and not ProducerAgent._has_confirmed_police_arrival(final_script)
        ):
            errors.append(f"{final_id}: 警灯或口头报告不算警方实际进入现场")

    final_goal_text = "\n".join(
        [
            str(final_goal.get("goal", "")),
            str(final_goal.get("contributes_to_global_goal", "")),
            *[str(item) for item in final_goal.get("completion_conditions", [])],
        ]
    )
    if (
        any(marker in final_goal_text for marker in ("拘留", "接管", "收取", "移交"))
        and not ProducerAgent._has_confirmed_police_handoff(final_script)
    ):
        errors.append(f"{final_id}: 缺少警方拘捕真凶并接收证物的可见移交场景")

    closure = final_review.get("closure_check", {})
    for field in REQUIRED_CLOSURE_FIELDS:
        if closure.get(field) is not True:
            errors.append(f"{final_id}: closure_check.{field} 必须为 true")
    if not _quoted_evidence_is_present(closure.get("evidence"), final_script):
        errors.append(f"{final_id}: closure_check 缺少剧本逐字证据")
    content_bodies = re.findall(
        r'<content\s+id="[^"]+">(.*?)</content>', final_script, flags=re.DOTALL
    )
    actual_final_beat = content_bodies[-1].strip() if content_bodies else ""
    if not closure.get("final_beat") or closure.get("final_beat") != actual_final_beat:
        errors.append(f"{final_id}: closure_check.final_beat 必须是剧本最后一个 content 正文")
    elif actual_final_beat:
        final_beat_position = final_script.rfind(actual_final_beat)
        prerequisite_quotes = [
            quote
            for check in terminal_checks
            if isinstance(check, dict)
            for quote in check.get("evidence", [])
            if not (
                str(quote).strip() == actual_final_beat
                and any(
                    marker in str(check.get("condition", ""))
                    for marker in ("封闭", "收束", "结局")
                )
            )
        ]
        prerequisite_quotes.extend(closure.get("evidence", [])[:-1])
        if any(
            isinstance(quote, str)
            and quote.strip()
            and final_script.rfind(quote.strip()) >= final_beat_position
            for quote in prerequisite_quotes
        ):
            errors.append(f"{final_id}: final_beat 必须严格晚于全部真相与收束证据")

    for condition in terminal_conditions:
        check = checks_by_condition.get(condition, {})
        evidence_text = "\n".join(check.get("evidence", []))
        for item in _enumerated_terminal_items(condition):
            if not _terminal_item_is_covered(item, evidence_text, core_gdd):
                errors.append(f"{final_id}: 终局证据未逐字覆盖列举项：{item}")

    return errors


def _enumerated_terminal_items(condition: str) -> list[str]:
    spans = re.findall(
        r'(?:^|[，：（(])([^，。；：()（）]*、[^，。；：()（）]+)(?=[，。；：）)]|$)',
        condition or "",
    )
    return [
        item
        for span in spans
        for raw_item in span.split("、")
        if (item := re.sub(r"等.*$", "", raw_item).strip())
    ]


def _terminal_item_is_covered(item: str, evidence_text: str, core_gdd: dict) -> bool:
    if item in evidence_text:
        return True
    if item != "凶器":
        return False
    facts_text = "\n".join(str(fact) for fact in core_gdd.get("immutable_facts", []))
    aliases: list[str] = []
    for definition in re.findall(r"凶器(?:是|为)([^，。；]+)", facts_text):
        aliases.extend(re.findall(r"[（(]([^）)]+)[）)]", definition))
        aliases.append(
            re.sub(r"^.*?的", "", re.sub(r"[（(].*$", "", definition)).strip()
        )
    return any(alias and alias in evidence_text for alias in aliases)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("--nodes", type=int, default=5)
    parser.add_argument("--characters", type=int, default=4)
    args = parser.parse_args()

    state = json.loads(args.checkpoint.read_text(encoding="utf-8"))
    story_path = args.checkpoint.with_name("story.txt")
    story_text = story_path.read_text(encoding="utf-8") if story_path.exists() else ""
    errors = audit_rolling_state(
        state,
        story_text,
        node_count=args.nodes,
        character_count=args.characters,
    )
    if errors:
        print(f"FAIL: {len(errors)} 项未通过")
        for error in errors:
            print(f"- {error}")
        return 1
    print("PASS: checkpoint 是完整、Actor 保真且有证据支持的封闭五节点故事")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

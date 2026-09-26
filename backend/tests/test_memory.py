from app.ambient.memory import MemoryService
from tests.conftest import MORGAN_ID


async def test_last_interaction_with_novara_is_access_guide(interactions, resources) -> None:
    memory = MemoryService(interactions, resources)
    last = await memory.get_last_interaction_with_entity(MORGAN_ID, "Novara")
    assert last is not None
    assert last.timestamp.date().isoformat() == "2026-07-02"
    assert last.resource_title and "Access Guide" in last.resource_title


async def test_whats_new_since_last_novara_look(interactions, resources) -> None:
    memory = MemoryService(interactions, resources)
    last = await memory.get_last_interaction_with_entity(MORGAN_ID, "Novara")
    result = await memory.whats_new(MORGAN_ID, "Novara", last)
    titles = {(r.title, r.version) for r in result.new_resources}
    assert titles == {("Novara Prescribing Information", "2.0"), ("Novara Trial A Long-Term Follow-Up", "1.0")}
    [(old, new)] = result.superseded_pairs
    assert (old.version, new.version) == ("1.0", "2.0")


async def test_viewed_resources_and_timeline(interactions, resources) -> None:
    memory = MemoryService(interactions, resources)
    viewed = await memory.get_viewed_resources(MORGAN_ID, "Novara")
    assert {r.title for r in viewed} == {"Novara Prescribing Information", "Novara Access Guide"}
    timeline = await memory.get_timeline(MORGAN_ID)
    assert timeline[0].label.startswith("Viewed Novara Access Guide")
    assert any(t.label == 'Asked "long-term outcomes"' for t in timeline)

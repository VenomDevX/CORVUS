

def test_saved_memories_reach_the_prompt(repo):
    # Memories were extracted and stored but never read back into chat.
    from corvus.memory.extractor import recall_prompt
    assert recall_prompt(repo) == ""
    repo.add_memory("preference", "Favourite language is Rust")
    assert "Favourite language is Rust" in recall_prompt(repo)

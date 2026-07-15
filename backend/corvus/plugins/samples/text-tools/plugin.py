"""Text Tools — a permission-free sample Corvus plugin.

Shows the minimal plugin shape: define register(ctx) and add actions with
ctx.action(...). Everything here is pure text, so the manifest declares no
permissions.
"""

from corvus.plugins.sdk import ActionResult, PluginContext


def register(ctx: PluginContext) -> None:
    def word_count(text: str) -> ActionResult:
        words = len(text.split())
        chars = len(text)
        return ActionResult(True, f"{words} words, {chars} characters.",
                            {"words": words, "characters": chars})

    ctx.action(
        "word_count", "Count the words and characters in some text.",
        {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        word_count,
    )

    def reverse_text(text: str) -> ActionResult:
        return ActionResult(True, text[::-1])

    ctx.action(
        "reverse", "Reverse a string of text.",
        {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        reverse_text,
    )

    def title_case(text: str) -> ActionResult:
        return ActionResult(True, text.title())

    ctx.action(
        "title_case", "Convert text to Title Case.",
        {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        title_case,
    )

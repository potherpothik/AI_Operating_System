import json
from sqlalchemy.orm import Session

from assembly.prompt_builder.templates import get_active_template
from assembly.prompt_builder.models import PromptRenderLog
from assembly.prompt_builder.shared_fragments import REFUSE_DELEGATE_APPROVAL_FRAGMENT, UNTRUSTED_CONTENT_WARNING, wrap_untrusted


class NoActiveTemplate(Exception):
    pass


class PromptTooLarge(Exception):
    pass


def render(db: Session, context_package: dict, context_items: list, task_description: str, agent_template_id: str, target_model: str, max_prompt_words: int = 4000) -> dict:
    template = get_active_template(db, agent_template_id)
    if not template:
        raise NoActiveTemplate(f"no active template registered for {agent_template_id!r}")

    # Every context item is wrapped, regardless of what the template body
    # itself does — this is structural, not left to the template author
    # to remember (Phase 4 design doc).
    context_blocks = [wrap_untrusted(item["content"], item.get("provenance") or item.get("source_type", "context")) for item in context_items]
    context_section = "\n\n".join(context_blocks) if context_blocks else "(no context retrieved)"

    rendered = template.body.format(
        task_description=task_description,
        context=context_section,
        untrusted_warning=UNTRUSTED_CONTENT_WARNING,
        shared_fragment=REFUSE_DELEGATE_APPROVAL_FRAGMENT,
    )

    word_count = len(rendered.split())
    if word_count > max_prompt_words:
        # Refuse outright rather than silently truncate — a silently
        # truncated prompt could drop the trailing safety instructions
        # without anyone knowing (Phase 4 design doc).
        raise PromptTooLarge(f"rendered prompt is {word_count} words, over the {max_prompt_words}-word limit for {target_model}")

    log = PromptRenderLog(
        context_package_id=context_package["id"],
        template_id=template.id,
        template_version=template.version,
        target_model=target_model,
    )
    db.add(log)
    db.commit()

    expected_schema = json.loads(template.expected_output_schema)
    return {
        "rendered_prompt": rendered,
        "expected_output_schema": expected_schema,
        "template_id": template.id,
        "template_version": template.version,
        "render_log_id": log.id,
    }

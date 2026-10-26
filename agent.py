"""Proposal agent: guide -> chapter plan (editable prompts) -> chapter drafts -> compliance check."""
from llm import chat, chat_json

LANG = "Write in the same language as the guide (Chinese if the guide is Chinese)."

OUTLINE_SYS = f"""You plan a project proposal (项目申报书) from a funding guide.
Return JSON: {{"project_title_hint": str, "chapters": [{{"title": str, "prompt": str, "requirements": [str]}}]}}.
- chapters: follow the chapter structure the guide demands, in order; if the guide gives none, use a standard one
  (background, objectives, content, technical route, innovation, schedule, budget, expected outcomes, risks).
- prompt: a clear instruction for writing THAT chapter (what to cover, length, tone). It will be shown to the user and edited.
- requirements: concrete rules from the guide that this chapter must satisfy (quote numbers/limits exactly). Never invent rules.
{LANG}"""

CHAPTER_SYS = f"""You write one chapter of a project proposal for a funding call.
Use ONLY facts from the guide and the applicant's idea; if a needed fact is missing write [待补充: what is missing] instead of inventing numbers, names, institutions, citations or results. General background is fine; specific named examples or statistics are not unless given.
Follow the chapter instruction and requirements exactly. Stay consistent with earlier chapters. Output the chapter body only, no title line.
{LANG}"""

CHECK_SYS = f"""You audit a proposal draft against its funding guide.
Return JSON: {{"items": [{{"requirement": str, "status": "ok"|"partial"|"missing", "where": str, "note": str}}]}}.
List every concrete requirement in the guide (eligibility, length/budget limits, required sections, indicators). Be strict; quote the draft chapter in "where". {LANG}"""


def outline(guide, idea):
    return chat_json(OUTLINE_SYS, f"# Guide\n{guide}\n\n# Applicant idea\n{idea}")


def _cap(budget, unit="chars"):
    return f"\nLength: at most {budget} {'words' if unit == 'words' else 'characters'} for this chapter (the whole proposal has a hard limit). Never exceed it." if budget else ""


def chapter(guide, idea, ch, previous, budget=None, unit="chars"):
    prev = "\n\n".join(f"## {p['title']}\n{p['text']}" for p in previous) or "(none yet)"
    reqs = "\n".join("- " + r for r in ch.get("requirements", [])) or "(none)"
    return chat(CHAPTER_SYS, f"# Guide\n{guide}\n\n# Applicant idea\n{idea}\n\n# Earlier chapters\n{prev}\n\n"
                             f"# Write this chapter: {ch['title']}\nInstruction: {ch['prompt']}\nRequirements:\n{reqs}{_cap(budget, unit)}")


def check(guide, chapters, count=None, unit="chars", info=""):
    draft = "\n\n".join(f"## {c['title']}\n{c['text']}" for c in chapters)
    n = count if count is not None else sum(len(c["text"]) for c in chapters)      # exact count (same rule as the UI): models cannot count length reliably
    u = "words" if unit == "words" else "characters"
    form = f"\n\n# Applicant information (cover page and form; counts as part of the submission)\n{info}" if info else ""
    return chat_json(CHECK_SYS, f"# Guide\n{guide}{form}\n\n# Draft (exactly {n} {u} in total, spaces and line breaks not counted)\n{draft}")


REVISE_SYS = f"""You revise one chapter of a project proposal. Apply the instruction/issues exactly, keep everything else that is good.
Do not invent numbers, names, institutions or results; use [待补充: …] for missing facts. Output the full revised chapter body only. {LANG}"""


def revise(guide, idea, ch, instruction, budget=None, unit="chars"):
    return chat(REVISE_SYS, f"# Guide\n{guide}\n\n# Applicant idea\n{idea}\n\n# Chapter: {ch['title']}\n{ch['text']}\n\n# Instruction / issues to fix\n{instruction}{_cap(budget, unit)}")

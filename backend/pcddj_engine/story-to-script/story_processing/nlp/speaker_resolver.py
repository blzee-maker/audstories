"""Speaker resolver — dependency-parse-based speaker attribution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from spacy.tokens import Doc

from story_processing.nlp.dialogue_extractor import DialogueTurn


# Common speech / communication verbs
SPEECH_VERBS: frozenset[str] = frozenset({
    "say", "said", "says", "saying",
    "tell", "told", "tells", "telling",
    "ask", "asked", "asks", "asking",
    "whisper", "whispered", "whispers", "whispering",
    "shout", "shouted", "shouts", "shouting",
    "reply", "replied", "replies", "replying",
    "respond", "responded", "responds", "responding",
    "mutter", "muttered", "mutters", "muttering",
    "exclaim", "exclaimed", "exclaims", "exclaiming",
    "murmur", "murmured", "murmurs", "murmuring",
    "cry", "cried", "cries", "crying",
    "scream", "screamed", "screams", "screaming",
    "call", "called", "calls", "calling",
    "announce", "announced", "announces", "announcing",
    "declare", "declared", "declares", "declaring",
    "add", "added", "adds", "adding",
    "continue", "continued", "continues", "continuing",
    "begin", "began", "begins", "beginning",
    "snap", "snapped", "snaps", "snapping",
    "sigh", "sighed", "sighs", "sighing",
    "groan", "groaned", "groans", "groaning",
    "plead", "pleaded", "pleads", "pleading",
    "insist", "insisted", "insists", "insisting",
    "demand", "demanded", "demands", "demanding",
    "stammer", "stammered", "stammers", "stammering",
})


@dataclass(frozen=True, slots=True)
class _Mention:
    """A single proper-noun mention found during the document scan."""

    token_index: int
    name: str
    is_person: bool


@dataclass(frozen=True, slots=True)
class AttributedTurn:
    """A dialogue turn with a resolved (or fallback) speaker."""

    speaker: str
    text: str
    start_char: int
    end_char: int
    quote_style: str = "double"


def _build_mention_chain(doc: Doc) -> list[_Mention]:
    """Scan the entire *doc* once and return an ordered list of PROPN mentions.

    Each mention records its token index, normalised surface form, and whether
    spaCy's NER labelled it as a PERSON entity.  The list is sorted by token
    index (i.e. document order) so that backward look-ups are a simple reverse
    walk.
    """
    mentions: list[_Mention] = []
    for token in doc:
        if token.pos_ == "PROPN":
            is_person = token.ent_type_ == "PERSON"
            mentions.append(
                _Mention(
                    token_index=token.i,
                    name=token.text,
                    is_person=is_person,
                )
            )
    return mentions


def resolve_speakers(
    doc: Doc,
    dialogue_turns: list[DialogueTurn],
) -> list[AttributedTurn]:
    """Attribute each dialogue turn to a speaker using dependency parsing.

    Strategy:
    1. For each dialogue turn, find the nearest speech verb in the same
       or adjacent sentence.
    2. Walk the dependency tree of that verb to find an ``nsubj``.
    3. If no speaker is found, assign ``"unknown_speaker_X"`` with an
       incrementing counter.

    No guessing. No LLM.
    """
    # Build document-level mention chain once for cross-sentence coreference
    mention_chain = _build_mention_chain(doc)

    # Pre-index: map char offsets → sentence objects for quick lookup
    sent_by_char: list[tuple[int, int, object]] = []
    for sent in doc.sents:
        sent_by_char.append((sent.start_char, sent.end_char, sent))

    unknown_counter = 0
    results: list[AttributedTurn] = []

    for turn in dialogue_turns:
        speaker = _find_speaker_near(doc, turn, sent_by_char, mention_chain)
        if speaker is None:
            unknown_counter += 1
            speaker = f"unknown_speaker_{unknown_counter}"
        results.append(
            AttributedTurn(
                speaker=speaker,
                text=turn.text,
                start_char=turn.start_char,
                end_char=turn.end_char,
                quote_style=turn.quote_style,
            )
        )

    return results


def _find_speaker_near(
    doc: Doc,
    turn: DialogueTurn,
    sent_by_char: list[tuple[int, int, object]],
    mention_chain: list[_Mention],
) -> str | None:
    """Try to find the speaker for a dialogue turn via dependency parse."""
    # Find the sentence(s) that overlap with the dialogue turn
    target_sents = []
    for s_start, s_end, sent in sent_by_char:
        if s_start <= turn.end_char and s_end >= turn.start_char:
            target_sents.append(sent)

    # Also look at the sentence immediately before and after the dialogue
    all_sents = list(doc.sents)
    expanded = set(id(s) for s in target_sents)
    for i, sent in enumerate(all_sents):
        if id(sent) in expanded:
            if i > 0:
                target_sents.append(all_sents[i - 1])
            if i < len(all_sents) - 1:
                target_sents.append(all_sents[i + 1])

    # Search for speech verbs in the target sentences
    for sent in target_sents:
        for token in sent:
            if token.lower_ in SPEECH_VERBS or token.lemma_.lower() in SPEECH_VERBS:
                # Walk children for nsubj
                for child in token.children:
                    if child.dep_ in ("nsubj", "nsubjpass"):
                        # If it's a pronoun, try to get a proper noun nearby
                        if child.pos_ == "PRON":
                            proper = _find_proper_noun_near(
                                child, mention_chain, doc,
                            )
                            if proper:
                                return proper
                        return child.text

                # Also check the verb's head if the verb is in a relative clause
                if token.dep_ in ("relcl", "advcl", "conj"):
                    for child in token.head.children:
                        if child.dep_ in ("nsubj", "nsubjpass"):
                            return child.text

    return None


_LOOKBACK_SENTS: int = 3  # how many sentences back to search


def _find_proper_noun_near(
    token,
    mention_chain: list[_Mention],
    doc: Doc,
) -> str | None:
    """Resolve a pronoun to a nearby proper noun.

    Resolution strategy
    -------------------
    1. **Same-sentence scan** (fast path, preserves legacy behaviour).
    2. **Backward mention-chain scan** – walk the pre-built mention chain in
       reverse from the pronoun's token index.  Prefer a PERSON-entity PROPN;
       fall back to any PROPN within the lookback window.

    The lookback window is defined as *_LOOKBACK_SENTS* sentences back from
    the pronoun's sentence, measured by sentence start-token indices.
    """

    # ── 1. Same-sentence scan (fast path) ──────────────────────────────
    sent = token.sent
    for t in sent:
        if t.pos_ == "PROPN" and t.i != token.i:
            return t.text

    # ── 2. Backward mention-chain scan ─────────────────────────────────
    # Determine the earliest token index we are willing to look back to.
    all_sents = list(doc.sents)
    current_sent_idx: int | None = None
    for idx, s in enumerate(all_sents):
        if s.start <= token.i < s.end:
            current_sent_idx = idx
            break

    if current_sent_idx is None:
        return None  # defensive: should never happen

    earliest_sent_idx = max(0, current_sent_idx - _LOOKBACK_SENTS)
    earliest_token_idx = all_sents[earliest_sent_idx].start

    # Walk the mention chain backwards from the pronoun's position.
    best_fallback: str | None = None
    for mention in reversed(mention_chain):
        if mention.token_index >= token.i:
            continue  # skip mentions at or after the pronoun
        if mention.token_index < earliest_token_idx:
            break  # outside the lookback window – stop early

        if mention.is_person:
            return mention.name  # prefer PERSON entity
        if best_fallback is None:
            best_fallback = mention.name  # remember first (nearest) PROPN

    return best_fallback

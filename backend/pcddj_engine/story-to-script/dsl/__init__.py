"""DSL Layer — transforms Narrative Plans into Draft Timelines.

The DSL (Domain Specific Language for Audio Storytelling) defines the
vocabulary and rules for expressing sonic intent.  The compiler reads
a Narrative Plan and emits a Draft Timeline JSON that is structurally
aligned with the audio engine's ``timeline.json`` schema but uses
descriptor fields (mood, tts_text, atmosphere) in place of concrete
values (file paths, durations, timing).
"""

__version__ = "1.0.0"

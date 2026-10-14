"""Session 10 Computer-Use skill.

Layer map (see skill.py for the cascade and its ordering rationale):

    Layer 1  — ax.enumerate_ui / UISnapshot.text_dump   no LLM
    Layer 2a — input.press_sequence / osascript          no LLM
    Layer 2b — driver.AXDriver                           text LLM
    Layer 2c — cdp.PageSession (electron_debugging_port)  no LLM
    Layer 3  — driver.VisionDriver                        vision LLM
"""
from .recorder import Recorder, start_recording
from .skill import ComputerSkill

__all__ = ["ComputerSkill", "Recorder", "start_recording"]

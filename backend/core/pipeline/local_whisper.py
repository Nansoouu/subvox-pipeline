"""Local whisper tiny (CPU)."""
from __future__ import annotations
import os; os.environ["XDG_CACHE_HOME"]="/tmp/.cache"
from pathlib import Path
from typing import Any, Optional
from core.logging_setup import get_logger; logger = get_logger(__name__)
MODEL_SIZE = "tiny"; _model = None
def _get_model():
    global _model
    if _model is None:
        import whisper; _model = whisper.load_model(MODEL_SIZE)
    return _model
def _secs_to_srt(s):
    h=int(s//3600); m=int((s%3600)//60); s2=int(s%60); ms=int((s-int(s))*1000)
    return f"{h:02d}:{m:02d}:{s2:02d},{ms:03d}"
def _transcribe_local(p,srt,txt,gk=""):
    import traceback as tb
    try:
        m=_get_model(); logger.info(f"whisper {MODEL_SIZE} transcribing {p.name}...")
        r=m.transcribe(str(p),language=None,temperature=0.0,no_speech_threshold=0.6,condition_on_previous_text=False)
        segs=r.get("segments",[]); sl,tp=[],[]
        for i,s in enumerate(segs,1):
            t=s.get("text","").strip()
            if not t: continue
            sl.append(f"{i}\n{_secs_to_srt(s['start'])} --> {_secs_to_srt(s['end'])}\n{t}\n"); tp.append(t)
        srt.parent.mkdir(parents=True,exist_ok=True); srt.write_text("\n".join(sl),encoding="utf-8"); txt.write_text(" ".join(tp),encoding="utf-8")
        logger.info(f"whisper done: {len(sl)} segs lang={r.get('language','?')}")
        return {"text":" ".join(tp),"language":r.get("language","en"),"model":f"whisper-{MODEL_SIZE}","segments":len(sl)}
    except Exception as e:
        logger.error(f"whisper failed: {e}\n{tb.format_exc()}"); return None

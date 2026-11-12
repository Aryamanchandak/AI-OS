from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.request import Request,urlopen
from datetime import datetime

Transport=Callable[[Request],bytes]
def _send(request:Request)->bytes:
    with urlopen(request,timeout=20) as response:return response.read()

@dataclass
class TelegramAdapter:
    token:str;transport:Transport=_send
    def send(self,chat_id:str,text:str)->dict:
        body=json.dumps({"chat_id":chat_id,"text":text}).encode()
        req=Request(f"https://api.telegram.org/bot{self.token}/sendMessage",data=body,headers={"Content-Type":"application/json"})
        return json.loads(self.transport(req))
    @staticmethod
    def incoming(update:dict)->tuple[str,str]|None:
        message=update.get("message") or update.get("edited_message") or {}
        text=message.get("text");chat=(message.get("chat") or {}).get("id")
        return (str(chat),text) if text and chat is not None else None

@dataclass
class WhatsAppAdapter:
    access_token:str;phone_number_id:str;transport:Transport=_send
    def send(self,to:str,text:str)->dict:
        body=json.dumps({"messaging_product":"whatsapp","to":to,"type":"text","text":{"body":text}}).encode()
        req=Request(f"https://graph.facebook.com/v21.0/{self.phone_number_id}/messages",data=body,headers={"Authorization":f"Bearer {self.access_token}","Content-Type":"application/json"})
        return json.loads(self.transport(req))
    @staticmethod
    def incoming(payload:dict)->tuple[str,str]|None:
        try:m=payload["entry"][0]["changes"][0]["value"]["messages"][0];return m["from"],m["text"]["body"]
        except (KeyError,IndexError,TypeError):return None

class LocalWhisperAdapter:
    def __init__(self,model_size:str="small",device:str="auto",compute_type:str="default"):
        try:from faster_whisper import WhisperModel
        except ImportError as e:raise RuntimeError("Install voice support with: uv sync --extra voice") from e
        self.model=WhisperModel(model_size,device=device,compute_type=compute_type)
    def transcribe(self,path:str|Path)->str:
        segments,_=self.model.transcribe(str(path),vad_filter=True)
        return " ".join(segment.text.strip() for segment in segments).strip()

class OfflineQueue:
    def __init__(self,path:str|Path):self.path=Path(path)
    def enqueue(self,channel:str,target:str,text:str)->None:
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.path.open("a",encoding="utf-8") as f:f.write(json.dumps({"at":datetime.now().astimezone().isoformat(),"channel":channel,"target":target,"text":text})+"\n")
    def pending(self)->list[dict]:
        if not self.path.exists():return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line]

import json
from decision_tracker.integrations import TelegramAdapter,WhatsAppAdapter,OfflineQueue

def transport(request):
    assert request.full_url.startswith("https://")
    return json.dumps({"ok":True}).encode()

def test_telegram_adapter_and_webhook_parser():
    assert TelegramAdapter("token",transport).send("1","hello")["ok"] is True
    assert TelegramAdapter.incoming({"message":{"chat":{"id":1},"text":"claim"}})==("1","claim")

def test_whatsapp_adapter_and_webhook_parser():
    assert WhatsAppAdapter("token","phone",transport).send("2","hello")["ok"] is True
    payload={"entry":[{"changes":[{"value":{"messages":[{"from":"2","text":{"body":"claim"}}]}}]}]}
    assert WhatsAppAdapter.incoming(payload)==("2","claim")

def test_offline_queue(tmp_path):
    queue=OfflineQueue(tmp_path/"outbox.jsonl");queue.enqueue("telegram","1","hello")
    assert queue.pending()[0]["text"]=="hello"

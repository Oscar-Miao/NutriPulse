"""Deterministic local gateway for migration QA; never a production Agent."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        kind, data = request["agent_type"], request["input"]
        if kind == "food_vision":
            response = {"items": [{"name": "QA 测试米饭", "estimated_grams": 100,
                "kcal": 116, "carb_g": 25.9, "protein_g": 2.6, "fat_g": .3,
                "confidence": .85, "assumptions": ["仅供迁移测试的固定返回"]}],
                "uncertainties": ["Mock Agent，不代表真实图像识别结果"]}
        elif kind == "food_chat":
            recipes = data["context"]["safe_recipes"]
            response = {"reply": "这是本机迁移测试回复，已读取对话上下文。"}
            if recipes:
                response["proposal"] = {"meal_type": "dinner", "recipe_id": recipes[0]["recipe_id"]}
        else:
            self.send_error(400, "This QA gateway only implements vision and chat")
            return
        encoded = json.dumps(response, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


if __name__ == "__main__":
    print("QA mock Agent listening on 127.0.0.1:8899", flush=True)
    ThreadingHTTPServer(("127.0.0.1", 8899), Handler).serve_forever()

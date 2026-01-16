
import os
import base64
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from google.adk.runners import InMemoryRunner
from google.genai import types
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from adk_project.app.agent import root_agent

app = FastAPI()

# Mount static files using absolute paths based on the current file location
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Setup templates
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Initialize ADK Runner
APP_NAME = "mermaid_app"
# InMemoryRunner creates its own internal InMemorySessionService
runner = InMemoryRunner(agent=root_agent, app_name=APP_NAME)
session_service = runner.session_service

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/chat")
async def chat(request: Request):
    data = await request.json()
    user_input = data.get("text", "")
    image_data = data.get("image", None) # Base64 encoded image

    user_id = "default_user" # Simplified for demo
    session_id = "default_session"

    # Ensure session exists in the runner's session service
    session = await session_service.get_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
    if not session:
        await session_service.create_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)

    parts = []
    if user_input:
        parts.append(types.Part.from_text(text=user_input))

    if image_data:
        # image_data is expected to be "data:image/png;base64,..."
        if "," in image_data:
            header, encoded = image_data.split(",", 1)
            mime_type = header.split(":")[1].split(";")[0]
            image_bytes = base64.b64decode(encoded)
            parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime_type))

    if not parts:
        return JSONResponse({"error": "No input provided"}, status_code=400)

    content = types.Content(role="user", parts=parts)

    # Run the agent
    response_text = ""
    try:
        async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=content):
            if event.is_final_response():
                # Extract text from final response
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            response_text += part.text
    except Exception as e:
        print(f"Error running agent: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

    return JSONResponse({"response": response_text})

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

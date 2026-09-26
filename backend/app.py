import os
import json
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import bcrypt
import boto3
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pinecone import Pinecone as PineconeClient
from pydantic import BaseModel, Field

# === Load environment
load_dotenv(".env")
if os.getenv("APP_ENV") == "production" or os.getenv("FLASK_ENV") == "production":
    load_dotenv(".env.production", override=True)


def _merge_secrets_manager_into_environ() -> None:
    """Optional: load a JSON secret from AWS Secrets Manager into os.environ."""
    secret_id = os.getenv("AWS_SECRETS_MANAGER_SECRET_ID") or os.getenv(
        "AWS_SECRETS_MANAGER_ARN"
    )
    if not secret_id or not str(secret_id).strip():
        return
    region = os.getenv("AWS_REGION") or "us-east-1"
    client = boto3.client("secretsmanager", region_name=region)
    resp = client.get_secret_value(SecretId=secret_id.strip())
    raw = resp.get("SecretString") or ""
    if not raw.strip():
        return
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            "AWS Secrets Manager secret must be JSON text with an object of key/value pairs."
        ) from e
    if not isinstance(data, dict):
        raise RuntimeError("AWS Secrets Manager JSON must be an object at the top level.")
    for key, val in data.items():
        if val is None:
            continue
        os.environ[str(key)] = str(val)
    print("✅ Loaded environment keys from AWS Secrets Manager.")


_merge_secrets_manager_into_environ()


def _cors_allowed_origins() -> list[str]:
    default = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://d3kbdjd8g1brr.cloudfront.net",
        "https://app2.heilab.pitt.edu",
    ]
    raw = os.getenv("CORS_ORIGINS", "").strip()
    if not raw:
        return default
    parsed = [o.strip() for o in raw.split(",") if o.strip()]
    return parsed if parsed else default


# === FastAPI app
app = FastAPI(title="Anatomy Chatbot API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
print("CORS allow origins:", _cors_allowed_origins(), flush=True)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    if request.method != "OPTIONS":
        print(f"\n--- Incoming Request ---\n{request.method} {request.url}\n------------------------\n")
    return await call_next(request)


# === AWS
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")
AWS_REGION = os.getenv("AWS_REGION") or "us-east-1"
DYNAMODB_TABLE_NAME = os.getenv("DYNAMODB_TABLE_NAME", "ChatbotInteractionsMsk3")
DYNAMODB_SESSION_TABLE = os.getenv("DYNAMODB_SESSION_TABLE", "ChatbotSessions")
USERS_TABLE = os.getenv("USERS_TABLE", "Users")

_dynamodb_kwargs: dict[str, Any] = {"region_name": AWS_REGION}
if AWS_ACCESS_KEY and AWS_SECRET_KEY:
    _dynamodb_kwargs["aws_access_key_id"] = AWS_ACCESS_KEY
    _dynamodb_kwargs["aws_secret_access_key"] = AWS_SECRET_KEY

dynamodb = boto3.resource("dynamodb", **_dynamodb_kwargs)
interactions_table = dynamodb.Table(DYNAMODB_TABLE_NAME)
sessions_table = dynamodb.Table(DYNAMODB_SESSION_TABLE)
users_table = dynamodb.Table(USERS_TABLE)

# === Pinecone + OpenAI (lazy — /healthz must stay lightweight)
_ai_chat_model = None
_ai_embeddings = None
_ai_index = None


def get_ai_clients():
    """Load Pinecone + LangChain clients on first chat use."""
    global _ai_chat_model, _ai_embeddings, _ai_index
    if _ai_chat_model is not None:
        return _ai_chat_model, _ai_embeddings, _ai_index
    pine_key = os.getenv("PINECONE_API_KEY")
    pine_index = os.getenv("PINECONE_INDEX_NAME")
    if not pine_key or not str(pine_key).strip():
        raise RuntimeError("PINECONE_API_KEY is not set")
    if not pine_index or not str(pine_index).strip():
        raise RuntimeError("PINECONE_INDEX_NAME is not set")
    pc = PineconeClient(api_key=pine_key.strip())
    idx = pc.Index(pine_index.strip())
    emb = OpenAIEmbeddings(model="text-embedding-3-large")
    chat = ChatOpenAI(model="gpt-4", temperature=0.7)
    _ai_index = idx
    _ai_embeddings = emb
    _ai_chat_model = chat
    return _ai_chat_model, _ai_embeddings, _ai_index


# === Request models


class AuthRequest(BaseModel):
    email: str = ""
    password: str = ""


class ChatMessage(BaseModel):
    role: str = ""
    content: str = ""


class ChatRequest(BaseModel):
    question: str = ""
    userEmail: str = "anonymous"
    conversationHistory: list[ChatMessage] = Field(default_factory=list)


# === Routes


@app.get("/healthz")
def healthz():
    """Load balancer / Kubernetes probe — keep lightweight."""
    return {"status": "ok"}


@app.post("/api/signup")
def signup(body: AuthRequest):
    print("✅ Signup route hit")
    email = body.email.strip()
    password = body.password.strip()

    if not email or not password:
        raise HTTPException(
            status_code=400,
            detail={"success": False, "message": "Email and password are required."},
        )

    try:
        hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
        users_table.put_item(
            Item={
                "user_email": email,
                "password": hashed_password.decode("utf-8"),
            }
        )
        return {"success": True, "message": "Signup successful!"}
    except HTTPException:
        raise
    except Exception as e:
        print("❌ Signup error:", e)
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={"success": False, "message": "Signup failed. Please try again."},
        ) from e


@app.post("/api/login")
def login(body: AuthRequest):
    print("✅ Login route hit")
    email = body.email.strip()
    password = body.password.strip()

    if not email or not password:
        raise HTTPException(
            status_code=400,
            detail={"success": False, "message": "Email and password are required."},
        )

    try:
        response = users_table.get_item(Key={"user_email": email})
        user = response.get("Item")
        if not user:
            raise HTTPException(
                status_code=404,
                detail={"success": False, "message": "User not found."},
            )
        if not bcrypt.checkpw(
            password.encode("utf-8"), user["password"].encode("utf-8")
        ):
            raise HTTPException(
                status_code=401,
                detail={"success": False, "message": "Invalid credentials."},
            )

        session_id = str(uuid.uuid4())
        sessions_table.put_item(
            Item={
                "session_id": session_id,
                "user_email": email,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        return {
            "success": True,
            "session_id": session_id,
            "user_email": email,
        }
    except HTTPException:
        raise
    except Exception as e:
        print("❌ Login error:", e)
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={"success": False, "message": "Login failed. Please try again."},
        ) from e


@app.post("/api/chat")
def chat(body: ChatRequest):
    print("✅ Chat route hit")
    try:
        user_question = body.question.strip()
        user_email = body.userEmail or "anonymous"
        conversation_history = [
            {"role": m.role, "content": m.content} for m in body.conversationHistory
        ]

        if not user_question:
            raise HTTPException(
                status_code=400,
                detail={"answer": "Please ask a valid question."},
            )

        chat_model, embeddings, index = get_ai_clients()

        history_section_for_extraction = ""
        if conversation_history:
            history_parts = []
            for msg in conversation_history[-3:]:
                role = "Student" if msg.get("role") == "user" else "Assistant"
                history_parts.append(f"{role}: {msg.get('content', '')}")
            history_for_extraction = "\n".join(history_parts)
            history_section_for_extraction = (
                f"Conversation History:\n{history_for_extraction}\n\n"
            )

        extraction_prompt = f"""You are helping extract the best search query for finding content in course materials.

{history_section_for_extraction}Current User Question: {user_question}

TASK: Extract the core topic or subject to search for in the course materials database.

RULES:
1. Remove meta-instructions: "create a quiz", "show me the video", "where can I find", "help me understand", etc.
2. Resolve pronouns: If the question uses "it", "that", "them", etc., replace with the actual topic from conversation history
3. Keep the core topic: anatomy terms, course policies, schedules, assignments, software, or ANY other course content
4. Be concise: Extract just the core topic, not a full sentence
5. ALWAYS return a short topic string — never refuse, never explain, never say the question lacks a topic

EXAMPLES:
- "Create a quiz on hip muscles" → "hip muscles"
- "Where can I find the deltoid in the videos?" → "deltoid"
- "Tell me about it" (after discussing rotator cuff) → "rotator cuff"
- "Help me understand the brachialis" → "brachialis"
- "What are the hip flexors?" → "hip flexors"
- "Quiz me on anterior thigh muscles" → "anterior thigh muscles"
- "What is the late policy?" → "late policy"
- "When should I be in class?" → "class schedule attendance"
- "How do I access Google links?" → "Google links access"
- "What software do I need?" → "software requirements"
- "How are we graded?" → "grading policy"
- "What happens if I miss a lab?" → "missed lab policy"
- "When are exams?" → "exam schedule"

Search Query (just the topic, no explanation):"""

        print("🤖 Using LLM to extract search query...")
        extraction_response = chat_model.invoke(extraction_prompt)
        search_query = extraction_response.content.strip()

        if search_query.lower() != user_question.lower():
            print(f"🎯 Extracted search query: '{user_question}' → '{search_query}'")

        print("🔍 Embedding question...")
        query_embedding = embeddings.embed_query(search_query)

        print("📡 Querying Pinecone...")
        results = index.query(
            vector=query_embedding,
            top_k=10,
            include_metadata=True,
        )

        print("🔎 RAW PINECONE RESULTS:")
        for i, match in enumerate(results.matches):
            text_preview = match.metadata.get("text", "")[:100] if match.metadata else ""
            print(f"  [{i}] score={match.score:.4f} | text='{text_preview}'")

        if not results or not results.matches:
            return {
                "answer": "I couldn't find relevant information to answer this question."
            }

        retrieved_items = []
        for match in results.matches:
            if match.metadata:
                retrieved_items.append(
                    {
                        "text": match.metadata.get("text", ""),
                        "source_type": match.metadata.get("source_type", "document"),
                        "video_title": match.metadata.get("video_title", ""),
                        "start_time": match.metadata.get("start_time", ""),
                        "end_time": match.metadata.get("end_time", ""),
                    }
                )

        context_parts = []
        has_video_content = False
        for item in retrieved_items:
            if item["source_type"] == "video_transcript":
                has_video_content = True
                context_parts.append(
                    f"[Video: {item['video_title']} | Timestamp: {item['start_time']} - {item['end_time']}]\n{item['text']}"
                )
            else:
                context_parts.append(f"[Document]\n{item['text']}")

        formatted_context = "\n\n".join(context_parts)

        history_text = ""
        if conversation_history:
            history_parts = []
            for msg in conversation_history:
                role = "Student" if msg.get("role") == "user" else "Assistant"
                history_parts.append(f"{role}: {msg.get('content', '')}")
            history_text = "\n".join(history_parts)

        history_section = (
            f"\n--- RECENT CONVERSATION ---\n{history_text}\n-------------------------\n"
            if history_text
            else ""
        )

        video_note = ""
        if has_video_content:
            video_note = " (Note: Video timestamps are available in the course materials below)"

        prompt = f"""You are an AI assistant helping anatomy students with questions based on course materials{video_note}.

--- COURSE MATERIALS ---
{formatted_context}
-------------------------
{history_section}
Student Question: {user_question}

🚨 CRITICAL CONSTRAINT - READ THIS FIRST:
You must ONLY use information from the course materials provided above. Do NOT supplement with your general knowledge of anatomy. If the provided materials don't contain enough information to fully answer the question, acknowledge this limitation rather than adding external information.

INSTRUCTIONS - Read the conversation context and respond naturally:

1. UNDERSTANDING CONTEXT:
   - Use conversation history to understand context and resolve pronouns (e.g., "it", "that", "this", "them")
   - Maintain conversation flow naturally - if you asked a question, recognize when the student is answering it
   - Be conversational and helpful, like ChatGPT

2. QUIZ CREATION (if student asks for a quiz):
   - FIRST TIME: Ask TWO things:
     (a) What SOURCE they want questions from: "Would you like questions from the lecture/reading materials, the cadaver lab videos, or both?"
     (b) What FORMAT they prefer: True/False, Multiple Choice, or a mix
     (c) How to show answers: immediately after each question, all at the end, or self-check mode
   - AFTER THEY RESPOND WITH PREFERENCES: Create the quiz based on their preferences using ONLY the course materials above
     * If they chose "lecture/reading materials" → use ONLY document/PDF content, no video content
     * If they chose "cadaver lab videos" → use ONLY video transcript content
     * If they chose "both" → use any available content
   - DO NOT provide instructions on how to use Complete Anatomy software - CREATE ACTUAL QUIZ QUESTIONS
   - Every question must come from the course materials - no general anatomy knowledge
   - If materials lack content for the chosen source, explain the limitation and ask if they'd like to broaden the source

3. VIDEO TIMESTAMPS - UNDERSTANDING VIDEO LOCATION INTENT:

   VIDEO LOCATION QUERIES (show timestamps):
   The student is asking WHERE/WHICH/WHEN to find content in videos. Key indicators:
   - Contains words like: "where", "which", "when", "find", "show me", "locate", "see"
   - References video context: "in the video", "in the videos", "in the lecture", "in the cadaver lab videos",
     "in the recording", "video shows", "lecture covers", "demonstration", "cadaver videos"
   - Examples of VIDEO LOCATION queries:
     * "Where in the video can I see X?"
     * "Which video shows X?"
     * "Where can I find X in the cadaver lab videos?"
     * "Show me the lecture on X"
     * "What video covers X?"
     * "Find X in the videos"
     * "Where in the recording is X?"

   GENERAL KNOWLEDGE QUERIES (NO timestamps):
   The student wants to LEARN about the topic, not find video locations. Key indicators:
   - Asks "what", "how", "why", "tell me about", "explain", "describe"
   - No reference to videos/lectures/recordings
   - Examples of GENERAL queries:
     * "What is X?"
     * "Tell me about X"
     * "How does X work?"
     * "Explain X to me"
     * "Describe X"

   WHEN YOU SHOW TIMESTAMPS:
   - Be conversational and helpful
   - Organize logically, explain what they'll see
   - Format: [Video: Title | Timestamp: 1:07 - 1:10]

   WHEN IN DOUBT: If the question mentions videos/lectures/recordings in ANY form, treat it as a video location query

4. GENERAL QUESTIONS (Most common - follow carefully):
   - Answer using course materials clearly and thoroughly
   - ABSOLUTELY NO VIDEO/TIMESTAMP REFERENCES IN ANY FORM:
     * NO timestamps: not "6:46 - 7:16", not "around 5:41", not any time format
     * NO video mentions: not "in the video", not "the video shows", not "as mentioned in the video"
     * NO parenthetical citations: not "(video timestamp: X)", not "(mentioned at X:XX)"
     * NO source attribution at all
   - Explain concepts directly as if you're teaching, not citing sources
   - Example of WRONG: "The muscle is located here (as mentioned in the video around 6:46 - 7:16 timestamp)"
   - Example of RIGHT: "The muscle is located between the metatarsal bones in the foot"
   - Focus ONLY on teaching the anatomical concept
   - If student asks about content not in materials, politely explain it's not covered in the course content provided

5. TONE:
   - Be friendly, conversational, and educational
   - Respond naturally based on the conversation flow
   - Don't be robotic or formulaic

Remember: You're having a conversation with a student. Use context to understand what they need and respond naturally."""

        print("💬 Sending prompt to OpenAI...")
        chat_response = chat_model.invoke(prompt)
        bot_response = chat_response.content.strip()

        log_interaction_in_dynamodb(user_question, bot_response, user_email)
        return {"answer": bot_response}

    except HTTPException:
        raise
    except Exception as e:
        print("❌ Chat error:", e)
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={
                "answer": "An error occurred while processing your question. Please try again."
            },
        ) from e


def log_interaction_in_dynamodb(user_question, bot_response, user_email="anonymous"):
    try:
        timestamp = datetime.now(timezone.utc).isoformat()
        interaction = {
            "user_email": user_email,
            "timestamp": timestamp,
            "question": user_question,
            "response": bot_response,
        }
        interactions_table.put_item(Item=interaction)
        print("✅ Interaction logged:", interaction)
    except Exception as e:
        print("❌ Log interaction error:", e)
        traceback.print_exc()


# FastAPI returns `detail` for HTTPException; frontend expects flat JSON for some errors.
# Normalize signup/login/chat client-facing error bodies via exception handler.


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    from fastapi.responses import JSONResponse

    content = exc.detail if isinstance(exc.detail, dict) else {"detail": exc.detail}
    return JSONResponse(status_code=exc.status_code, content=content)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 5000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=os.getenv("APP_ENV") != "production")

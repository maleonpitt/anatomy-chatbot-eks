import os
import json
import boto3
import requests
import traceback
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timezone
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import Pinecone as PineconeStore
from pinecone import Pinecone as PineconeClient
import bcrypt
import uuid


# === Load environment
# Always load .env first so local settings apply when FLASK_ENV is only set inside that file.
# If the process is production (e.g. shell or systemd), overlay .env.production.
load_dotenv(".env")
if os.getenv("FLASK_ENV") == "production":
    load_dotenv(".env.production", override=True)


def _merge_secrets_manager_into_environ() -> None:
    """Optional: load a JSON secret from AWS Secrets Manager into os.environ.

    Set AWS_SECRETS_MANAGER_SECRET_ID (name or ARN) or AWS_SECRETS_MANAGER_ARN.
    Secret must be SecretString containing a JSON object: {\"KEY\": \"value\", ...}.
    Uses default boto3 credentials (e.g. EC2 instance profile). Keys from the secret
    override values from dotenv for the same name.
    """
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


def _cors_allowed_origins():
    """Explicit origins required when supports_credentials=True (wildcard * is invalid with cookies)."""
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
    # If CORS_ORIGINS is set but parses to nothing (e.g. ","), use defaults.
    return parsed if parsed else default


# === Flask App
app = Flask(__name__)
app.secret_key = os.getenv("SESSION_SECRET_KEY")
# Do not set allow_headers to a short list — axios preflight can request other header names.
CORS(
    app,
    supports_credentials=True,
    origins=_cors_allowed_origins(),
    allow_headers="*",
)
print("CORS allow origins:", _cors_allowed_origins(), flush=True)


# === Debug every request
@app.before_request
def log_request_info():
    if request.method == "OPTIONS":
        return  # let flask-cors answer preflight without touching body
    print(f"\n--- Incoming Request ---")
    print(f"{request.method} {request.url}")
    print(f"Headers: {dict(request.headers)}")
    print(f"Body: {request.get_data().decode('utf-8')}")
    print(f"------------------------\n")


# === AWS
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")
# EC2/Docker often omit AWS_REGION in env; boto3 requires an explicit region for DynamoDB.
AWS_REGION = os.getenv("AWS_REGION") or "us-east-1"
# Interactions / chat log table (override with DYNAMODB_TABLE_NAME; must match your account)
DYNAMODB_TABLE_NAME = os.getenv("DYNAMODB_TABLE_NAME", "ChatbotInteractionsMsk3")
DYNAMODB_SESSION_TABLE = os.getenv("DYNAMODB_SESSION_TABLE", "ChatbotSessions")
USERS_TABLE = os.getenv("USERS_TABLE", "Users")

dynamodb = boto3.resource(
    "dynamodb",
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_REGION,
)

interactions_table = dynamodb.Table(DYNAMODB_TABLE_NAME)
sessions_table = dynamodb.Table(DYNAMODB_SESSION_TABLE)
users_table = dynamodb.Table(USERS_TABLE)

# === Pinecone + OpenAI (lazy — must not block app startup / CodeDeploy health checks)
_ai_chat_model = None
_ai_embeddings = None
_ai_index = None


def get_ai_clients():
    """Load Pinecone + LangChain clients on first use so /healthz works without full config."""
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


# === Routes


@app.route("/healthz", methods=["GET"])
def healthz():
    """Used by CodeDeploy validate.sh and load balancers; keep lightweight."""
    return jsonify({"status": "ok"}), 200


@app.route("/api/signup", methods=["POST"])
def signup():
    print("✅ Signup route hit")
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()

    if not email or not password:
        return (
            jsonify({"success": False, "message": "Email and password are required."}),
            400,
        )

    try:
        hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
        users_table.put_item(
            Item={
                "user_email": email,
                "password": hashed_password.decode("utf-8"),
            }
        )
        return jsonify({"success": True, "message": "Signup successful!"})
    except Exception as e:
        print("❌ Signup error:", e)
        traceback.print_exc()
        return (
            jsonify({"success": False, "message": "Signup failed. Please try again."}),
            500,
        )


@app.route("/api/login", methods=["POST"])
def login():
    print("✅ Login route hit")
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()

    if not email or not password:
        return (
            jsonify({"success": False, "message": "Email and password are required."}),
            400,
        )

    try:
        response = users_table.get_item(Key={"user_email": email})
        user = response.get("Item")
        if not user:
            return jsonify({"success": False, "message": "User not found."}), 404
        if not bcrypt.checkpw(
            password.encode("utf-8"), user["password"].encode("utf-8")
        ):
            return jsonify({"success": False, "message": "Invalid credentials."}), 401

        session_id = str(uuid.uuid4())
        sessions_table.put_item(
            Item={
                "session_id": session_id,
                "user_email": email,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        return jsonify({"success": True, "session_id": session_id, "user_email": email})
    except Exception as e:
        print("❌ Login error:", e)
        traceback.print_exc()
        return (
            jsonify({"success": False, "message": "Login failed. Please try again."}),
            500,
        )


@app.route("/api/chat", methods=["POST"])
def chat():
    print("✅ Chat route hit")
    try:
        data = request.json
        user_question = data.get("question", "").strip()
        user_email = data.get("userEmail", "anonymous")
        conversation_history = data.get("conversationHistory", [])

        if not user_question:
            return jsonify({"answer": "Please ask a valid question."}), 400

        chat_model, embeddings, index = get_ai_clients()

        search_query = user_question

        # DYNAMIC SEARCH QUERY EXTRACTION: Use LLM to intelligently extract what to search for
        # This handles: quiz requests, video location queries, pronoun resolution, etc.

        # Build context for query extraction
        history_section_for_extraction = ""
        if conversation_history:
            history_parts = []
            for msg in conversation_history[-3:]:  # Last 3 messages
                role = "Student" if msg.get("role") == "user" else "Assistant"
                history_parts.append(f"{role}: {msg.get('content', '')}")
            history_for_extraction = "\n".join(history_parts)
            history_section_for_extraction = f"Conversation History:\n{history_for_extraction}\n\n"

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

        # DEBUG: print raw Pinecone results
        print("🔎 RAW PINECONE RESULTS:")
        for i, match in enumerate(results.matches):
            text_preview = match.metadata.get("text", "")[:100] if match.metadata else ""
            print(f"  [{i}] score={match.score:.4f} | text='{text_preview}'")

        # Pinecone SDK v3+ returns an object, not a dict
        if not results or not results.matches:
            return jsonify(
                {
                    "answer": "I couldn't find relevant information to answer this question."
                }
            )

        # Build context with source information (supports both documents and video transcripts)
        retrieved_items = []
        for match in results.matches:
            if match.metadata:
                item = {
                    "text": match.metadata.get("text", ""),
                    "source_type": match.metadata.get("source_type", "document"),
                    "video_title": match.metadata.get("video_title", ""),
                    "start_time": match.metadata.get("start_time", ""),
                    "end_time": match.metadata.get("end_time", ""),
                }
                retrieved_items.append(item)

        # Format context with source info
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

        # Format conversation history for context
        history_text = ""
        if conversation_history:
            history_parts = []
            for msg in conversation_history:
                role = "Student" if msg.get("role") == "user" else "Assistant"
                history_parts.append(f"{role}: {msg.get('content', '')}")
            history_text = "\n".join(history_parts)

        # No more explicit detection - let the LLM handle it naturally!

        # Build unified prompt - ONE prompt for all scenarios
        history_section = f"\n--- RECENT CONVERSATION ---\n{history_text}\n-------------------------\n" if history_text else ""

        # Check if video content is present (to inform prompt about available timestamp info)
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

        return jsonify({"answer": bot_response})

    except Exception as e:
        print("❌ Chat error:", e)
        traceback.print_exc()
        return (
            jsonify(
                {
                    "answer": "An error occurred while processing your question. Please try again."
                }
            ),
            500,
        )


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


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_ENV") != "production"
    app.run(debug=debug, host="0.0.0.0", port=port)

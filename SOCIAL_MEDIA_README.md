# Social Media Automation - Context-Aware LLM Replies

A powerful, context-aware social media automation system that:
- **Reads conversations** from Instagram, WhatsApp, Telegram
- **Analyzes context** using LLM to understand the conversation flow
- **Generates intelligent replies** with personality customization
- **Sends replies automatically** with no timeouts
- **Remembers history** across sessions using persistent memory
- **Routes models intelligently** (NVIDIA NIM → Gemini → fallback)

## Features

### 🧠 LLM-Powered Intelligence
- Uses Danphe's model routing (FastLLM → DeepSeek → Nemotron)
- Context-aware replies that understand conversation history
- Personality modes: Friendly, Professional, Casual, Helpful, Empathetic, Witty
- Streaming generation for real-time feedback

### 📱 Multi-Platform Support
- **Instagram DMs** - Read thread history, auto-reply with context
- **WhatsApp Web** - Conversation reading, intelligent responses
- **Telegram** - (Foundation for future implementation)
- Extensible architecture for more platforms

### 💾 Persistent Context
- SessionMemory stores all conversations locally
- Auto-save to `~/.danphe/social_memory.json`
- Resume conversations with full context
- Analytics and conversation summaries

### ⚡ No Timeouts
- Async/await with graceful error handling
- Configurable wait times
- Scroll-based history loading
- Resilient selectors for DOM changes

## Installation

```bash
# Install social media automation dependencies
pip install -r social_requirements.txt

# This installs:
# - playwright (browser automation)
# - openai (LLM API client)
# - python-dotenv (env config)
# - rich (terminal UI)
```

### Setup Browser Profiles

```bash
# First run - will prompt you to log in manually
cd instra-automate
python social_media.py instagram your_username --auto-reply
```

Browser data is stored in:
- `./browser_data_ig` - Instagram persistent session
- `./browser_data_wa` - WhatsApp persistent session
- `./browser_data_tg` - Telegram persistent session (future)

## Usage

### Basic: Read and display conversation

```bash
# Instagram
python social_media.py instagram @username

# WhatsApp
python social_media.py whatsapp "Contact Name"
```

### Auto-reply with default personality

```bash
python social_media.py instagram @username --auto-reply
python social_media.py whatsapp "Contact Name" --auto-reply
```

### Auto-reply with custom personality

```bash
python social_media.py instagram @username \
  --auto-reply \
  --personality "casual and humorous"

python social_media.py whatsapp "Friend" \
  --auto-reply \
  --personality "warm and empathetic"
```

### Personality Presets

In code or extend via `social_config.py`:

```python
from danphe.social_agent import ReplyGenerator

# Pre-defined personalities
generator = ReplyGenerator(personality="professional")
generator = ReplyGenerator(personality="casual and fun")
generator = ReplyGenerator(personality="witty and clever")

# Or fully custom
generator = ReplyGenerator(
    personality="like a 1920s detective, mysterious and noir"
)
```

## Architecture

```
danphe/
├── social_agent.py          # LLM reply generation engine
├── social_config.py         # Personality & platform config
└── llm/
    ├── nvidia.py            # NVIDIA NIM backend
    └── gemini.py            # Google Gemini fallback

instra-automate/
└── social_media.py          # Browser automation + CLI

~/.danphe/
└── social_memory.json       # Persistent conversation history
```

### Core Components

**ConversationContext**
```python
ctx = ConversationContext(user_id="@username", platform="instagram")
ctx.add_message(sender="@username", text="Hey! How are you?")
ctx.add_message(sender="self", text="Great! How about you?")
print(ctx.get_summary())  # Formatted for LLM
```

**ReplyGenerator**
```python
generator = ReplyGenerator(
    personality="friendly and encouraging",
    system_prompt=""  # leave empty for auto-generation
)
reply = generator.generate(ctx, platform="instagram")
```

**SessionMemory**
```python
memory = SessionMemory()
memory.load()  # Restore from disk

ctx = memory.get_or_create("@username", "instagram")
ctx.add_message("@username", "Hi!")

memory.save()  # Persist conversations
print(memory.summarize_all())
```

**InstagramDMClient**
```python
client = InstagramDMClient(headless=False)
ctx = await client.launch()
page = ctx.pages[0]

# Read conversation
messages = await client.read_messages(page, "@username")

# Auto-reply with LLM
await client.auto_reply(page, "@username", generator)

await client.close()
```

## Configuration

### Environment Variables

```bash
# .env or ~/.danphe/.env
NVIDIA_API_KEY=xxx        # For NVIDIA NIM models
GEMINI_API_KEY=xxx        # For Gemini fallback
DANPHE_MODEL=long         # Force model: fast|long|reasoning|gemini
DANPHE_MAX_TOKENS=16384   # Max tokens in response
DANPHE_DEBUG=1            # Show debug info
```

### Python Configuration

```python
from danphe.social_config import SocialConfig

config = SocialConfig(
    headless=False,           # Show browser
    max_reply_length=200,     # Max chars per message
    model_tier="long",        # Model size
    scroll_history=5,         # Scroll up 5 times for history
)
```

## Model Selection Flow

```
User's question (~100-500 chars with context)
    ↓
Danphe Router estimates tokens
    ↓
NVIDIA available?
├─ < 6K tokens → GLM-4.7 (fastest)
├─ < 60K tokens → DeepSeek V3 (best for code/long)
└─ > 60K tokens → Nemotron (heavy reasoning)
    ↓
NVIDIA unavailable?
└─ → Gemini Flash (fallback)
```

## Example: Intelligent Context-Aware Reply

```python
import asyncio
from danphe.social_agent import ReplyGenerator, ConversationContext
from instra_automate.social_media import InstagramDMClient

async def demo():
    # Setup
    client = InstagramDMClient()
    ctx = await client.launch()
    page = ctx.pages[0]

    # Login
    await client.ensure_logged_in(page)

    # Read conversation
    messages = await client.read_messages(page, "@friend")
    # [
    #   {"sender": "@friend", "text": "Hey! How's the project going?"},
    #   {"sender": "self", "text": "Great! Almost done."},
    #   {"sender": "@friend", "text": "That's awesome! When will you launch?"}
    # ]

    # Build context
    conversation = ConversationContext("@friend", "instagram", "helpful and enthusiastic")
    for msg in messages:
        conversation.add_message(msg["sender"], msg["text"])

    # Generate intelligent reply
    generator = ReplyGenerator(personality="helpful and enthusiastic")
    reply = generator.generate(conversation, platform="instagram")
    # Output: "Thanks for asking! 🚀 We're targeting next month. Will share details soon!"

    # Send it
    await client.send_message(page, "@friend", reply)

    await client.close()

asyncio.run(demo())
```

## Advanced: Custom System Prompts

```python
custom_system = """You are a customer service representative for a tech company.
You should be helpful, professional, and quick to resolve issues.
Always offer multiple solutions if applicable.
Keep responses under 200 characters."""

generator = ReplyGenerator(system_prompt=custom_system)
reply = generator.generate(ctx, platform="instagram")
```

## Error Handling

The system handles gracefully:
- **Browser not responding** - Retry with backoff
- **Missing selectors** - Fallback to alternative selectors
- **API timeouts** - Fallback model routing
- **No messages found** - Graceful skip
- **Login required** - Manual intervention prompt

```python
try:
    await client.auto_reply(page, username, generator)
except RuntimeError as e:
    print(f"Critical error: {e}")
except Exception as e:
    print(f"Recoverable error: {e}")
    # Attempt recovery...
```

## Monitoring & Debugging

```bash
# Enable debug output
export DANPHE_DEBUG=1

# Show model selection
python social_media.py instagram @user --auto-reply
# Output: [danphe debug] model=deepseek-ai/deepseek-v3-0324

# View conversation history
python -c "
from danphe.social_agent import SessionMemory
memory = SessionMemory()
memory.load()
print(memory.summarize_all())
"
```

## Performance Notes

| Operation | Time | Notes |
|-----------|------|-------|
| Browser launch | 2-3s | One-time per session |
| Read 20 messages | 1-2s | With scroll history |
| Generate reply | 0.5-2s | Via streaming LLM |
| Send message | 1s | With input simulation |
| Full auto-reply cycle | 3-5s | Sequential |

## Troubleshooting

### Browser won't load Instagram
```
>> Ensure you have Firefox installed
>> Check internet connection
>> Try: rm -rf ./browser_data_ig && python social_media.py ...
```

### Can't find message input box
```
Instagram updated UI → Update selectors in InstagramDMClient.send_message()
WhatsApp → Check if in correct chat window
```

### LLM API errors
```
Check NVIDIA_API_KEY is set → env.show() in danphe config
Try forcing a different model → DANPHE_MODEL=fast
Check internet bandwidth for streaming
```

### Conversations not persisting
```
Ensure ~/.danphe/ directory exists
Check file permissions on social_memory.json
Call memory.save() after changes
```

## Future Enhancements

- [ ] Telegram bot protocol support
- [ ] Discord webhook integration
- [ ] Email automation
- [ ] Multi-reply batching
- [ ] Context-aware image generation
- [ ] Conversation summarization
- [ ] Sentiment analysis & response tuning
- [ ] Rate limiting & scheduling

## Contributing

To add a new platform:

1. Create `class YourPlatformClient` inheriting from base pattern
2. Implement: `launch()`, `ensure_logged_in()`, `read_messages()`, `send_message()`
3. Add to CLI in `social_media.py` main()
4. Document selectors and platform quirks

Example:
```python
class TelegramClient:
    async def read_messages(self, page, username):
        # Extract messages...
        return messages

    async def send_message(self, page, username, text):
        # Send...
        pass
```

## License

Part of Danphe project. See main LICENSE file.

---

**Questions?** File an issue or check the Danphe documentation.


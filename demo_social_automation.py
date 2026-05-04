#!/usr/bin/env python3
"""
demo_social_automation.py — Examples of using the context-aware social media automation.

Run:
  python demo_social_automation.py

Or with specific examples:
  python demo_social_automation.py --demo instagram
  python demo_social_automation.py --demo whatsapp
  python demo_social_automation.py --demo context-aware
  python demo_social_automation.py --demo memory
"""
import sys

from danphe.social_agent import (
    ConversationContext,
    ReplyGenerator,
    SessionMemory,
)


def demo_conversation_context():
    """Demo 1: Build and format conversation context."""
    print("\n" + "="*60)
    print("DEMO 1: Conversation Context")
    print("="*60)

    # Create a conversation with Instagram friend
    ctx = ConversationContext(
        user_id="@sarah_designs",
        platform="instagram",
        personality="friendly and creative"
    )

    # Add some messages
    ctx.add_message("@sarah_designs", "Hey! Love your recent design work 🎨")
    ctx.add_message("self", "Thanks so much! 😊 Been working on new portfolio pieces")
    ctx.add_message("@sarah_designs", "When is your site launching? I want to check it out!")
    ctx.add_message("self", "Next week! Will send you the link")
    ctx.add_message("@sarah_designs", "Awesome! Can't wait! BTW, want to collab on a project?")

    # Display the conversation
    print("\nConversation history:")
    print(ctx.get_summary())

    # Show metadata
    print(f"\nMetadata:")
    print(f"  User: {ctx.user_id}")
    print(f"  Platform: {ctx.platform}")
    print(f"  Total messages: {len(ctx.messages)}")
    print(f"  Personality: {ctx.personality}")


def demo_reply_generator():
    """Demo 2: Generate replies with different personalities."""
    print("\n" + "="*60)
    print("DEMO 2: Reply Generation (Multiple Personalities)")
    print("="*60)

    # Create a conversation
    ctx = ConversationContext("@john_dev", "instagram")
    ctx.add_message("@john_dev", "Hey! Saw your GitHub. The project looks awesome!")
    ctx.add_message("self", "Thanks! Been working on it for months.")
    ctx.add_message("@john_dev", "Would love to contribute. What's the best way to start?")

    print(f"\nLast message to reply to:")
    print(f"  {ctx.messages[-1]['sender']}: {ctx.messages[-1]['text']}")

    # Generate replies with different personalities
    personalities = [
        "friendly and welcoming",
        "professional and formal",
        "casual and humorous",
        "enthusiastic and motivating",
    ]

    print(f"\n\nGenerated replies with different personalities:")
    print("-" * 60)

    for personality in personalities:
        generator = ReplyGenerator(personality=personality)
        # In real usage, we'd call:
        # reply = generator.generate(ctx, platform="instagram")
        # For demo, we'll just show what would be generated
        print(f"\n🎭 Personality: '{personality}'")
        print(f"   Would generate a friendly, welcoming response that invites")
        print(f"   contribution with clear first steps and support.")


def demo_multiple_conversations():
    """Demo 3: Manage multiple conversations in memory."""
    print("\n" + "="*60)
    print("DEMO 3: Session Memory (Multiple Conversations)")
    print("="*60)

    memory = SessionMemory()

    # Simulate multiple conversations
    ig_user = memory.get_or_create("@alice", "instagram", personality="friendly")
    ig_user.add_message("@alice", "Hi! How are you?")
    ig_user.add_message("self", "Great! How about you?")
    ig_user.add_message("@alice", "All good, just busy with work")

    wa_contact = memory.get_or_create("Sarah", "whatsapp", personality="casual")
    wa_contact.add_message("Sarah", "Want to grab coffee tomorrow?")
    wa_contact.add_message("self", "Sure! What time?")
    wa_contact.add_message("Sarah", "Around 3pm?")

    wa_contact2 = memory.get_or_create("Mom", "whatsapp", personality="warm")
    wa_contact2.add_message("Mom", "Did you eat lunch?")
    wa_contact2.add_message("self", "Yes, just finished!")

    # Display summary
    print("\nActive conversations in memory:")
    print(memory.summarize_all())

    # Show individual conversations
    print(f"\n\nConversation details:")
    print("-" * 60)

    for key, ctx in memory.conversations.items():
        print(f"\n📱 {key}")
        print(f"   Messages: {len(ctx.messages)}")
        print(f"   Personality: {ctx.personality}")
        print(f"   Last message: {ctx.messages[-1]['text'][:50]}...")


def demo_platform_specific():
    """Demo 4: Platform-specific system prompts."""
    print("\n" + "="*60)
    print("DEMO 4: Platform-Specific Responses")
    print("="*60)

    from danphe.social_config import get_system_prompt

    # Same conversation, different platforms
    ctx = ConversationContext("@user", "instagram")
    ctx.add_message("@user", "What do you think about AI?")

    print(f"\nSame last message: '{ctx.messages[-1]['text']}'")
    print(f"\nBut different system prompts by platform:\n")

    platforms = ["instagram", "whatsapp", "twitter"]
    for platform in platforms:
        prompt = get_system_prompt(platform, personality="thoughtful")
        print(f"\n📱 {platform.upper()}")
        print(f"   {prompt[:100]}...")


def demo_conversation_scenarios():
    """Demo 5: Real-world scenario simulations."""
    print("\n" + "="*60)
    print("DEMO 5: Real-World Scenarios")
    print("="*60)

    scenarios = {
        "technical_support": {
            "user": "support_team",
            "platform": "instagram",
            "personality": "helpful and solution-oriented",
            "messages": [
                ("support_team", "Hi! App crashed on login page"),
                ("self", "Sorry to hear! Can you describe what happened?"),
                ("support_team", "Shows 'connection error' before I can even enter password"),
                ("self", "Hmm, could be server issue..."),
                ("support_team", "Any ideas on workaround?"),
            ],
        },
        "creative_collaboration": {
            "user": "@designer123",
            "platform": "instagram",
            "personality": "creative and collaborative",
            "messages": [
                ("@designer123", "Loved the design system doc!"),
                ("self", "Thanks! Spent weeks refining it"),
                ("@designer123", "Want to co-create a tool around it?"),
                ("self", "That sounds amazing! What did you have in mind?"),
                ("@designer123", "A Figma plugin to speed up design handoff?"),
            ],
        },
        "casual_catch_up": {
            "user": "bestfriend",
            "platform": "whatsapp",
            "personality": "casual and warm",
            "messages": [
                ("bestfriend", "OMG haven't talked in forever 😭"),
                ("self", "I know right!! How've you been?"),
                ("bestfriend", "Crazy! Got the promotion I wanted!"),
                ("self", "WAIT WHAT?? That's amazing! Congrats!"),
                ("bestfriend", "Thanks!! We need to celebrate 🥳"),
            ],
        },
        "nepali_english_mixed": {
            "user": "@nepali_friend",
            "platform": "instagram",
            "personality": "nepali-english mixed like 'k gardai' - casual, friendly, uses Nepali slang with English",
            "messages": [
                ("@nepali_friend", "k gardai?"),
                ("self", "bas yesto nai, tmi?"),
                ("@nepali_friend", "ma ta college jane lagi ready hunu paryo"),
                ("self", "acha, best of luck! padhai ma focus gar"),
                ("@nepali_friend", "thanks dai, ani tero project k gardai?"),
            ],
        },
    }

    for scenario_name, scenario_data in scenarios.items():
        print(f"\n\n🎬 Scenario: {scenario_name.upper()}")
        print("-" * 60)

        ctx = ConversationContext(
            user_id=scenario_data["user"],
            platform=scenario_data["platform"],
            personality=scenario_data["personality"]
        )

        for sender, text in scenario_data["messages"]:
            ctx.add_message(sender, text)

        print(f"Platform: {scenario_data['platform']}")
        print(f"Personality: {scenario_data['personality']}")
        print(f"\nConversation:")
        for msg in scenario_data["messages"][-3:]:
            print(f"  {msg[0]}: {msg[1]}")

        print(f"\nLLM would generate a reply using:")
        print(f"  - Last 3 messages for context")
        print(f"  - Personality: {scenario_data['personality']}")
        print(f"  - Platform rules for {scenario_data['platform']}")


def main():
    """Run all demos."""
    demo_name = None

    # Check for --demo argument
    if "--demo" in sys.argv:
        idx = sys.argv.index("--demo")
        if idx + 1 < len(sys.argv):
            demo_name = sys.argv[idx + 1].lower()

    demos = {
        "context": demo_conversation_context,
        "generator": demo_reply_generator,
        "memory": demo_multiple_conversations,
        "platform": demo_platform_specific,
        "scenario": demo_conversation_scenarios,
    }

    if demo_name and demo_name in demos:
        # Run specific demo
        demos[demo_name]()
    else:
        # Run all demos
        print("\n" + "🎭 " * 20)
        print("\nContext-Aware Social Media Automation - Demos")
        print("\n" + "🎭 " * 20)

        demo_conversation_context()
        demo_reply_generator()
        demo_multiple_conversations()
        demo_platform_specific()
        demo_conversation_scenarios()

        print("\n\n" + "="*60)
        print("✅ All demos complete!")
        print("="*60)
        print("\nNext steps:")
        print("  1. Setup: pip install -r social_requirements.txt")
        print("  2. Login: python instra-automate/social_media.py instagram @user")
        print("  3. Auto-reply: python instra-automate/social_media.py instagram @user --auto-reply")
        print("\nFor production:")
        print("  - Configure personality in code or via CLI")
        print("  - Set LLM API keys (NVIDIA_API_KEY, GEMINI_API_KEY)")
        print("  - Enable persistent memory via SessionMemory")
        print("\nSee SOCIAL_MEDIA_README.md for full documentation")
        print("="*60 + "\n")


if __name__ == "__main__":
    main()


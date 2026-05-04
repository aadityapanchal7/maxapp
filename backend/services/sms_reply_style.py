"""
Shared copy rules for SMS / iMessage — keeps outbound text human and avoids
meta lines ("I'm texting you…", "this is a reminder…").
"""

# Appended to Max chat system prompt when the reply is delivered over SMS/iMessage.
SMS_CONVERSATION_APPENDIX = """

## TEXT MESSAGE OUTPUT (CRITICAL)
This answer is sent as a normal phone text. The user already sees it in their Messages thread.
- Do NOT narrate the medium. Avoid: "texting you", "sending you a message", "quick text", "wanted to reach out", "this is a reminder", "just a heads up", "pinging you", "I'm messaging you about".
- Do NOT explain that they can reply here — they know. If a photo would help (e.g. progress log), mention it in one casual clause (e.g. "pic back if you want it saved") — not "reply to this thread" or "via MMS".
- No sign-off line. Jump straight into what you'd actually say.
- Never use * or ** in the message body.
"""

# Appended to prompts for AI-generated proactive SMS (check-ins, bedtime nudges).
SMS_OUTBOUND_LLM_APPENDIX = """
## How this text should read
This becomes the user's real message in iMessage/SMS. One peer texting another.
- No meta: don't announce that you're texting, reminding, reaching out, or sending a notification.
- Don't explain how texting works.
- If you invite a photo, one short casual clause only — not a product tutorial.
- Never use * or ** (no markdown bold or fake bullets).
"""


def sms_chat_appendix(delivery_channel: str) -> str:
    return SMS_CONVERSATION_APPENDIX.strip() if (delivery_channel or "").lower() == "sms" else ""

from __future__ import annotations

import random
import time

import httpx
from secretbox import SecretBox

secrets = SecretBox(auto_load=True)


ROUTING_KEY = secrets.get("PAGERDUTY_ROUTING_KEY")
INCIDENTS_URL = "https://events.pagerduty.com/v2/enqueue"
TITLES = [
    "Why most technology fail",
    "Create a technology a high school bully would be afraid of",
    "The mafia guide to technology",
    "Never changing technology will eventually destroy you",
    "The lazy man's guide to technology",
    "Don't be fooled by technology",
    "3 ways a technology lies to you everyday",
    "How to deal with a very bad technology",
    "Most people will never be great at technology. read why",
    "Lies and damn lies about technology",
    "3 surefire ways technology will drive your business into the ground",
    "Beware the technology scam",
    "How to slap down a technology",
    "technology smackdown!",
    "What ancient greeks knew about technology that you still don't",
    "Why i hate technology",
    "3 ridiculous rules about technology",
    "Congratulations! your technology is about to stop being relevant",
    "How to lose money with technology",
    "Don't fall for this technology scam",
    "What you should have asked your teachers about technology",
    "How technology made me a better salesperson than you",
    "3 reasons technology is a waste of time",
    "Rules not to follow about technology",
    "3 myths about technology",
    "Why everything you know about technology is a lie",
    "Why my technology is better than yours",
    "3 mistakes in technology that make you look dumb",
    "3 ways technology can drive you bankrupt - fast!",
    "3 rules about technology meant to be broken",
    "Why you never see a technology that actually works",
    "It's about the technology, stupid!",
    "3 things a child knows about technology that you don't",
    "How to be happy at technology - not!",
    "Slacker's guide to technology",
    "3 lies technologys tell",
    "In 10 minutes, i'll give you the truth about technology",
    "Here's a quick way to solve the technology problem",
    "Get rid of technology problems once and for all",
    "Super easy ways to handle your extra technology",
    "technology: what a mistake!",
    "Too busy? try these tips to streamline your technology",
    "Warning: what can you do about technology right now",
    "Death, technology and taxes: tips to avoiding technology",
    "Open the gates for technology by using these simple tips",
    "If you don't technology now, you'll hate yourself later",
    "Having a provocative technology works only under these conditions",
    "Never lose your technology again",
    "No more mistakes with technology",
    "technology? it's easy if you do it smart",
    "technology: do you really need it? this will help you decide!",
    "Need more time? read these tips to eliminate technology",
    "Fighting for technology: the samurai way",
    "The death of technology and how to avoid it",
    "technology shortcuts - the easy way",
]
CRITICALALITIES = ["critical", "error", "warning", "info"]


def generate_incidents() -> None:
    for idx, title in enumerate(TITLES, start=1):
        print(f"Generating incident {idx} of {len(TITLES)}")
        payload = {
            "routing_key": ROUTING_KEY,
            "event_action": "trigger",
            "dedup_key": str(random.randint(100_000, 999_999)),
            "payload": {
                "summary": title,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "severity": random.choice(CRITICALALITIES),
                "source": "pdvconsole",
            },
        }
        with httpx.Client() as client:
            client.post(INCIDENTS_URL, json=payload)
        time.sleep(0.5)


if __name__ == "__main__":
    generate_incidents()

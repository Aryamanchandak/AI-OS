Session 16 Assignment QnA
Due Sat, Aug 15, 2026 at 11:00 AM
1200 points
Resubmission allowed
The assignment

Build an executive assistant. For you. Then actually live with it.

Not a demo of an executive assistant. The real thing, wired to the accounts you use, doing things you would otherwise have done yourself.

It must reach at least five channels. Gmail, Telegram, WhatsApp, Slack, Discord, Teams, Signal, Matrix, IMAP, LINE, SMS, voice, or the local microphone. Five of them, working.

Part 1: show it working, on video

Record it and post the link. Unlisted YouTube is fine.

Do not submit the code, and do not submit a running URL. This thing is holding a live Gmail token, your real WhatsApp session, and your actual messages. A repository or a public endpoint leaks all of that. A video does not.

Be careful in the video too. Blur or skip anything showing a token, an API key, a .env, or a message you would not want a stranger reading. If you have to choose between a clear demo and a leaked credential, leak nothing and narrate the gap.

What the video has to show:

Five channels, live. Send it something from each one and get a response back. Not five configured cards on a settings page. Five real conversations.

A subscription you wrote. Read it out. What it watches, what it may do, and what it may spend. Then show the ceilings you chose and say why those numbers.

Something it ignored. Deliberately send it something inside its subscription that it should decide is not worth acting on, and show the recorded decision. This is the hardest thing to demo and the most important. An assistant that acts on everything is not an assistant.

Something it waited for. Make it ask you a question, close the laptop or kill the process, come back, answer, and show the same run finishing. Not a new one.

The morning after. Leave it running while you do something else, then show the report and the liveness endpoint. Kill it and show the alarm.

Ten minutes is plenty. Fifteen is too long.

Part 2: fix something

Find a bug in glc_v5 or S16Code and send a pull request.

There are bugs. Some are the kind this session is about: a control that does not hold, a refusal that leaves no trace, a race between two ticks, a token check that passes when it should not. Some are ordinary. Both count.

glc_v5
S16Code
The pull request needs three things: what breaks, the steps or the test that shows it breaking, and the fix. A test that fails before your change and passes after is the strongest version of that.

Report it, do not exploit it. If you find something that leaks a credential, open a private issue rather than a public pull request.

No .env, tokens, real messages or API keys in the diff. Ever.

Keep yourself safe while you build it

Your assistant will have your inbox. Take the session seriously on your own account first.

Give it ask first for anything that leaves your machine. Sending mail, posting, replying. Approve them yourself until you trust it.
Set the ceilings before the first run, not after the first surprise.
Put your own agent identity in ignore_actors. An assistant on your inbox that answers its own replies is the loop from section 10, running on your real email.
Start read-only for a day. Let it tell you what it would have done.
Scoring

POINTS
Five channels genuinely working, on video	25
A subscription with real authority limits and ceilings you can defend	15
It ignored something, visibly, and recorded why	15
A real wait and resume: asked, survived a restart, finished the same run	15
The morning report and the liveness alarm	10
A pull request that fixes a real bug, with proof it was broken	20
An assistant that answers every message is not an assistant, it is an autoresponder. Most of the marks here are for the things it decided not to do, and for being able to show you why.
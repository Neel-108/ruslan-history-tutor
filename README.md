## RUSLAN — AI History Tutor Bot for Russian Students

RUSLAN is a Telegram bot that helps Russian school students (Grades 6-11) study history within their FGOS curriculum. I built this as part of teaching myself how AI systems actually work in production and not just in a notebook, but as a real deployed system.

I am an electronics engineer. I have no formal CS or ML background. Everything here was figured out independently.


## What it does:

RUSLAN answers history questions from school students but refuses to go outside their grade's curriculum. A Grade 7 student cannot get answers about Grade 10 topics. It will not do homework for the student. It will not give opinions on historical figures. It stays within the FGOS program and that constraint is the whole point.

Generic AI assistants like ChatGPT, Deepseek or Alice AI do not enforce this. Parents and teachers cannot trust them for this use case. That is the gap RUSLAN was trying to fill.


## How it actually works:

Every message goes through 2 stages before any real API call happens.

First, a cheap classifier model (YandexGPT Lite) reads the message and labels it like is this a genuine history question, a casual message, or something inappropriate? If it is not a real teaching request, the bot responds with a template and stops there. No expensive API call made.

If it is a genuine teaching request, the backend assembles a prompt by combining the student's grade, current topic, chronological position in the curriculum and last few conversation turns and sends it to YandexGPT Pro.
The backend decides everything. The LLM only teaches. This separation was the core architectural decision and it took me a while to arrive at it.


## Why the architecture looks the way it does:

I did not start directly here, I started with a single large prompt RUSLAN_v1.6 that I had tested extensively on ChatGPT. It worked well, the prompt handled state, routing, curriculum enforcement, and memory all internally and ChatGPT followed it reliably.

When I moved to YandexGPT API, everything broke. The bot lost track of where the student was, ignored grade boundaries, and produced inconsistent outputs. My first instinct was to blame the model and that was wrong.

The real problem was that I had built the entire system inside the prompt and I was asking the LLM to maintain state across turns, make routing decisions and enforce curriculum rules simultaneously. ChatGPT masked these problems but YandexGPT exposed them.

I spent late January researching how people solve these problems in real systems using context management, state machines, tiered execution. I had not heard these terms before. The 3 documents in the reasoning folder capture that entire process as it was happening.

The redesign moved everything the LLM was failing at into the backend. Database owns state. Backend owns routing. Classifier handles intent. Pro model handles teaching only. That became RUSLAN v3.4.

The design principles behind this architecture are part of a personal framework I call RITA which is my approach to building structured, reliable AI systems on top of LLM APIs.


## Memory system:

There are 3 layers:
1. HOT state is always active -> current grade, topic, and checkpoint injected into every call.
2. WARM summary -> injected only when the student goes back to revise something already covered.
3. COLD log -> everything stored in the database, never injected into prompts, only for debugging.
   
The goal was to give the model exactly what it needs and nothing extra, because every extra token costs money and adds noise.

## Current status:

The core teaching function works. History questions within FGOS boundaries are handled well across all target grades. I tested this with a real Grade 5 student and the teaching responses were accurate and appropriate.

What did not fully work was the non-teaching flows. Casual messages, edge cases, and some classifier failures produced inconsistent behaviour. I could diagnose the problems but could not fully fix them without guidance I did not have access to and thus my development stopped here.
The Yandex API credits ran out and the bot is not running currently.


## What is in this repository:

The original v1.6 prompt that started everything, the full architecture and flowchart, all eleven Python modules, the QA report covering 33 test scenarios and live smoke test outputs from real API calls.


## A note on the code:

I did not write the code myself. The architecture, logic, memory design, and QA were mine. The implementation was done with AI assistance. I have made this explicit because I think it is the honest thing to do and because the distinction between designing a system and writing its code matters. 
However I am studying Python in parallel to understand the code even better and code independently in future projects.


Built with Python, aiogram, YandexGPT API, SQLite and Telegram Bot API.

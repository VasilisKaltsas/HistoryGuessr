# HistoryGuessr
AI-powered historical geography game built with FastAPI and Claude API
## What is this?
A browser-based history & geography game powered by the Claude AI API. 
You're given a mysterious historical scenario and must guess where and when 
it took place on a world map.

## Features
- AI-generated historical scenarios via Claude API
- 3 difficulty levels (Easy / Medium / Hard)
- Progressive hint system
- Greek & English language support
- Wikipedia image integration

## Tech Stack
- Backend: Python, FastAPI
- Frontend: HTML, CSS, JavaScript
- AI: Anthropic Claude API

## How to run
1. Add your Anthropic API key to a `.env` file: `ANTHROPIC_API_KEY=your_key`
2. Install dependencies: `pip install -r requirements.txt`
3. Run `start.bat` — browser opens automatically at `http://localhost:8000`

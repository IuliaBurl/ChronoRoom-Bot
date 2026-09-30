# ChronoRoom Bot Ecosystem

Developed a high-load Telegram bot ecosystem for data processing and automated matchmaking. Refactored a 5-bot microservice architecture into a highly optimized monolithic application.

## 🛠 Tech Stack
- **Language:** Python 3
- **Framework:** Aiogram / Telebot 
- **Database:** SQLite / PostgreSQL
- **Architecture:** Monolith (Refactored from Microservices)

## 🚀 Core Features
- **API Gateway (Forced Sub):** Access restricted until channel subscription is verified via Telegram API.
- **Dynamic Database & Matchmaking:** Handled 80+ variables per user. Custom SQL queries calculate compatibility percentages.
- **FSM & Concurrency Control:** Users can queue up to 8 profiles. Designed secure group invites preventing race conditions.
- **Real-Time Sync & Media:** Built state-based mini-games and custom audio voice-changer filters synchronized across clients.

## 🔒 Security
- Strict rate-limiting algorithms to prevent API throttling and database flooding.
- Hidden invite links generated dynamically only after mutual consent.

*Note: For security reasons, environment variables (.env) and API tokens are not included in this repository.*

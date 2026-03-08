# 🏓 PONG PRO v6.0

> A production-ready, neon-styled Pong game with player vs CPU, animated UI, procedural sound, API integration, and local leaderboard.

![PONG PRO Screenshot](https://pong.deewhy.ovh/assets/preview.png)

## ✨ Features

- 🎮 **Player vs CPU** – Challenge an AI with 3 difficulty levels: Easy, Medium, Hard
- 🔐 **User Profiles** – Login with a username; sync stats to the cloud API
- 🔊 **Procedural Sound** – No external audio files; synthesized in real-time using pure Python stdlib
- 🎨 **Polished UI** – Animated splash screen, countdown, game-over stats, neon visuals, particles & screen shake
- 🏆 **Local Leaderboard** – Tracks wins, losses, and win rate (saved to `leaderboard.json`)
- ⌨️ **Remappable Controls** – Customize keys for Up, Down, and Pause (saved to `save.json`)
- 📊 **Match Statistics** – Duration, longest rally, total hits, average rally, performance badges
- 🌐 **Cross-Platform** – Runs on macOS, Windows, and Linux; paths auto-resolve for dev & bundled modes

## 🚀 Quick Start

### Requirements
- Python 3.8+
- `pygame>=2.5.0`
- `requests>=2.28.0`

### Install Dependencies
```bash
pip install pygame requests
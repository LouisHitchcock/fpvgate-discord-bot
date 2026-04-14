#!/bin/bash
set -e

echo "=== Updating system ==="
sudo apt update && sudo apt upgrade -y

echo "=== Installing Python & Git ==="
sudo apt install -y python3 python3-pip python3-venv git

echo "=== Cloning bot repo ==="
cd /home/ubuntu
git clone https://github.com/LouisHitchcock/fpvgate-discord-bot.git
cd fpvgate-discord-bot

echo "=== Creating virtual environment ==="
python3 -m venv venv
source venv/bin/activate

echo "=== Installing dependencies ==="
pip install -r requirements.txt

echo "=== Creating .env file ==="
read -p "Enter your BOT_TOKEN: " token
echo "BOT_TOKEN=$token" > .env

echo "=== Installing systemd service ==="
sudo cp deploy/fpvgate-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable fpvgate-bot
sudo systemctl start fpvgate-bot

echo "=== Done! Bot is running ==="
sudo systemctl status fpvgate-bot

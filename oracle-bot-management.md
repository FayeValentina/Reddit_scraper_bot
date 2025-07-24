# Oracle Cloud Reddit Bot 管理命令

这个文件包含管理部署在Oracle Cloud上的Reddit Bot的所有常用命令。

## 初始化部署（首次安装）

### 1. 系统基础环境准备

```bash
# 检查系统版本
lsb_release -a

# 更新系统包（选择15跳过服务重启）
sudo apt update && sudo apt upgrade -y
```

### 2. 安装必要的系统依赖

```bash
# 安装基础工具
sudo apt install -y curl wget git vim htop sqlite3 nano

# 安装Python 3.11和pip
sudo apt install -y python3.11 python3.11-venv python3.11-dev python3-pip

# 安装构建工具（某些Python包需要）
sudo apt install -y build-essential
```

### 3. 从GitHub克隆项目

```bash
# 克隆项目到用户主目录
cd ~
git clone https://github.com/FayeValentina/Reddit_scraper_bot.git reddit-bot

# 进入项目目录
cd reddit-bot

# 查看项目文件
ls -la
```

### 4. 创建Python虚拟环境

```bash
# 在项目目录中创建虚拟环境
python3.11 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 升级pip
pip install --upgrade pip
```

### 5. 安装Python依赖

```bash
# 安装项目依赖
pip install -r requirements.txt

# 验证重要依赖是否安装成功
python3 -c "import asyncpraw, tweepy, telegram, google.genai; print('主要依赖安装成功')"

# 验证twitter_text导入（包名为twitter-text-parser，导入名为twitter_text）
python3 -c "import twitter_text; print('twitter_text导入成功')"
```

### 6. 配置环境变量

```bash
# 复制.env.example为.env
cp .env.example .env

# 编辑.env文件，填入实际的API密钥
nano .env

# 验证.env文件配置（检查前几行）
head -n 5 .env
```

### 7. 创建systemd服务

```bash
# 创建systemd服务文件
sudo nano /etc/systemd/system/reddit-bot.service
```

**服务文件内容：**
```ini
[Unit]
Description=Reddit to Twitter Bot
After=network.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/reddit-bot
Environment=PATH=/home/ubuntu/reddit-bot/venv/bin
ExecStart=/home/ubuntu/reddit-bot/venv/bin/python bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### 8. 启用并启动服务

```bash
# 重新加载systemd配置
sudo systemctl daemon-reload

# 启用开机自启动
sudo systemctl enable reddit-bot.service

# 启动服务
sudo systemctl start reddit-bot.service

# 检查服务状态
sudo systemctl status reddit-bot.service

# 查看实时日志确认正常运行
sudo journalctl -u reddit-bot.service -f
```

### 9. 初始化验证

```bash
# 测试健康端点
curl http://localhost:8000/health

# 检查bot进程
ps aux | grep python

# 检查端口监听
ss -tuln | grep :8000
```

### 10. 创建自动更新脚本（推荐）

```bash
# 在项目目录中创建更新脚本
cd ~/reddit-bot
nano update-bot.sh
```

**脚本内容：**
```bash
#!/bin/bash

# Reddit Bot 自动更新脚本
# 使用方法: ./update-bot.sh

echo "🔄 开始更新 Reddit Bot..."

# 停止服务
echo "⏹️  停止 reddit-bot 服务..."
sudo systemctl stop reddit-bot.service

# 进入项目目录
cd ~/reddit-bot

# 拉取最新代码
echo "📥 拉取最新代码..."
git pull origin main

# 激活虚拟环境并更新依赖
echo "📦 更新Python依赖..."
source venv/bin/activate
pip install -r requirements.txt --upgrade

# 启动服务
echo "▶️  启动 reddit-bot 服务..."
sudo systemctl start reddit-bot.service

# 检查服务状态
echo "✅ 检查服务状态..."
sleep 3
sudo systemctl status reddit-bot.service --no-pager

echo "🎉 更新完成！"
echo "💡 使用以下命令查看实时日志:"
echo "   sudo journalctl -u reddit-bot.service -f"
```

```bash
# 给脚本添加执行权限
chmod +x update-bot.sh

# 测试脚本
./update-bot.sh

# 可选：创建全局别名方便使用
mkdir -p ~/bin
ln -sf ~/reddit-bot/update-bot.sh ~/bin/update-bot
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

---

## SSH连接

```bash
# 连接到Oracle Cloud虚拟机
ssh -i ~/.ssh/oracle-ssh-key.pem ubuntu@217.142.254.48

# 简化连接方式（需要先配置 ~/.ssh/config）
ssh reddit-bot
```

## Bot服务管理

```bash
# 查看bot服务状态
sudo systemctl status reddit-bot.service

# 启动bot服务
sudo systemctl start reddit-bot.service

# 停止bot服务
sudo systemctl stop reddit-bot.service

# 重启bot服务
sudo systemctl restart reddit-bot.service

# 重新加载systemd配置（修改service文件后使用）
sudo systemctl daemon-reload

# 启用开机自启动
sudo systemctl enable reddit-bot.service

# 禁用开机自启动
sudo systemctl disable reddit-bot.service
```

## 日志查看

```bash
# 查看实时日志（按Ctrl+C退出）
sudo journalctl -u reddit-bot.service -f

# 查看最近20行日志
sudo journalctl -u reddit-bot.service --lines=20

# 查看今天的日志
sudo journalctl -u reddit-bot.service --since today

# 查看特定时间段的日志
sudo journalctl -u reddit-bot.service --since "2025-07-21 10:00:00"
```

## 代码更新部署

```bash
# 方法1：手动更新
sudo systemctl stop reddit-bot.service
cd ~/reddit-bot
git pull origin main
source venv/bin/activate
pip install -r requirements.txt --upgrade
sudo systemctl start reddit-bot.service

# 方法2：使用更新脚本（推荐）
./update-bot.sh

# 或者如果配置了全局别名
update-bot
```

## 配置文件管理

```bash
# 查看环境配置
cd ~/reddit-bot
cat .env

# 编辑环境配置
nano .env

# 查看systemd服务配置
sudo cat /etc/systemd/system/reddit-bot.service

# 编辑systemd服务配置
sudo nano /etc/systemd/system/reddit-bot.service
```

## 健康检查

```bash
# 在虚拟机内测试健康端点
curl http://localhost:8000/health

# 在浏览器中访问（如果配置了Oracle Cloud安全组）
# http://217.142.254.48:8000/health
```

## Python环境管理

```bash
# 进入项目目录
cd ~/reddit-bot

# 激活虚拟环境
source venv/bin/activate

# 查看已安装的包
pip list

# 安装新的依赖
pip install package_name

# 更新所有依赖
pip install -r requirements.txt --upgrade

# 退出虚拟环境
deactivate
```

## 数据库管理

```bash
# 查看数据库文件
ls -la ~/reddit-bot/reddit_data.db

# 使用SQLite查看数据库
cd ~/reddit-bot
sqlite3 reddit_data.db

# SQLite常用命令（在sqlite3环境中）
.schema                    # 查看表结构
.tables                    # 查看所有表
SELECT * FROM bot_config;  # 查看配置
SELECT * FROM reddit_comments ORDER BY scraped_at DESC LIMIT 10;  # 查看最近评论
.quit                      # 退出SQLite
```

## 系统监控

```bash
# 查看系统资源使用情况
htop

# 查看内存使用
free -h

# 查看磁盘使用
df -h

# 查看网络连接
ss -tuln | grep :8000

# 查看Python进程
ps aux | grep python
```

## 防火墙管理

```bash
# 查看防火墙状态
sudo ufw status

# 开放端口（如果需要）
sudo ufw allow 8000

# 启用防火墙（谨慎使用）
sudo ufw enable
```

## 故障排除

```bash
# 如果bot无法启动，检查以下项目：

# 1. 检查服务状态和错误信息
sudo systemctl status reddit-bot.service

# 2. 查看详细日志
sudo journalctl -u reddit-bot.service --lines=50

# 3. 检查Python依赖
cd ~/reddit-bot
source venv/bin/activate
python3 -c "import asyncpraw, tweepy, telegram, google.genai; print('依赖正常')"

# 4. 检查配置文件
python3 -c "from dotenv import load_dotenv; import os; load_dotenv(); print('Token配置:', 'OK' if os.getenv('TELEGRAM_BOT_TOKEN') else 'Missing')"

# 5. 手动运行bot查看错误
cd ~/reddit-bot
source venv/bin/activate
python3 bot.py

# 6. 检查端口占用
sudo netstat -tlnp | grep :8000
```

## 备份重要文件

```bash
# 备份配置文件
cp ~/.ssh/oracle-ssh-key.pem ~/backup/
cp ~/reddit-bot/.env ~/backup/

# 备份数据库
cp ~/reddit-bot/reddit_data.db ~/backup/reddit_data_$(date +%Y%m%d).db
```

## 有用的别名（可选）

可以在 `~/.bashrc` 中添加这些别名来简化命令：

```bash
# 编辑bashrc
nano ~/.bashrc

# 添加以下别名
alias bot-status='sudo systemctl status reddit-bot.service'
alias bot-start='sudo systemctl start reddit-bot.service'
alias bot-stop='sudo systemctl stop reddit-bot.service'
alias bot-restart='sudo systemctl restart reddit-bot.service'
alias bot-logs='sudo journalctl -u reddit-bot.service -f'
alias bot-dir='cd ~/reddit-bot && source venv/bin/activate'

# 重新加载bashrc
source ~/.bashrc
```

## 重要提醒

- 🔐 **永远不要**将 `.env` 文件提交到GitHub
- 🔄 修改代码后记得 `git push` 到GitHub，然后在服务器上 `git pull`
- 🚨 修改 `.env` 配置后需要重启服务：`sudo systemctl restart reddit-bot.service`
- 📊 定期查看日志确保bot正常运行
- 💾 定期备份数据库文件
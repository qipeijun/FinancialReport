#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Actions 通知脚本

功能：
- 发送邮件通知（HTML格式）
- 支持多种通知渠道（邮件/企业微信/钉钉/Telegram）
- 生成执行摘要
- 可扩展的通知模板系统

用法：
    python scripts/send_notification.py \
        --fetch-status success \
        --analysis-status success \
        --deploy-status success \
        --news-count 45 \
        --trigger schedule \
        --run-url "https://github.com/..."
"""

import argparse
import os
import smtplib
import sys
import yaml
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, Optional

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.logger import get_logger
from scripts.utils.print_utils import print_header, print_success, print_error, print_info

logger = get_logger('notification')


def load_config() -> Dict:
    """加载配置文件
    
    Returns:
        配置字典
    """
    config_path = PROJECT_ROOT / 'config' / 'config.yml'
    if not config_path.exists():
        logger.debug('配置文件不存在，使用环境变量')
        return {}
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
        logger.debug(f'成功加载配置文件: {config_path}')
        return config
    except Exception as e:
        logger.warning(f'加载配置文件失败: {e}')
        return {}


class NotificationSender:
    """通知发送器"""
    
    def __init__(self, config: Dict):
        """初始化
        
        Args:
            config: 配置字典，包含status信息和SMTP配置
        """
        self.config = config
        self.today = datetime.now().strftime('%Y-%m-%d')
        self.timestamp = datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')
    
    def get_status_emoji(self, status: str) -> str:
        """获取状态对应的emoji"""
        status_map = {
            'success': '✅',
            'failure': '❌',
            'skipped': '⏭️',
            'cancelled': '🚫'
        }
        return status_map.get(status, '❓')
    
    def get_status_text(self, status: str) -> str:
        """获取状态文本"""
        status_map = {
            'success': '成功',
            'failure': '失败',
            'skipped': '跳过',
            'cancelled': '取消'
        }
        return status_map.get(status, '未知')
    
    def get_overall_status(self) -> tuple:
        """判断整体状态
        
        Returns:
            (emoji, text) 元组
        """
        fetch = self.config['fetch_status']
        analysis = self.config['analysis_status']
        deploy = self.config['deploy_status']
        
        if fetch == 'success' and analysis == 'success' and deploy == 'success':
            return '✅', '全部成功'
        elif fetch == 'failure' or analysis == 'failure' or deploy == 'failure':
            return '❌', '部分失败'
        else:
            return '⚠️', '部分跳过'
    
    def generate_html_email(self) -> str:
        """生成HTML邮件内容"""
        overall_emoji, overall_text = self.get_overall_status()
        
        fetch_emoji = self.get_status_emoji(self.config['fetch_status'])
        fetch_text = self.get_status_text(self.config['fetch_status'])
        
        analysis_emoji = self.get_status_emoji(self.config['analysis_status'])
        analysis_text = self.get_status_text(self.config['analysis_status'])
        
        deploy_emoji = self.get_status_emoji(self.config['deploy_status'])
        deploy_text = self.get_status_text(self.config['deploy_status'])
        
        news_count = self.config.get('news_count', 0)
        trigger_text = '⏰ 定时任务' if self.config.get('trigger') == 'schedule' else '🖱️ 手动触发'
        
        website_url = self.config.get('website_url', '#')
        run_url = self.config.get('run_url', '#')
        
        html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>财经报告 - {self.today}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
        }}
        .email-container {{
            max-width: 600px;
            margin: 20px auto;
            background: white;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px 30px;
            text-align: center;
        }}
        .header h1 {{
            font-size: 28px;
            margin-bottom: 10px;
            font-weight: 600;
        }}
        .header .date {{
            font-size: 16px;
            opacity: 0.95;
        }}
        .content {{
            padding: 30px;
        }}
        .status-overview {{
            background: #f8f9fa;
            border-left: 4px solid {('#28a745' if overall_emoji == '✅' else '#ffc107' if overall_emoji == '⚠️' else '#dc3545')};
            padding: 15px 20px;
            margin-bottom: 25px;
            border-radius: 4px;
        }}
        .status-overview h2 {{
            font-size: 18px;
            margin-bottom: 8px;
            color: #333;
        }}
        .status-card {{
            background: white;
            border: 1px solid #e9ecef;
            border-radius: 8px;
            margin-bottom: 20px;
            overflow: hidden;
        }}
        .status-card-header {{
            background: #f8f9fa;
            padding: 15px 20px;
            border-bottom: 1px solid #e9ecef;
        }}
        .status-card-header h3 {{
            font-size: 16px;
            color: #495057;
        }}
        .status-item {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 15px 20px;
            border-bottom: 1px solid #f1f3f5;
        }}
        .status-item:last-child {{
            border-bottom: none;
        }}
        .status-label {{
            font-weight: 500;
            color: #495057;
        }}
        .status-value {{
            font-weight: 600;
            font-size: 15px;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
            margin-bottom: 25px;
        }}
        .stat-box {{
            background: #e3f2fd;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }}
        .stat-box .label {{
            font-size: 12px;
            color: #666;
            margin-bottom: 5px;
        }}
        .stat-box .value {{
            font-size: 24px;
            font-weight: bold;
            color: #1976d2;
        }}
        .buttons {{
            display: flex;
            gap: 10px;
            margin-top: 25px;
        }}
        .button {{
            flex: 1;
            display: block;
            padding: 14px 20px;
            text-align: center;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 500;
            font-size: 14px;
            transition: all 0.3s;
        }}
        .button-primary {{
            background: #667eea;
            color: white !important;
        }}
        .button-secondary {{
            background: #6c757d;
            color: white !important;
        }}
        .footer {{
            background: #f8f9fa;
            padding: 20px 30px;
            text-align: center;
            color: #6c757d;
            font-size: 12px;
            border-top: 1px solid #e9ecef;
        }}
        .footer p {{
            margin: 5px 0;
        }}
        
        /* 移动端适配 */
        @media (max-width: 600px) {{
            .email-container {{
                margin: 0;
                border-radius: 0;
            }}
            .stats-grid {{
                grid-template-columns: 1fr;
            }}
            .buttons {{
                flex-direction: column;
            }}
        }}
    </style>
</head>
<body>
    <div class="email-container">
        <div class="header">
            <h1>{overall_emoji} 每日财经报告</h1>
            <div class="date">{self.timestamp}</div>
        </div>
        
        <div class="content">
            <div class="status-overview">
                <h2>整体状态: {overall_text}</h2>
                <p style="margin: 5px 0 0 0; color: #666;">工作流已完成所有任务</p>
            </div>
            
            <div class="status-card">
                <div class="status-card-header">
                    <h3>📋 执行状态详情</h3>
                </div>
                <div class="status-item">
                    <span class="status-label">📰 数据抓取</span>
                    <span class="status-value">{fetch_emoji} {fetch_text}</span>
                </div>
                <div class="status-item">
                    <span class="status-label">🤖 AI分析</span>
                    <span class="status-value">{analysis_emoji} {analysis_text}</span>
                </div>
                <div class="status-item">
                    <span class="status-label">🚀 网站部署</span>
                    <span class="status-value">{deploy_emoji} {deploy_text}</span>
                </div>
            </div>
            
            <div class="stats-grid">
                <div class="stat-box">
                    <div class="label">新增新闻</div>
                    <div class="value">{news_count}</div>
                </div>
                <div class="stat-box">
                    <div class="label">触发方式</div>
                    <div class="value" style="font-size: 16px;">{trigger_text}</div>
                </div>
            </div>
            
            <div class="buttons">
                <a href="{website_url}" class="button button-primary">
                    🌐 查看报告网站
                </a>
                <a href="{run_url}" class="button button-secondary">
                    🔍 查看执行日志
                </a>
            </div>
        </div>
        
        <div class="footer">
            <p><strong>此邮件由 GitHub Actions 自动发送</strong></p>
            <p>仓库: {self.config.get('repository', 'N/A')} | 分支: {self.config.get('branch', 'main')}</p>
            <p style="margin-top: 10px; color: #999;">请勿直接回复此邮件</p>
        </div>
    </div>
</body>
</html>
"""
        return html.strip()
    
    def generate_text_email(self) -> str:
        """生成纯文本邮件内容（作为HTML的备选）"""
        overall_emoji, overall_text = self.get_overall_status()
        
        text = f"""
{'='*50}
  每日财经报告 - {self.today}
{'='*50}

整体状态: {overall_text}
执行时间: {self.timestamp}

【执行状态】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  📰 数据抓取: {self.get_status_text(self.config['fetch_status'])}
  🤖 AI分析:   {self.get_status_text(self.config['analysis_status'])}
  🚀 网站部署: {self.get_status_text(self.config['deploy_status'])}

【数据统计】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  新增新闻: {self.config.get('news_count', 0)} 条
  触发方式: {self.config.get('trigger', 'manual')}

【链接】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  报告网站: {self.config.get('website_url', 'N/A')}
  执行日志: {self.config.get('run_url', 'N/A')}

{'='*50}
此邮件由 GitHub Actions 自动发送
仓库: {self.config.get('repository', 'N/A')}
{'='*50}
"""
        return text.strip()
    
    def send_email(self) -> bool:
        """发送邮件通知
        
        Returns:
            是否发送成功
        """
        try:
            # 加载配置文件
            config = load_config()
            email_config = config.get('notify', {}).get('email', {})
            
            # 优先使用配置文件，其次使用环境变量
            smtp_server = email_config.get('smtp_server') or os.getenv('SMTP_SERVER', 'smtp.gmail.com')
            smtp_port = email_config.get('smtp_port') or int(os.getenv('SMTP_PORT', '587'))
            username = email_config.get('username') or os.getenv('EMAIL_USERNAME')
            password = email_config.get('password') or os.getenv('EMAIL_PASSWORD')
            from_email = email_config.get('from') or os.getenv('EMAIL_FROM', username)
            to_email_raw = email_config.get('to') or os.getenv('EMAIL_TO')
            
            # 处理多个收件人（支持列表或逗号分隔的字符串）
            if isinstance(to_email_raw, list):
                # 配置文件中的YAML列表
                to_emails = [email.strip() for email in to_email_raw if email.strip()]
            elif isinstance(to_email_raw, str):
                # 逗号分隔的字符串
                to_emails = [email.strip() for email in to_email_raw.split(',') if email.strip()]
            else:
                to_emails = []
            
            # 验证必需参数
            if not all([username, password, to_emails]):
                print_error('❌ 邮件配置不完整，跳过发送')
                print_info('需要配置文件 config/config.yml 中的 notify.email 或环境变量:')
                print_info('  - EMAIL_USERNAME (发件邮箱)')
                print_info('  - EMAIL_PASSWORD (授权密码)')
                print_info('  - EMAIL_TO (收件邮箱，支持多个用逗号分隔)')
                return False
            
            # 收件人邮箱字符串（用于显示）
            to_email = ', '.join(to_emails)
            
            # 显示配置来源
            config_source = '配置文件' if email_config else '环境变量'
            print_info(f'📝 使用{config_source}中的邮件配置')
            
            # 生成邮件内容
            overall_emoji, _ = self.get_overall_status()
            subject = f"{overall_emoji} 财经报告 - {self.today}"
            html_body = self.generate_html_email()
            text_body = self.generate_text_email()
            
            # 创建邮件
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            # QQ邮箱要求From必须和登录用户名一致
            msg['From'] = username if '@' in username else from_email
            msg['To'] = to_email
            msg['Date'] = datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0800')
            
            # 添加纯文本和HTML版本
            msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))
            
            # 发送邮件
            print_info(f'连接SMTP服务器: {smtp_server}:{smtp_port}')
            
            server = None
            try:
                # QQ邮箱使用SSL连接（端口465）或TLS连接（端口587）
                if smtp_port == 465:
                    # 使用SSL连接
                    print_info('使用SSL加密连接...')
                    server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=30)
                else:
                    # 使用TLS连接（587端口）
                    print_info('使用TLS加密连接...')
                    server = smtplib.SMTP(smtp_server, smtp_port, timeout=30)
                    server.starttls()
                
                print_info('登录邮箱服务器...')
                server.login(username, password)
                
                print_info(f'发送邮件给 {len(to_emails)} 个收件人...')
                server.send_message(msg)
                
                print_success(f'✅ 邮件发送成功: {to_email}')
                logger.info(f'Email sent to {len(to_emails)} recipient(s): {to_email}')
                return True
                
            finally:
                if server:
                    try:
                        server.quit()
                    except:
                        pass
            
        except Exception as e:
            print_error(f'❌ 邮件发送失败: {e}')
            logger.error(f'Failed to send email: {e}', exc_info=True)
            return False
    
    def send_wechat(self) -> bool:
        """发送企业微信通知（TODO）"""
        webhook_url = os.getenv('WECHAT_WEBHOOK')
        if not webhook_url:
            logger.debug('未配置企业微信webhook，跳过')
            return False
        
        # TODO: 实现企业微信通知
        print_info('企业微信通知功能待实现')
        return False
    
    def send_dingtalk(self) -> bool:
        """发送钉钉通知（TODO）"""
        webhook_url = os.getenv('DINGTALK_WEBHOOK')
        if not webhook_url:
            logger.debug('未配置钉钉webhook，跳过')
            return False
        
        # TODO: 实现钉钉通知
        print_info('钉钉通知功能待实现')
        return False
    
    def send_telegram(self) -> bool:
        """发送Telegram通知（TODO）"""
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        chat_id = os.getenv('TELEGRAM_CHAT_ID')
        
        if not all([bot_token, chat_id]):
            logger.debug('未配置Telegram，跳过')
            return False
        
        # TODO: 实现Telegram通知
        print_info('Telegram通知功能待实现')
        return False


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='发送GitHub Actions执行通知')
    
    # 执行状态
    parser.add_argument('--fetch-status', required=True, 
                        choices=['success', 'failure', 'skipped', 'cancelled'],
                        help='数据抓取状态')
    parser.add_argument('--analysis-status', required=True,
                        choices=['success', 'failure', 'skipped', 'cancelled'],
                        help='AI分析状态')
    parser.add_argument('--deploy-status', required=True,
                        choices=['success', 'failure', 'skipped', 'cancelled'],
                        help='网站部署状态')
    
    # 统计信息
    parser.add_argument('--news-count', type=int, default=0,
                        help='新增新闻数量')
    parser.add_argument('--trigger', default='manual',
                        help='触发方式（schedule/manual/workflow_dispatch）')
    
    # 链接
    parser.add_argument('--website-url', default='',
                        help='报告网站URL')
    parser.add_argument('--run-url', default='',
                        help='GitHub Actions运行URL')
    parser.add_argument('--repository', default='',
                        help='仓库名称')
    parser.add_argument('--branch', default='main',
                        help='分支名称')
    
    # 通知渠道
    parser.add_argument('--channels', nargs='+', 
                        default=['email'],
                        choices=['email', 'wechat', 'dingtalk', 'telegram'],
                        help='通知渠道（可多选）')
    
    return parser.parse_args()


def main():
    """主函数"""
    print_header('📬 发送执行通知')
    
    args = parse_args()
    
    # 准备配置
    config = {
        'fetch_status': args.fetch_status,
        'analysis_status': args.analysis_status,
        'deploy_status': args.deploy_status,
        'news_count': args.news_count,
        'trigger': args.trigger,
        'website_url': args.website_url,
        'run_url': args.run_url,
        'repository': args.repository,
        'branch': args.branch,
    }
    
    # 创建通知发送器
    sender = NotificationSender(config)
    
    # 发送通知
    success_count = 0
    for channel in args.channels:
        print_info(f'\n📤 发送 {channel} 通知...')
        
        if channel == 'email':
            if sender.send_email():
                success_count += 1
        elif channel == 'wechat':
            if sender.send_wechat():
                success_count += 1
        elif channel == 'dingtalk':
            if sender.send_dingtalk():
                success_count += 1
        elif channel == 'telegram':
            if sender.send_telegram():
                success_count += 1
    
    # 汇总结果
    print()
    if success_count == len(args.channels):
        print_success(f'✅ 所有通知发送成功 ({success_count}/{len(args.channels)})')
        return 0
    elif success_count > 0:
        print_info(f'⚠️ 部分通知发送成功 ({success_count}/{len(args.channels)})')
        return 0
    else:
        print_error(f'❌ 所有通知发送失败 (0/{len(args.channels)})')
        return 1


if __name__ == '__main__':
    sys.exit(main())


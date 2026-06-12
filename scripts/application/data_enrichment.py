#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据增强工具：为AI报告自动附加实时股票数据（智能版）

核心思路：
1. 使用AI从报告中自动提取投资建议和提到的公司
2. 自动查询股票代码和实时数据
3. 生成数据表格附加到报告

智能化：无需硬编码，完全根据报告内容动态处理
"""

import re
import json
import requests
from typing import Dict, List, Optional
from datetime import datetime


class DataEnricher:
    """智能数据增强器"""
    
    def __init__(self, ai_client=None):
        """
        Args:
            ai_client: AI客户端（Gemini或DeepSeek），用于提取投资建议
        """
        self.ai_client = ai_client
        self.cache = {}
    
    # ==================== AI提取投资建议 ====================
    
    def extract_investment_suggestions_with_ai(self, report_text: str) -> List[Dict]:
        """
        使用AI从报告中提取投资建议和公司名称
        
        Args:
            report_text: AI生成的报告全文
            
        Returns:
            投资建议列表，格式：[{
                'theme': '主题名称',
                'companies': [{'name': '公司名', 'reason': '推荐理由'}]
            }]
        """
        if not self.ai_client:
            print("⚠️ 未提供AI客户端，跳过智能提取")
            return []
        
        extraction_prompt = f"""
请仔细分析以下财经报告，提取出所有投资建议和提到的上市公司。

报告内容：
{report_text}

请以JSON格式输出，只输出JSON，不要任何其他文字：
{{
  "suggestions": [
    {{
      "theme": "投资主题名称",
      "description": "简短描述",
      "companies": [
        {{
          "name": "公司名称（中文或英文）",
          "reason": "推荐理由（一句话）"
        }}
      ]
    }}
  ]
}}

注意：
1. 只提取报告中明确提到的公司
2. 如果报告没有提到具体公司，companies为空数组
3. 确保输出是合法的JSON格式
"""
        
        try:
            # 调用AI进行提取
            result = self._call_ai_extract(extraction_prompt)
            suggestions = json.loads(result).get('suggestions', [])
            return suggestions
        except Exception as e:
            print(f"⚠️ AI提取失败: {e}")
            return []
    
    def _call_ai_extract(self, prompt: str) -> str:
        """
        调用AI进行提取（需要根据实际AI客户端实现）
        
        这里提供一个简化版本，实际使用时需要传入真实的AI客户端
        """
        if hasattr(self.ai_client, 'generate_content'):
            # Gemini客户端
            response = self.ai_client.generate_content(prompt)
            return response.text
        elif hasattr(self.ai_client, 'chat'):
            # OpenAI/DeepSeek客户端
            response = self.ai_client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            return response.choices[0].message.content
        else:
            raise ValueError("不支持的AI客户端类型")
    
    # ==================== 正则表达式提取（备选方案） ====================
    
    def extract_companies_simple(self, report_text: str) -> List[Dict]:
        """
        简化的公司提取（无AI时的fallback）
        
        策略：使用AI的简化版提示词，提取公司名
        注意：这仍然需要AI，只是提示词更简单
        """
        if not self.ai_client:
            print("⚠️ 无AI客户端，无法提取公司信息")
            return []
        
        # 简化的提取提示词
        prompt = f"""
请从以下财经报告中找出所有提到的上市公司名称。

报告内容：
{report_text[:2000]}  # 只取前2000字符，避免太长

要求：
1. 只输出公司名称，一行一个
2. 中文公司保留中文名，英文公司保留英文名
3. 如果提到股票代码，也请列出
4. 不要输出任何其他文字

示例输出：
贵州茅台
NVIDIA
中芯国际
"""
        
        try:
            result = self._call_ai_extract(prompt)
            # 解析结果（每行一个公司）
            companies = [line.strip() for line in result.strip().split('\n') if line.strip()]
            return [{'name': c} for c in companies[:10]]  # 最多10个
        except Exception as e:
            print(f"⚠️ 提取失败: {e}")
            return []
    
    # ==================== 股票代码查询 ====================
    
    def search_stock_code_with_ai(self, company_name: str) -> Optional[Dict]:
        """
        使用AI查询公司的股票代码（智能方案）
        
        Args:
            company_name: 公司名称（中文或英文）
            
        Returns:
            {'code': '股票代码', 'name': '公司全称', 'market': 'CN/US/HK'}
        """
        if not self.ai_client:
            return None
        
        prompt = f"""
请告诉我公司"{company_name}"的股票代码。

要求：
1. 如果是A股，格式为：sh600519 或 sz002594（加上交易所前缀）
2. 如果是美股，格式为：AAPL, NVDA等（纯代码）
3. 如果是港股，格式为：hk00700

只输出JSON格式：
{{"code": "股票代码", "name": "公司全称", "market": "CN/US/HK"}}

如果不知道或不是上市公司，输出：
{{"code": null}}
"""
        
        try:
            result = self._call_ai_extract(prompt)
            # 提取JSON
            json_match = re.search(r'\{[^}]+\}', result)
            if json_match:
                data = json.loads(json_match.group())
                if data.get('code'):
                    return data
        except Exception as e:
            print(f"⚠️ AI查询{company_name}失败: {e}")
        
        return None
    
    # ==================== 股票数据获取 ====================
    
    def get_stock_realtime_data(self, stock_code: str, market: str = "CN") -> Optional[Dict]:
        """获取股票实时数据"""
        cache_key = f"{market}_{stock_code}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            if market == "CN":
                # A股数据（新浪财经）
                url = f"http://hq.sinajs.cn/list={stock_code}"
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Referer': 'http://finance.sina.com.cn'
                }
                response = requests.get(url, headers=headers, timeout=5)
                response.encoding = 'gbk'
                
                # 解析返回数据
                if '"' not in response.text:
                    # print(f"⚠️ {stock_code}: API返回格式异常")
                    return None
                
                parts = response.text.split('"')
                if len(parts) < 2:
                    return None
                    
                data_str = parts[1]
                if not data_str or data_str.strip() == '':
                    # print(f"⚠️ {stock_code}: 无数据（可能股票代码不存在或已退市）")
                    return None
                
                data_list = data_str.split(',')
                if len(data_list) < 32:
                    # print(f"⚠️ {stock_code}: 数据字段不完整 (仅{len(data_list)}个字段)")
                    return None
                
                # 验证价格数据有效性
                try:
                    current_price = float(data_list[3])
                    close_yesterday = float(data_list[2])
                    if current_price <= 0:
                        # print(f"⚠️ {stock_code}: 价格数据无效")
                        return None
                except (ValueError, IndexError):
                    return None
                
                change_pct = round((current_price - close_yesterday) / close_yesterday * 100, 2) if close_yesterday > 0 else 0
                
                result = {
                    'code': stock_code,
                    'name': data_list[0],
                    'price': current_price,
                    'change': f"{'+' if change_pct > 0 else ''}{change_pct}%",
                    'high': float(data_list[4]),
                    'low': float(data_list[5]),
                    'volume_million': round(int(data_list[8]) / 1e6, 2),
                }
                
                self.cache[cache_key] = result
                return result
                
            elif market == "US":
                # 美股数据（需要yfinance）
                try:
                    import yfinance as yf
                    ticker = yf.Ticker(stock_code)
                    info = ticker.info
                    
                    result = {
                        'code': stock_code,
                        'name': info.get('shortName', stock_code),
                        'price': round(info.get('currentPrice', 0), 2),
                        'change': f"{info.get('regularMarketChangePercent', 0):.2f}%",
                        'market_cap_billion': round(info.get('marketCap', 0) / 1e9, 2),
                        'pe': round(info.get('trailingPE', 0), 2) if info.get('trailingPE') else 'N/A',
                    }
                    
                    self.cache[cache_key] = result
                    return result
                except ImportError:
                    print("⚠️ 美股数据需要安装yfinance: pip install yfinance")
                    return None
        
        except Exception as e:
            # 静默失败，避免输出过多错误信息
            # print(f"⚠️ 获取{stock_code}数据失败: {e}")
            return None
    
    # ==================== 报告增强 ====================
    
    def enrich_report(self, report_text: str) -> str:
        """
        为AI报告增强数据（智能版）
        
        Args:
            report_text: AI生成的原始报告
            
        Returns:
            增强后的报告（附带实时数据表格）
        """
        print("📊 开始智能数据增强...")
        
        # 必须使用AI提取（无AI则跳过）
        if not self.ai_client:
            print("⚠️ 数据增强需要AI客户端，请传入ai_client参数")
            print("   提示：enricher = DataEnricher(ai_client=your_ai_client)")
            return report_text
        
        # 使用AI提取投资建议和公司
        suggestions = self.extract_investment_suggestions_with_ai(report_text)
        
        if not suggestions or all(not s.get('companies') for s in suggestions):
            print("ℹ️ 未提取到具体公司，跳过数据增强")
            return report_text
        
        # 查询股票数据
        enriched_data = []
        total_companies = 0
        success_count = 0
        
        for suggestion in suggestions:
            theme = suggestion.get('theme', '投资建议')
            companies = suggestion.get('companies', [])
            
            theme_data = {'theme': theme, 'stocks': []}
            
            for company in companies[:5]:  # 每个主题最多5个公司
                company_name = company.get('name')
                if not company_name:
                    continue
                
                total_companies += 1
                
                # 使用AI查询股票代码
                stock_info = self.search_stock_code_with_ai(company_name)
                if not stock_info:
                    continue
                
                # 获取实时数据
                realtime_data = self.get_stock_realtime_data(
                    stock_info['code'],
                    stock_info['market']
                )
                
                if realtime_data:
                    realtime_data['reason'] = company.get('reason', '')
                    theme_data['stocks'].append(realtime_data)
                    success_count += 1
            
            if theme_data['stocks']:
                enriched_data.append(theme_data)
        
        # 显示统计信息
        if total_companies > 0:
            success_rate = round(success_count * 100 / total_companies) if total_companies > 0 else 0
            print(f"📈 数据统计: 尝试 {total_companies} 个公司，成功获取 {success_count} 个 (成功率 {success_rate}%)")
            if success_count < total_companies:
                failed_count = total_companies - success_count
                print(f"   ℹ️  {failed_count} 个失败（可能原因：股票代码不存在、已退市、或API限流）")
        
        if not enriched_data:
            print("⚠️ 未获取到有效股票数据，跳过数据增强")
            return report_text
        
        # 生成数据附录
        enriched_report = report_text
        enriched_report += "\n\n---\n\n"
        enriched_report += "## 📊 实时数据参考\n\n"
        enriched_report += "> 以下为报告中提到的相关公司的实时股票数据，供参考。\n\n"
        
        for theme_data in enriched_data:
            enriched_report += f"\n### {theme_data['theme']}\n\n"
            
            # 生成表格
            stocks = theme_data['stocks']
            if stocks[0].get('market_cap_billion'):
                # 美股表格
                enriched_report += "| 代码 | 名称 | 当前价 | 涨跌 | 市值(亿$) | PE |\n"
                enriched_report += "|------|------|--------|------|-----------|----|\n"
                for stock in stocks:
                    enriched_report += f"| {stock['code']} | {stock['name']} | ${stock['price']} | {stock['change']} | {stock['market_cap_billion']} | {stock['pe']} |\n"
            else:
                # A股表格
                enriched_report += "| 代码 | 名称 | 当前价 | 涨跌 | 最高 | 最低 |\n"
                enriched_report += "|------|------|--------|------|------|------|\n"
                for stock in stocks:
                    enriched_report += f"| {stock['code']} | {stock['name']} | ¥{stock['price']} | {stock['change']} | ¥{stock['high']} | ¥{stock['low']} |\n"
            
            enriched_report += "\n"
        
        enriched_report += f"\n> 💡 数据更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        enriched_report += "\n**免责声明**：以上数据仅供参考，不构成投资建议。\n"
        
        print(f"✅ 数据增强完成，添加了{len(enriched_data)}个主题的实时数据")
        return enriched_report


# ==================== 使用示例 ====================

def example_without_ai():
    """不使用AI客户端的示例（使用正则提取）"""
    enricher = DataEnricher()  # 不传入AI客户端
    
    sample_report = """
# 财经分析报告

## 投资主题

### AI芯片
英伟达(NVIDIA)继续领跑AI芯片市场，国内的中芯国际也在加速追赶。

### 新能源
比亚迪和特斯拉(Tesla)在新能源汽车领域竞争激烈，宁德时代提供动力电池支持。
"""
    
    enriched = enricher.enrich_report(sample_report)
    print(enriched)


# ==================== 独立工具函数（供Function Calling使用） ====================

def query_stock_by_company_name(company_name: str, ai_client=None) -> Dict:
    """
    根据公司名称查询股票实时数据（供Function Calling使用）
    
    Args:
        company_name: 公司名称（中文或英文）
        ai_client: AI客户端（用于智能查询股票代码）
        
    Returns:
        股票数据字典，格式：
        {
            "success": True/False,
            "company_name": "公司名称",
            "stock_code": "股票代码",
            "stock_name": "股票名称",
            "market": "CN/US/HK",
            "price": 当前价格,
            "change": "涨跌幅",
            "data": {...}  # 完整数据
        }
    """
    enricher = DataEnricher(ai_client=ai_client)
    
    # 使用AI查询股票代码
    stock_info = enricher.search_stock_code_with_ai(company_name)
    
    if not stock_info or not stock_info.get('code'):
        return {
            "success": False,
            "company_name": company_name,
            "error": "无法找到该公司的股票代码，可能不是上市公司或名称有误"
        }
    
    stock_code = stock_info['code']
    market = stock_info.get('market', 'CN')
    
    # 获取实时数据
    stock_data = enricher.get_stock_realtime_data(stock_code, market)
    
    if not stock_data:
        return {
            "success": False,
            "company_name": company_name,
            "stock_code": stock_code,
            "market": market,
            "error": "无法获取股票实时数据，可能是API限流或股票已退市"
        }
    
    # 返回成功结果
    return {
        "success": True,
        "company_name": company_name,
        "stock_code": stock_code,
        "stock_name": stock_data.get('name', ''),
        "market": market,
        "price": stock_data.get('price', 0),
        "change": stock_data.get('change', '0%'),
        "high": stock_data.get('high'),
        "low": stock_data.get('low'),
        "volume": stock_data.get('volume'),
        "market_cap": stock_data.get('market_cap'),
        "pe_ratio": stock_data.get('pe_ratio'),
        "data": stock_data,
        "summary": f"{stock_data.get('name', company_name)} ({stock_code}): 当前价格 {stock_data.get('price', 0)}，{stock_data.get('change', '0%')}"
    }


if __name__ == '__main__':
    example_without_ai()

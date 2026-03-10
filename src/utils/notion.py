import os
import requests

NOTION_TOKEN = os.getenv('NOTION_TOKEN')
NOTION_DB = os.getenv('NOTION_DB')


def create_task_if_env(title: str, url: str, sku: str, order_id):
    if not (NOTION_TOKEN and NOTION_DB):
        return
    headers = {
        'Authorization': f'Bearer {NOTION_TOKEN}',
        'Notion-Version': '2022-06-28',
        'Content-Type': 'application/json'
    }
    payload = {
        'parent': {'database_id': NOTION_DB},
        'properties': {
            'Name': {'title': [{'text': {'content': title}}]},
            'Order ID': {'rich_text': [{'text': {'content': str(order_id)}}]},
            'SKU': {'rich_text': [{'text': {'content': sku}}]},
            'Source URL': {'url': url}
        }
    }
    r = requests.post('https://api.notion.com/v1/pages', headers=headers, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()

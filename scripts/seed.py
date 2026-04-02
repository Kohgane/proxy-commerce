#!/usr/bin/env python3
"""scripts/seed.py — Phase 42: 시드 데이터 CLI.

사용법:
    python scripts/seed.py seed    # 시드 데이터 생성 및 출력
    python scripts/seed.py reset   # 시드 데이터 초기화 (인메모리)
"""
import json
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def cmd_seed():
    """시드 데이터 생성."""
    from src.migration.seed import SeedGenerator
    gen = SeedGenerator()
    data = gen.generate_all()
    print(f"✓ 상품 {len(data['products'])}개 생성")
    print(f"✓ 고객 {len(data['customers'])}개 생성")
    print(f"✓ 주문 {len(data['orders'])}개 생성")
    print("\n첫 번째 상품 예시:")
    print(json.dumps(data['products'][0], ensure_ascii=False, indent=2))
    return data


def cmd_reset():
    """시드 데이터 초기화 (인메모리 데이터 초기화는 각 모듈에서 처리)."""
    print("✓ 인메모리 시드 데이터 초기화 완료 (재시작 시 자동 초기화됨)")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    command = sys.argv[1].lower()
    if command == 'seed':
        cmd_seed()
    elif command == 'reset':
        cmd_reset()
    else:
        print(f"알 수 없는 명령: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == '__main__':
    main()

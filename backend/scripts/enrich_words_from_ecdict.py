"""用 ECDICT 富化四级词库：补考试标签、真实语料词频、缺失音标

数据来源：
    ECDICT（https://github.com/skywind3000/ECDICT，MIT）
    ecdict.csv 的列：word, phonetic, definition, translation, pos,
                    collins, oxford, tag, bnc, frq, exchange, detail, audio

产出（写回 app/data/cet4_words.json，写前自动备份）：
    tags     考试标签，空格分隔并规范化，如 "cet4 cet6 ky toefl"
    frq      COCA 语料词频序号（越小越高频）
    bnc      BNC 语料词频序号
    collins  柯林斯星级 1-5
    oxford   是否牛津核心 3000（1/0）

用法：
    python scripts/enrich_words_from_ecdict.py --ecdict D:\\path\\to\\ecdict.csv
    python scripts/enrich_words_from_ecdict.py --ecdict ... --dry-run   # 只看统计不改文件

注意：**只补缺失音标，不覆盖已有音标**；已有 definition/example 等字段一律不动。
"""

import argparse
import csv
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

csv.field_size_limit(10 ** 9)

# ECDICT 的 tag 取值 → 规范化顺序（顺便过滤 ECDICT 里一些非考纲标签）
KNOWN_TAGS = ["zk", "gk", "cet4", "cet6", "ky", "toefl", "ielts", "gre"]


def parse_int(value: str | None) -> int | None:
    """ECDICT 里空串表示缺失，不能当成 0"""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def normalize_tags(raw: str | None) -> str:
    """把 "gk cet4  cet6" 规范化成固定顺序的 "gk cet4 cet6"，未知标签丢弃"""
    if not raw:
        return ""
    present = {t.strip().lower() for t in raw.split() if t.strip()}
    return " ".join(t for t in KNOWN_TAGS if t in present)


def load_ecdict(path: Path, wanted: set[str]) -> dict[str, dict]:
    """流式扫一遍 ECDICT，只留需要的词（63MB 文件不适合整体载入）"""
    found: dict[str, dict] = {}
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
        for row in csv.DictReader(f):
            key = (row.get("word") or "").strip().lower()
            if key in wanted and key not in found:
                found[key] = row
                if len(found) == len(wanted):
                    break
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description="用 ECDICT 富化四级词库")
    parser.add_argument("--ecdict", required=True, type=Path, help="ecdict.csv 路径")
    parser.add_argument(
        "--words",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "app" / "data" / "cet4_words.json",
        help="词库 JSON 路径（默认 app/data/cet4_words.json）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写文件")
    args = parser.parse_args()

    if not args.ecdict.exists():
        print(f"找不到 ECDICT 文件：{args.ecdict}", file=sys.stderr)
        return 2
    if not args.words.exists():
        print(f"找不到词库文件：{args.words}", file=sys.stderr)
        return 2

    words = json.loads(args.words.read_text(encoding="utf-8"))
    wanted = {w["word"].strip().lower() for w in words}
    print(f"词库 {len(words)} 词，开始扫描 ECDICT …")

    ec = load_ecdict(args.ecdict, wanted)
    print(f"ECDICT 命中 {len(ec)}/{len(wanted)} 词（{len(ec) * 100.0 / len(wanted):.1f}%）")

    tagged = frq_filled = phonetic_filled = 0
    for item in words:
        row = ec.get(item["word"].strip().lower())
        if not row:
            # 未命中：显式留空，避免下游把缺失当 0
            item.setdefault("tags", "")
            continue

        tags = normalize_tags(row.get("tag"))
        item["tags"] = tags
        item["frq"] = parse_int(row.get("frq"))
        item["bnc"] = parse_int(row.get("bnc"))
        item["collins"] = parse_int(row.get("collins"))
        oxford = parse_int(row.get("oxford"))
        item["oxford"] = 1 if oxford else 0

        if tags:
            tagged += 1
        if item.get("frq"):
            frq_filled += 1
        # 只补缺失音标：已有音标（带斜杠、来源更细）优先保留
        if not (item.get("phonetic_us") or item.get("phonetic_uk")):
            ph = (row.get("phonetic") or "").strip()
            if ph:
                item["phonetic_us"] = f"/{ph.strip('/')}/"
                phonetic_filled += 1

    print(f"  有考试标签: {tagged}")
    print(f"  有 COCA 词频: {frq_filled}")
    print(f"  补上缺失音标: {phonetic_filled}")

    if args.dry_run:
        print("dry-run：未写文件")
        return 0

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = args.words.with_name(f"{args.words.name}.bak-{stamp}")
    shutil.copy(args.words, backup)
    args.words.write_text(json.dumps(words, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已写回 {args.words}")
    print(f"原文件备份：{backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
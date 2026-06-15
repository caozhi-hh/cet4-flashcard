"""
从 KyleBing/english-vocabulary 下载 CET4 词库并转换为项目格式
数据源: https://github.com/KyleBing/english-vocabulary
json-sentence 格式: word, us, uk, translations[{translation, type}], sentences[{sentence, translation}]
"""
import json
import subprocess
import sys
import os

sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = "https://cdn.jsdelivr.net/gh/KyleBing/english-vocabulary@master/json_original/json-sentence/"
CET4_FILES = ["CET4_1.json", "CET4_2.json", "CET4_3.json"]
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "..", "app", "data", "cet4_words.json")
TMP_DIR = os.path.join(SCRIPT_DIR, "..", "tmp")


def download_json(filename):
    """用 curl 下载 JSON 到本地"""
    url = BASE_URL + filename
    local_path = os.path.join(TMP_DIR, filename)

    # 如果已下载就直接用
    if os.path.exists(local_path) and os.path.getsize(local_path) > 1000:
        print(f"  使用缓存 {filename}")
        with open(local_path, "r", encoding="utf-8") as f:
            return json.load(f)

    print(f"  下载 {filename}...")
    os.makedirs(TMP_DIR, exist_ok=True)
    result = subprocess.run(
        ["curl", "-sL", "--connect-timeout", "30", "--max-time", "180",
         "--retry", "3", "-o", local_path, url],
        capture_output=True, timeout=300
    )
    if result.returncode != 0:
        raise Exception(f"curl error {result.returncode}")

    with open(local_path, "r", encoding="utf-8") as f:
        return json.load(f)


def convert_entry(entry, rank):
    """将 json-sentence 格式转换为项目格式"""
    word = entry.get("word", "").strip()
    if not word:
        return None

    # 音标
    us = entry.get("us", "")
    uk = entry.get("uk", "")
    phonetic_us = f"/{us}/" if us else None
    phonetic_uk = f"/{uk}/" if uk else None

    # 释义和词性
    translations = entry.get("translations", [])
    if translations:
        defs = []
        pos_list = []
        for t in translations:
            pos = t.get("type", "")
            cn = t.get("translation", "")
            if pos and cn:
                defs.append(f"{pos}. {cn}")
                pos_list.append(pos)
            elif cn:
                defs.append(cn)
        definition = "；".join(defs) if defs else ""
        pos = "；".join(pos_list) if pos_list else None
    else:
        definition = ""
        pos = None

    if not definition:
        return None

    # 例句
    sentences = entry.get("sentences", [])
    example = sentences[0].get("sentence", "") if sentences else None
    example_cn = sentences[0].get("translation", "") if sentences else None

    return {
        "word": word,
        "phonetic_us": phonetic_us,
        "phonetic_uk": phonetic_uk,
        "definition": definition,
        "pos": pos,
        "example": example,
        "example_cn": example_cn,
        "frequency": rank,
    }


def main():
    print("=== CET-4 词库转换工具 ===\n")

    seen = set()
    all_words = []
    rank = 0

    for filename in CET4_FILES:
        try:
            data = download_json(filename)
            count = len(data)
            print(f"  解析到 {count} 个词条")
        except Exception as e:
            print(f"  ⚠️ {filename} 失败: {e}")
            continue

        for entry in data:
            word = entry.get("word", "").strip()
            if word and word not in seen:
                seen.add(word)
                rank += 1
                converted = convert_entry(entry, rank)
                if converted:
                    all_words.append(converted)

    total = len(all_words)
    if total == 0:
        print("\n❌ 没有获取到任何词汇")
        sys.exit(1)

    # 按 frequency 排序（已是顺序）
    all_words.sort(key=lambda w: w["frequency"])

    # 输出
    output_dir = os.path.dirname(OUTPUT_PATH)
    os.makedirs(output_dir, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_words, f, ensure_ascii=False, indent=2)

    # 统计
    has_phonetic = sum(1 for w in all_words if w["phonetic_us"])
    has_example = sum(1 for w in all_words if w["example"])
    has_pos = sum(1 for w in all_words if w["pos"])

    print(f"\n✅ 转换完成!")
    print(f"  总词数: {total}")
    print(f"  有音标: {has_phonetic} ({has_phonetic * 100 // total}%)")
    print(f"  有词性: {has_pos} ({has_pos * 100 // total}%)")
    print(f"  有例句: {has_example} ({has_example * 100 // total}%)")

    print(f"\n📋 前3个词:")
    for w in all_words[:3]:
        print(f"  {w['frequency']}. {w['word']} {w['phonetic_us'] or ''}")
        print(f"     {w['definition']}")
        if w['example']:
            print(f"     例: {w['example']}")

    print(f"\n  输出: {os.path.abspath(OUTPUT_PATH)}")


if __name__ == "__main__":
    main()
